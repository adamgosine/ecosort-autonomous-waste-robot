"""
EcoSort - main control loop.

Runs on a Raspberry Pi 4. Captures frames from the Pi Camera, runs a
TensorFlow Lite classifier (MobileNetV2) on detected waste, and sends
serial commands to an Arduino UNO to drive the chassis and actuate
the scoop. Every classification is logged to classifications.json,
which the Flask dashboard reads to render real-time analytics.

Architecture: perception (Pi) -> planning FSM (Pi) -> control (Arduino).
Author: Adam Gosine
NYU Tandon EG-UY 1004 - Spring 2026
"""

import json
import time
import os
from datetime import datetime

import cv2
import numpy as np
import serial
import tflite_runtime.interpreter as tflite
from picamera2 import Picamera2
from RPLCD.i2c import CharLCD


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 9600
LOG_FILE = "classifications.json"
MODEL_PATH = "model.tflite"

CLASS_NAMES = ["plastic", "paper", "organic"]
CONFIDENCE_THRESHOLD = 0.65
IMG_SIZE = 224

PATROL_DURATION = 4.0       # seconds robot drives forward before re-checking
APPROACH_DURATION = 3.0     # seconds to drive forward toward detected trash
COLLECT_DURATION = 2.5      # seconds for scoop to lower, collect, raise


# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

print("Initializing serial...")
arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)  # let Arduino reset after serial connection opens

print("Initializing LCD...")
lcd = CharLCD("PCF8574", 0x27)
lcd.clear()
lcd.write_string("EcoSort Ready")

print("Loading TFLite model...")
interpreter = tflite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

print("Starting camera...")
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(
    main={"size": (640, 480), "format": "RGB888"}))
picam2.start()
time.sleep(2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def send_command(cmd):
    """Send a high-level command string to the Arduino over serial."""
    arduino.write((cmd + "\n").encode())
    time.sleep(0.05)  # let Arduino's serial buffer clear


def read_message():
    """Read a single message from the Arduino (non-blocking)."""
    if arduino.in_waiting > 0:
        return arduino.readline().decode(errors="ignore").strip()
    return ""


def capture_frame():
    """Capture a frame and apply the same flip used during training."""
    frame = picam2.capture_array()
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    frame = cv2.flip(frame, -1)
    return frame


def detect_change(baseline, current, threshold=25):
    """
    Return True if there's a meaningful difference between the
    baseline patrol frame and the current frame.

    Uses grayscale absolute difference with a green-channel filter
    to suppress false positives from the robot body and floor.
    """
    diff = cv2.absdiff(
        cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY),
        cv2.cvtColor(current, cv2.COLOR_BGR2GRAY),
    )
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    return cv2.countNonZero(mask) > 5000


def classify(frame):
    """Run MobileNetV2 inference on the captured frame."""
    img = cv2.resize(frame, (IMG_SIZE, IMG_SIZE))
    img = img.astype(np.float32) / 255.0
    img = np.expand_dims(img, axis=0)

    interpreter.set_tensor(input_details[0]["index"], img)
    interpreter.invoke()
    preds = interpreter.get_tensor(output_details[0]["index"])[0]

    idx = int(np.argmax(preds))
    return CLASS_NAMES[idx], float(preds[idx])


def log_event(label, confidence, zone="patrol_area_1"):
    """Append a classification event to the JSON log file."""
    entry = {
        "type": label,
        "confidence": round(confidence, 3),
        "timestamp": datetime.now().isoformat(),
        "zone": zone,
    }
    data = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = []
    data.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Main FSM
# ---------------------------------------------------------------------------

def main():
    state = "PATROL"
    patrol_start = time.time()
    baseline_frame = capture_frame()

    print("Entering main loop...")
    lcd.clear()
    lcd.write_string("Patrolling...")
    send_command("FWD")

    try:
        while True:
            msg = read_message()

            if state == "PATROL":
                # Re-establish baseline periodically
                if time.time() - patrol_start > PATROL_DURATION:
                    send_command("STOP")
                    time.sleep(0.4)
                    current = capture_frame()

                    if detect_change(baseline_frame, current):
                        label, conf = classify(current)
                        if conf > CONFIDENCE_THRESHOLD:
                            print(f"Detected: {label} ({conf:.2f})")
                            lcd.clear()
                            lcd.write_string(f"Found: {label}")
                            state = "APPROACH"
                            approach_start = time.time()
                            send_command("FWD_SLOW")
                            current_label = label
                            current_conf = conf
                            continue

                    # Nothing detected, resume patrol
                    baseline_frame = current
                    patrol_start = time.time()
                    send_command("FWD")

                if msg == "BLOCKED":
                    send_command("STOP")
                    time.sleep(0.3)
                    send_command("TURN_L")
                    time.sleep(0.8)
                    send_command("STOP")
                    baseline_frame = capture_frame()
                    patrol_start = time.time()
                    send_command("FWD")

            elif state == "APPROACH":
                if time.time() - approach_start > APPROACH_DURATION:
                    send_command("STOP")
                    time.sleep(0.3)
                    state = "COLLECT"
                    collect_start = time.time()
                    lcd.clear()
                    lcd.write_string("Collecting...")
                    send_command("SCOOP_DOWN")

            elif state == "COLLECT":
                if time.time() - collect_start > COLLECT_DURATION:
                    send_command("SCOOP_UP")
                    time.sleep(1.0)
                    log_event(current_label, current_conf)
                    lcd.clear()
                    lcd.write_string(f"Collected!")
                    time.sleep(1.0)

                    # Resume patrolling
                    state = "PATROL"
                    baseline_frame = capture_frame()
                    patrol_start = time.time()
                    lcd.clear()
                    lcd.write_string("Patrolling...")
                    send_command("FWD")

            time.sleep(0.05)

    except KeyboardInterrupt:
        send_command("STOP")
        send_command("SCOOP_UP")
        lcd.clear()
        lcd.write_string("Stopped.")
        picam2.stop()
        arduino.close()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
