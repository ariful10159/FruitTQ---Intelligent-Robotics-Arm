"""
arm_kinematics.py
Camera position → Servo angle conversion।
CH1 (Shoulder) ছাড়া শুধু:
  Base (left/right) + Elbow (up/down) + Wrist + Gripper

CH1 না থাকায় arm এর reach সীমিত।
Solution: Elbow কে দিয়ে up/down, Base দিয়ে left/right,
          Wrist দিয়ে fine-tune করা হবে।
"""

from servo_control import (
    CH_BASE, CH_ELBOW, CH_WRIST_V, CH_WRIST_R, CH_GRIPPER,
    SERVO_CONFIG
)


# =====================
# Arm Geometry (cm)
# =====================
# CH1 (shoulder) skip করায় আমরা elbow কে "মূল arm" হিসেবে ব্যবহার করবো।
# Physical measurement অনুযায়ী adjust করো।
ELBOW_LENGTH  = 12.0   # Elbow segment length (cm)
WRIST_LENGTH  = 8.0    # Wrist segment length (cm)

# Camera frame → real world mapping
# এটা estimate — actual workspace দেখে calibrate করো
WORKSPACE_X_CM  = 30   # Camera frame width = 30cm real world
WORKSPACE_Y_CM  = 20   # Camera frame height = 20cm real world


# =====================
# Base: X pixel → angle
# =====================
def x_to_base_angle(norm_x: float, base_center: int = 90) -> int:
    """
    norm_x: -1 (left) ~ +1 (right)
    Base servo: 0° = far left, 90° = center, 180° = far right
    """
    angle = base_center + norm_x * 70   # ±70° range
    cfg   = SERVO_CONFIG[CH_BASE]
    return int(max(cfg["min_ang"], min(cfg["max_ang"], angle)))


# =====================
# Elbow: Y + Distance → angle
# =====================
def y_to_elbow_angle(norm_y: float, distance_cm: float = 20) -> int:
    """
    norm_y: -1 (top/far) ~ +1 (bottom/near)
    Distance: estimated distance from camera

    Logic:
    - Object কাছে (norm_y > 0) → elbow নামে (angle বাড়ে)
    - Object দূরে (norm_y < 0) → elbow ওঠে (angle কমে)
    - Distance বেশি হলে elbow আরও বাড়ানো দরকার
    """
    base_elbow = 90

    # Y position effect
    y_offset = norm_y * 30      # ±30°

    # Distance effect: দূরে হলে elbow বেশি extend
    dist_offset = max(0, (25 - distance_cm)) * 1.2

    angle = base_elbow + y_offset + dist_offset
    cfg   = SERVO_CONFIG[CH_ELBOW]
    return int(max(cfg["min_ang"], min(cfg["max_ang"], angle)))


# =====================
# Wrist: Fine adjustment
# =====================
def calc_wrist_vertical(norm_y: float, elbow_angle: int) -> int:
    """
    Elbow angle এর compensation + Y position fine-tune।
    Wrist টা ground এর সাথে parallel রাখার চেষ্টা করে।
    """
    # Elbow যত বাড়ে, wrist তত নামে (compensation)
    compensation = (elbow_angle - 90) * 0.4
    wrist_angle  = 90 - compensation + norm_y * 10
    cfg          = SERVO_CONFIG[CH_WRIST_V]
    return int(max(cfg["min_ang"], min(cfg["max_ang"], wrist_angle)))


def calc_wrist_rotate(norm_x: float) -> int:
    """
    Base rotation এর fine-tune হিসেবে wrist rotation।
    Object টা একটু বাঁকা থাকলে wrist দিয়ে adjust।
    """
    angle = 90 + norm_x * 20   # ±20° fine adjustment
    cfg   = SERVO_CONFIG[CH_WRIST_R]
    return int(max(cfg["min_ang"], min(cfg["max_ang"], angle)))


# =====================
# Main: Position → All Angles
# =====================
def position_to_angles(
    norm_x: float,
    norm_y: float,
    distance_cm: float = 20.0,
) -> dict:
    """
    Camera normalized position → সব servo এর target angle।

    Args:
        norm_x     : -1 (left) ~ +1 (right)
        norm_y     : -1 (top)  ~ +1 (bottom)
        distance_cm: estimated distance

    Returns:
        dict of {channel: angle}
    """
    base    = x_to_base_angle(norm_x)
    elbow   = y_to_elbow_angle(norm_y, distance_cm)
    wrist_v = calc_wrist_vertical(norm_y, elbow)
    wrist_r = calc_wrist_rotate(norm_x)

    return {
        CH_BASE   : base,
        CH_ELBOW  : elbow,
        CH_WRIST_V: wrist_v,
        CH_WRIST_R: wrist_r,
        # Gripper main.py থেকে control হবে
    }


def is_reachable(norm_x: float, norm_y: float) -> bool:
    """
    Position টা arm এর reach এর মধ্যে আছে কিনা check করো।
    খুব কোণায় বা খুব দূরে হলে False।
    """
    if abs(norm_x) > 0.95:
        return False
    if norm_y < -0.9:   # খুব উপরে
        return False
    return True
