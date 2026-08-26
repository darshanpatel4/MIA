"""
MIA Screen Service — High-performance screen capture and streaming.
"""

import asyncio
import time
from typing import Optional

import mss
import cv2
import numpy as np

from server.config import config


class ScreenStreamer:
    """Captures screen frames and streams them via WebSocket."""

    def __init__(self):
        self.fps = config.SCREEN_FPS
        self.quality = config.SCREEN_QUALITY
        self.width = config.SCREEN_WIDTH
        self.height = config.SCREEN_HEIGHT
        self.is_streaming = False
        self.scale = 1.0  # Downscale factor (0.25, 0.5, 0.75, 1.0)
        self.monitor_index = 1  # 1-based; mss.monitors[0] is "all monitors combined"
        self._clients: set = set()
        self._frame_count = 0
        self._fps_actual = 0
        self._fps_timer = time.time()
        # Bounds of the monitor currently being captured, kept in sync with the
        # live grab so input_control.py can map click coordinates correctly.
        self._active_bounds = {"left": 0, "top": 0, "width": self.width, "height": self.height}

    def list_monitors(self) -> list:
        """Enumerate all connected physical monitors (1-based index)."""
        try:
            with mss.mss() as sct:
                monitors = []
                for i, m in enumerate(sct.monitors[1:], start=1):
                    monitors.append({
                        "index": i,
                        "width": m["width"],
                        "height": m["height"],
                        "left": m["left"],
                        "top": m["top"],
                        "is_primary": m["left"] == 0 and m["top"] == 0,
                    })
                return monitors
        except Exception as e:
            print(f"  list_monitors error: {e}")
            return []

    def set_monitor(self, index: int):
        """Switch which monitor is being captured (clamped to available monitors)."""
        try:
            with mss.mss() as sct:
                max_index = len(sct.monitors) - 1
            self.monitor_index = max(1, min(int(index), max(max_index, 1)))
        except Exception as e:
            print(f"  set_monitor error: {e}")

    def get_active_bounds(self) -> dict:
        """Bounds (left, top, width, height) of the monitor currently being streamed."""
        return self._active_bounds

    async def start_streaming(self, websocket):
        """Stream screen frames to a WebSocket client."""
        self._clients.add(websocket)
        self.is_streaming = True

        try:
            with mss.mss() as sct:
                current_index = None
                monitor = None
                frame_interval = 1.0 / self.fps

                while self.is_streaming and websocket in self._clients:
                    frame_start = time.time()

                    # Pick up monitor switches without restarting the stream
                    if self.monitor_index != current_index:
                        max_index = len(sct.monitors) - 1
                        safe_index = max(1, min(self.monitor_index, max(max_index, 1)))
                        monitor = sct.monitors[safe_index]
                        current_index = self.monitor_index = safe_index
                        self.width, self.height = monitor["width"], monitor["height"]
                        self._active_bounds = {
                            "left": monitor["left"],
                            "top": monitor["top"],
                            "width": monitor["width"],
                            "height": monitor["height"],
                        }
                        frame_interval = 1.0 / self.fps

                    # Capture screen
                    img = sct.grab(monitor)
                    frame = np.array(img, dtype=np.uint8)

                    # Convert BGRA to BGR
                    frame = frame[:, :, :3]

                    # Downscale if needed
                    if self.scale < 1.0:
                        new_w = int(frame.shape[1] * self.scale)
                        new_h = int(frame.shape[0] * self.scale)
                        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

                    # Encode as JPEG
                    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                    _, buffer = cv2.imencode('.jpg', frame, encode_params)

                    # Send binary frame
                    try:
                        await websocket.send_bytes(buffer.tobytes())
                    except Exception:
                        break

                    # FPS tracking
                    self._frame_count += 1
                    elapsed_since_fps = time.time() - self._fps_timer
                    if elapsed_since_fps >= 1.0:
                        self._fps_actual = self._frame_count / elapsed_since_fps
                        self._frame_count = 0
                        self._fps_timer = time.time()

                    # Frame pacing
                    elapsed = time.time() - frame_start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                    else:
                        await asyncio.sleep(0.001)  # Yield to event loop

        except Exception as e:
            print(f"  Screen streaming error: {e}")
        finally:
            self._clients.discard(websocket)
            if not self._clients:
                self.is_streaming = False

    def stop_streaming(self, websocket=None):
        """Stop streaming for a specific client or all."""
        if websocket:
            self._clients.discard(websocket)
            if not self._clients:
                self.is_streaming = False
        else:
            self._clients.clear()
            self.is_streaming = False

    def set_quality(self, quality: int):
        """Set JPEG quality (1-100)."""
        self.quality = max(1, min(100, quality))

    def set_scale(self, scale: float):
        """Set downscale factor (0.25, 0.5, 0.75, 1.0)."""
        self.scale = max(0.25, min(1.0, scale))

    def set_fps(self, fps: int):
        """Set target FPS."""
        self.fps = max(1, min(60, fps))

    def get_stats(self) -> dict:
        """Get streaming statistics."""
        return {
            "is_streaming": self.is_streaming,
            "clients": len(self._clients),
            "fps_target": self.fps,
            "fps_actual": round(self._fps_actual, 1),
            "quality": self.quality,
            "scale": self.scale,
            "resolution": f"{self.width}x{self.height}",
            "monitor_index": self.monitor_index,
        }


# Global instance
screen_streamer = ScreenStreamer()
