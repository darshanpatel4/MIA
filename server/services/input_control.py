"""
MIA Input Control — Remote mouse and keyboard control.
"""

import pyautogui
from pynput.keyboard import Key, Controller as KeyboardController

from server.config import config
from server.services.screen import screen_streamer

# Setup
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05
keyboard_controller = KeyboardController()

# Special key mapping
SPECIAL_KEYS = {
    "enter": Key.enter,
    "return": Key.enter,
    "tab": Key.tab,
    "space": Key.space,
    "backspace": Key.backspace,
    "delete": Key.delete,
    "escape": Key.esc,
    "esc": Key.esc,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "home": Key.home,
    "end": Key.end,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
    "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
    "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
    "ctrl": Key.ctrl_l, "control": Key.ctrl_l,
    "alt": Key.alt_l,
    "shift": Key.shift_l,
    "win": Key.cmd, "windows": Key.cmd, "super": Key.cmd,
    "capslock": Key.caps_lock,
    "printscreen": Key.print_screen,
    "insert": Key.insert,
}


class InputController:
    """Handles remote mouse and keyboard input."""

    def __init__(self):
        self.screen_width = config.SCREEN_WIDTH
        self.screen_height = config.SCREEN_HEIGHT

    def process_input(self, data: dict):
        """Process an input event from the client.

        Event format:
        {
            "type": "mousemove|mousedown|mouseup|click|dblclick|scroll|keydown|keyup|keypress|hotkey",
            "x": int,        # For mouse events
            "y": int,        # For mouse events
            "button": str,   # "left", "right", "middle"
            "delta": int,    # For scroll events
            "key": str,      # For keyboard events
            "keys": [str],   # For hotkey combinations
            "text": str,     # For typing text
            "viewWidth": int,  # Client viewport width
            "viewHeight": int, # Client viewport height
        }
        """
        event_type = data.get("type", "")

        try:
            if event_type in ("mousemove", "mousedown", "mouseup", "click", "dblclick"):
                self._handle_mouse(event_type, data)
            elif event_type == "scroll":
                self._handle_scroll(data)
            elif event_type in ("keydown", "keyup", "keypress"):
                self._handle_key(event_type, data)
            elif event_type == "hotkey":
                self._handle_hotkey(data)
            elif event_type == "type":
                self._handle_type(data)
        except Exception as e:
            print(f"  Input error ({event_type}): {e}")

    def _map_coordinates(self, x: float, y: float, view_width: int, view_height: int) -> tuple:
        """Map client viewport coordinates to actual (virtual-desktop) screen coordinates.

        Coordinates are scaled against whichever monitor is currently being streamed,
        then offset by that monitor's (left, top) position so clicks land correctly
        on secondary monitors too.
        """
        bounds = screen_streamer.get_active_bounds()
        mon_width = bounds["width"] or self.screen_width
        mon_height = bounds["height"] or self.screen_height

        if view_width and view_height:
            local_x = x * mon_width / view_width
            local_y = y * mon_height / view_height
        else:
            local_x = x
            local_y = y

        actual_x = int(bounds["left"] + local_x)
        actual_y = int(bounds["top"] + local_y)
        return actual_x, actual_y

    def _handle_mouse(self, event_type: str, data: dict):
        """Handle mouse events."""
        view_w = data.get("viewWidth", self.screen_width)
        view_h = data.get("viewHeight", self.screen_height)
        x, y = self._map_coordinates(
            data.get("x", 0), data.get("y", 0), view_w, view_h
        )
        button = data.get("button", "left")

        if event_type == "mousemove":
            pyautogui.moveTo(x, y, _pause=False)
        elif event_type == "mousedown":
            pyautogui.mouseDown(x, y, button=button, _pause=False)
        elif event_type == "mouseup":
            pyautogui.mouseUp(x, y, button=button, _pause=False)
        elif event_type == "click":
            pyautogui.click(x, y, button=button, _pause=False)
        elif event_type == "dblclick":
            pyautogui.doubleClick(x, y, button=button, _pause=False)

    def _handle_scroll(self, data: dict):
        """Handle scroll events."""
        delta = data.get("delta", 0)
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            view_w = data.get("viewWidth", self.screen_width)
            view_h = data.get("viewHeight", self.screen_height)
            ax, ay = self._map_coordinates(x, y, view_w, view_h)
            pyautogui.scroll(delta, ax, ay, _pause=False)
        else:
            pyautogui.scroll(delta, _pause=False)

    def _handle_key(self, event_type: str, data: dict):
        """Handle keyboard events."""
        key_str = data.get("key", "")

        # Map to pynput key
        if key_str.lower() in SPECIAL_KEYS:
            key = SPECIAL_KEYS[key_str.lower()]
        elif len(key_str) == 1:
            key = key_str
        else:
            return  # Unknown key

        if event_type == "keydown":
            keyboard_controller.press(key)
        elif event_type == "keyup":
            keyboard_controller.release(key)
        elif event_type == "keypress":
            keyboard_controller.press(key)
            keyboard_controller.release(key)

    def _handle_hotkey(self, data: dict):
        """Handle hotkey combinations (e.g., Ctrl+C, Alt+Tab)."""
        keys = data.get("keys", [])
        if not keys:
            return

        mapped_keys = []
        for k in keys:
            if k.lower() in SPECIAL_KEYS:
                mapped_keys.append(SPECIAL_KEYS[k.lower()])
            elif len(k) == 1:
                mapped_keys.append(k)

        # Press all keys down then release
        for key in mapped_keys:
            keyboard_controller.press(key)
        for key in reversed(mapped_keys):
            keyboard_controller.release(key)

    def _handle_type(self, data: dict):
        """Handle typing text."""
        text = data.get("text", "")
        if text:
            pyautogui.write(text, interval=0.02)


# Global instance
input_controller = InputController()
