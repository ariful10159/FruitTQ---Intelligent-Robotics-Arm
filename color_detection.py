"""
color_detection.py
OpenCV দিয়ে Red/Green/Blue ball detect করার module।
Imperfect circle এও কাজ করে।
"""

import cv2
import numpy as np


# =====================
# HSV Color Ranges
# =====================
COLOR_RANGES = {
    "red": [
        (np.array([0,   110, 60]),  np.array([10,  255, 255])),
        (np.array([170, 110, 60]),  np.array([180, 255, 255])),
    ],
    "green": [
        (np.array([35,  80,  50]),  np.array([85,  255, 255])),
    ],
    "blue": [
        (np.array([95,  80,  50]),  np.array([130, 255, 255])),
    ],
}

# Minimum contour area (noise filter)
MIN_AREA = 1200

# Morphology kernel
KERNEL = np.ones((6, 6), np.uint8)


def build_mask(hsv, color: str):
    """HSV frame থেকে নির্দিষ্ট color এর mask বানাও"""
    final_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for (lower, upper) in COLOR_RANGES[color]:
        m = cv2.inRange(hsv, lower, upper)
        final_mask = cv2.bitwise_or(final_mask, m)

    # Noise কমাও
    final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_OPEN,  KERNEL)
    final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, KERNEL)
    return final_mask


def find_best_contour(mask):
    """Mask থেকে সবচেয়ে বড় valid contour বের করো"""
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area    = cv2.contourArea(largest)

    if area < MIN_AREA:
        return None

    return largest


def detect_objects(frame):
    """
    Frame থেকে সব color এর object detect করো।

    Return:
        list of dict:
        {
            "color"   : "red"/"green"/"blue",
            "cx"      : int,   # center X pixel
            "cy"      : int,   # center Y pixel
            "area"    : float,
            "bbox"    : (x, y, w, h),
            "contour" : np array,
        }
    """
    hsv     = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    results = []

    for color in COLOR_RANGES:
        mask    = build_mask(hsv, color)
        contour = find_best_contour(mask)

        if contour is None:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        cx = x + w // 2
        cy = y + h // 2
        area = cv2.contourArea(contour)

        results.append({
            "color"  : color,
            "cx"     : cx,
            "cy"     : cy,
            "area"   : area,
            "bbox"   : (x, y, w, h),
            "contour": contour,
        })

    # Area অনুযায়ী sort (সবচেয়ে বড় আগে)
    results.sort(key=lambda r: r["area"], reverse=True)
    return results


def draw_detections(frame, detections):
    """Frame এ detection results আঁকো"""
    COLOR_BGR = {
        "red"  : (0,   0,   255),
        "green": (0,   255, 0),
        "blue" : (255, 0,   0),
    }

    for det in detections:
        bgr     = COLOR_BGR[det["color"]]
        x, y, w, h = det["bbox"]
        cx, cy  = det["cx"], det["cy"]

        # Bounding box
        cv2.rectangle(frame, (x, y), (x+w, y+h), bgr, 2)

        # Center dot
        cv2.circle(frame, (cx, cy), 6, bgr, -1)

        # Contour
        cv2.drawContours(frame, [det["contour"]], -1, bgr, 1)

        # Label
        label = f"{det['color'].upper()} ({cx},{cy}) A:{int(det['area'])}"
        cv2.putText(frame, label, (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, bgr, 2)

    return frame


def get_frame_position(cx, cy, frame_w, frame_h):
    """
    Pixel position → normalized position (-1 to +1)
    cx=0 → left, cx=frame_w → right
    cy=0 → top,  cy=frame_h → bottom

    Return:
        norm_x: -1 (far left) ~ +1 (far right)
        norm_y: -1 (top)      ~ +1 (bottom)
    """
    norm_x = (cx - frame_w / 2) / (frame_w / 2)
    norm_y = (cy - frame_h / 2) / (frame_h / 2)
    return norm_x, norm_y


def estimate_distance_by_area(area, known_area_at_30cm=8000):
    """
    Object area দিয়ে approximate distance estimate।
    known_area_at_30cm: 30cm দূরে ball এর area (calibrate করো)
    Return: distance in cm (approximate)
    """
    if area <= 0:
        return None
    distance = 30 * (known_area_at_30cm / area) ** 0.5
    return round(distance, 1)
