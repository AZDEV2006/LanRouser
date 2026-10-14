import ipaddress
import json
import re
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from backend import scanner, wol_engine


TEMPLATE_DIRECTORY = Path(__file__).parent / "frontend" / "templates"
app = Flask(__name__, template_folder=str(TEMPLATE_DIRECTORY))
STORAGE_PATH = Path(__file__).with_name("storage.json")
MAC_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2})$")


def load_devices():
    if not STORAGE_PATH.exists() or not STORAGE_PATH.read_text(encoding="utf-8").strip():
        return []

    devices = json.loads(STORAGE_PATH.read_text(encoding="utf-8"))
    if not isinstance(devices, list):
        raise ValueError("Device storage must contain a JSON list")
    return devices


def save_devices(devices):
    temporary_path = STORAGE_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(devices, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(STORAGE_PATH)


def find_device(device_id):
    return next((device for device in load_devices() if device.get("id") == device_id), None)


def error_response(message, status_code):
    return jsonify({"error": message}), status_code


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "LanRouser"})


@app.get("/api/devices")
def get_devices():
    try:
        return jsonify({"devices": load_devices()})
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return error_response(f"Unable to read device storage: {error}", 500)


@app.post("/api/devices")
def register_device():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Send device details as JSON", 400)

    name = str(data.get("name", "")).strip()
    address = str(data.get("ip", "")).strip()
    mac = str(data.get("mac", "")).strip()
    if not name:
        return error_response("A device name is required", 400)
    try:
        parsed_address = ipaddress.ip_address(address)
        if parsed_address.version != 4:
            raise ValueError
    except ValueError:
        return error_response("Enter a valid IPv4 address", 400)
    if not MAC_PATTERN.fullmatch(mac):
        return error_response("Enter a valid MAC address", 400)

    normalized_mac = re.sub(r"[:-]", "", mac).upper()
    normalized_mac = ":".join(normalized_mac[index:index + 2] for index in range(0, 12, 2))
    try:
        devices = load_devices()
        if any(device.get("mac", "").replace(":", "").replace("-", "").upper() == normalized_mac.replace(":", "") for device in devices):
            return error_response("A device with this MAC address is already registered", 409)

        device = {
            "id": uuid.uuid4().hex,
            "name": name,
            "ip": str(parsed_address),
            "mac": normalized_mac,
        }
        devices.append(device)
        save_devices(devices)
        return jsonify({"device": device}), 201
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return error_response(f"Unable to save device: {error}", 500)


@app.delete("/api/devices/<device_id>")
def delete_device(device_id):
    try:
        devices = load_devices()
        remaining_devices = [device for device in devices if device.get("id") != device_id]
        if len(remaining_devices) == len(devices):
            return error_response("Device not found", 404)
        save_devices(remaining_devices)
        return jsonify({"deleted": True})
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return error_response(f"Unable to update device storage: {error}", 500)


@app.post("/api/scan")
def scan_network():
    discover_hosts = getattr(scanner, "discover_hosts", None)
    if not callable(discover_hosts):
        return error_response("Subnet scanning is not available yet", 503)
    try:
        return jsonify({"hosts": discover_hosts()})
    except Exception as error:
        return error_response(f"Subnet scan failed: {error}", 500)


@app.post("/api/devices/<device_id>/ping")
def ping_device(device_id):
    ping_host = getattr(wol_engine, "ping_host", None)
    if not callable(ping_host):
        return error_response("Reachability checks are not available yet", 503)
    try:
        device = find_device(device_id)
        if device is None:
            return error_response("Device not found", 404)
        return jsonify({"online": bool(ping_host(device["ip"]))})
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return error_response(f"Unable to check device reachability: {error}", 500)


@app.post("/api/devices/<device_id>/wake")
def wake_device(device_id):
    send_magic_packet = getattr(wol_engine, "send_magic_packet", None)
    if not callable(send_magic_packet):
        return error_response("Wake-on-LAN is not available yet", 503)
    try:
        device = find_device(device_id)
        if device is None:
            return error_response("Device not found", 404)
        send_magic_packet(device["mac"])
        return jsonify({"sent": True})
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return error_response(f"Unable to send Wake-on-LAN packet: {error}", 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
