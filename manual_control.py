"""
manual_control.py
Robotic Arm — Dual-mode Manual Controller

Mode 1: Keyboard (terminal, no display needed)
Mode 2: Tkinter GUI (with sliders, buttons, live angle display)

Usage:
  python manual_control.py           → GUI mode
  python manual_control.py keyboard  → Keyboard mode
"""

import os
os.environ["BLINKA_RASPBERRY_PI5"] = "1"

import sys
import time
import threading

from servo_control import (
    ServoController,
    SERVO_CONFIG,
    ACTIVE_CHANNELS,
    CH_BASE, CH_ELBOW,
    CH_WRIST_V, CH_WRIST_R, CH_GRIPPER,
    GRIPPER_OPEN, GRIPPER_CLOSE,
)

# ─────────────────────────────────────────────
#  KEYBOARD MODE
# ─────────────────────────────────────────────

KEYBOARD_HELP = """
╔══════════════════════════════════════════════╗
║        ROBOTIC ARM — KEYBOARD CONTROL        ║
╠══════════════════════════════════════════════╣
║  A / D   →  Base       left  / right         ║
║  Q / E   →  Elbow      up    / down          ║
║  X / Z   →  Wrist V    up    / down          ║
║  L / J   →  Wrist R    right / left          ║
║  O / C   →  Gripper    open  / close         ║
╠══════════════════════════════════════════════╣
║  +  / -  →  Step size  bigger / smaller      ║
║  H       →  Go to Home position              ║
║  P       →  Print current angles             ║
║  ESC/Q   →  Quit                             ║
╚══════════════════════════════════════════════╝
"""

KEY_MAP = {
    'a': (CH_BASE,     -1),
    'd': (CH_BASE,     +1),
    'q': (CH_ELBOW,    +1),
    'e': (CH_ELBOW,    -1),
    'x': (CH_WRIST_V,  +1),
    'z': (CH_WRIST_V,  -1),
    'l': (CH_WRIST_R,  +1),
    'j': (CH_WRIST_R,  -1),
}


def run_keyboard():
    """Terminal keyboard control — uses tty raw mode"""
    import tty
    import termios

    ctrl = ServoController()
    ctrl.go_home()
    ctrl.gripper_open()

    step = 3   # degrees per keypress

    print(KEYBOARD_HELP)
    print(f"[READY]  Step size: {step}°  — start pressing keys\n")

    def print_angles():
        parts = []
        names = {
            CH_BASE: "Base",
            CH_ELBOW: "Elbow", CH_WRIST_V: "Wrist↕",
            CH_WRIST_R: "Wrist↔", CH_GRIPPER: "Gripper",
        }
        for ch in ACTIVE_CHANNELS:
            angle = ctrl.current_angles.get(ch, SERVO_CONFIG[ch]["default"])
            parts.append(f"{names[ch]}:{angle:3d}°")
        print("  " + "  │  ".join(parts))

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        while True:
            ch_key = sys.stdin.read(1)
            key = ch_key.lower()

            if key in ('\x1b', '\x03') or ch_key == 'Q':
                break

            elif key in KEY_MAP:
                ch, direction = KEY_MAP[key]
                current = ctrl.current_angles.get(ch, SERVO_CONFIG[ch]["default"])
                target  = current + direction * step
                cfg     = SERVO_CONFIG[ch]
                target  = max(cfg["min_ang"], min(cfg["max_ang"], target))
                ctrl.set_angle_instant(ch, target)
                print_angles()

            elif ch_key == 'O' or key == 'o':
                ctrl.gripper_open()
                print_angles()

            elif key == 'c':
                ctrl.gripper_close()
                print_angles()

            elif key == 'h':
                print("\n  → Going home...")
                ctrl.go_home()
                ctrl.gripper_open()
                print_angles()

            elif key == 'p':
                print_angles()

            elif ch_key == '+' or ch_key == '=':
                step = min(15, step + 1)
                print(f"\r  Step: {step}°      ")

            elif ch_key == '-':
                step = max(1, step - 1)
                print(f"\r  Step: {step}°      ")

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print("\n\n[EXIT] Parking arm at home...")
        ctrl.go_home()
        ctrl.deinit()
        print("[DONE]")


# ─────────────────────────────────────────────
#  GUI MODE
# ─────────────────────────────────────────────

def run_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, font as tkfont
    except ImportError:
        print("[ERROR] tkinter not found. Run: sudo apt install python3-tk")
        sys.exit(1)

    ctrl = ServoController()
    ctrl.go_home()
    ctrl.gripper_open()

    # ── Design tokens ──────────────────────────
    BG        = "#0f1117"   # near-black bg
    PANEL     = "#1a1d27"   # card background
    BORDER    = "#2a2d3a"   # subtle border
    ACCENT    = "#4f9eff"   # electric blue — arm "active" colour
    ACCENT2   = "#ff6b35"   # orange — gripper / danger
    TEXT      = "#e8eaf0"
    TEXT_DIM  = "#6b7280"
    GREEN     = "#22c55e"
    SLIDER_TR = "#2d3148"   # slider trough

    FONT_MONO   = ("JetBrains Mono", 10) if sys.platform != "win32" else ("Consolas", 10)
    FONT_LABEL  = ("Inter", 9, "bold") if sys.platform != "win32" else ("Segoe UI", 9, "bold")
    FONT_TITLE  = ("Inter", 11, "bold") if sys.platform != "win32" else ("Segoe UI", 11, "bold")
    FONT_BIG    = ("Inter", 20, "bold") if sys.platform != "win32" else ("Segoe UI", 20, "bold")

    # ── Servo state ────────────────────────────
    angle_vars = {}   # ch → tk.IntVar  (mirrors current_angles)
    speed_var  = None

    move_lock = threading.Lock()

    def smooth_move(ch, target_angle):
        """Non-blocking smooth move in background thread"""
        def _move():
            with move_lock:
                ctrl.set_angle_smooth(ch, target_angle, delay=0.010)
                angle_vars[ch].set(
                    ctrl.current_angles.get(ch, SERVO_CONFIG[ch]["default"])
                )
        threading.Thread(target=_move, daemon=True).start()

    def on_slider(ch, val):
        angle = int(float(val))
        smooth_move(ch, angle)

    def go_home():
        def _home():
            ctrl.go_home()
            ctrl.gripper_open()
            for ch in ACTIVE_CHANNELS:
                angle_vars[ch].set(SERVO_CONFIG[ch]["default"])
            angle_vars[CH_GRIPPER].set(GRIPPER_OPEN)
        threading.Thread(target=_home, daemon=True).start()

    def emergency_stop():
        ctrl.stop()
        status_var.set("⚡ EMERGENCY STOP")
        status_lbl.config(fg=ACCENT2)

    def gripper_open():
        threading.Thread(
            target=lambda: ctrl.gripper_open(), daemon=True
        ).start()
        angle_vars[CH_GRIPPER].set(GRIPPER_OPEN)

    def gripper_close():
        threading.Thread(
            target=lambda: ctrl.gripper_close(), daemon=True
        ).start()
        angle_vars[CH_GRIPPER].set(GRIPPER_CLOSE)

    # ── Window ─────────────────────────────────
    root = tk.Tk()
    root.title("Robotic Arm — Manual Control")
    root.configure(bg=BG)
    root.resizable(False, False)

    # ── Header ─────────────────────────────────
    hdr = tk.Frame(root, bg=BG, pady=10)
    hdr.pack(fill="x", padx=20)

    tk.Label(hdr, text="⚙", font=("", 22), bg=BG, fg=ACCENT).pack(side="left")
    tk.Label(hdr, text="  ROBOTIC ARM", font=FONT_BIG,
             bg=BG, fg=TEXT).pack(side="left")
    tk.Label(hdr, text="MANUAL CONTROL", font=FONT_LABEL,
             bg=BG, fg=TEXT_DIM).pack(side="left", padx=(8, 0), pady=(6, 0))

    sep = tk.Frame(root, bg=BORDER, height=1)
    sep.pack(fill="x", padx=20, pady=(0, 12))

    # ── Main area: servo cards ──────────────────
    main_frame = tk.Frame(root, bg=BG)
    main_frame.pack(padx=20, pady=0)

    SERVO_META = [
        (CH_BASE,     "BASE",     "◀  ▶",  ACCENT,  "Rotation left / right"),
        (CH_ELBOW,    "ELBOW",    "▲  ▼",  ACCENT,  "Elbow bend"),
        (CH_WRIST_V,  "WRIST ↕",  "▲  ▼",  ACCENT,  "Wrist tilt up / down"),
        (CH_WRIST_R,  "WRIST ↔",  "◀  ▶",  ACCENT,  "Wrist rotate"),
        (CH_GRIPPER,  "GRIPPER",  "◉  ✊", ACCENT2, "Open=0°  Close=80°"),
    ]

    def make_card(parent, ch, title, icon, color, tip, row, col):
        cfg = SERVO_CONFIG[ch]
        var = tk.IntVar(value=cfg["default"])
        angle_vars[ch] = var

        card = tk.Frame(parent, bg=PANEL, bd=0, padx=14, pady=12,
                        highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

        # Title row
        th = tk.Frame(card, bg=PANEL)
        th.pack(fill="x")
        tk.Label(th, text=icon, font=("", 11), bg=PANEL, fg=color).pack(side="left")
        tk.Label(th, text=f"  {title}", font=FONT_TITLE, bg=PANEL, fg=TEXT).pack(side="left")
        tk.Label(th, text=tip, font=("", 7), bg=PANEL, fg=TEXT_DIM).pack(side="right")

        # Angle readout
        readout_frame = tk.Frame(card, bg=PANEL)
        readout_frame.pack(fill="x", pady=(6, 4))

        angle_lbl = tk.Label(
            readout_frame,
            textvariable=var,
            font=(FONT_MONO[0], 26, "bold"),
            bg=PANEL, fg=color, width=4, anchor="e"
        )
        angle_lbl.pack(side="left")
        tk.Label(readout_frame, text="°", font=(FONT_MONO[0], 14),
                 bg=PANEL, fg=TEXT_DIM).pack(side="left", padx=(0, 6))

        # Range label
        tk.Label(
            readout_frame,
            text=f"{cfg['min_ang']}° – {cfg['max_ang']}°",
            font=("", 8), bg=PANEL, fg=TEXT_DIM
        ).pack(side="right")

        # Slider
        sld = tk.Scale(
            card,
            from_=cfg["min_ang"], to=cfg["max_ang"],
            orient="horizontal",
            variable=var,
            command=lambda v, c=ch: on_slider(c, v),
            length=230,
            bg=PANEL, fg=TEXT,
            troughcolor=SLIDER_TR,
            activebackground=color,
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            showvalue=False,
        )
        sld.pack(fill="x", pady=(0, 6))

        # ±5° quick buttons
        btn_row = tk.Frame(card, bg=PANEL)
        btn_row.pack()

        def make_step_btn(parent, label, ch, delta):
            btn = tk.Button(
                parent, text=label, width=4,
                bg=BORDER, fg=TEXT, activebackground=color,
                activeforeground=BG,
                relief="flat", bd=0, padx=6, pady=2,
                font=FONT_LABEL,
                command=lambda: step_servo(ch, delta)
            )
            btn.pack(side="left", padx=2)

        def step_servo(ch, delta):
            cur    = ctrl.current_angles.get(ch, SERVO_CONFIG[ch]["default"])
            target = max(SERVO_CONFIG[ch]["min_ang"],
                         min(SERVO_CONFIG[ch]["max_ang"], cur + delta))
            smooth_move(ch, target)
            var.set(target)

        make_step_btn(btn_row, "−10", ch, -10)
        make_step_btn(btn_row, "−5",  ch, -5)
        make_step_btn(btn_row, "−1",  ch, -1)
        make_step_btn(btn_row, "+1",  ch, +1)
        make_step_btn(btn_row, "+5",  ch, +5)
        make_step_btn(btn_row, "+10", ch, +10)

    # Render all 6 servo cards in 2 columns
    grid_frame = tk.Frame(main_frame, bg=BG)
    grid_frame.pack()

    for i, (ch, title, icon, color, tip) in enumerate(SERVO_META):
        row = i // 2
        col = i %  2
        make_card(grid_frame, ch, title, icon, color, tip, row, col)

    # ── Bottom Controls ────────────────────────
    sep2 = tk.Frame(root, bg=BORDER, height=1)
    sep2.pack(fill="x", padx=20, pady=(10, 0))

    bot = tk.Frame(root, bg=BG, pady=12)
    bot.pack(padx=20)

    tk.Button(
        bot, text="⌂  HOME", width=12, height=1,
        bg=BORDER, fg=TEXT, activebackground=ACCENT,
        activeforeground=BG, relief="flat", bd=0,
        font=FONT_TITLE, command=go_home
    ).pack(side="left", padx=6)

    tk.Button(
        bot, text="⚡ STOP", width=12, height=1,
        bg="#3a1a1a", fg=ACCENT2, activebackground=ACCENT2,
        activeforeground=BG, relief="flat", bd=0,
        font=FONT_TITLE, command=emergency_stop
    ).pack(side="left", padx=6)

    tk.Button(
        bot, text="✕  QUIT", width=12, height=1,
        bg=BORDER, fg=TEXT_DIM, activebackground=TEXT_DIM,
        activeforeground=BG, relief="flat", bd=0,
        font=FONT_TITLE,
        command=lambda: on_close()
    ).pack(side="left", padx=6)

    # ── Status bar ─────────────────────────────
    status_var = tk.StringVar(value="● CONNECTED — all servos ready")
    status_lbl = tk.Label(
        root, textvariable=status_var,
        font=("", 8), bg="#0a0c12", fg=GREEN,
        anchor="w", padx=12, pady=4
    )
    status_lbl.pack(fill="x", side="bottom")

    # ── Keyboard shortcuts (even in GUI) ───────
    KEY_GUI_MAP = {
        'a': (CH_BASE,     -5),
        'd': (CH_BASE,     +5),
        'q': (CH_ELBOW,    +5),
        'e': (CH_ELBOW,    -5),
        'x': (CH_WRIST_V,  +5),
        'z': (CH_WRIST_V,  -5),
        'l': (CH_WRIST_R,  +5),
        'j': (CH_WRIST_R,  -5),
    }

    def on_key(event):
        k = event.char.lower()
        if k in KEY_GUI_MAP:
            ch, delta = KEY_GUI_MAP[k]
            cur    = ctrl.current_angles.get(ch, SERVO_CONFIG[ch]["default"])
            target = max(SERVO_CONFIG[ch]["min_ang"],
                         min(SERVO_CONFIG[ch]["max_ang"], cur + delta))
            smooth_move(ch, target)
            angle_vars[ch].set(target)
        elif k == 'o':
            gripper_open()
        elif k == 'c':
            gripper_close()
        elif k == 'h':
            go_home()
        elif k == '\x1b':
            on_close()

    root.bind("<Key>", on_key)

    # ── Cleanup ────────────────────────────────
    def on_close():
        status_var.set("Parking arm...")
        root.update()
        ctrl.go_home()
        ctrl.gripper_open()
        time.sleep(0.3)
        ctrl.deinit()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "keyboard":
        run_keyboard()
    else:
        run_gui()
