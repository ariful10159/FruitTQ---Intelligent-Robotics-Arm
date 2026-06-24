"""
calibration.py
Servo calibration interactive tool।
প্রথমবার run করলে সব servo এর সঠিক position খুঁজে নেওয়া যাবে।
keyboard দিয়ে fine-tune করো, তারপর save করো।
"""

import os
os.environ["BLINKA_RASPBERRY_PI5"] = "1"

import sys
import time
from servo_control import (
    ServoController,
    SERVO_CONFIG,
    ACTIVE_CHANNELS,
    CH_BASE, CH_ELBOW, CH_WRIST_V, CH_WRIST_R, CH_GRIPPER
)

def run_calibration():
    ctrl = ServoController()

    print("\n" + "="*55)
    print("  SERVO CALIBRATION TOOL")
    print("="*55)
    print("প্রতিটা servo এর জন্য:")
    print("  '+' চাপো → angle বাড়াও (+1°)")
    print("  '-' চাপো → angle কমাও (-1°)")
    print("  's' চাপো → এই channel save করে পরেরটায় যাও")
    print("  'q' চাপো → quit without save")
    print("="*55 + "\n")

    # Prompt: সব servo আগে 90° এ নিয়ে যাবে কি?
    answer = input("সব servo কে 90° এ নিয়ে যাই? (y/n): ").strip().lower()
    if answer == 'y':
        for ch in ACTIVE_CHANNELS:
            ctrl.set_angle_instant(ch, 90)
        print("সব servo 90° এ আছে। Physical position দেখো।\n")
        time.sleep(2)

    offsets = {}

    for ch in ACTIVE_CHANNELS:
        cfg  = SERVO_CONFIG[ch]
        name = cfg["name"]
        print(f"\n── Channel {ch}: {name} ({cfg['type']}) ──")
        print(f"   Range: {cfg['min_ang']}° ~ {cfg['max_ang']}°")
        print(f"   Default: {cfg['default']}°")

        current = cfg["default"]
        ctrl.set_angle_instant(ch, current)
        time.sleep(0.5)

        print(f"   Current angle: {current}°")
        print("   '+'/'-' দিয়ে adjust করো, 's' দিয়ে save করো:\n")

        while True:
            key = input(f"   [{name}] angle={current}° → (+/-/s/q): ").strip().lower()

            if key == '+':
                current = min(cfg["max_ang"], current + 1)
                ctrl.set_angle_instant(ch, current)

            elif key == '-':
                current = max(cfg["min_ang"], current - 1)
                ctrl.set_angle_instant(ch, current)

            elif key == 'S' or key == 's':
                offset = current - cfg["default"]
                offsets[ch] = offset
                ctrl.set_offset(ch, offset)
                print(f"   ✅ {name}: offset = {offset:+d}° saved.")
                break

            elif key == 'q':
                print("\n[Calibration] Quit — কিছু save হয়নি।")
                ctrl.deinit()
                sys.exit(0)

            elif key.lstrip('-').isdigit():
                # সরাসরি angle দেওয়া যাবে
                val = int(key)
                current = max(cfg["min_ang"], min(cfg["max_ang"], val))
                ctrl.set_angle_instant(ch, current)
                print(f"   → angle set to {current}°")

    # Save
    ctrl.save_calibration()
    print("\n" + "="*55)
    print("  Calibration complete!")
    print("  calibration.json ফাইলে save হয়েছে।")
    print("="*55)

    # Verify
    print("\n[Verify] সব servo Home position এ যাচ্ছে...")
    ctrl.go_home()
    time.sleep(2)

    ctrl.deinit()
    print("[Done] Calibration শেষ।")


def quick_test():
    """Calibration ছাড়া quick servo sweep test"""
    ctrl = ServoController()
    print("\n[Quick Test] প্রতিটা servo 45° → 90° → 45° করবে\n")

    for ch in ACTIVE_CHANNELS:
        name = SERVO_CONFIG[ch]["name"]
        print(f"Testing {name} (CH{ch})...")
        ctrl.set_angle_smooth(ch, 45)
        time.sleep(0.5)
        ctrl.set_angle_smooth(ch, 90)
        time.sleep(0.5)
        ctrl.set_angle_smooth(ch, 45)
        time.sleep(0.3)
        print(f"  ✅ {name} OK")

    ctrl.go_home()
    ctrl.deinit()
    print("[Quick Test] Done!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        quick_test()
    else:
        run_calibration()
