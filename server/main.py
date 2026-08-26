"""
MIA Main Server — FastAPI application entry point.
"""

import sys
import os
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Fix DPI scaling issue on Windows for full screen capture across multiple monitors.
# SetProcessDPIAware() only makes the process "System DPI Aware" (one scale factor
# for the whole virtual desktop, based on the primary monitor), which clips/distorts
# capture on any other monitor running a different effective scale. Per-Monitor V2
# awareness tells Windows to report/capture each monitor at its own true resolution.
if sys.platform == "win32":
    try:
        import ctypes
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+)
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        if not ctypes.windll.user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            raise OSError("SetProcessDpiAwarenessContext failed")
    except Exception:
        try:
            # Fallback: PROCESS_PER_MONITOR_DPI_AWARE (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # Last-resort fallback for older Windows versions
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
from contextlib import asynccontextmanager

from server.config import config
from server.routes.auth_routes import router as auth_router
from server.routes.api import router as api_router
from server.routes.websocket import router as ws_router
from server.auth import get_token_from_request, verify_token

# ── Setup Logging ─────────────────────────────────────────────
logs_dir = PROJECT_ROOT / "Logs"
logs_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(logs_dir / "server.log"),
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ── Startup / Shutdown ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup."""
    print(config.summary())

    # Validate config
    errors = config.validate()
    for err in errors:
        print(f"  ⚠️  {err}")

    # Start scheduler
    from server.services.scheduler import task_scheduler
    task_scheduler.start()

    # Start Telegram Bot Channel
    import asyncio
    from server.channels.telegram_bot import start_telegram_bot
    asyncio.create_task(start_telegram_bot())

    print(f"  🚀 MIA is ready at http://{config.HOST}:{config.PORT}")
    print(f"  🔒 Login with your configured password")
    print()
    
    yield
    
    """Clean up on shutdown."""
    from server.services.scheduler import task_scheduler
    from server.services.screen import screen_streamer
    from server.services.system_monitor import system_monitor

    task_scheduler.stop()
    screen_streamer.stop_streaming()
    system_monitor.stop_monitoring()
    print("  👋 MIA shutting down...")

# ── Create App ───────────────────────────────────────────────

app = FastAPI(
    title="MIA — Multi-model Interactive Agentic-system",
    description="Full PC control from anywhere",
    version="1.0.0",
    docs_url=None,  # Disable docs in production
    redoc_url=None,
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register Routes ──────────────────────────────────────────

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(ws_router)


# ── Static Files ─────────────────────────────────────────────

# Mount frontend static files
frontend_dir = config.FRONTEND_DIR
if frontend_dir.exists():
    app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")
    if (frontend_dir / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")


# ── Page Routes ──────────────────────────────────────────────

@app.get("/")
async def root(request: Request):
    """Serve main page or redirect to login."""
    token = get_token_from_request(request)
    if token and verify_token(token):
        return FileResponse(str(frontend_dir / "index.html"))
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page(request: Request):
    """Serve login page."""
    # If already authenticated, redirect to main
    token = get_token_from_request(request)
    if token and verify_token(token):
        return RedirectResponse(url="/")
    return FileResponse(str(frontend_dir / "login.html"))


# ── Run ──────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level="warning",  # Hides the INFO spam from terminal
        ws="wsproto",
    )
