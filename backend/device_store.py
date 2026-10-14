import json
from pathlib import Path


STORAGE_PATH = Path(__file__).resolve().parent.parent / "storage.json"


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