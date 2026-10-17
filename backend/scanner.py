"""
หมายเหตุเรื่อง state:
  REACHABLE = เพิ่งยืนยันว่าอยู่จริง | STALE/DELAY/PROBE = เคยเจอ แต่ยังไม่ยืนยันซ้ำ
  LOCAL = เครื่อง Pi เอง | UNKNOWN = มาจาก `arp -an` (ไม่มีข้อมูล state)
  ถ้ารันด้วยสิทธิ์ root จะ flush neighbour table ก่อนสแกน ทำให้ผลสดและไม่มี "ผี"
"""

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_HOSTS = 1024            # กัน subnet ใหญ่เกิน (เช่น /16) ทำให้ Pi ค้าง
PROBE_PORT = 9              # UDP discard port ใช้เป็นแค่ตัวกระตุ้น ARP
PROBE_WORKERS = 64          # จำนวน thread ที่ส่ง probe พร้อมกัน
ARP_SETTLE_SECONDS = 1.5    # รอให้ ARP reply กลับมาลง neighbour table
CMD_TIMEOUT = 5             # timeout ของ subprocess (วินาที)
HOSTNAME_TIMEOUT = 3.0      # เวลารวมสูงสุดสำหรับ reverse DNS ทั้งหมด

MAC_RE = re.compile(r"^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$", re.IGNORECASE)

# สถานะใน `ip neigh` ที่ถือว่า "ไม่มี MAC ที่ใช้ได้"
_BAD_STATES = {"FAILED", "INCOMPLETE"}

# กัน scan ซ้อนกัน (เช่น ผู้ใช้กดปุ่ม Scan รัว ๆ หรือหลายคนเปิดหน้าเว็บ)
_scan_lock = threading.Lock()


class ScannerError(Exception):
    """ข้อผิดพลาดของ scanner (ให้ Flask จับแล้วตอบ JSON error ได้)"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd):
    """
    รันคำสั่งแบบปลอดภัย: ส่งเป็น list (ไม่ใช้ shell=True) จึงไม่เสี่ยง
    command injection. คืน stdout หรือ "" ถ้าคำสั่งไม่มี/ล้มเหลว
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
            check=False,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _normalize_mac(mac):
    """
    แปลง MAC ให้เป็นรูป AA:BB:CC:DD:EE:FF
    (macOS ตัด 0 นำหน้าทิ้ง เช่น 'a:b:c:d:e:f' ต้อง pad กลับ)
    คืน None ถ้ารูปแบบผิด
    """
    parts = mac.strip().split(":")
    if len(parts) != 6 or not all(1 <= len(p) <= 2 for p in parts):
        return None
    mac = ":".join(p.zfill(2) for p in parts).upper()
    return mac if MAC_RE.match(mac) else None


def _is_unicast_mac(mac):
    """ตัด broadcast (FF:FF:..) และ multicast (bit ต่ำสุดของ byte แรก = 1) ทิ้ง"""
    return (int(mac[:2], 16) & 1) == 0


# ---------------------------------------------------------------------------
# 1) Find local network
# ---------------------------------------------------------------------------

def _default_interface():
    """หา interface ที่ใช้ออก default route (เช่น eth0 / wlan0 / en0)"""
    if shutil.which("ip"):
        out = _run(["ip", "-4", "route", "show", "default"])
        best = None  # (metric, iface) เลือก metric ต่ำสุด
        for line in out.splitlines():
            dev = re.search(r"\bdev\s+(\S+)", line)
            if not dev:
                continue
            metric = re.search(r"\bmetric\s+(\d+)", line)
            candidate = (int(metric.group(1)) if metric else 0, dev.group(1))
            if best is None or candidate < best:
                best = candidate
        return best[1] if best else None

    # macOS: `route -n get default` -> "interface: en0"
    match = re.search(r"interface:\s*(\S+)", _run(["route", "-n", "get", "default"]))
    return match.group(1) if match else None


def get_default_ipv4_network(interface=None):
    """
    คืนค่า (network, interface, local_ip)
        network   : ipaddress.IPv4Network เช่น 192.168.1.0/24
        interface : ชื่อ interface เช่น 'eth0'
        local_ip  : IP ของเครื่องเราเอง

    ถ้าไม่ระบุ interface จะใช้ interface ของ default route
    """
    if not shutil.which("ip") and not shutil.which("ifconfig"):
        raise ScannerError(
            "ไม่พบคำสั่ง `ip` (ติดตั้งแพ็กเกจ iproute2) หรือ `ifconfig` บนเครื่องนี้"
        )

    interface = interface or _default_interface()
    if not interface:
        raise ScannerError("ไม่พบ default network interface (ไม่ได้ต่อ LAN?)")

    if shutil.which("ip"):
        out = _run(["ip", "-4", "-o", "addr", "show", "dev", interface])
        # "2: eth0    inet 192.168.1.50/24 brd 192.168.1.255 scope global ..."
        match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)", out)
        address = match.group(1) if match else None
    else:
        # macOS: "inet 192.168.1.23 netmask 0xffffff00 broadcast 192.168.1.255"
        out = _run(["ifconfig", interface])
        match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)", out)
        address = None
        if match:
            netmask = str(ipaddress.IPv4Address(int(match.group(2), 16)))
            address = f"{match.group(1)}/{netmask}"

    if not address:
        raise ScannerError(f"interface '{interface}' ไม่มี IPv4 address")

    iface_ip = ipaddress.ip_interface(address)
    return iface_ip.network, interface, str(iface_ip.ip)


# ---------------------------------------------------------------------------
# 2) Trigger ARP
# ---------------------------------------------------------------------------

def _probe(ip):
    """ส่ง UDP 1 byte ไปที่ ip เพื่อให้ kernel ยิง ARP request ออกไป"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"\x00", (ip, PROBE_PORT))
    except OSError:
        pass  # ไม่เป็นไร เราสนแค่ให้เกิด ARP
    finally:
        sock.close()


def _populate_neighbour_table(network):
    """ส่ง probe ไปทุก host ใน subnet พร้อมกันด้วย thread pool"""
    hosts = [str(h) for h in network.hosts()]
    with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as pool:
        list(pool.map(_probe, hosts))
    time.sleep(ARP_SETTLE_SECONDS)


# ---------------------------------------------------------------------------
# 3) Parse output
# ---------------------------------------------------------------------------

def parse_ip_neigh_output(output):
    """
    parse ผลลัพธ์ของ `ip neigh show`
    ตัวอย่างบรรทัด:
        192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
        192.168.1.20 dev eth0  FAILED
    """
    records = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4 or "lladdr" not in parts:
            continue

        ip = parts[0]
        try:
            ipaddress.IPv4Address(ip)       # ข้าม IPv6 / ค่าแปลก ๆ
        except ValueError:
            continue

        mac = _normalize_mac(parts[parts.index("lladdr") + 1])
        state = parts[-1].upper()
        if not mac or not _is_unicast_mac(mac) or state in _BAD_STATES:
            continue

        iface = parts[parts.index("dev") + 1] if "dev" in parts else None
        records.append({
            "ip": ip,
            "mac": mac,
            "interface": iface,
            "state": state,
        })
    return records


# รองรับทั้ง Linux:  "? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0"
#            และ macOS: "? (192.168.1.1) at a:b:c:d:e:f on en0 ifscope [ethernet]"
_ARP_LINE_RE = re.compile(
    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5})"
    r"(?:\s+\[\w+\])?(?:\s+on\s+(\S+))?"
)


def parse_arp_output(output):
    """parse ผลลัพธ์ของ `arp -an` (fallback / macOS) ดู format ด้านบน"""
    records = []
    for line in output.splitlines():
        match = _ARP_LINE_RE.search(line)
        if not match:
            continue
        ip, raw_mac, iface = match.groups()
        mac = _normalize_mac(raw_mac)
        if mac and _is_unicast_mac(mac):
            records.append({
                "ip": ip,
                "mac": mac,
                "interface": iface,
                "state": "UNKNOWN",
            })
    return records


# ---------------------------------------------------------------------------
# 4) Extras: hostname + own MAC
# ---------------------------------------------------------------------------

def _resolve_hostname(ip):
    """reverse DNS แบบพยายามเต็มที่ ถ้าไม่ได้คืน None"""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def _resolve_hostnames(ips, timeout=HOSTNAME_TIMEOUT):
    """
    reverse DNS หลายเครื่องพร้อมกัน โดยมี "เวลารวมสูงสุด" (timeout)
    เพราะ gethostbyaddr ไม่มี timeout ในตัว ถ้า DNS ช้าอาจค้างหลายวินาทีต่อเครื่อง
    เครื่องที่ตอบไม่ทันจะได้ None
    """
    pool = ThreadPoolExecutor(max_workers=16)
    futures = {ip: pool.submit(_resolve_hostname, ip) for ip in ips}
    deadline = time.monotonic() + timeout
    names = {}
    for ip, future in futures.items():
        try:
            names[ip] = future.result(timeout=max(0.0, deadline - time.monotonic()))
        except Exception:
            names[ip] = None
    pool.shutdown(wait=False, cancel_futures=True)  # ไม่รอ thread ที่ยังค้าง
    return names


def _own_mac(interface):
    """หา MAC ของ interface ตัวเอง (neighbour table ไม่มีเครื่องเราเอง)"""
    try:  # Linux
        with open(f"/sys/class/net/{interface}/address") as f:
            return _normalize_mac(f.read())
    except OSError:
        pass
    # macOS: "ether aa:bb:cc:dd:ee:ff"
    match = re.search(r"\bether\s+(\S+)", _run(["ifconfig", interface]))
    return _normalize_mac(match.group(1)) if match else None


def _flush_neighbours(interface):
    """
    ล้าง neighbour table ของ interface ก่อนสแกน เพื่อไม่ให้เครื่องที่ออกจากเครือข่าย
    ไปแล้วยังค้างเป็น STALE ในผลลัพธ์. ต้องใช้ root (ถ้าไม่ใช่ root ข้ามไปเฉย ๆ)
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("ip"):
        _run(["ip", "neigh", "flush", "dev", interface])


def _read_neighbours(interface):
    """อ่าน neighbour table ด้วย `ip neigh` ถ้าไม่มีหรือว่างค่อย fallback ไป `arp -an`"""
    records = []
    if shutil.which("ip"):
        records = parse_ip_neigh_output(_run(["ip", "-4", "neigh", "show", "dev", interface]))
    if not records:
        records = [
            r for r in parse_arp_output(_run(["arp", "-an"]))
            if r["interface"] in (None, interface)
        ]
    return records


# ---------------------------------------------------------------------------
# 5) Public API
# ---------------------------------------------------------------------------

def discover_hosts(subnet=None, interface=None, resolve_hostnames=True):
    """
    สแกน subnet แล้วคืน list ของ host ที่เจอ (เรียงตาม IP)

    subnet    : เช่น "192.168.1.0/24"  (ไม่ระบุ = ใช้ subnet ของ interface)
    interface : เช่น "eth0" / "wlan0"  (ไม่ระบุ = ใช้ default route)

    raise ScannerError ถ้า input ไม่ถูกต้องหรือหา network ไม่เจอ
    """
    local_network, interface, local_ip = get_default_ipv4_network(interface)

    if subnet:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError as exc:
            raise ScannerError(f"subnet ไม่ถูกต้อง: {subnet}") from exc
        if network.version != 4:
            raise ScannerError("รองรับเฉพาะ IPv4")
    else:
        network = local_network

    if network.num_addresses > MAX_HOSTS:
        raise ScannerError(
            f"subnet ใหญ่เกินไป ({network.num_addresses} addresses, "
            f"สูงสุด {MAX_HOSTS}) กรุณาใช้ /22 หรือเล็กกว่า"
        )

    with _scan_lock:  # ให้ scan ทีละงาน
        # 1) (ถ้าเป็น root) ล้างของเก่า  2) กระตุ้น ARP  3) อ่าน neighbour table
        _flush_neighbours(interface)
        _populate_neighbour_table(network)
        records = _read_neighbours(interface)

    # กรองเฉพาะ IP ที่อยู่ใน subnet และตัดซ้ำ
    found = {}
    for rec in records:
        if ipaddress.IPv4Address(rec["ip"]) in network:
            found[rec["ip"]] = rec

    # เพิ่มเครื่องเราเอง (Raspberry Pi)
    if ipaddress.IPv4Address(local_ip) in network and local_ip not in found:
        own_mac = _own_mac(interface)
        if own_mac:
            found[local_ip] = {
                "ip": local_ip,
                "mac": own_mac,
                "interface": interface,
                "state": "LOCAL",
            }

    results = sorted(found.values(), key=lambda r: ipaddress.IPv4Address(r["ip"]))

    names = _resolve_hostnames([r["ip"] for r in results]) if resolve_hostnames else {}
    for rec in results:
        rec["hostname"] = names.get(rec["ip"])

    return results


# ---------------------------------------------------------------------------
# Manual test:  python -m backend.scanner   (รันจากโฟลเดอร์ LanRouser)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    net, iface, ip = get_default_ipv4_network()
    print(f"Interface: {iface} | Local IP: {ip} | Network: {net}")
    print("Scanning...")
    print(json.dumps(discover_hosts(), indent=2, ensure_ascii=False))