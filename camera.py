"""
camera.py
IP Webcam থেকে frame capture করার module।
Auto-reconnect এবং frame buffer management সহ।
"""

import cv2
import time
import threading


class IPCamera:
    def __init__(self, url: str, reconnect_delay: float = 3.0):
        self.url             = url
        self.reconnect_delay = reconnect_delay
        self._cap            = None
        self._frame          = None
        self._lock           = threading.Lock()
        self._running        = False
        self._thread         = None
        self.width           = 640
        self.height          = 480

    def connect(self) -> bool:
        self._cap = cv2.VideoCapture(self.url)
        if not self._cap.isOpened():
            print(f"[Camera] Connect failed: {self.url}")
            return False

        # Resolution পড়ো
        self.width  = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Camera] Connected → {self.width}x{self.height}")
        return True

    def start(self):
        """Background thread এ frame capture শুরু করো"""
        if not self.connect():
            raise RuntimeError("Camera connect হয়নি!")
        self._running = True
        self._thread  = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("[Camera] Capture thread started.")

    def _capture_loop(self):
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                print("[Camera] Reconnecting...")
                time.sleep(self.reconnect_delay)
                self.connect()
                continue

            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
            else:
                print("[Camera] Frame read failed. Reconnecting...")
                self._cap.release()
                self._cap = None
                time.sleep(self.reconnect_delay)

    def get_frame(self):
        """Latest frame নাও (thread-safe)"""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
        print("[Camera] Stopped.")
