# Autonomous Robotic Arm — Raspberry Pi 5

## File Structure
```
robot_arm/
├── main.py             ← Main autonomous loop
├── servo_control.py    ← PCA9685 servo controller
├── calibration.py      ← Servo calibration tool
├── color_detection.py  ← OpenCV color detection
├── camera.py           ← IP webcam module
├── arm_kinematics.py   ← Camera → servo angle mapping
├── calibration.json    ← Auto-generated after calibration
└── README.md
```

---

## Step 1: Fresh OS Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git i2c-tools -y

# I2C enable করো
sudo raspi-config
# → Interface Options → I2C → Enable

# Reboot
sudo reboot
```

---

## Step 2: Virtual Environment

```bash
cd ~/robot_arm
python3 -m venv env
source env/bin/activate
```

---

## Step 3: Install Dependencies

```bash
# Pi 5 environment
echo 'export BLINKA_RASPBERRY_PI5=1' >> ~/.bashrc
source ~/.bashrc

# Core packages
pip install opencv-python numpy

# PCA9685 (no-deps দিয়ে rpi_ws281x/RPi.GPIO avoid করো)
pip install adafruit-blinka --no-deps
pip install adafruit-circuitpython-pca9685 \
            adafruit-circuitpython-busdevice \
            adafruit-circuitpython-register \
            Adafruit-PlatformDetect \
            Adafruit-PureIO \
            hid binho-host-adapter \
            adafruit-circuitpython-typing \
            Adafruit-Blinka-Raspberry-Pi5-Neopixel \
            --no-deps
```

---

## Step 4: I2C Check

```bash
sudo i2cdetect -y 1
# 0x40 এবং 0x70 দেখা যাওয়া উচিত
```

---

## Step 5: Calibration (প্রথমবার অবশ্যই করো)

```bash
python calibration.py
```

- প্রতিটা servo এর জন্য `+`/`-` দিয়ে correct 0° position খুঁজো
- `s` চাপো save করতে এবং পরের servo তে যাও
- শেষে `calibration.json` তৈরি হবে

Quick test (calibration ছাড়া):
```bash
python calibration.py test
```

---

## Step 6: Run Main Program

```bash
python main.py
```

### Keyboard Controls
| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Drop ball (HOLDING state) / Reset (TRACKING state) |
| `p` | Pause / Resume |
| `1` | Target RED only |
| `2` | Target GREEN only |
| `3` | Target BLUE only |
| `0` | Target ALL colors |

---

## CH1 Shoulder Servo ছাড়া কীভাবে কাজ করে

Shoulder (CH1) না থাকায় arm এর vertical reach কমে গেছে।
Solution হিসেবে:

- **Elbow (CH2)** দিয়ে up/down movement handle করা হচ্ছে
- **Wrist Vertical (CH3)** দিয়ে fine compensation দেওয়া হচ্ছে
- Object টা arm এর সামনে মাঝারি উচ্চতায় রাখলে সবচেয়ে ভালো কাজ করবে
- খুব উঁচু বা খুব নিচু object এ reach নাও হতে পারে

---

## Camera Position → Servo Angle Mapping

```
Camera Frame (640x480):
  norm_x = (cx - 320) / 320   → -1 (left) to +1 (right)
  norm_y = (cy - 240) / 240   → -1 (top)  to +1 (bottom)

Base angle   = 90 + norm_x × 70
Elbow angle  = 90 + norm_y × 30 + distance_offset
Wrist_V      = 90 - elbow_compensation
```

---

## Tuning Tips

`arm_kinematics.py` এ এই values adjust করো:

```python
# Base range (±70 মানে center থেকে ৭০° পর্যন্ত যাবে)
angle = base_center + norm_x * 70

# Elbow range
y_offset = norm_y * 30

# Drop position (অন্যদিকে কতটুকু rotate করবে)
DROP_BASE_ANGLE = 170   # main.py তে
```

---

## Troubleshooting

| সমস্যা | সমাধান |
|--------|--------|
| `ModuleNotFoundError: hid` | `pip install hid` |
| `BLINKA_MCP2221` error | `unset BLINKA_MCP2221` তারপর `export BLINKA_RASPBERRY_PI5=1` |
| Servo randomly নড়ে | GND common করো (Pi GND + External GND একসাথে) |
| Camera connect হয় না | IP Webcam app চালু আছে কিনা দেখো, same WiFi এ আছে কিনা দেখো |
| Ball detect হচ্ছে না | আলো ভালো করো, `MIN_AREA` কমাও `color_detection.py` তে |
