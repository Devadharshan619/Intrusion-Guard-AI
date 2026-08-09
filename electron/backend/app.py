import os, cv2, time, json, numpy as np, subprocess, threading
from queue import Queue, Empty
from threading import Lock
from dotenv import load_dotenv
from flask import Flask, render_template, Response, request, jsonify, send_from_directory, redirect, url_for

from detection import DetectionRunner
from email_utils import send_mail

# ----- paths that work in dev & packaged -----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../electron/backend
ROOT_DIR = os.path.dirname(BASE_DIR)                           # .../electron (packaged: .../resources)
load_dotenv()

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates")
)

# ---------- persistent config ----------
CFG_DIR = os.path.join(ROOT_DIR, "config")
os.makedirs(CFG_DIR, exist_ok=True)
CFG_PATH = os.path.join(CFG_DIR, "config.json")

def load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(cfg: dict):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

CONFIG_DEFAULTS = {
    "trigger_mode": "person_only",   # person_only | motion
    "use_yolo": True,
    "person_conf": 0.5,
    "min_person_area_px": 2000,
    "motion_min_area": 8000,
    "snapshot_cooldown_sec": 8,
    "webcam_index": 0,

    "email_enabled": False,
    "email_cooldown_sec": 30,
    "attach_snapshot": True,
    "last_email_sent": 0,

    "sound_mode": "external",  # none|system|external|both
    "buzzer_serial_port": "",
    "buzzer_hold_ms": 2000,

    "GMAIL_ADDRESS": "",
    "GMAIL_APP_PASSWORD": "",
    "ALERT_TO_EMAIL": ""
}
CONFIG = {**CONFIG_DEFAULTS, **load_cfg()}

def _apply_email_env_from_cfg(cfg):
    for k in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "ALERT_TO_EMAIL"):
        os.environ[k] = str(cfg.get(k) or "")

_apply_email_env_from_cfg(CONFIG)

# ---------- queues / detector ----------
event_queue = Queue(maxsize=200)
detector = None
detector_lock = Lock()

# ---------- optional serial buzzer ----------
SERIAL_AVAILABLE = False
try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
except Exception:
    SERIAL_AVAILABLE = False

class BuzzerController:
    def __init__(self, baud=9600, wait_after_open=2.0):
        self.lock = Lock()
        self.port = None
        self.baud = baud
        self.wait_after_open = float(wait_after_open)
        self.ser = None
        self.active_until = 0.0
        self.is_on = False
        self._stop_flag = False
        threading.Thread(target=self._watchdog, daemon=True).start()

    def set_port(self, port: str | None):
        with self.lock:
            self._close_locked()
            self.port = (port or "").strip() or None
            self._ensure_open_locked()

    def _ensure_open_locked(self):
        if not SERIAL_AVAILABLE: return False
        if self.ser and getattr(self.ser, "is_open", False): return True
        if not self.port: return False
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.3)
            try: self.ser.dtr = False
            except: pass
            time.sleep(self.wait_after_open)
            try:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            except: pass
            return True
        except Exception as e:
            print(f"[buzzer] Serial error on {self.port}: {e}")
            try:
                if self.ser: self.ser.close()
            except: pass
            self.ser = None
            return False

    def _close_locked(self):
        try:
            if self.ser: self.ser.close()
        except: pass
        self.ser = None

    def _write_line_locked(self, line_bytes: bytes):
        if not self._ensure_open_locked():
            return False, "not_open"
        try:
            self.ser.write(line_bytes + b"\n")
            self.ser.flush()
            try:
                resp = self.ser.readline().decode("ascii", errors="ignore").strip()
                if resp: print(f"[buzzer] {resp}")
            except: pass
            return True, "ok"
        except Exception as e:
            print(f"[buzzer] write error: {e}")
            try:
                if self.ser: self.ser.close()
            except: pass
            self.ser = None
            return False, str(e)

    def on(self):
        with self.lock:
            ok, _ = self._write_line_locked(b"ON")
            if ok: self.is_on = True
            return ok

    def off(self):
        with self.lock:
            ok, _ = self._write_line_locked(b"OFF")
            self.is_on = False
            return ok

    def beep(self, ms: int):
        ms = max(50, int(ms))
        with self.lock:
            ok, _ = self._write_line_locked(f"BEEP {ms}".encode("ascii"))
            if ok:
                self.is_on = True
                self.active_until = max(self.active_until, time.time() + ms/1000.0)
            return ok

    def pulse_or_extend(self, hold_ms: int):
        now = time.time()
        with self.lock:
            self.active_until = max(self.active_until, now + (max(50, int(hold_ms))/1000.0))
        self.on()

    def stop_now(self):
        with self.lock:
            self.active_until = 0.0
        self.off()

    def _watchdog(self):
        while not self._stop_flag:
            time.sleep(0.05)
            with self.lock:
                due = (time.time() >= self.active_until)
                should_off = due and self.is_on
            if should_off: self.off()

    def status(self):
        with self.lock:
            return {"port": self.port, "is_on": self.is_on, "active_until": self.active_until}

buzzer = BuzzerController(baud=9600, wait_after_open=2.0)
buzzer.set_port(CONFIG.get("buzzer_serial_port") or None)

# ---------- optional PC speaker siren ----------
def _trigger_system_siren():
    try:
        siren_path = os.path.join(app.static_folder, "sounds", "siren.wav")
        if os.name == "nt":
            import winsound
            winsound.PlaySound(siren_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            for cmd in (["paplay", siren_path], ["aplay", siren_path], ["afplay", siren_path], ["play", siren_path]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except FileNotFoundError:
                    continue
    except Exception as e:
        print(f"[sound] system siren failed: {e}")

# ---------- intrusion hook ----------
def _handle_intrusion(evt):
    mode = str(CONFIG.get("sound_mode", "none"))
    hold_ms = int(CONFIG.get("buzzer_hold_ms", 2000))
    if mode in ("external", "both"):
        buzzer.pulse_or_extend(hold_ms)
    if mode in ("system", "both"):
        _trigger_system_siren()

    if CONFIG.get("email_enabled", False):
        now = time.time()
        if now - CONFIG.get("last_email_sent", 0) >= CONFIG.get("email_cooldown_sec", 30):
            CONFIG["last_email_sent"] = now
            attach = evt.get("snapshot_fs") if CONFIG.get("attach_snapshot", True) else None
            save_cfg(CONFIG)  # persist last_email_sent
            send_mail("Intrusion detected", "An intrusion was detected.", attach)

# ---------- routes ----------
@app.route("/")
def root(): return redirect(url_for("home"))

@app.route("/home")
def home(): return render_template("home.html")

@app.route("/live")
def live(): return render_template("index.html", page_mode="live")

@app.route("/demo")
def demo(): return render_template("index.html", page_mode="demo")

@app.route("/settings")
def settings(): return render_template("settings.html")

# config get/set
@app.route("/config", methods=["GET","POST"])
def config():
    global CONFIG
    if request.method == "POST":
        d = request.json or {}
        CONFIG["trigger_mode"]          = str(d.get("trigger_mode", CONFIG["trigger_mode"]))
        CONFIG["use_yolo"]              = (CONFIG["trigger_mode"] == "person_only") or bool(d.get("use_yolo", CONFIG["use_yolo"]))
        CONFIG["person_conf"]           = float(d.get("person_conf", CONFIG["person_conf"]))
        CONFIG["min_person_area_px"]    = int(d.get("min_person_area_px", CONFIG["min_person_area_px"]))
        CONFIG["motion_min_area"]       = int(d.get("motion_min_area", CONFIG["motion_min_area"]))
        CONFIG["snapshot_cooldown_sec"] = int(d.get("snapshot_cooldown_sec", CONFIG["snapshot_cooldown_sec"]))
        CONFIG["webcam_index"]          = int(d.get("webcam_index", CONFIG["webcam_index"]))

        CONFIG["email_enabled"]         = bool(d.get("email_enabled", CONFIG["email_enabled"]))
        CONFIG["email_cooldown_sec"]    = int(d.get("email_cooldown_sec", CONFIG["email_cooldown_sec"]))
        CONFIG["attach_snapshot"]       = bool(d.get("attach_snapshot", CONFIG["attach_snapshot"]))

        CONFIG["GMAIL_ADDRESS"]         = str(d.get("GMAIL_ADDRESS", CONFIG.get("GMAIL_ADDRESS","")))
        CONFIG["GMAIL_APP_PASSWORD"]    = str(d.get("GMAIL_APP_PASSWORD", CONFIG.get("GMAIL_APP_PASSWORD","")))
        CONFIG["ALERT_TO_EMAIL"]        = str(d.get("ALERT_TO_EMAIL", CONFIG.get("ALERT_TO_EMAIL","")))

        mode = str(d.get("sound_mode", CONFIG["sound_mode"])).lower()
        if mode not in ("none","system","external","both"): mode = "none"
        CONFIG["sound_mode"]            = mode
        CONFIG["buzzer_serial_port"]    = str(d.get("buzzer_serial_port", CONFIG["buzzer_serial_port"]))
        CONFIG["buzzer_hold_ms"]        = int(d.get("buzzer_hold_ms", CONFIG["buzzer_hold_ms"]))

        _apply_email_env_from_cfg(CONFIG)
        buzzer.set_port(CONFIG["buzzer_serial_port"])
        save_cfg(CONFIG)
        return jsonify({"ok": True, "config": CONFIG})
    return jsonify(CONFIG)

@app.route("/upload_video", methods=["POST"])
def upload_video():
    f = request.files.get("video")
    if not f: return jsonify({"ok": False, "error": "no_file"}), 400
    up_dir = os.path.join(BASE_DIR, "uploads", "videos")
    os.makedirs(up_dir, exist_ok=True)
    path = os.path.join(up_dir, f.filename)
    f.save(path)
    return jsonify({"ok": True, "path": path})

@app.route("/start", methods=["POST"])
def start():
    global detector
    data = request.json or {}
    src_type = data.get("source", "webcam")
    webcam_index = int(data.get("webcam_index", CONFIG.get("webcam_index", 0)))
    video_path = data.get("video_path")

    with detector_lock:
        if detector:
            try: detector.stop()
            except: pass
            detector = None

        if src_type == "webcam":
            source = f"webcam:{webcam_index}"
        elif src_type == "file" and video_path:
            if not os.path.isabs(video_path):
                video_path = os.path.abspath(os.path.join(BASE_DIR, video_path))
            if not os.path.exists(video_path):
                return jsonify({"ok": False, "error": f"file_not_found: {video_path}"}), 400
            source = f"file:{video_path}"
        else:
            return jsonify({"ok": False, "error": "bad_source"}), 400

        snap_dir = os.path.join(BASE_DIR, "snapshots")
        detector = DetectionRunner(source=source, config=CONFIG, event_queue=event_queue, snapshot_dir=snap_dir)
        detector.start()
        print(f"[server] started: {source}")
    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
def stop():
    global detector
    with detector_lock:
        if detector:
            try: detector.stop()
            except: pass
            detector = None
    buzzer.stop_now()
    if os.name == "nt":
        try:
            import winsound; winsound.PlaySound(None, winsound.SND_PURGE)
        except: pass
    return jsonify({"ok": True})

@app.route("/frame.jpg")
def frame_jpg():
    with detector_lock:
        det = detector
    if det is None:
        frame = None
    else:
        try:
            with det._frame_lock:
                frame = None if det.output_frame is None else det.output_frame.copy()
        except Exception:
            frame = None

    if frame is None:
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", blank)
    else:
        ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return Response(status=204)
    resp = Response(buf.tobytes(), mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/events")
def events():
    def gen():
        last_beat = time.time()
        while True:
            try:
                evt = event_queue.get(timeout=1.0)
                if evt.get("type") == "intrusion":
                    _handle_intrusion(evt)
                yield f"data: {json.dumps(evt)}\n\n"
            except Empty:
                if time.time() - last_beat >= 5:
                    yield f"data: {json.dumps({'type':'heartbeat','ts':time.time()})}\n\n"
                    last_beat = time.time()
    return Response(gen(), mimetype="text/event-stream")

@app.route("/snapshots/<path:filename>")
def snapshots(filename): return send_from_directory(os.path.join(BASE_DIR,"snapshots"), filename)

@app.route("/email_test", methods=["POST"])
def email_test():
    ok, msg = send_mail("Test: Intrusion Guard", "This is a test email.", None)
    return jsonify({"ok": bool(ok), "message": msg})

# serial helpers
@app.route("/buzzer_test", methods=["POST"])
def buzzer_test():
    try:
        buzzer.pulse_or_extend(int(CONFIG.get("buzzer_hold_ms", 2000)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/buzzer_off", methods=["POST"])
def buzzer_off():
    try:
        buzzer.stop_now()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/buzzer_on", methods=["POST"])
def buzzer_on():
    try:
        hold_ms = int(request.json.get("ms", CONFIG.get("buzzer_hold_ms", 2000))) if request.is_json else CONFIG.get("buzzer_hold_ms", 2000)
        buzzer.pulse_or_extend(int(hold_ms))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/buzzer_beep", methods=["POST"])
def buzzer_beep():
    try:
        ms = int(request.json.get("ms", 800)) if request.is_json else 800
        ok = buzzer.beep(ms)
        return jsonify({"ok": bool(ok)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/buzzer_status")
def buzzer_status(): return jsonify(buzzer.status())

@app.route("/serial_ports")
def serial_ports():
    if not SERIAL_AVAILABLE:
        return jsonify({"ok": False, "error": "pyserial_not_installed"}), 500
    ports = [p.device for p in list_ports.comports()]
    return jsonify({"ok": True, "ports": ports})

@app.route("/set_port", methods=["POST"])
def set_port():
    data = request.json or {}
    port = (data.get("port") or "").strip()
    buzzer.set_port(port if port else None)
    CONFIG["buzzer_serial_port"] = port
    save_cfg(CONFIG)
    return jsonify({"ok": True, "port": port})

@app.route("/diag")
def diag():
    with detector_lock:
        det = detector
        if not det:
            return jsonify({"running": False, "config": CONFIG, "buzzer": buzzer.status()})
        s = det.stats.copy()
        s.update({"running": True, "source": det.source, "use_yolo": bool(det.yolo is not None)})
        return jsonify({"detector": s, "config": CONFIG, "buzzer": buzzer.status()})

@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    os.makedirs(os.path.join(BASE_DIR, "snapshots"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "uploads","videos"), exist_ok=True)

    port = int(os.getenv("IG3_PORT") or os.getenv("PORT") or os.getenv("FLASK_PORT") or 5123)
    host = os.getenv("FLASK_HOST") or "127.0.0.1"
    debug = (os.getenv("FLASK_DEBUG") == "1")

    print(f"Starting server on http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=debug)
