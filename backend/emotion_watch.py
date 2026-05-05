#!/usr/bin/env python3
"""
Emotion Watch — Silent stress monitor with live visualization.
Uses MediaPipe FaceLandmarker (tasks API) with blendshapes, 100% local.
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import json
import os
import random
import sys
from collections import deque
from mediapipe.tasks.python import vision, BaseOptions
from mediapipe import Image, ImageFormat

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "face_landmarker_v2_with_blendshapes.task")
STRESS_JSON_PATH = "/tmp/banban_stress.json"
PREVIEW_IMAGE_PATH = "/tmp/banban_preview.jpg"

STRESS_THRESHOLD = 60
COOLDOWN_SECONDS = 120
CONSECUTIVE_REQUIRED = 3
CAPTURE_INTERVAL = 3
CALIBRATION_SECONDS = 12
MIN_CALIBRATION_SAMPLES = 3
WINDOW_NAME = "Emotion Watch"
PANEL_W = 300
CAM_W = 400
CAM_H = 400
TOTAL_W = CAM_W + PANEL_W

MESSAGES = {
    "brow_furrow": "Hey, things feeling a bit heavy right now? Take a slow breath — drop your shoulders, unclench your jaw. You've got this.",
    "expression_freeze": "You've been deep in it for a while. That kind of focus is great, but your brain needs air too. Two minutes away — seriously, it helps.",
    "lip_press": "Pause for a sec. Breathe in slowly through your nose... and out. Do that three times. You'll feel the difference.",
    "eye_squint": "Your eyes have been working overtime. Pick something far away and just... look at it for 20 seconds. No screen, no task. Just rest.",
}
HIGH_STRESS_MSG = "Hey — I think you need a real break right now. Not a quick stretch, a proper one. Step away for 5 minutes. You'll come back clearer, I promise."
DEFAULT_POOL = [
    "Quick check-in — when did you last drink some water? Grab a glass and step away for a moment.",
    "You've been at this for a while. Stand up, stretch it out. 60 seconds is all it takes.",
    "Take a breath. Find something far away and just look at it for a minute. Let your mind wander.",
    "Hey, how are you actually doing right now? Sometimes a short walk is the best thing you can do.",
    "Five minutes away from the screen will pay back double. You've earned a break.",
]

BLENDSHAPE_MAP = {}


def camera_backend():
    if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
        return cv2.CAP_AVFOUNDATION
    return 0


def camera_index_override():
    env_idx = os.environ.get("BANBAN_CAMERA_INDEX")
    if env_idx is not None:
        try:
            return int(env_idx)
        except ValueError:
            print(f"Ignoring invalid BANBAN_CAMERA_INDEX={env_idx!r}")

    if "--camera-index" in sys.argv:
        try:
            return int(sys.argv[sys.argv.index("--camera-index") + 1])
        except (ValueError, IndexError):
            print("Ignoring invalid --camera-index argument")
    return None


def has_continuity_camera():
    if sys.platform != "darwin":
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["system_profiler", "SPCameraDataType"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except Exception as exc:
        print(f"Camera profile unavailable: {exc}")
        return False

    text = (result.stdout + result.stderr).lower()
    return "continuity" in text or "iphone" in text or "desk view" in text


def camera_candidates():
    order = os.environ.get("BANBAN_CAMERA_ORDER")
    if order:
        try:
            return [int(part.strip()) for part in order.split(",") if part.strip()]
        except ValueError:
            print(f"Ignoring invalid BANBAN_CAMERA_ORDER={order!r}")

    # On Macs with Continuity Camera available, OpenCV often exposes the iPhone
    # at index 0 and the built-in camera after it. Try local indices first.
    if has_continuity_camera():
        return [1, 2, 3, 4, 0]
    return [0, 1, 2, 3, 4]


def probe_camera(idx):
    start = time.time()
    cap = cv2.VideoCapture(idx, camera_backend())
    open_time = time.time() - start

    if not cap.isOpened():
        cap.release()
        return None

    ret, frame = cap.read()
    if not ret or frame is None or frame.shape[0] == 0:
        cap.release()
        return None

    h, w = frame.shape[:2]
    cap.release()
    return {"idx": idx, "width": w, "height": h, "open_time": open_time}


def find_builtin_camera():
    """Find a local camera, de-prioritizing iPhone Continuity Camera."""
    override = camera_index_override()
    if override is not None:
        print(f"Using camera override index: {override}")
        return override

    for idx in camera_candidates():
        info = probe_camera(idx)
        if not info:
            continue
        print(
            f"Camera {info['idx']}: {info['width']}x{info['height']}, "
            f"open_time={info['open_time']:.2f}s"
        )
        return info["idx"]

    print("No preferred camera responded; using fallback camera index: 0")
    return 0


def build_blendshape_map(blendshapes):
    global BLENDSHAPE_MAP
    if not BLENDSHAPE_MAP:
        for i, bs in enumerate(blendshapes):
            BLENDSHAPE_MAP[bs.category_name] = i


def get_bs(blendshapes, name):
    idx = BLENDSHAPE_MAP.get(name)
    if idx is not None and idx < len(blendshapes):
        return blendshapes[idx].score
    return 0.0


SIGNAL_DEADBANDS = {
    "brow_furrow": 0.03,
    "lip_press": 0.02,
    "eye_squint": 0.03,
    "expression_freeze": 0.04,
}

SIGNAL_RANGES = {
    "brow_furrow": 0.14,
    "lip_press": 0.10,
    "eye_squint": 0.14,
    "expression_freeze": 0.14,
}

SIGNAL_WEIGHTS = {
    "brow_furrow": 0.35,
    "lip_press": 0.30,
    "eye_squint": 0.20,
    "expression_freeze": 0.15,
}


def extract_signals(blendshapes):
    build_blendshape_map(blendshapes)

    brow_down_l = get_bs(blendshapes, "browDownLeft")
    brow_down_r = get_bs(blendshapes, "browDownRight")
    brow_inner_up = get_bs(blendshapes, "browInnerUp")
    mouth_press_l = get_bs(blendshapes, "mouthPressLeft")
    mouth_press_r = get_bs(blendshapes, "mouthPressRight")
    mouth_stretch_l = get_bs(blendshapes, "mouthStretchLeft")
    mouth_stretch_r = get_bs(blendshapes, "mouthStretchRight")
    eye_squint_l = get_bs(blendshapes, "eyeSquintLeft")
    eye_squint_r = get_bs(blendshapes, "eyeSquintRight")
    jaw_open = get_bs(blendshapes, "jawOpen")
    jaw_clench_val = get_bs(blendshapes, "jawForward")
    nose_sneer_l = get_bs(blendshapes, "noseSneerLeft")
    nose_sneer_r = get_bs(blendshapes, "noseSneerRight")

    # Keep calibration features unclamped and close to MediaPipe's original
    # scale. Amplifying before calibration can saturate a neutral face and
    # remove the headroom needed to detect later changes.
    brow_raw = max((brow_down_l + brow_down_r) / 2.0, brow_inner_up * 0.8)
    lip_raw = (mouth_press_l + mouth_press_r) / 2.0
    stretch_raw = (mouth_stretch_l + mouth_stretch_r) / 2.0
    lip_tension = lip_raw + stretch_raw * 0.5 + jaw_clench_val * 0.5
    eye_raw = (eye_squint_l + eye_squint_r) / 2.0
    sneer_raw = (nose_sneer_l + nose_sneer_r) / 2.0
    eye_tension = eye_raw + sneer_raw * 0.3

    jaw_shut = max(0, 1.0 - jaw_open * 10) if jaw_open < 0.05 else 0.0
    avg_tension = (brow_raw + lip_tension + eye_tension) / 3.0
    expression_freeze = jaw_shut * 0.2 + avg_tension * 0.8

    signals = {
        "brow_furrow": round(min(1.0, brow_raw), 3),
        "lip_press": round(min(1.0, lip_tension), 3),
        "eye_squint": round(min(1.0, eye_tension), 3),
        "expression_freeze": round(min(1.0, expression_freeze), 3),
    }
    return signals


def dominant_signal(signals):
    dominant = max(signals, key=signals.get)
    if signals[dominant] < 0.3:
        dominant = "none"
    return dominant


def average_signal_samples(samples):
    if not samples:
        return dict(ZEROED_SIGNALS)
    return {
        key: round(sum(sample.get(key, 0.0) for sample in samples) / len(samples), 2)
        for key in ZEROED_SIGNALS
    }


def compute_stress(signals, baseline=None):
    if baseline:
        adjusted = {}
        for key, raw in signals.items():
            delta = max(0.0, raw - baseline.get(key, 0.0) - SIGNAL_DEADBANDS[key])
            normalized = min(1.0, delta / SIGNAL_RANGES[key])
            adjusted[key] = normalized ** 0.65

        active_count = sum(1 for value in adjusted.values() if value >= 0.25)
        weighted = sum(SIGNAL_WEIGHTS[key] * adjusted[key] for key in SIGNAL_WEIGHTS)
        max_signal = max(adjusted.values())

        if active_count <= 1:
            score_raw = max(weighted, max_signal * 0.60)
        else:
            score_raw = max(weighted * 1.15, max_signal * 0.85)

        stress_score = int(100 * min(1.0, score_raw))
        return min(100, max(0, stress_score)), {
            key: round(value, 2) for key, value in adjusted.items()
        }, dominant_signal(adjusted)

    weighted = sum(SIGNAL_WEIGHTS[key] * signals[key] for key in SIGNAL_WEIGHTS)
    max_signal = max(signals.values())
    stress_score = int(100 * max(weighted, max_signal * 0.45))
    stress_score = min(100, max(0, stress_score))

    return stress_score, signals, dominant_signal(signals)


def mosaic_with_face_reveal(frame, landmarks, padding=0.3, mosaic_factor=20):
    """Full frame with heavy mosaic everywhere except the face region."""
    h, w = frame.shape[:2]
    xs = [lm.x * w for lm in landmarks]
    ys = [lm.y * h for lm in landmarks]
    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))

    face_w = x_max - x_min
    face_h = y_max - y_min
    pad_x = int(face_w * padding)
    pad_y = int(face_h * padding)

    x_min = max(0, x_min - pad_x)
    x_max = min(w, x_max + pad_x)
    y_min = max(0, y_min - pad_y)
    y_max = min(h, y_max + pad_y)

    # Create mosaic version of entire frame
    small = cv2.resize(frame, (w // mosaic_factor, h // mosaic_factor), interpolation=cv2.INTER_LINEAR)
    mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

    # Create elliptical mask for face region
    mask = np.zeros((h, w), dtype=np.uint8)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    rx = (x_max - x_min) // 2
    ry = (y_max - y_min) // 2
    cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)

    # Feather the edge for smooth transition
    mask = cv2.GaussianBlur(mask, (31, 31), 10)
    mask_3ch = cv2.merge([mask, mask, mask]).astype(np.float32) / 255.0

    # Blend: face area = original, rest = mosaic
    result = (frame.astype(np.float32) * mask_3ch + mosaic.astype(np.float32) * (1.0 - mask_3ch)).astype(np.uint8)
    return result


def select_message(stress_score, dominant):
    if stress_score >= 80:
        return HIGH_STRESS_MSG
    if dominant in MESSAGES:
        return MESSAGES[dominant]
    return random.choice(DEFAULT_POOL)


def draw_signal_bar(panel, x, y, w, val, color):
    bar_h = 8
    cv2.rectangle(panel, (x, y), (x + w, y + bar_h), (50, 50, 50), -1)
    fill = int(w * min(1.0, val))
    if fill > 0:
        cv2.rectangle(panel, (x, y), (x + fill, y + bar_h), color, -1)
    return y + bar_h + 4


def stress_color(score):
    if score >= 80:
        return (70, 70, 255)
    elif score >= 60:
        return (60, 180, 255)
    elif score >= 40:
        return (60, 230, 230)
    return (80, 220, 120)


def wrap_text(text, max_chars=32):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        test = line + " " + word if line else word
        if len(test) > max_chars:
            if line:
                lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def build_panel(h, stress_score, signals, dominant, message, has_face, consecutive, cooldown_remaining):
    panel = np.zeros((h, PANEL_W, 3), dtype=np.uint8)
    panel[:] = (25, 25, 30)

    x0 = 15
    y = 30

    # Title
    cv2.putText(panel, "EMOTION WATCH", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 220, 255), 2)

    # Status
    y += 30
    status_color = (80, 220, 120) if has_face else (70, 70, 255)
    status_text = "Face Detected" if has_face else "No Face"
    cv2.circle(panel, (x0 + 5, y - 4), 5, status_color, -1)
    cv2.putText(panel, status_text, (x0 + 18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)

    if not has_face:
        y += 30
        cv2.putText(panel, "Waiting for face...", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
        return panel

    # Stress score
    y += 25
    cv2.putText(panel, "STRESS", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (130, 130, 130), 1)
    y += 5

    sc = stress_color(stress_score)
    cv2.putText(panel, str(stress_score), (x0, y + 35), cv2.FONT_HERSHEY_SIMPLEX, 1.4, sc, 3)
    cv2.putText(panel, "/ 100", (x0 + 60, y + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
    y += 42

    # Stress bar
    bar_w = PANEL_W - 30
    bar_h = 10
    cv2.rectangle(panel, (x0, y), (x0 + bar_w, y + bar_h), (50, 50, 50), -1)
    fill_w = int(bar_w * stress_score / 100)
    if fill_w > 0:
        cv2.rectangle(panel, (x0, y), (x0 + fill_w, y + bar_h), sc, -1)
    y += bar_h + 15

    # Divider
    cv2.line(panel, (x0, y), (PANEL_W - 15, y), (50, 50, 50), 1)
    y += 12

    # Signals
    cv2.putText(panel, "SIGNALS", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (130, 130, 130), 1)
    y += 14

    signal_labels = {
        "brow_furrow": "Brow",
        "lip_press": "Lip",
        "eye_squint": "Eye",
        "expression_freeze": "Freeze",
    }
    bar_w = PANEL_W - 90
    for key, label in signal_labels.items():
        val = signals.get(key, 0)
        is_dom = (key == dominant)
        color = (100, 220, 255) if is_dom else (120, 120, 120)
        cv2.putText(panel, f"{label}", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)
        cv2.putText(panel, f"{val:.2f}", (PANEL_W - 50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
        y += 4
        y = draw_signal_bar(panel, x0 + 50, y, bar_w - 20, val, color)
        y += 2

    # Consecutive + cooldown
    y += 8
    cv2.line(panel, (x0, y), (PANEL_W - 15, y), (50, 50, 50), 1)
    y += 14
    cv2.putText(panel, f"Streak: {consecutive}/{CONSECUTIVE_REQUIRED}", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 120), 1)
    y += 18
    if cooldown_remaining > 0:
        cv2.putText(panel, f"Cooldown: {cooldown_remaining}s", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (60, 180, 255), 1)
        y += 18

    # Alert message
    if message:
        y += 5
        cv2.line(panel, (x0, y), (PANEL_W - 15, y), (70, 70, 255), 1)
        y += 14
        cv2.putText(panel, "ALERT", (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (70, 70, 255), 2)
        y += 18
        for line in wrap_text(message):
            cv2.putText(panel, line, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 255), 1)
            y += 15

    return panel


ZEROED_SIGNALS = {"brow_furrow": 0.0, "lip_press": 0.0, "eye_squint": 0.0, "expression_freeze": 0.0}


def write_preview(frame):
    preview = cv2.resize(frame, (480, 360))
    cv2.imwrite(PREVIEW_IMAGE_PATH, preview, [int(cv2.IMWRITE_JPEG_QUALITY), 82])


def clear_preview():
    try:
        os.unlink(PREVIEW_IMAGE_PATH)
    except FileNotFoundError:
        pass


def write_stress_data(
    stress_score,
    signals,
    face_detected,
    camera_blocked,
    calibration_state="ready",
    calibration_progress=1.0,
    baseline=None,
    raw_signals=None,
):
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stress_score": stress_score,
        "signals": signals,
        "face_detected": face_detected,
        "camera_blocked": camera_blocked,
        "calibration": {
            "state": calibration_state,
            "progress": round(calibration_progress, 2),
            "baseline": baseline,
            "raw_signals": raw_signals,
        },
    }
    with open(STRESS_JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)


def write_alert(message, stress_score, signals):
    alert = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stress_score": stress_score,
        "signals": signals,
        "message": message,
    }
    with open(STRESS_JSON_PATH, "w") as f:
        json.dump(alert, f, indent=2)
    print(f"\n{'='*50}")
    print(f"STRESS ALERT (score: {stress_score})")
    print(f"Message: {message}")
    print(f"Signals: {json.dumps(signals)}")
    print(f"{'='*50}\n")


def main():
    headless = '--headless' in sys.argv

    print("Scanning cameras...")
    cam_idx = find_builtin_camera()
    print(f"Using camera index: {cam_idx}")

    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=False,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        running_mode=vision.RunningMode.IMAGE,
    )
    landmarker = vision.FaceLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(cam_idx, camera_backend())
    if not cap.isOpened():
        print("ERROR: Cannot open camera")
        clear_preview()
        write_stress_data(0, dict(ZEROED_SIGNALS), False, True, calibration_state="waiting")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    consecutive = 0
    last_alert_time = 0
    current_message = None
    message_display_until = 0
    stress_history = deque(maxlen=5)
    last_analysis_time = 0
    last_signals = {"brow_furrow": 0, "lip_press": 0, "eye_squint": 0, "expression_freeze": 0}
    last_dominant = "none"
    last_has_face = False
    last_stress = 0
    face_crop = None
    calibration_start = time.time()
    calibration_samples = []
    baseline_signals = None

    if not headless:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    print(
        f"Emotion Watch started{' (headless)' if headless else ''}. "
        f"Hold a relaxed, neutral face for {CALIBRATION_SECONDS}s. Press Ctrl+C to quit."
    )

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        now = time.time()

        if now - last_analysis_time >= CAPTURE_INTERVAL:
            last_analysis_time = now

            # Camera blocked detection: very low average brightness means lens is covered
            brightness = np.mean(frame)
            if brightness < 10:
                last_has_face = False
                stress_history.clear()
                consecutive = 0
                face_crop = None
                clear_preview()
                write_stress_data(
                    0,
                    dict(ZEROED_SIGNALS),
                    False,
                    True,
                    calibration_state="waiting" if baseline_signals is None else "ready",
                    baseline=baseline_signals,
                )
            else:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_image)

                if result.face_blendshapes and len(result.face_blendshapes) > 0:
                    last_has_face = True
                    blendshapes = result.face_blendshapes[0]
                    raw_signals = extract_signals(blendshapes)

                    if baseline_signals is None:
                        calibration_samples.append(raw_signals)
                        elapsed = now - calibration_start
                        progress = min(1.0, elapsed / CALIBRATION_SECONDS)
                        if elapsed >= CALIBRATION_SECONDS and len(calibration_samples) >= MIN_CALIBRATION_SAMPLES:
                            baseline_signals = average_signal_samples(calibration_samples)
                            print(f"Calibration baseline: {json.dumps(baseline_signals)}")
                        else:
                            remaining = max(0, int(CALIBRATION_SECONDS - elapsed))
                            last_stress = 0
                            last_signals = dict(ZEROED_SIGNALS)
                            last_dominant = "none"
                            stress_history.clear()
                            consecutive = 0

                            if result.face_landmarks and len(result.face_landmarks) > 0:
                                face_crop = mosaic_with_face_reveal(frame, result.face_landmarks[0])
                                write_preview(face_crop)

                            write_stress_data(
                                0,
                                dict(ZEROED_SIGNALS),
                                True,
                                False,
                                calibration_state="calibrating",
                                calibration_progress=progress,
                                baseline=None,
                                raw_signals=raw_signals,
                            )
                            print(f"Calibrating neutral face: {remaining}s remaining")
                            continue

                    stress_score, signals, dominant = compute_stress(raw_signals, baseline_signals)
                    last_stress = stress_score
                    last_signals = signals
                    last_dominant = dominant
                    stress_history.append(stress_score)

                    # Mosaic background, reveal face only
                    if result.face_landmarks and len(result.face_landmarks) > 0:
                        face_crop = mosaic_with_face_reveal(frame, result.face_landmarks[0])
                        write_preview(face_crop)

                    avg_stress = int(sum(stress_history) / len(stress_history))
                    cooldown_remaining = max(0, int(COOLDOWN_SECONDS - (now - last_alert_time)))

                    write_stress_data(
                        stress_score,
                        signals,
                        True,
                        False,
                        calibration_state="ready",
                        calibration_progress=1.0,
                        baseline=baseline_signals,
                        raw_signals=raw_signals,
                    )

                    if avg_stress >= STRESS_THRESHOLD and cooldown_remaining == 0:
                        consecutive += 1
                        if consecutive >= CONSECUTIVE_REQUIRED:
                            current_message = select_message(avg_stress, dominant)
                            message_display_until = now + 10
                            last_alert_time = now
                            consecutive = 0
                            write_alert(current_message, avg_stress, signals)
                    else:
                        if avg_stress < STRESS_THRESHOLD:
                            consecutive = 0
                else:
                    last_has_face = False
                    stress_history.clear()
                    consecutive = 0
                    face_crop = None
                    clear_preview()
                    if baseline_signals is None:
                        calibration_start = now
                        calibration_samples.clear()
                    write_stress_data(
                        0,
                        dict(ZEROED_SIGNALS),
                        False,
                        False,
                        calibration_state="waiting" if baseline_signals is None else "ready",
                        baseline=baseline_signals,
                    )

        if now > message_display_until:
            current_message = None

        if headless:
            # Headless mode: just sleep until next cycle, no UI
            time.sleep(0.1)
            continue

        cooldown_remaining = max(0, int(COOLDOWN_SECONDS - (now - last_alert_time)))
        avg_stress = int(sum(stress_history) / len(stress_history)) if stress_history else 0

        # Left side: face crop only (privacy)
        if face_crop is not None:
            cam_display = cv2.resize(face_crop, (CAM_W, CAM_H))
        else:
            cam_display = np.zeros((CAM_H, CAM_W, 3), dtype=np.uint8)
            cv2.putText(cam_display, "No Face", (CAM_W // 2 - 60, CAM_H // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 80), 2)

        # Right side: panel
        panel = build_panel(
            CAM_H, avg_stress, last_signals, last_dominant,
            current_message, last_has_face, consecutive, cooldown_remaining
        )

        combined = np.hstack([cam_display, panel])
        cv2.imshow(WINDOW_NAME, combined)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        try:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
        except cv2.error:
            break

    cap.release()
    cv2.destroyAllWindows()
    clear_preview()
    landmarker.close()
    print("Emotion Watch stopped.")


if __name__ == "__main__":
    main()
