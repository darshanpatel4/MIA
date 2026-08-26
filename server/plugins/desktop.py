import subprocess
import time
from datetime import datetime
import psutil
import pyautogui
import mss
import cv2
import numpy as np
import pygetwindow as gw
import webbrowser
from server.plugins import tool

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1

@tool(
    name="take_screenshot",
    description="Take a screenshot of the current screen.",
    parameters={},
    required=[]
)
def take_screenshot() -> str:
    """Take a screenshot and save it. Returns the file path."""
    try:
        from server.config import config
        screenshot_dir = config.DATA_DIR / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = screenshot_dir / filename

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            # Convert to numpy array and save
            frame = np.array(img)
            cv2.imwrite(str(filepath), frame[:, :, :3])

        return f"📸 Screenshot saved: {filepath}"

    except Exception as e:
        return f"❌ Error taking screenshot: {str(e)}"

@tool(
    name="get_clipboard",
    description="Read the current clipboard content.",
    parameters={},
    required=[]
)
def get_clipboard() -> str:
    """Read the current clipboard content."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        content = result.stdout.strip()
        return f"📋 Clipboard: {content}" if content else "📋 Clipboard is empty."
    except Exception as e:
        return f"❌ Error reading clipboard: {str(e)}"

@tool(
    name="set_clipboard",
    description="Copy text to the clipboard.",
    parameters={
        "text": {"type": "string", "description": "Text to copy"}
    },
    required=["text"]
)
def set_clipboard(text: str) -> str:
    """Set clipboard content."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return f"✅ Copied to clipboard: {text[:100]}{'...' if len(text) > 100 else ''}"
    except Exception as e:
        return f"❌ Error setting clipboard: {str(e)}"

@tool(
    name="type_text",
    description="Type text using the keyboard at the current cursor position.",
    parameters={
        "text": {"type": "string", "description": "Text to type"}
    },
    required=["text"]
)
def type_text(text: str) -> str:
    """Type text using the keyboard."""
    try:
        pyautogui.typewrite(text, interval=0.02)
        return f"✅ Typed: {text[:50]}{'...' if len(text) > 50 else ''}"
    except Exception as e:
        return f"❌ Error typing: {str(e)}"

@tool(
    name="click_at",
    description="Click at specific screen coordinates.",
    parameters={
        "x": {"type": "integer", "description": "X coordinate"},
        "y": {"type": "integer", "description": "Y coordinate"},
        "button": {"type": "string", "description": "Mouse button: 'left', 'right', or 'middle'", "default": "left"}
    },
    required=["x", "y"]
)
def click_at(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates."""
    try:
        pyautogui.click(x, y, button=button)
        return f"✅ Clicked {button} at ({x}, {y})"
    except Exception as e:
        return f"❌ Error clicking: {str(e)}"

@tool(
    name="open_url",
    description="Open a URL in the default browser.",
    parameters={
        "url": {"type": "string", "description": "URL to open"}
    },
    required=["url"]
)
def open_url(url: str) -> str:
    """Open a URL in the default browser."""
    try:
        webbrowser.open(url)
        return f"✅ Opened: {url}"
    except Exception as e:
        return f"❌ Error opening URL: {str(e)}"

@tool(
    name="get_network_info",
    description="Get network interfaces, IPs, and active connections.",
    parameters={},
    required=[]
)
def get_network_info() -> str:
    """Get network interface information and active connections."""
    try:
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        io = psutil.net_io_counters(pernic=True)

        lines = ["🌐 **Network Interfaces**\n"]
        for name, addrs in interfaces.items():
            stat = stats.get(name)
            is_up = stat.isup if stat else False
            speed = stat.speed if stat else 0

            for addr in addrs:
                if addr.family.name == "AF_INET":
                    lines.append(f"  **{name}**: {addr.address} {'🟢 UP' if is_up else '🔴 DOWN'} ({speed}Mbps)")

        connections = psutil.net_connections(kind="inet")
        established = [c for c in connections if c.status == "ESTABLISHED"]
        lines.append(f"\n📡 **Active connections:** {len(established)}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting network info: {str(e)}"

@tool(
    name="visual_find_and_click",
    description="Visually find a UI element on the screen (like a human) and click it. Always use this to close windows, click buttons, icons, or UI elements.",
    parameters={
        "element_description": {"type": "string", "description": "Description of what to click (e.g., 'Notepad close button', 'Start menu icon')"},
        "click_type": {"type": "string", "description": "'left', 'right', or 'double'", "default": "left"}
    },
    required=["element_description"]
)
def visual_find_and_click(element_description: str, click_type: str = "left") -> str:
    """Find a UI element visually on the screen and click it like a human."""
    try:
        desc_lower = element_description.lower()
        if "close" in desc_lower and "button" in desc_lower:
            words = desc_lower.replace("close button", "").replace("window", "").replace("the", "").strip().split()
            if words:
                app_name = words[0]
                windows = [w for w in gw.getAllWindows() if app_name in w.title.lower()]
                if windows:
                    win = windows[0]
                    center_x = win.right - 25
                    center_y = win.top + 20
                    pyautogui.moveTo(center_x, center_y, duration=0.5, tween=pyautogui.easeInOutQuad)
                    time.sleep(0.1)
                    pyautogui.click(button=click_type)
                    return f"✅ Found '{win.title}' and clicked close button at ({center_x}, {center_y})."

        from server.config import config
        from google import genai
        from google.genai import types
        import re

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            frame = np.array(img)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
            success, buffer = cv2.imencode(".jpg", rgb_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                return "❌ Failed to encode screenshot for vision processing."
            image_bytes = buffer.tobytes()

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        
        prompt = (
            f"You are a precise screen reader. Locate the exact UI element: '{element_description}'. "
            "Return ONLY its 2D bounding box in the format: [ymin, xmin, ymax, xmax]. "
            "Coordinates must be integers from 0 to 1000. Be extremely precise."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ],
            config=types.GenerateContentConfig(temperature=0.0)
        )

        text = response.text.strip()
        match = re.search(r'\[\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\]', text)
        if not match:
            return f"❌ Could not locate '{element_description}'. Model output: {text}"
            
        ymin, xmin, ymax, xmax = map(int, match.groups())
        
        screen_w = monitor["width"]
        screen_h = monitor["height"]
        
        x_min_px = int(xmin * screen_w / 1000)
        y_min_px = int(ymin * screen_h / 1000)
        x_max_px = int(xmax * screen_w / 1000)
        y_max_px = int(ymax * screen_h / 1000)
        
        center_x = x_min_px + (x_max_px - x_min_px) // 2
        center_y = y_min_px + (y_max_px - y_min_px) // 2

        pyautogui.moveTo(center_x, center_y, duration=0.5, tween=pyautogui.easeInOutQuad)
        time.sleep(0.1)
        
        if click_type == "double":
            pyautogui.doubleClick()
        else:
            pyautogui.click(button=click_type)

        return f"✅ Visually found '{element_description}' and clicked {click_type} at ({center_x}, {center_y})."

    except Exception as e:
        return f"❌ Visual click failed: {str(e)}"

@tool(
    name="analyze_screen",
    description="Use Computer Vision to analyze the screen and answer questions like 'How many tabs are open in Chrome' or 'What is on my desktop'.",
    parameters={
        "query": {"type": "string", "description": "The question to ask about the screen"}
    },
    required=["query"]
)
def analyze_screen(query: str) -> str:
    """Analyze the current screen to answer a visual question."""
    try:
        from server.config import config
        from google import genai
        from google.genai import types

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            frame = np.array(img)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
            
            success, buffer = cv2.imencode(".jpg", rgb_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                return "❌ Failed to encode screenshot for vision processing."
            image_bytes = buffer.tobytes()

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=f"Analyze the screen carefully and answer: {query}")
                    ]
                )
            ],
            config=types.GenerateContentConfig(temperature=0.2)
        )

        return f"👁️ Screen Analysis: {response.text.strip()}"

    except Exception as e:
        return f"❌ Screen analysis failed: {str(e)}"
