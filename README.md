# 🛡️ Intrusion Guard AI

### AI-Powered Real-Time Intrusion Detection & Alert System

> **A desktop-based intelligent surveillance system that combines YOLOv8 person detection, OpenCV motion detection, real-time webcam/video monitoring, configurable alerts, email notifications, and optional hardware-based siren activation.**

**Intrusion Guard AI** is a real-time computer-vision security application designed to detect potential human intrusion through a connected webcam or video source.

The system combines **YOLOv8n-based person detection** with a lightweight **OpenCV motion-detection fallback**, allowing it to continue operating even when the AI detector is unavailable.

When an intrusion is detected, the application can:

* 📸 Capture a snapshot
* 🚨 Trigger a system siren
* 🔊 Activate an external Arduino-controlled buzzer/siren
* 📧 Send an email alert
* 🖥️ Display the detection in the live monitoring interface

The application is packaged as a **Windows desktop application using Electron**, while the detection and alerting backend is powered by **Python + Flask**.

---

## ✨ Key Features

### 🤖 AI Person Detection

Uses **YOLOv8n** to detect people from the camera feed.

The detector specifically filters for the **person class (class 0)** and applies configurable confidence and area thresholds.

### 📹 Live Webcam Monitoring

Monitor a connected webcam in real time.

The system supports configurable webcam indexes and captures frames at a resolution of up to **1280 × 720** for webcam input.

### 🎥 Video File Demo Mode

The detector can also process video files, with demo videos looping automatically when playback reaches the end.

### 🧠 Motion Detection

In addition to YOLO detection, the system provides an OpenCV-based motion detection mode using:

* Background modeling
* Gaussian blur
* Frame differencing
* Thresholding
* Contour detection
* Minimum motion-area filtering

This also serves as a fallback when YOLO cannot be loaded.

### 🔄 Intelligent YOLO Fallback

If YOLO fails to load or inference fails, the system can automatically fall back to motion detection rather than completely stopping the surveillance pipeline.

### 📸 Automatic Snapshots

When an intrusion event is detected, the system captures and stores a timestamped snapshot.

Snapshots are generated in the application's snapshot directory and are associated with the intrusion event.

### 📧 Email Alerts

Optional Gmail-based email alerts can be enabled.

The latest intrusion snapshot can also be attached to the alert email, subject to the configured cooldown.

### 🔊 Multiple Alert Outputs

The application supports several sound-alert modes:

```text
None
System
External
Both
```

The system siren can use the computer's audio output, while the external mode communicates with an Arduino-controlled buzzer/relay.

### 🔌 Arduino External Buzzer

An Arduino can control an external relay and siren.

The Python backend communicates with the Arduino through **Serial communication using PySerial**.

### ⚙️ Configurable Detection Parameters

The system provides configurable parameters including:

* Detection mode
* YOLO confidence
* Minimum person area
* Motion area threshold
* Snapshot cooldown
* Webcam index
* Email settings
* Email cooldown
* Snapshot attachment
* Sound mode
* Arduino serial port
* Buzzer duration

Configuration is persisted in JSON.

---

# 🏗️ System Architecture

```text
                         ┌─────────────────────┐
                         │     Camera / Video  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   OpenCV Capture    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Detection Engine    │
                         └──────────┬──────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
              ┌──────────────┐              ┌──────────────┐
              │   YOLOv8n    │              │ OpenCV Motion│
              │ Person Mode  │              │    Mode      │
              └──────┬───────┘              └──────┬───────┘
                     │                             │
                     └──────────────┬──────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Intrusion Detected? │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Snapshot Generation │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
                  ▼                 ▼                 ▼
            ┌───────────┐    ┌────────────┐    ┌────────────┐
            │  Email    │    │ PC Siren   │    │  Arduino   │
            │  Alert    │    │   Alert    │    │   Buzzer   │
            └───────────┘    └────────────┘    └─────┬──────┘
                                                     │
                                                     ▼
                                                  Relay
                                                     │
                                                     ▼
                                                   Siren
```

---

# 🧠 Detection Pipeline

Intrusion Guard uses two detection strategies.

## 1. YOLO Person Detection

When `person_only` mode is enabled, the application loads the local **YOLOv8n** model.

The detector:

1. Captures a frame.
2. Runs YOLO inference.
3. Filters for the person class.
4. Applies a confidence threshold.
5. Applies a minimum bounding-box area.
6. Performs additional local non-maximum suppression.
7. Determines whether an intrusion event occurred.

The implementation uses model-level IoU/max-detection settings together with an additional local NMS stage to reduce duplicate detections.

```text
Camera Frame
     │
     ▼
 YOLOv8n
     │
     ▼
Person Class
     │
     ▼
Confidence Filter
     │
     ▼
Area Filter
     │
     ▼
Local NMS
     │
     ▼
Intrusion Event
```

---

## 2. OpenCV Motion Detection

The motion mode uses traditional computer vision rather than an AI model.

```text
Frame
  │
  ▼
Grayscale
  │
  ▼
Gaussian Blur
  │
  ▼
Background Difference
  │
  ▼
Threshold
  │
  ▼
Dilation
  │
  ▼
Contours
  │
  ▼
Area Filtering
  │
  ▼
Motion Event
```

This provides a lightweight alternative when person detection is not required or when YOLO is unavailable.

---

# 🚨 Intrusion Response Pipeline

Once an intrusion event is generated:

```text
Intrusion
    │
    ├──────────────► 📸 Snapshot
    │
    ├──────────────► 🔊 System Siren
    │
    ├──────────────► 🔌 Arduino Buzzer
    │
    └──────────────► 📧 Email Alert
```

The available responses depend on the configured alert settings. Email notifications use a cooldown mechanism to prevent excessive repeated alerts.

---

# 🔌 Arduino + External Siren

Intrusion Guard can integrate with an Arduino through a serial connection.

### Communication

The Python backend uses **PySerial** to communicate with the Arduino at **9600 baud**.

The Arduino can receive commands such as:

```text
ON
OFF
BEEP <milliseconds>
```

This allows the application to control an external relay and siren.

### Example Hardware Setup

```text
Arduino
   │
   │ D8
   ▼
Relay Module
   │
   ├──── COM
   │
   └──── NO
          │
          ▼
        Siren
          │
          ▼
       Battery
```

The repository also includes an Arduino sketch under:

```text
arduino/relay_buzzer/
```

The current project documentation specifies the relay input on **D8** and provides the intended relay/siren wiring procedure.

> ⚠️ Use appropriate electrical isolation, fusing, power ratings, and safe wiring practices when connecting a relay and external siren.

---

# 🖥️ Application Architecture

Intrusion Guard uses a hybrid desktop architecture:

```text
┌──────────────────────────────────────────────┐
│                Electron Desktop              │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │          Renderer / UI               │   │
│   └──────────────────┬───────────────────┘   │
│                      │                       │
│                Electron IPC                  │
│                      │                       │
│   ┌──────────────────▼───────────────────┐   │
│   │          Electron Main Process       │   │
│   └──────────────────┬───────────────────┘   │
└──────────────────────┼───────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Python Backend  │
              │     Flask       │
              └────────┬────────┘
                       │
          ┌────────────┼─────────────┐
          │            │             │
          ▼            ▼             ▼
      OpenCV        YOLOv8n       PySerial
          │            │             │
          └────────────┼─────────────┘
                       │
                       ▼
                Alert Management
```

The Electron application uses `electron/main.js` as its entry point and packages the backend as an additional resource.

---

# 🛠️ Technology Stack

| Technology              | Purpose                               |
| ----------------------- | ------------------------------------- |
| **Python**              | Detection and backend logic           |
| **Flask**               | Local web backend/API                 |
| **OpenCV**              | Video processing and motion detection |
| **YOLOv8n**             | Person detection                      |
| **Ultralytics**         | YOLO implementation                   |
| **PyTorch**             | Deep-learning inference               |
| **NumPy**               | Numerical/image processing            |
| **Pillow**              | Image processing                      |
| **PySerial**            | Arduino communication                 |
| **python-dotenv**       | Environment configuration             |
| **Electron**            | Desktop application shell             |
| **Electron Builder**    | Windows application packaging         |
| **HTML/CSS/JavaScript** | Monitoring interface                  |
| **Arduino**             | External buzzer/relay control         |

The backend dependency versions currently specified by the repository include Flask 3.0.3, OpenCV 4.9.0.80, NumPy 1.26.4, Ultralytics 8.2.0, PySerial 3.5, PyTorch 2.5.1 and torchvision 0.20.1.

---

# 📂 Project Structure

```text
Intrusion-Guard-AI/
│
├── arduino/
│   └── relay_buzzer/
│       └── relay_buzzer.ino
│
├── electron/
│   │
│   ├── backend/
│   │   ├── app.py
│   │   ├── detection.py
│   │   ├── email_utils.py
│   │   ├── launcher.py
│   │   ├── requirements.txt
│   │   │
│   │   ├── config/
│   │   │   └── config.json
│   │   │
│   │   ├── static/
│   │   │   ├── css/
│   │   │   ├── js/
│   │   │   └── sounds/
│   │   │
│   │   ├── templates/
│   │   │   ├── home.html
│   │   │   ├── index.html
│   │   │   └── settings.html
│   │   │
│   │   └── yolov8n.pt
│   │
│   ├── config/
│   │   └── config.json
│   │
│   ├── main.js
│   ├── preload.js
│   │
│   └── renderer/
│       └── index.html
│
├── .env.example
├── .gitignore
├── package.json
├── package-lock.json
├── README.md
└── README.txt
```

---

# ⚙️ Configuration

Intrusion Guard maintains persistent configuration for detection, alerts, sound output, and hardware integration.

Important configuration options include:

```json
{
  "trigger_mode": "person_only",
  "use_yolo": true,
  "person_conf": 0.5,
  "min_person_area_px": 2000,
  "motion_min_area": 8000,
  "snapshot_cooldown_sec": 8,
  "webcam_index": 0,
  "email_enabled": false,
  "email_cooldown_sec": 30,
  "attach_snapshot": true,
  "sound_mode": "external",
  "buzzer_serial_port": "",
  "buzzer_hold_ms": 2000
}
```

The application supports two primary trigger modes:

```text
person_only
motion
```

and four sound modes:

```text
none
system
external
both
```

These settings are handled by the Flask backend and persisted to JSON.

---

# 🚀 Installation

## Prerequisites

Recommended environment:

* Windows
* Python 3.x
* Node.js
* npm
* Webcam
* Optional Arduino Uno
* Optional relay + siren

---

## 1. Clone the Repository

```bash
git clone https://github.com/Devadharshan619/Intrusion-Guard-AI.git
```

```bash
cd Intrusion-Guard-AI
```

---

# 🐍 Python Backend Setup

Create a virtual environment:

### Windows PowerShell

```powershell
py -3 -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```powershell
pip install -r electron/backend/requirements.txt
```

The repository's backend requirements are defined in `electron/backend/requirements.txt`.

---

# 🔐 Environment Variables

Copy:

```text
.env.example
```

to:

```text
.env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Configure the email credentials only if email alerts are required.

Example:

```env
GMAIL_ADDRESS=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
ALERT_TO_EMAIL=recipient@example.com
```

> **Never commit `.env` to GitHub.**

For Gmail, use an appropriate **App Password** rather than exposing your normal account password.

---

# 🖥️ Electron Setup

Install Node.js dependencies:

```bash
npm install
```

The project uses Electron and Electron Builder, with the Electron entry point defined as `electron/main.js`.

---

# ▶️ Running the Application

Start the Electron application:

```bash
npm run dev
```

The repository's current `package.json` defines:

```text
npm run dev
npm run pack
npm run dist
```

for development, unpacked packaging, and distribution builds respectively.

---

# 🌐 Backend Routes

The Flask backend exposes pages including:

```text
/
/home
/live
/demo
/settings
/config
```

The live and demo interfaces are served through Flask templates, while configuration can be retrieved or updated through the `/config` endpoint.

---

# 📹 Detection Modes

## Person-Only Mode

Recommended when the goal is to detect human intrusion.

```text
Camera
   ↓
YOLOv8n
   ↓
Person Class
   ↓
Confidence Filter
   ↓
Area Filter
   ↓
NMS
   ↓
Intrusion
```

---

## Motion Mode

Useful when general movement detection is sufficient.

```text
Camera
   ↓
OpenCV
   ↓
Background Difference
   ↓
Threshold
   ↓
Contours
   ↓
Motion
   ↓
Intrusion
```

---

# 📧 Email Alert Flow

When enabled:

```text
Intrusion Detected
       │
       ▼
Snapshot Captured
       │
       ▼
Cooldown Check
       │
       ▼
Email Generated
       │
       ├── Alert Message
       │
       └── Optional Snapshot
```

The backend applies an email cooldown to reduce repeated notifications during continuous intrusion events.

---

# 📸 Snapshot Management

Snapshots are generated automatically when an intrusion is triggered.

Example:

```text
snapshots/
├── snapshot_20250825_220558.jpg
├── snapshot_20250825_220606.jpg
└── ...
```

The detection engine also uses a configurable snapshot cooldown to avoid generating excessive images.

---

# 📦 Build Windows Installer

The project is configured with Electron Builder to create a Windows NSIS installer.

Run:

```bash
npm run dist
```

The package configuration defines:

```text
Product Name: IG3
Installer Target: NSIS
Artifact: IG3-Setup-${version}.exe
```

The Electron build also packages the backend as an extra resource.

---

# 🧪 Testing Scenarios

The system can be tested using:

| Scenario            | Expected Behavior           |
| ------------------- | --------------------------- |
| Empty scene         | No intrusion                |
| Person enters frame | YOLO detects person         |
| Person leaves frame | Detection stops             |
| Multiple people     | Multiple person boxes       |
| Large movement      | Motion detection triggers   |
| YOLO unavailable    | Motion fallback can operate |
| Intrusion detected  | Snapshot generated          |
| Email enabled       | Alert email sent            |
| External mode       | Arduino siren activated     |
| System mode         | PC siren activated          |
| Both mode           | PC + external alert         |

---

# 📊 Detection Controls

The detection engine provides several tunable parameters:

### Confidence

Controls the minimum YOLO confidence required for person detection.

### Minimum Person Area

Filters very small detections that may represent distant/noisy objects.

### Motion Area

Controls the minimum contour area required for motion detection.

### Model IoU

Controls YOLO's NMS behavior.

### Deduplication IoU

Applies an additional local NMS stage to reduce duplicate bounding boxes.

### Maximum Detections

Limits the number of detections processed per frame.

These controls are implemented directly in the detection pipeline.

---

# 🔒 Security Considerations

Intrusion Guard is designed for local/desktop surveillance, but deployments should still follow security best practices.

### Protect credentials

Never commit:

```text
.env
passwords
API keys
email credentials
tokens
```

### Restrict camera access

Only authorized users should have access to the surveillance workstation.

### Protect hardware

The Arduino, relay, and siren wiring should be physically secured against tampering.

### Validate deployment conditions

Camera placement, lighting, environmental conditions, and detection thresholds should be tested before relying on the system for real-world security decisions.

---

# ⚠️ Limitations

The current system has several practical limitations:

* YOLO detection is currently focused on the **person class**.
* Motion detection can trigger on non-human movement.
* Low-light conditions may reduce detection quality.
* Occlusion can affect person detection.
* Camera positioning affects detection performance.
* CPU inference may limit frame rate.
* Email alerts depend on network/email availability.
* External siren functionality requires compatible Arduino/relay hardware.
* The system is an AI-assisted monitoring tool and should not be treated as a replacement for professional security systems.

---

# 🔮 Future Enhancements

Potential improvements include:

* [ ] Multi-person tracking
* [ ] Object tracking across frames
* [ ] Face recognition with privacy controls
* [ ] Restricted-zone / ROI detection
* [ ] Night-vision optimization
* [ ] RTSP/IP camera support
* [ ] Multi-camera monitoring
* [ ] Mobile notifications
* [ ] Telegram/WhatsApp alerts
* [ ] SMS alerts
* [ ] Cloud event dashboard
* [ ] Detection analytics
* [ ] Event history database
* [ ] User authentication
* [ ] Role-based access
* [ ] Improved threat classification
* [ ] Edge-device deployment
* [ ] GPU acceleration
* [ ] Automatic camera health monitoring

---

# 🎯 Project Objectives

Intrusion Guard AI focuses on four primary objectives:

### 1. Detect

Identify potential human intrusion using computer vision.

### 2. Verify

Use configurable confidence, area, and suppression thresholds to reduce unnecessary detections.

### 3. Alert

Provide immediate visual, audio, hardware, and email responses.

### 4. Record

Capture snapshots associated with detected intrusion events.

---

# 🌍 Potential Applications

Intrusion Guard can be adapted for:

* 🏠 Home security
* 🏢 Office monitoring
* 🏭 Industrial premises
* 🏗️ Construction sites
* 🌾 Agricultural land
* 🏫 Campus security
* 🚧 Restricted zones
* 🏪 Small business surveillance
* 📦 Warehouse monitoring
* 🌲 Remote-area monitoring

---

# 🧠 Project Highlights

```text
AI Computer Vision
        +
Real-Time Monitoring
        +
Motion Detection
        +
Hardware Integration
        +
Email Automation
        +
Desktop Application
        ↓
Intelligent Intrusion Monitoring
```

This project demonstrates the integration of **AI/ML, computer vision, backend development, desktop application development, automation, and hardware communication** into a single security-focused system.

---

# 👨‍💻 Author

## Devadharshan

Computer Science Engineering — Artificial Intelligence & Machine Learning

GitHub:

https://github.com/Devadharshan619

---

# ⭐ Support

If you find this project useful:

⭐ Star the repository
🍴 Fork the project
🐛 Report issues
💡 Suggest improvements

---

# 📜 License

Please refer to the repository's license configuration for the applicable usage and distribution terms.

---

## 🛡️ Intrusion Guard AI

> **Detect. Alert. Respond.**

An AI-powered intrusion monitoring system combining **YOLOv8, OpenCV, Flask, Electron, Arduino, and real-time alerting** into a practical desktop security solution.
