import os, cv2, time, threading
import numpy as np
from threading import Lock

# -------- optional YOLO (ultralytics) --------
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None


# -------- small helpers: IoU + local NMS (to merge duplicate boxes) --------
def _iou_xyxy(a, b):
    ax1, ay1, ax2, ay2, _ = a
    bx1, by1, bx2, by2, _ = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0, inter_x2 - inter_x1)
    ih = max(0, inter_y2 - inter_y1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _nms_local(boxes, iou_thresh=0.55):
    """Greedy NMS on [(x1,y1,x2,y2,conf), ...], keep highest conf for overlaps >= thresh."""
    if not boxes:
        return boxes
    boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    keep = []
    suppressed = [False] * len(boxes)
    for i, bi in enumerate(boxes):
        if suppressed[i]:
            continue
        keep.append(bi)
        for j in range(i + 1, len(boxes)):
            if suppressed[j]:
                continue
            if _iou_xyxy(bi, boxes[j]) >= iou_thresh:
                suppressed[j] = True
    return keep


class DetectionRunner:
    """
    Reads frames from webcam or video file, runs:
      - YOLO person detection ("person_only"), OR
      - Motion detection ("motion") and as fallback if YOLO not available.

    Emits "intrusion" events via event_queue and draws overlays to output_frame.
    Snapshots are throttled by cooldown.
    """

    def __init__(self, source: str, config: dict, event_queue, snapshot_dir: str):
        self.source = source  # "webcam:0" or "file:C:\path\to\video.mp4"
        self.cfg = config
        self.q = event_queue
        self.snapshot_dir = snapshot_dir

        self.cap = None
        self.thread = None
        self.stop_flag = False

        self.yolo = None
        self.bg = None  # background for motion mode

        self.output_frame = None
        self._frame_lock = Lock()

        self.stats = {"frames": 0, "intrusions": 0, "last_snapshot": 0}

        # debug state
        self._last_yolo_err = None
        self._last_mode = "idle"  # "yolo", "motion", "fallback"

    # ---------------- lifecycle ----------------
    def start(self):
        self.stop_flag = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag = True
        try:
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.0)
        except:
            pass
        try:
            if self.cap:
                self.cap.release()
        except:
            pass
        self.cap = None

    # ---------------- setup ----------------
    def _open_source(self):
        if self.source.startswith("webcam:"):
            idx = int(self.source.split(":")[1])
            self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == "nt" else 0)
            # give YOLO a decent resolution to work with
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            print(f"[detector] Opened webcam {idx}")
        elif self.source.startswith("file:"):
            path = self.source.split(":", 1)[1]
            self.cap = cv2.VideoCapture(path)
            print(f"[detector] Opened file {path}")
        else:
            raise ValueError("bad source")

    def _load_yolo(self):
        # only when enabled
        if self.cfg.get("use_yolo", True) and self.cfg.get("trigger_mode") == "person_only":
            if YOLO is None:
                self._last_yolo_err = "ultralytics not installed"
                print("[detector] YOLO not available (ultralytics not installed)")
                return
            try:
                here = os.path.dirname(os.path.abspath(__file__))
                local_weight = os.path.join(here, "yolov8n.pt")  # ship this file next to detection.py
                weight = local_weight if os.path.exists(local_weight) else "yolov8n.pt"
                print(f"[detector] Loading YOLO weights from: {weight}")
                self.yolo = YOLO(weight)  # n = small model
                # CPU for widest compatibility
                try:
                    self.yolo.to("cpu")
                except Exception as e:
                    print(f"[detector] CPU fallback not needed: {e}")
                print("[detector] YOLO loaded OK.")
                self._last_yolo_err = None
            except Exception as e:
                self._last_yolo_err = str(e)
                print(f"[detector] YOLO load failed: {e}")
                self.yolo = None
        else:
            print("[detector] YOLO not loaded (use_yolo is false or trigger_mode != 'person_only').")

    # ---------------- helpers ----------------
    def _take_snapshot(self, frame_bgr):
        os.makedirs(self.snapshot_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.snapshot_dir, f"snapshot_{ts}.jpg")
        cv2.imwrite(path, frame_bgr)
        self.stats["last_snapshot"] = time.time()
        return path

    def _emit_intrusion(self, snap_fs):
        self.stats["intrusions"] += 1
        evt = {
            "type": "intrusion",
            "ts": time.time(),
            "snapshot_url": f"snapshots/{os.path.basename(snap_fs)}",
            "snapshot_fs": snap_fs,
        }
        try:
            self.q.put_nowait(evt)
        except:
            pass

    def _draw(self, frame, boxes, color=(125, 64, 255)):
        for (x1, y1, x2, y2, conf) in boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame,
                f"person {conf:.2f}",
                (x1, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )

    def _overlay_debug(self, vis, boxes_kept, boxes_raw, fps, person_conf, min_area, yolo_iou, dedup_iou):
        lines = [
            f"mode: {self._last_mode}   yolo: {'on' if self.yolo is not None else 'off'}",
            f"boxes: kept={boxes_kept} raw={boxes_raw}   conf>={person_conf:.2f} area>={min_area}",
            f"nms: model_iou={yolo_iou:.2f} local_iou={dedup_iou:.2f}   fps={fps:.1f}",
        ]
        if self._last_yolo_err:
            lines.append(f"yolo_err: {self._last_yolo_err[:60]}")
        y = 18
        for ln in lines:
            cv2.putText(vis, ln, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2, cv2.LINE_AA)
            y += 22

    # ---------------- main loop ----------------
    def _run(self):
        try:
            self._open_source()
            self._load_yolo()
        except Exception as e:
            print(f"[detector] start failed: {e}")
            return

        # thresholds (with sensible defaults)
        snap_cd = int(self.cfg.get("snapshot_cooldown_sec", 8))
        min_person_area = int(self.cfg.get("min_person_area_px", 1500))   # tuned up a bit
        person_conf = float(self.cfg.get("person_conf", 0.45))            # tuned up a bit
        motion_min_area = int(self.cfg.get("motion_min_area", 8000))
        # new tunables for duplicate suppression
        yolo_iou = float(self.cfg.get("nms_iou", 0.70))       # stricter model NMS
        max_det = int(self.cfg.get("max_det", 10))            # cap detections
        dedup_iou = float(self.cfg.get("dedup_iou", 0.55))    # local NMS to merge leftovers

        last_snap = 0
        t0 = time.time()
        frames_for_fps = 0
        fps = 0.0

        while not self.stop_flag and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if not ok:
                if self.source.startswith("file:"):
                    # loop video files for demo convenience
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.03)
                continue

            self.stats["frames"] += 1
            frames_for_fps += 1
            if frames_for_fps >= 10:
                t1 = time.time()
                fps = frames_for_fps / max(1e-6, (t1 - t0))
                t0 = t1
                frames_for_fps = 0

            boxes = []
            trig = False
            raw_len = 0

            # ---- YOLO person mode ----
            if self.cfg.get("trigger_mode") == "person_only" and self.yolo is not None:
                self._last_mode = "yolo"
                try:
                    # model-side NMS tightened via iou + max_det
                    res = self.yolo(
                        frame,
                        verbose=False,
                        conf=person_conf,
                        iou=yolo_iou,
                        max_det=max_det,
                        classes=[0],  # 0 = person
                    )
                    r0 = res[0]
                    raw = []
                    for b in r0.boxes:
                        x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                        conf = float(b.conf.item())
                        area = max(0, (x2 - x1)) * max(0, (y2 - y1))
                        if area >= min_person_area:
                            raw.append((x1, y1, x2, y2, conf))
                    raw_len = len(raw)
                    # local extra NMS to squash doubles
                    boxes = _nms_local(raw, iou_thresh=dedup_iou)
                    trig = len(boxes) > 0
                except Exception as e:
                    self._last_yolo_err = f"infer: {e}"
                    print(f"[detector] YOLO error: {e}")
                    self.yolo = None  # force fallback

            # ---- motion mode OR fallback from YOLO ----
            if (self.cfg.get("trigger_mode") == "motion") or (
                self.cfg.get("trigger_mode") == "person_only" and self.yolo is None
            ):
                self._last_mode = "motion" if self.cfg.get("trigger_mode") == "motion" else "fallback"
                try:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray = cv2.GaussianBlur(gray, (21, 21), 0)
                    if self.bg is None:
                        self.bg = gray
                    diff = cv2.absdiff(self.bg, gray)
                    thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                    thresh = cv2.dilate(thresh, None, iterations=2)
                    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    motion_boxes = []
                    for c in cnts:
                        area = cv2.contourArea(c)
                        if area < motion_min_area:
                            continue
                        x, y, w, h = cv2.boundingRect(c)
                        motion_boxes.append((x, y, x + w, y + h, 1.0))
                    # combine (if YOLO also produced boxes, keep them)
                    if motion_boxes and not boxes:
                        boxes = motion_boxes
                    trig = trig or (len(boxes) > 0)
                    # slowly update bg
                    if self.bg is not None:
                        self.bg = cv2.addWeighted(self.bg, 0.95, gray, 0.05, 0)
                except Exception as e:
                    print(f"[detector] motion error: {e}")

            # ---- draw & publish ----
            vis = frame.copy()
            self._draw(vis, boxes)
            self._overlay_debug(
                vis,
                boxes_kept=len(boxes),
                boxes_raw=raw_len,
                fps=fps,
                person_conf=person_conf,
                min_area=min_person_area,
                yolo_iou=yolo_iou,
                dedup_iou=dedup_iou,
            )

            with self._frame_lock:
                self.output_frame = vis

            now = time.time()
            if trig and (now - last_snap >= snap_cd):
                snap_fs = self._take_snapshot(frame)
                self._emit_intrusion(snap_fs)
                last_snap = now

            time.sleep(0.01)

        try:
            if self.cap:
                self.cap.release()
        except:
            pass
