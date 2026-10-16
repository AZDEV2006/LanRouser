"""Local IPv4 discovery for Linux/Raspberry Pi OS and macOS.

Install ``arp-scan`` for discovery of hosts that block ICMP. If it is missing
or cannot open raw sockets, use a bounded ping sweep and the ARP table instead.
The fallback only reports ping responders (plus Linux REACHABLE neighbours),
never arbitrary stale cache entries. No command is run through a shell or sudo.
"""

import ipaddress
import json
import platform
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor


MAX_SCAN_ADDRESSES = 1024
MAX_WORKERS = 32
COMMAND_TIMEOUT = 5
MAC_PATTERN = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}(?![\w:])")
IP_PATTERN = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


def _run(command, timeout=COMMAND_TIMEOUT):
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"Required network command not found: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Network command timed out: {command[0]}") from error


def _output(command):
    result = _run(command)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"{command[0]} failed")
    return result.stdout


def _interface_details(interface=None):
    """Return (interface name, IPv4Interface) for the selected LAN adapter."""
    if interface is not None and (
        not isinstance(interface, str)
        or not re.fullmatch(r"[a-zA-Z0-9_.:-]+", interface)
        or interface.startswith("-")
    ):
        raise ValueError("Enter a valid network interface name")

    system = platform.system()
    if system == "Linux":
        if interface is None:
            routes = json.loads(_output(["ip", "-j", "-4", "route", "show", "default"]))
            routes = sorted(routes, key=lambda route: route.get("metric", 0))
            interface = next((route["dev"] for route in routes if route.get("dev")), None)
            if interface is None:
                raise RuntimeError("No default IPv4 route; specify a LAN interface")
        adapters = json.loads(_output(["ip", "-j", "-4", "addr", "show", "dev", interface]))
        addresses = [
            f"{address['local']}/{address['prefixlen']}"
            for adapter in adapters
            for address in adapter.get("addr_info", [])
            if address.get("family") == "inet" and address.get("scope") == "global"
        ]
    elif system == "Darwin":
        if interface is None:
            route = _output(["route", "-n", "get", "default"])
            match = re.search(r"^\s*interface:\s*(\S+)", route, re.MULTILINE)
            if not match:
                raise RuntimeError("No default IPv4 route; specify a LAN interface")
            interface = match.group(1)
        config = _output(["ifconfig", interface])
        addresses = []
        for address, mask in re.findall(r"\binet\s+([\d.]+)\s+netmask\s+(\S+)", config):
            if mask.startswith("0x"):
                mask = str(ipaddress.IPv4Address(int(mask, 16)))
            addresses.append(f"{address}/{mask}")
    else:
        raise RuntimeError("Subnet discovery supports Linux and macOS")

    for address in addresses:
        local = ipaddress.IPv4Interface(address)
        if not local.ip.is_loopback and not local.ip.is_link_local:
            return interface, local
    raise RuntimeError(f"No usable IPv4 address on interface {interface}")


def get_default_ipv4_network(interface=None):
    """Return the selected interface's IPv4Network, using its actual netmask."""
    return _interface_details(interface)[1].network


def parse_arp_output(output):
    """Parse arp-scan, ip-neigh, or arp -an text into sorted IP/MAC records.

    Incomplete, failed, multicast, broadcast and invalid entries are ignored.
    macOS may omit leading zeroes in individual MAC octets.
    """
    hosts = {}
    for line in output.splitlines():
        if re.search(r"\b(?:incomplete|failed)\b", line, re.IGNORECASE):
            continue
        ip_match = IP_PATTERN.search(line)
        mac_match = MAC_PATTERN.search(line)
        if not ip_match or not mac_match:
            continue
        try:
            address = ipaddress.IPv4Address(ip_match.group())
        except ipaddress.AddressValueError:
            continue
        octets = [int(part, 16) for part in mac_match.group().split(":")]
        if address.is_multicast or address.is_unspecified or address.is_loopback:
            continue
        if octets[0] & 1 or not any(octets):
            continue
        mac = ":".join(f"{octet:02X}" for octet in octets)
        hosts[str(address)] = {"ip": str(address), "mac": mac}
    return sorted(hosts.values(), key=lambda host: ipaddress.IPv4Address(host["ip"]))


def _ping(address):
    command = ["ping", "-n", "-c", "1"]
    if platform.system() == "Darwin":
        command += ["-t", "1", "-W", "1000"]
    else:
        command += ["-W", "1"]
    try:
        result = _run(command + [address], timeout=3)
    except RuntimeError as error:
        if isinstance(error.__cause__, subprocess.TimeoutExpired):
            return False
        raise
    if re.search(r"not permitted|permission denied", result.stderr, re.IGNORECASE):
        raise RuntimeError("Network scanning is not permitted for this process")
    return result.returncode == 0


def _ping_scan(network, interface, local_ip):
    targets = [str(address) for address in network.hosts() if address != local_ip]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        online = {address for address, alive in zip(targets, executor.map(_ping, targets)) if alive}

    if platform.system() == "Linux":
        # Read only this adapter's table. A fresh ARP reply can confirm a host
        # even when its firewall does not answer our ICMP echo request.
        output = _output(["ip", "-4", "neigh", "show", "dev", interface])
        reachable = "\n".join(line for line in output.splitlines() if "REACHABLE" in line.split())
        online.update(host["ip"] for host in parse_arp_output(reachable))
    else:
        output = _output(["arp", "-an", "-i", interface])
    macs = {host["ip"]: host["mac"] for host in parse_arp_output(output)}
    return [
        {"ip": address, "mac": macs.get(address, "")}
        for address in sorted(online, key=ipaddress.IPv4Address)
        if ipaddress.IPv4Address(address) in network and address != str(local_ip)
    ]


def discover_hosts(subnet=None, interface=None):
    """Return [{"ip": "192.168.1.2", "mac": "AA:BB:CC:DD:EE:FF"}, ...].

    The default route selects the adapter unless ``interface`` is supplied.
    An explicit IPv4 subnet must fit inside that adapter's network. Scans are
    limited to 1024 addresses; select a smaller subnet for larger LANs.
    Hostname lookup is omitted to avoid blocking on reverse DNS.
    """
    network = None
    if subnet is not None:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4:
            raise ValueError("Subnet discovery requires an IPv4 subnet")
    interface, local = _interface_details(interface)
    network = network if network is not None else local.network
    if not network.subnet_of(local.network):
        raise ValueError(f"Subnet must be within the local network {local.network}")
    if network.num_addresses > MAX_SCAN_ADDRESSES:
        raise ValueError(f"Subnet is too large; select at most {MAX_SCAN_ADDRESSES} addresses")

    executable = shutil.which("arp-scan")
    if executable:
        result = _run([
            executable, f"--interface={interface}", "--plain", "--quiet",
            "--retry=2", str(network),
        ], timeout=15)
        if result.returncode == 0:
            return [
                host for host in parse_arp_output(result.stdout)
                if ipaddress.IPv4Address(host["ip"]) in network
                and host["ip"] != str(local.ip)
                and (network.prefixlen >= 31 or ipaddress.IPv4Address(host["ip"]) not in
                     (network.network_address, network.broadcast_address))
            ]
    return _ping_scan(network, interface, local.ip)
