"""
main.py
Autonomous Robotic Arm — Main Control Loop

Flow:
Camera → Color Detect → Position → Move Arm → Grip → Rotate → Drop

Controls (keyboard):
  'q' → quit
  'r' → reset / drop ball
  'p' → pause/resume
  '1' → target RED only
  '2' → target GREEN only
  '3' → target BLUE only
  '0' → target ANY color
"""

import os
os.environ["BLINKA_RASPBERRY_PI5"] = "1"

import cv2
import time
import sys

from camera           import IPCamera
from color_detection  import detect_objects, draw_detections, get_frame_position, estimate_distance_by_area
from servo_control    import ServoController, CH_BASE, CH_ELBOW, CH_WRIST_V, CH_WRIST_R, CH_GRIPPER
from arm_kinematics   import position_to_angles, is_reachable

# =====================
# Config
# =====================
CAMERA_URL       = "http://172.20.10.3:8080/video"
TARGET_COLORS    = ["red", "green", "blue"]   # সব color target
DROP_BASE_ANGLE  = 170    # Ball drop করার জন্য base angle
HOME_BASE_ANGLE  = 90     # Home position

# Pickup sequence timing (seconds)
T_APPROACH   = 1.5   # arm position এ পৌঁছাতে সময়
T_LOWER      = 1.0   # wrist নামাতে সময়
T_GRIP       = 1.2   # gripper close হতে সময়
T_LIFT       = 1.0   # উঁচু করতে সময়
T_ROTATE     = 1.5   # rotate করতে সময়
T_DROP       = 0.8   # drop করতে সময়
T_RETURN     = 1.5   # home ফিরতে সময়

# Detection stability
DETECT_CONFIRM_FRAMES = 8   # N frame detect হলে তবেই pickup


# =====================
# State Machine
# =====================
class State:
    SEARCHING  = "SEARCHING"
    TRACKING   = "TRACKING"
    PICKING    = "PICKING"
    HOLDING    = "HOLDING"
    DROPPING   = "DROPPING"
    RETURNING  = "RETURNING"
    PAUSED     = "PAUSED"


def run():
    # ── Init ──────────────────────────────────────
    print("\n" + "="*55)
    print("  AUTONOMOUS ROBOTIC ARM")
    print("="*55)

    ctrl   = ServoController()
    camera = IPCamera(CAMERA_URL)

    try:
        camera.start()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        ctrl.deinit()
        sys.exit(1)

    # Startup
    print("[INIT] Home position এ যাচ্ছি...")
    ctrl.go_home()
    ctrl.gripper_open()
    time.sleep(1)

    # ── State variables ────────────────────────────
    state           = State.SEARCHING
    target_color    = None
    detect_count    = 0
    last_detection  = None
    target_filter   = TARGET_COLORS   # কোন color target করবে
    paused_state    = None

    print(f"\n[READY] Searching for: {target_filter}")
    print("Controls: q=quit  r=reset  p=pause  1=red  2=green  3=blue  0=all\n")

    # ── Main Loop ─────────────────────────────────
    while True:
        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        fh, fw = frame.shape[:2]
        detections = detect_objects(frame)

        # Filter by target color
        detections = [d for d in detections if d["color"] in target_filter]

        # Draw
        display = draw_detections(frame.copy(), detections)

        # State label
        cv2.putText(display, f"STATE: {state}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2)
        if target_filter != TARGET_COLORS:
            cv2.putText(display, f"TARGET: {target_filter}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2)

        # ── PAUSED ────────────────────────────────
        if state == State.PAUSED:
            cv2.putText(display, "PAUSED — press 'p' to resume",
                        (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (0, 200, 255), 2)

        # ── SEARCHING ─────────────────────────────
        elif state == State.SEARCHING:
            cv2.putText(display, "Searching...",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (100, 100, 255), 2)
            detect_count = 0

            if detections:
                best        = detections[0]
                state       = State.TRACKING
                target_color = best["color"]
                print(f"\n[FOUND] {target_color.upper()} ball detected! Tracking...")

        # ── TRACKING ──────────────────────────────
        elif state == State.TRACKING:
            if not detections:
                detect_count = max(0, detect_count - 1)
                if detect_count == 0:
                    print("[LOST] Ball হারিয়ে গেছে। Searching...")
                    state = State.SEARCHING
                continue

            # Target color এর detection নাও
            det = next(
                (d for d in detections if d["color"] == target_color),
                detections[0]
            )
            last_detection = det

            cx, cy = det["cx"], det["cy"]
            norm_x, norm_y = get_frame_position(cx, cy, fw, fh)
            dist = estimate_distance_by_area(det["area"])
            dist = dist if dist else 20.0

            # Reachable check
            if not is_reachable(norm_x, norm_y):
                cv2.putText(display, "OUT OF REACH",
                            (10, 80), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, (0, 0, 255), 2)
            else:
                # Arm কে track করাও (live follow)
                angles = position_to_angles(norm_x, norm_y, dist)
                ctrl.move_all_smooth(angles, delay=0.008)

                detect_count += 1
                cv2.putText(display,
                            f"Tracking {target_color} | dist~{dist}cm | confirm {detect_count}/{DETECT_CONFIRM_FRAMES}",
                            (10, 55), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 255, 100), 2)

                if detect_count >= DETECT_CONFIRM_FRAMES:
                    print(f"[CONFIRM] Ball confirmed at ({cx},{cy}). Picking up...")
                    state = State.PICKING

        # ── PICKING ───────────────────────────────
        elif state == State.PICKING:
            det = last_detection
            if det is None:
                state = State.SEARCHING
                continue

            cx, cy = det["cx"], det["cy"]
            norm_x, norm_y = get_frame_position(cx, cy, fw, fh)
            dist = estimate_distance_by_area(det["area"]) or 20.0

            print("[PICK] Step 1: Final position adjust...")
            angles = position_to_angles(norm_x, norm_y, dist)
            ctrl.move_all_smooth(angles, delay=0.012)
            time.sleep(T_APPROACH)

            print("[PICK] Step 2: Wrist নামাচ্ছি...")
            ctrl.set_angle_smooth(CH_WRIST_V, 130)
            time.sleep(T_LOWER)

            print("[PICK] Step 3: Gripper বন্ধ করছি...")
            ctrl.gripper_close()
            time.sleep(T_GRIP)

            print("[PICK] Step 4: Arm উঁচু করছি...")
            ctrl.set_angle_smooth(CH_ELBOW,   50)
            ctrl.set_angle_smooth(CH_WRIST_V, 90)
            time.sleep(T_LIFT)

            state = State.HOLDING
            print("[HOLD] Ball ধরা হয়েছে!")

        # ── HOLDING ───────────────────────────────
        elif state == State.HOLDING:
            cv2.putText(display, f"HOLDING {target_color} ball | 'r' to drop",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 255), 2)
            # Auto drop এর জন্য timer চাইলে এখানে add করো
            # এখন 'r' key দিয়ে manually drop করতে হবে

        # ── DROPPING ──────────────────────────────
        elif state == State.DROPPING:
            print("[DROP] Step 1: অন্যদিকে rotate করছি...")
            ctrl.set_angle_smooth(CH_BASE, DROP_BASE_ANGLE)
            time.sleep(T_ROTATE)

            print("[DROP] Step 2: Ball ছাড়ছি...")
            ctrl.gripper_open()
            time.sleep(T_DROP)

            state = State.RETURNING

        # ── RETURNING ─────────────────────────────
        elif state == State.RETURNING:
            print("[RETURN] Home position এ ফিরছি...")
            ctrl.go_home()
            time.sleep(T_RETURN)
            detect_count  = 0
            last_detection = None
            state = State.SEARCHING
            print("[READY] আবার searching শুরু...\n")

        # ── Display ───────────────────────────────
        cv2.imshow("Robotic Arm — Autonomous", display)

        # ── Key Controls ──────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("\n[EXIT] Quit করছি...")
            break

        elif key == ord('r'):
            if state == State.HOLDING:
                state = State.DROPPING
            elif state in (State.TRACKING, State.PICKING):
                print("[RESET] Abort — Home এ ফিরছি...")
                ctrl.go_home()
                ctrl.gripper_open()
                state = State.SEARCHING

        elif key == ord('p'):
            if state == State.PAUSED:
                state = paused_state
                print(f"[RESUME] State: {state}")
            else:
                paused_state = state
                state        = State.PAUSED
                print("[PAUSE]")

        elif key == ord('1'):
            target_filter = ["red"]
            state = State.SEARCHING
            print("[FILTER] Target: RED only")

        elif key == ord('2'):
            target_filter = ["green"]
            state = State.SEARCHING
            print("[FILTER] Target: GREEN only")

        elif key == ord('3'):
            target_filter = ["blue"]
            state = State.SEARCHING
            print("[FILTER] Target: BLUE only")

        elif key == ord('0'):
            target_filter = TARGET_COLORS
            state = State.SEARCHING
            print("[FILTER] Target: ALL colors")

    # ── Cleanup ───────────────────────────────────
    camera.stop()
    cv2.destroyAllWindows()
    ctrl.go_home()
    ctrl.gripper_open()
    time.sleep(0.5)
    ctrl.deinit()
    print("[DONE] Program শেষ।")


if __name__ == "__main__":
    run()
