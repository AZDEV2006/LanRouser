import ipaddress
import platform
import socket
import subprocess
from typing import Union


DEFAULT_BROADCAST_ADDRESS = "255.255.255.255"
DEFAULT_WOL_PORT = 9
DEFAULT_PING_TIMEOUT_SECONDS = 2


def normalize_mac(mac: Union[str, bytes]) -> str:
    """Return a MAC address in AA:BB:CC:DD:EE:FF format."""
    if isinstance(mac, bytes):
        mac_text = mac.decode("ascii", errors="strict")
    elif isinstance(mac, str):
        mac_text = mac
    else:
        raise TypeError("MAC address must be text")

    compact = mac_text.strip().replace(":", "").replace("-", "").replace(".", "")
    if len(compact) != 12 or any(
        character not in "0123456789abcdefABCDEF" for character in compact
    ):
        raise ValueError("Enter a valid MAC address")

    compact = compact.upper()
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def create_magic_packet(mac: Union[str, bytes]) -> bytes:
    normalized_mac = normalize_mac(mac)
    mac_bytes = bytes.fromhex(normalized_mac.replace(":", ""))
    return b"\xff" * 6 + (mac_bytes * 16)


def send_magic_packet(
    mac: Union[str, bytes],
    broadcast_address: str = DEFAULT_BROADCAST_ADDRESS,
    port: int = DEFAULT_WOL_PORT,
) -> int:
    packet = create_magic_packet(mac)

    try:
        parsed_port = int(port)
    except (TypeError, ValueError) as error:
        raise ValueError("Wake-on-LAN port must be a number") from error
    if not 1 <= parsed_port <= 65535:
        raise ValueError("Wake-on-LAN port must be between 1 and 65535")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return udp_socket.sendto(packet, (broadcast_address, parsed_port))


def ping_host(address: str, timeout_seconds: int = DEFAULT_PING_TIMEOUT_SECONDS) -> bool:
    """Return True when an IPv4 host responds to one ICMP ping."""
    parsed_address = ipaddress.ip_address(str(address).strip())
    if parsed_address.version != 4:
        raise ValueError("Enter a valid IPv4 address")

    try:
        parsed_timeout = int(timeout_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("Ping timeout must be a number") from error
    if parsed_timeout < 1:
        raise ValueError("Ping timeout must be at least 1 second")

    command = _ping_command(str(parsed_address), parsed_timeout)
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=parsed_timeout + 3,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _ping_command(address: str, timeout_seconds: int) -> list[str]:
    system_name = platform.system().lower()
    if system_name == "darwin":
        return [
            "ping",
            "-c",
            "1",
            "-t",
            str(timeout_seconds),
            "-W",
            str(timeout_seconds * 1000),
            address,
        ]
    if system_name == "windows":
        return ["ping", "-n", "1", "-w", str(timeout_seconds * 1000), address]
    return ["ping", "-c", "1", "-W", str(timeout_seconds), address]
