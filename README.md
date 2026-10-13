# LanRouser: Subnet Device Discovery & Remote Wake-on-LAN Controller

LanRouser is an academic Operating Systems laboratory project for building a lightweight Raspberry Pi web appliance. The system is intended to discover active hosts on a local subnet, register target devices with their MAC addresses, check reachability with ICMP, and wake registered machines using Wake-on-LAN Magic Packets.

## Project Context

- Course context: Operating Systems lab project
- Team size: 3 students
- Host hardware: Raspberry Pi 5, 8GB RAM
- Host OS: Raspberry Pi OS 64-bit, Debian bookworm based, Linux kernel 6.x
- Network target: Local residential or lab LAN such as `192.168.1.0/24`
- Target device: PC or desktop with Ethernet Wake-on-LAN enabled in BIOS/UEFI and OS power settings

## Planned Architecture

```text
LanRouser/
├── backend/
│   ├── __init__.py
│   ├── scanner.py
│   └── wol_engine.py
├── frontend/
│   └── templates/
│       └── index.html
├── storage.json
├── app.py
├── requirements.txt
└── AI_AGENT_PROMPT.md
```

## Team Responsibilities

### Developer 1: `backend/scanner.py`

Responsible for subnet discovery.

Expected scope:
- Discover active hosts on the local subnet using ARP-based discovery.
- Execute Linux networking commands safely through Python subprocesses.
- Parse command output into structured Python data.
- Return discovered IP addresses, MAC addresses, and optional host metadata.

### Developer 2: `backend/wol_engine.py`

Responsible for Wake-on-LAN and reachability logic.

Expected scope:
- Validate and normalize MAC addresses.
- Generate Wake-on-LAN Magic Packets.
- Send raw UDP broadcast packets to wake target machines.
- Check whether a host is reachable using ICMP ping.

### Developer 3: `app.py` and `frontend/templates/index.html`

Responsible for the Flask orchestration layer and web interface.

Expected scope:
- Build REST endpoints for scanning, registering devices, ping checks, and wake requests.
- Read and write persistent device records in `storage.json`.
- Build a clean responsive dashboard for controlling the system.
- Connect frontend actions to backend endpoints.

## Functional Requirements

- Scan local subnet for active devices.
- Display discovered devices with IP and MAC address.
- Register a device into persistent JSON storage.
- List registered devices.
- Check whether a registered device is online.
- Send a Wake-on-LAN Magic Packet to a registered MAC address.

## Non-Functional Requirements

- Keep modules decoupled to reduce merge conflicts.
- Use simple Python and Flask for readability.
- Avoid unnecessary external infrastructure.
- Target Linux/Raspberry Pi OS behavior first.
- Keep networking behavior transparent enough for OS lab demonstration.

## Development Notes

The source files are intentionally empty at this stage. Each team member should implement only the file assigned to their responsibility and avoid changing other modules unless the team agrees on an interface change.

