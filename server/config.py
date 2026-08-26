"""
MIA Configuration — Central config loader with auto-detection.
"""

import os
import secrets
import ctypes
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


def _get_screen_resolution():
    """Auto-detect primary monitor resolution on Windows."""
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080  # Fallback


class Config:
    """Application configuration with sensible defaults."""

    # --- AI Provider ---
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini").lower()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")

    # --- Security ---
    MIA_PASSWORD: str = os.getenv("MIA_PASSWORD", "changeme")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "") or secrets.token_hex(32)
    SESSION_EXPIRY_HOURS: int = int(os.getenv("SESSION_EXPIRY_HOURS", "24"))

    # --- Server ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8765"))

    # --- Screen ---
    SCREEN_FPS: int = int(os.getenv("SCREEN_FPS", "30"))
    SCREEN_QUALITY: int = int(os.getenv("SCREEN_QUALITY", "50"))
    SCREEN_AUTO_RESOLUTION: bool = os.getenv("SCREEN_AUTO_RESOLUTION", "true").lower() == "true"

    # Auto-detected screen resolution
    if SCREEN_AUTO_RESOLUTION:
        SCREEN_WIDTH, SCREEN_HEIGHT = _get_screen_resolution()
    else:
        SCREEN_WIDTH: int = int(os.getenv("SCREEN_WIDTH", "1920"))
        SCREEN_HEIGHT: int = int(os.getenv("SCREEN_HEIGHT", "1080"))

    # --- Cloudflare Tunnel ---
    TUNNEL_HOSTNAME: str = os.getenv("TUNNEL_HOSTNAME", "")

    # --- Telegram Channel ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_TELEGRAM_USER_ID: str = os.getenv("ALLOWED_TELEGRAM_USER_ID", "")

    # --- Paths ---
    FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    MEMORY_FILE: Path = DATA_DIR / "memory.json"
    SCHEDULER_DB: Path = DATA_DIR / "scheduler.db"

    @classmethod
    def validate(cls):
        """Validate configuration on startup."""
        errors = []

        if cls.AI_PROVIDER == "gemini" and not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        elif cls.AI_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        elif cls.AI_PROVIDER not in ("gemini", "openai", "ollama"):
            errors.append(f"Unknown AI_PROVIDER: {cls.AI_PROVIDER}. Use gemini, openai, or ollama")

        if cls.MIA_PASSWORD == "changeme":
            errors.append("⚠️  WARNING: Using default password 'changeme'. Change it in .env!")

        # Ensure data directory exists
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

        return errors

    @classmethod
    def summary(cls):
        """Print config summary for startup."""
        res = f"{cls.SCREEN_WIDTH}x{cls.SCREEN_HEIGHT}"
        return (
            f"\n"
            f"  ╔══════════════════════════════════════════╗\n"
            f"  ║          🤖  M I A  v1.0                 ║\n"
            f"  ║  Multi-model Interactive Agentic-system  ║\n"
            f"  ╠══════════════════════════════════════════╣\n"
            f"  ║  AI Provider : {cls.AI_PROVIDER:<25} ║\n"
            f"  ║  Server      : {cls.HOST}:{cls.PORT:<18} ║\n"
            f"  ║  Screen      : {res:<25} ║\n"
            f"  ║  Stream FPS  : {str(cls.SCREEN_FPS):<25} ║\n"
            f"  ║  Tunnel      : {'Quick Tunnel' if not cls.TUNNEL_HOSTNAME else cls.TUNNEL_HOSTNAME:<25} ║\n"
            f"  ╚══════════════════════════════════════════╝\n"
        )


config = Config()
