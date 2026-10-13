# วิธีเริ่มต้นโปรเจกต์ LanRouser

เอกสารนี้อธิบายวิธีเตรียม Python environment, ติดตั้ง dependencies และรัน Flask project สำหรับโปรเจกต์ LanRouser

## 1. เข้าโฟลเดอร์โปรเจกต์

```bash
cd LanRouser
```

หรือถ้าอยู่บนเครื่องนี้:

```bash
cd /Users/azdev-macpro/Developer/LanRouser
```

## 2. สร้าง Virtual Environment

แนะนำให้ใช้ virtual environment เพื่อแยก dependency ของโปรเจกต์นี้ออกจาก Python หลักของเครื่อง

```bash
python3 -m venv .venv
```

## 3. เปิดใช้งาน Virtual Environment

### macOS / Linux / Raspberry Pi OS

```bash
source .venv/bin/activate
```

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

ถ้าเปิดใช้งานสำเร็จ จะเห็นชื่อ environment เช่น `(.venv)` อยู่หน้าบรรทัด terminal

## 4. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

ตอนนี้ dependency หลักของโปรเจกต์คือ Flask

## 5. รัน Flask Application

```bash
python app.py
```

โดยค่าเริ่มต้น Flask จะรันที่:

```text
http://127.0.0.1:5000
```

ถ้ารันบน Raspberry Pi และต้องการเปิดจากเครื่องอื่นในวง LAN ให้เข้า URL ด้วย IP ของ Raspberry Pi เช่น:

```text
http://192.168.1.50:5000
```

## 6. ทดสอบ Health Check

เปิด browser หรือใช้คำสั่ง:

```bash
curl http://127.0.0.1:5000/health
```

ผลลัพธ์ที่ควรได้:

```json
{
  "service": "LanRouser",
  "status": "ok"
}
```

## 7. หยุด Server

กด:

```text
Ctrl + C
```

ใน terminal ที่กำลังรัน Flask server

## หมายเหตุสำหรับ Raspberry Pi

- ใช้ Raspberry Pi OS 64-bit จะเหมาะกับโปรเจกต์นี้ที่สุด
- ฟีเจอร์ ARP scan, ICMP ping และ Wake-on-LAN จะพัฒนาเพิ่มในไฟล์ backend ภายหลัง
- บางคำสั่งเกี่ยวกับ network อาจต้องใช้สิทธิ์ root หรือ `sudo`
- เครื่องเป้าหมายที่จะปลุกด้วย Wake-on-LAN ต้องเปิดใช้งาน WoL ใน BIOS/UEFI และ OS ก่อน

