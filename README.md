# Intrusion Guard v3 (Webcam + External Buzzer)

## Quickstart (Windows PowerShell)
```powershell
cd C:\path\to\intrusion_guard_v3
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # optional: set Gmail for email alerts
python app.py
# open http://127.0.0.1:5000/home
```

## External buzzer
- Flash `arduino/relay_buzzer.ino` to your Arduino Uno (D8 → Relay IN, 5V → VCC, GND → GND).
- Wire battery + → fuse → Relay COM; Relay NO → siren +; siren − → battery −; diode across siren (stripe to +).
- In **Settings**: Alert sound output = **External**, Refresh ports, pick COMx, **Apply Port**, test **ON/OFF/BEEP**.

## Notes
- Debug reloader is disabled so only one Python process runs (prevents COM ownership clashes).
- Person-only detection uses YOLOv8n (class 0). Motion mode uses MOG2 area threshold.
- Snapshots land in `/snapshots`; email (optional) attaches latest snapshot on cooldown.
