"""
servo_control.py
PCA9685 দিয়ে সব servo control করার module।
MG995 এবং SG90 দুটোর জন্যই কাজ করে।
CH1 (Shoulder) intentionally skip করা হয়েছে।
"""

import os
os.environ["BLINKA_RASPBERRY_PI5"] = "1"

import board
import busio
from adafruit_pca9685 import PCA9685
import time
import json

# =====================
# Channel Config
# =====================
CH_BASE    = 0   # MG995 → Base left/right
# CH1 SKIP  → Shoulder (damaged)
CH_ELBOW   = 2   # MG995 → Elbow up/down
CH_WRIST_V = 3   # SG90  → Wrist up/down
CH_WRIST_R = 4   # SG90  → Wrist rotate
CH_GRIPPER = 5   # SG90  → Gripper open/close

ACTIVE_CHANNELS = [CH_BASE, CH_ELBOW, CH_WRIST_V, CH_WRIST_R, CH_GRIPPER]

# =====================
# Servo Limits (Safe)
# MG995: pulse 500-2500us
# SG90:  pulse 500-2400us
# 50Hz → period 20ms
# duty = pulse/20000 * 65535
# =====================
SERVO_CONFIG = {
    CH_BASE: {
        "name"   : "Base",
        "type"   : "MG995",
        "min_us" : 500,
        "max_us" : 2500,
        "min_ang": 0,
        "max_ang": 180,
        "default": 90,   # center
        "speed"  : 2,    # degree per step
    },
    CH_ELBOW: {
        "name"   : "Elbow",
        "type"   : "MG995",
        "min_us" : 500,
        "max_us" : 2500,
        "min_ang": 20,   # physical limit
        "max_ang": 160,
        "default": 90,
        "speed"  : 2,
    },
    CH_WRIST_V: {
        "name"   : "Wrist_Vertical",
        "type"   : "SG90",
        "min_us" : 500,
        "max_us" : 2400,
        "min_ang": 0,
        "max_ang": 180,
        "default": 90,
        "speed"  : 3,
    },
    CH_WRIST_R: {
        "name"   : "Wrist_Rotate",
        "type"   : "SG90",
        "min_us" : 500,
        "max_us" : 2400,
        "min_ang": 0,
        "max_ang": 180,
        "default": 90,
        "speed"  : 3,
    },
    CH_GRIPPER: {
        "name"   : "Gripper",
        "type"   : "SG90",
        "min_us" : 500,
        "max_us" : 2400,
        "min_ang": 0,
        "max_ang": 90,
        "default": 0,    # open
        "speed"  : 5,
    },
}

GRIPPER_OPEN  = 0
GRIPPER_CLOSE = 80

CALIB_FILE = "calibration.json"


class ServoController:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = PCA9685(i2c)
        self.pca.frequency = 50
        self.current_angles = {}
        self.calibration = self._load_calibration()
        print("[ServoController] PCA9685 ready.")

    # ─── PWM Calculation ───────────────────────────
    def _us_to_duty(self, ch, pulse_us):
        """Microsecond pulse → 16-bit duty cycle"""
        cfg = SERVO_CONFIG[ch]
        pulse_us = max(cfg["min_us"], min(cfg["max_us"], pulse_us))
        return int(pulse_us / 20000 * 0xFFFF)

    def _angle_to_us(self, ch, angle):
        """Angle → microsecond pulse (calibration offset dahle)"""
        cfg = SERVO_CONFIG[ch]
        offset = self.calibration.get(str(ch), {}).get("offset", 0)
        angle  = max(cfg["min_ang"], min(cfg["max_ang"], angle + offset))
        ratio  = (angle - cfg["min_ang"]) / (cfg["max_ang"] - cfg["min_ang"])
        return int(cfg["min_us"] + ratio * (cfg["max_us"] - cfg["min_us"]))

    # ─── Core Set ──────────────────────────────────
    def set_angle_instant(self, ch, angle):
        """Instant move — calibration ছাড়া use করো না"""
        if ch not in ACTIVE_CHANNELS:
            return
        cfg  = SERVO_CONFIG[ch]
        angle = max(cfg["min_ang"], min(cfg["max_ang"], angle))
        duty  = self._us_to_duty(ch, self._angle_to_us(ch, angle))
        self.pca.channels[ch].duty_cycle = duty
        self.current_angles[ch] = angle

    def set_angle_smooth(self, ch, target, delay=0.015):
        """Smooth move — current থেকে target এ ধীরে ধীরে যাবে"""
        if ch not in ACTIVE_CHANNELS:
            return
        cfg     = SERVO_CONFIG[ch]
        current = self.current_angles.get(ch, cfg["default"])
        step    = cfg["speed"]
        if current < target:
            angles = range(int(current), int(target) + 1, step)
        else:
            angles = range(int(current), int(target) - 1, -step)
        for a in angles:
            self.set_angle_instant(ch, a)
            time.sleep(delay)
        self.set_angle_instant(ch, target)

    # ─── Multi-servo ───────────────────────────────
    def move_all_smooth(self, targets: dict, delay=0.015):
        """
        একসাথে একাধিক servo smooth move।
        targets = {CH_BASE: 90, CH_ELBOW: 45, ...}
        """
        cfg_map = {
            ch: {
                "current": self.current_angles.get(ch, SERVO_CONFIG[ch]["default"]),
                "target" : targets[ch],
                "step"   : SERVO_CONFIG[ch]["speed"],
                "done"   : False,
            }
            for ch in targets if ch in ACTIVE_CHANNELS
        }
        while not all(v["done"] for v in cfg_map.values()):
            for ch, info in cfg_map.items():
                if info["done"]:
                    continue
                cur = info["current"]
                tgt = info["target"]
                stp = info["step"]
                if abs(cur - tgt) <= stp:
                    info["current"] = tgt
                    info["done"]    = True
                elif cur < tgt:
                    info["current"] += stp
                else:
                    info["current"] -= stp
                self.set_angle_instant(ch, info["current"])
            time.sleep(delay)

    # ─── Gripper ───────────────────────────────────
    def gripper_open(self):
        self.set_angle_smooth(CH_GRIPPER, GRIPPER_OPEN)
        print("[Gripper] Open")

    def gripper_close(self):
        self.set_angle_smooth(CH_GRIPPER, GRIPPER_CLOSE)
        print("[Gripper] Close")

    # ─── Home Position ─────────────────────────────
    def go_home(self):
        """সব servo কে default/home position এ নিয়ে যাও"""
        print("[Arm] Home position এ যাচ্ছি...")
        home = {ch: SERVO_CONFIG[ch]["default"] for ch in ACTIVE_CHANNELS}
        self.move_all_smooth(home)
        print("[Arm] Home reached.")

    # ─── Calibration ───────────────────────────────
    def _load_calibration(self):
        try:
            with open(CALIB_FILE, "r") as f:
                data = json.load(f)
                print("[Calib] Calibration file loaded.")
                return data
        except Exception:
            print("[Calib] No calibration file. Using defaults.")
            return {}

    def save_calibration(self):
        with open(CALIB_FILE, "w") as f:
            json.dump(self.calibration, f, indent=2)
        print(f"[Calib] Saved to {CALIB_FILE}")

    def set_offset(self, ch, offset):
        """Channel এর offset set করো (calibration)"""
        self.calibration[str(ch)] = {"offset": offset}

    # ─── Safe Stop ─────────────────────────────────
    def stop(self):
        """সব servo PWM বন্ধ করো (jitter এড়াতে)"""
        for ch in ACTIVE_CHANNELS:
            self.pca.channels[ch].duty_cycle = 0
        print("[ServoController] All servos stopped.")

    def deinit(self):
        self.stop()
        self.pca.deinit()
        print("[ServoController] PCA9685 released.")
