import os
import sys
import subprocess
import argparse
from pathlib import Path
import shutil

# Enable ANSI escape sequences on Windows
if os.name == 'nt':
    os.system('')

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

def print_banner():
    banner = f"""{Colors.CYAN}{Colors.BOLD}
    __  ___  ____    ___ 
   /  |/  / /  _/   /   |
  / /|_/ /  / /    / /| |
 / /  / / _/ /    / ___ |
/_/  /_/ /___/   /_/  |_|
{Colors.ENDC}{Colors.DIM}
    MIA AI Control CLI Setup
    =========================={Colors.ENDC}
"""
    print(banner)

def styled_input(prompt, default_display="", default_value=""):
    if default_display:
        res = input(f"{Colors.GREEN}?{Colors.ENDC} {prompt} {Colors.YELLOW}[{default_display}]{Colors.ENDC}: ")
        return res if res else default_value
    else:
        res = input(f"{Colors.GREEN}?{Colors.ENDC} {prompt}: ")
        return res if res else default_value

PROJECT_ROOT = Path(__file__).parent
SERVER_DIR = PROJECT_ROOT / "server"

import threading
import re
import urllib.request
import urllib.parse
import json

def read_tunnel_output(process, tg_token, tg_user):
    logs_dir = PROJECT_ROOT / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "tunnel.log"
    
    with open(log_file, "a", encoding="utf-8") as f:
        for line in iter(process.stdout.readline, b''):
            decoded = line.decode(errors='replace')
            
            # Log everything to the file silently
            f.write(decoded)
            f.flush()
            
            # Only print the most important information to the console
            if "trycloudflare.com" in decoded:
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', decoded)
                if match:
                    url = match.group(0)
                    print(f"\n{Colors.CYAN}🌐 Cloudflare Tunnel Online: {url}{Colors.ENDC}")
                    
                    if tg_token and tg_user:
                        try:
                            api_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                            data = json.dumps({
                                "chat_id": tg_user,
                                "text": f"🚀 MIA Server Started!\n🌐 Cloudflare Tunnel: {url}"
                            }).encode('utf-8')
                            req = urllib.request.Request(api_url, data=data, headers={'Content-Type': 'application/json'})
                            urllib.request.urlopen(req, timeout=5)
                            print(f"{Colors.GREEN}✔ Sent Cloudflare URL to Telegram!{Colors.ENDC}\n")
                        except Exception as e:
                            print(f"{Colors.RED}Failed to send URL to Telegram: {e}{Colors.ENDC}\n")

def start_server(tunnel=False):
    env_path = PROJECT_ROOT / ".env"
    if not tunnel and env_path.exists():
        if "USE_TUNNEL=true" in env_path.read_text():
            tunnel = True
            
    port = os.environ.get("PORT") or _read_env().get("PORT", "8765")
    if _server_running(port):
        print(f"{Colors.YELLOW}MIA is already running at http://localhost:{port}{Colors.ENDC}")
        return
    print("Starting MIA server...")
    main_py_path = SERVER_DIR / "main.py"
    server_process = None
    tunnel_process = None
    try:
        if tunnel:
            if not shutil.which("cloudflared"):
                print("\ncloudflared is not installed. Attempting to install it via winget...")
                if sys.platform == "win32":
                    subprocess.run(["winget", "install", "--id", "Cloudflare.cloudflared", "--accept-source-agreements", "--accept-package-agreements"])
                    # Refresh PATH in current process is hard, but winget usually puts it in a known location or system PATH
                    # However, if it's not immediately available in PATH, we might need to tell the user to restart the terminal.
                    if not shutil.which("cloudflared"):
                        print("❌ Please restart your terminal and run the command again for the tunnel to work.")
                        return
                else:
                    print("❌ Please install cloudflared manually to use the tunnel feature.")
                    return
            
            from dotenv import load_dotenv
            load_dotenv(env_path)
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            tg_user = os.environ.get("ALLOWED_TELEGRAM_USER_ID")
            
            print("Starting server in background for tunnel...")
            server_process = subprocess.Popen([sys.executable, str(main_py_path)], cwd=str(PROJECT_ROOT))
            import time
            time.sleep(3)
            print("Starting Cloudflare tunnel (Look for .trycloudflare.com URL)...")
            tunnel_process = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", "http://localhost:8765"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            
            t = threading.Thread(target=read_tunnel_output, args=(tunnel_process, tg_token, tg_user))
            t.daemon = True
            t.start()
            
            tunnel_process.wait()
        else:
            subprocess.run([sys.executable, str(main_py_path)], cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        print("MIA server stopped.")
    finally:
        if tunnel_process:
            tunnel_process.terminate()
        if server_process:
            server_process.terminate()

def list_plugins():
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from server.plugins import TOOL_REGISTRY, load_plugins
        load_plugins()
        print(f"Loaded {len(TOOL_REGISTRY)} tools from plugins:")
        for tool_name, tool_data in TOOL_REGISTRY.items():
            print(f"  - {tool_name}: {tool_data['description']}")
    except ImportError as e:
        print(f"Error loading plugins: {e}")

# ── AI Model setup (python mia.py --model [claude|gpt|gemini|ollama]) ──

PROVIDER_ALIASES = {
    "openrouter": "openrouter", "or": "openrouter",
    "claude": "anthropic", "anthropic": "anthropic",
    "gpt": "openai", "openai": "openai", "chatgpt": "openai",
    "gemini": "gemini", "google": "gemini",
    "deepseek": "deepseek",
    "ollama": "ollama",
}

def _load_provider_service():
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from server.services import ai_providers
        from server.config import config
        return ai_providers, config
    except ImportError as e:
        print(f"{Colors.RED}Dependencies are missing ({e}). Run {Colors.YELLOW}python mia.py --setup{Colors.RED} first.{Colors.ENDC}")
        return None, None

def _provider_line(ap, config, pid):
    info = ap.PROVIDERS[pid]
    if pid == "ollama":
        state = "local, no key needed"
    elif pid == "anthropic" and config.ANTHROPIC_AUTH == "login":
        state = "signed in with browser"
    else:
        key = getattr(config, info["key_env"])
        state = f"key saved …{key[-4:]}" if key else "not set up"
    in_use = f" {Colors.GREEN}← in use ({getattr(config, info['model_env'])}){Colors.ENDC}" if pid == config.AI_PROVIDER else ""
    return f"{info['label']:<22} {Colors.DIM}{state}{Colors.ENDC}{in_use}"

def _ask_api_key(ap, config, pid):
    import getpass
    info = ap.PROVIDERS[pid]
    current = getattr(config, info["key_env"])
    print(f"{Colors.DIM}Get a key at: {info['key_url']}{Colors.ENDC}")
    prompt = f"Paste your {info['label']} API key" + (f" (Enter keeps the saved key …{current[-4:]})" if current else "")
    for _ in range(3):
        key = getpass.getpass(f"{Colors.GREEN}?{Colors.ENDC} {prompt} {Colors.DIM}(hidden){Colors.ENDC}: ").strip()
        if not key and current:
            if pid == "anthropic":
                ap._persist("ANTHROPIC_AUTH", "api_key")
            return True
        try:
            ap.save_api_key(pid, key)
            print(f"{Colors.GREEN}✔ Key saved.{Colors.ENDC}")
            return True
        except ap.ProviderError as e:
            print(f"{Colors.RED}✖ {e}{Colors.ENDC}")
    return False

def _find_or_install_ant(ap):
    ant = ap.ant_path()
    if ant:
        return ant
    print(f"{Colors.YELLOW}{ap.ANT_INSTALL_HINT}{Colors.ENDC}")
    if styled_input("Download and install it now? (y/n)", "y", "y").lower() == "y":
        print("Downloading and verifying `ant`…")
        try:
            ant = ap.install_ant()
            print(f"{Colors.GREEN}✔ Installed: {ant}{Colors.ENDC}")
            return ant
        except ap.ProviderError as e:
            print(f"{Colors.RED}✖ {e}{Colors.ENDC}")
    print(f"{Colors.DIM}You can also rerun this and choose the API key option instead.{Colors.ENDC}")
    return None

def _connect_claude(ap, config):
    print(f"\nHow should MIA connect to Claude?")
    print(f"  1. Sign in with your browser  {Colors.DIM}(Claude Console account — no key to copy){Colors.ENDC}")
    print(f"  2. Paste an API key           {Colors.DIM}(https://platform.claude.com/settings/keys){Colors.ENDC}")
    default = "2" if config.ANTHROPIC_AUTH == "api_key" and config.ANTHROPIC_API_KEY else "1"
    if styled_input("Choose (1-2)", default, default) == "2":
        return _ask_api_key(ap, config, "anthropic")

    ant = _find_or_install_ant(ap)
    if not ant:
        return False
    if config.ANTHROPIC_AUTH == "login":
        if styled_input("You're already signed in. Sign in again? (y/n)", "n", "n").lower() != "y":
            return True

    remote = styled_input("Open the browser on this PC? (n = show a link to open on any device, then paste the code here)", "y", "y").lower() == "n"
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    print(f"{Colors.CYAN}Starting Claude sign-in… finish it in the browser, then come back here.{Colors.ENDC}\n")
    code = subprocess.run([ant, "auth", "login"] + (["--no-browser"] if remote else []), env=env).returncode
    if code != 0:
        print(f"{Colors.RED}✖ Sign-in didn't finish (exit code {code}).{Colors.ENDC}")
        return False
    ap.set_claude_auth_mode("login")
    print(f"{Colors.GREEN}✔ Signed in.{Colors.ENDC}")
    return True

def _pick_openrouter_model(ap, current):
    """Ask for an OpenRouter model: an exact id, or words to search the live catalogue."""
    try:
        catalogue = {m["id"]: m for m in ap.openrouter_models()}
    except ap.ProviderError as e:
        print(f"{Colors.YELLOW}{e} — type the model id directly.{Colors.ENDC}")
        return styled_input("Model", current, current).strip()

    print(f"{Colors.DIM}{len(catalogue)} models with tool support. Type an id, or words to search (e.g. 'claude', 'gemini flash', 'free').{Colors.ENDC}")
    query = styled_input("Model", current, current).strip()
    while True:
        if query in catalogue:
            m = catalogue[query]
            print(f"{Colors.DIM}{m['name']} · ${m['input_per_m']} in / ${m['output_per_m']} out per 1M tokens{Colors.ENDC}")
            return query
        matches = ap.search_openrouter_models(query, limit=10)
        if not matches:
            query = styled_input(f"No model matches '{query}'. Search again", current, current).strip()
            continue
        for i, m in enumerate(matches, 1):
            print(f"  {i:>2}. {m['id']:<42} {Colors.DIM}${m['input_per_m']}/${m['output_per_m']} per 1M{Colors.ENDC}")
        choice = styled_input("Pick a number, or type another search", "1", "1").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            query = matches[int(choice) - 1]["id"]
        else:
            query = choice

def _openrouter_browser_code(ap):
    """Sign in on this PC: open the browser and catch OpenRouter's redirect on a temporary localhost page."""
    import http.server
    import threading
    import webbrowser
    import urllib.parse as up

    received = {}
    done = threading.Event()

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = up.parse_qs(up.urlparse(self.path).query)
            if "code" in query:
                received["code"] = query["code"][0]
                body = "<h2>OpenRouter connected.</h2><p>You can close this tab and go back to the terminal.</p>"
                done.set()
            else:
                body = "<h2>No sign-in code received.</h2><p>Go back to the terminal and try again.</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Callback)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = ap.openrouter_auth_start(f"http://localhost:{server.server_port}/callback")
    print(f"{Colors.CYAN}Opening your browser to sign in to OpenRouter… (waiting up to 5 minutes, Ctrl+C to cancel){Colors.ENDC}")
    print(f"{Colors.DIM}If it didn't open, visit: {url}{Colors.ENDC}")
    webbrowser.open(url)
    try:
        done.wait(timeout=300)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return received.get("code")

def _connect_openrouter(ap, config):
    if config.OPENROUTER_API_KEY:
        keep = styled_input(f"OpenRouter is already connected (key …{config.OPENROUTER_API_KEY[-4:]}). Keep it? (y/n)", "y", "y")
        if keep.lower() == "y":
            return True
    print(f"\nHow should MIA connect to OpenRouter?")
    print(f"  1. Sign in with your browser on this PC  {Colors.DIM}(no key to copy){Colors.ENDC}")
    print(f"  2. Sign in on another device             {Colors.DIM}(open a link, paste the code back){Colors.ENDC}")
    print(f"  3. Paste an API key                      {Colors.DIM}(https://openrouter.ai/settings/keys){Colors.ENDC}")
    choice = styled_input("Choose (1-3)", "1", "1")
    if choice == "3":
        return _ask_api_key(ap, config, "openrouter")
    if choice == "2":
        url = ap.openrouter_auth_start(None)
        print(f"Open this link, approve, and copy the code it shows:\n  {Colors.CYAN}{url}{Colors.ENDC}")
        code = styled_input("Paste the code").strip()
    else:
        code = _openrouter_browser_code(ap)
    if not code:
        print(f"{Colors.RED}✖ No sign-in code received.{Colors.ENDC}")
        return False
    try:
        ap.openrouter_auth_finish(code)
    except ap.ProviderError as e:
        print(f"{Colors.RED}✖ {e}{Colors.ENDC}")
        return False
    print(f"{Colors.GREEN}✔ OpenRouter connected — key saved.{Colors.ENDC}")
    return True

def configure_ai_model(preselect=None):
    """Interactive: choose provider + model, connect (browser sign-in or API key), test, and save to .env."""
    import asyncio

    ap, config = _load_provider_service()
    if not ap:
        return False
    ids = list(ap.PROVIDERS)

    print(f"\n{Colors.CYAN}{Colors.BOLD}--- AI Model ---{Colors.ENDC}")
    if preselect:
        pid = PROVIDER_ALIASES.get(preselect.lower())
        if not pid:
            print(f"{Colors.RED}Unknown provider '{preselect}'. Use: openrouter, claude, gpt, gemini, deepseek or ollama.{Colors.ENDC}")
            return False
    else:
        for i, provider_id in enumerate(ids, 1):
            print(f"  {i}. {_provider_line(ap, config, provider_id)}")
        default = str(ids.index(config.AI_PROVIDER) + 1) if config.AI_PROVIDER in ids else "1"
        choice = styled_input(f"Choose a provider (1-{len(ids)})", default, default)
        if not choice.isdigit() or not 1 <= int(choice) <= len(ids):
            print(f"{Colors.RED}Invalid choice.{Colors.ENDC}")
            return False
        pid = ids[int(choice) - 1]

    info = ap.PROVIDERS[pid]
    current_model = getattr(config, info["model_env"]) or info["models"][0]
    if pid == "openrouter":
        model = _pick_openrouter_model(ap, current_model)
    else:
        print(f"{Colors.DIM}Suggested models: {', '.join(info['models'])}{Colors.ENDC}")
        model = styled_input("Model", current_model, current_model).strip()

    if pid == "openrouter":
        connected = _connect_openrouter(ap, config)
    elif pid == "anthropic":
        connected = _connect_claude(ap, config)
    elif info["key_env"]:
        connected = _ask_api_key(ap, config, pid)
    else:
        print(f"{Colors.DIM}Ollama runs locally at {config.OLLAMA_BASE_URL}. Pull the model first: ollama pull {model}{Colors.ENDC}")
        connected = True
    if not connected:
        print(f"{Colors.YELLOW}Model not changed.{Colors.ENDC}")
        return False

    print("Testing connection…")
    result = asyncio.run(ap.test_provider(pid, model))
    if result["ok"]:
        print(f"{Colors.GREEN}✔ {result['message']}{Colors.ENDC}")
    else:
        print(f"{Colors.RED}✖ {result['message']}{Colors.ENDC}")
        if styled_input("Use this model anyway? (y/n)", "n", "n").lower() != "y":
            print(f"{Colors.YELLOW}Model not changed.{Colors.ENDC}")
            return False

    try:
        ap.set_active(pid, model)
    except ap.ProviderError as e:
        print(f"{Colors.RED}✖ {e}{Colors.ENDC}")
        return False
    print(f"{Colors.GREEN}{Colors.BOLD}✔ MIA will use {info['label']} · {model}.{Colors.ENDC}")
    print(f"{Colors.DIM}If MIA is already running, restart it (or switch models live in the web UI under Settings → AI Models).{Colors.ENDC}")
    return True

# ── Onboarding wizard (mia onboard) ──────────────────────────

REPO_URL = "https://github.com/darshanpatel4/MIA"
STARTUP_BAT = Path(os.getenv("APPDATA") or "") / r"Microsoft\Windows\Start Menu\Programs\Startup" / "mia_startup.bat"
REQUIRED_MODULES = ["fastapi", "uvicorn", "dotenv", "openai", "anthropic", "google.genai", "telegram", "apscheduler", "mss", "pyautogui"]

def _env_file():
    return PROJECT_ROOT / ".env"

def _read_env():
    values = {}
    if _env_file().exists():
        for line in _env_file().read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"\'')
    return values

def _set_env(key, value):
    """Update one setting in .env, keeping everything else (and comments) as it is."""
    from dotenv import set_key
    _env_file().touch(exist_ok=True)
    set_key(str(_env_file()), key, str(value), quote_mode="never")
    os.environ[key] = str(value)

def _missing_modules():
    import importlib.util
    missing = []
    for name in REQUIRED_MODULES:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except ModuleNotFoundError:
            missing.append(name)
    return missing

def _ensure_dependencies():
    missing = _missing_modules()
    if not missing:
        print(f"{Colors.GREEN}✔ All dependencies are installed.{Colors.ENDC}")
        return True
    print(f"{Colors.YELLOW}Missing: {', '.join(missing)}{Colors.ENDC}")
    if styled_input("Install them now? (y/n)", "y", "y").lower() != "y":
        return False
    code = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(SERVER_DIR / "requirements.txt")]).returncode
    if code != 0 or _missing_modules():
        print(f"{Colors.RED}✖ Installing dependencies failed.{Colors.ENDC}")
        return False
    return True

def _step(n, total, title):
    print(f"\n{Colors.CYAN}{Colors.BOLD}➜ [{n}/{total}] {title}{Colors.ENDC}")

def _yes(prompt, default=True):
    d = "y" if default else "n"
    return styled_input(f"{prompt} (y/n)", d, d).strip().lower().startswith("y")

def _setup_password(env):
    import getpass
    import secrets
    if env.get("MIA_PASSWORD") and env.get("MIA_PASSWORD") != "changeme":
        if _yes("A login password is already set. Keep it?"):
            return
    print(f"{Colors.DIM}You'll use this password to log in to MIA's web page (from this PC or your phone).{Colors.ENDC}")
    while True:
        first = getpass.getpass(f"{Colors.GREEN}?{Colors.ENDC} Choose a password (hidden): ")
        if len(first) < 8:
            print(f"{Colors.RED}Use at least 8 characters — this password protects full control of your PC.{Colors.ENDC}")
            continue
        if getpass.getpass(f"{Colors.GREEN}?{Colors.ENDC} Type it again: ") != first:
            print(f"{Colors.RED}The passwords don't match. Try again.{Colors.ENDC}")
            continue
        break
    _set_env("MIA_PASSWORD", first)
    if not env.get("JWT_SECRET"):
        _set_env("JWT_SECRET", secrets.token_hex(32))
    print(f"{Colors.GREEN}✔ Password saved.{Colors.ENDC}")

def _telegram_api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as response:
        data = json.loads(response.read())
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram error"))
    return data["result"]

def _setup_telegram(env):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if token and env.get("ALLOWED_TELEGRAM_USER_ID"):
        if _yes("Telegram is already connected. Keep it?"):
            return
    elif not _yes("Connect Telegram so you can chat with MIA and get alerts on your phone?", default=False):
        return

    print(f"{Colors.DIM}1. In Telegram, open @BotFather and send /newbot\n"
          f"2. Pick a name and a username for your bot\n"
          f"3. BotFather replies with a token like 123456:ABC-DEF… — paste it below{Colors.ENDC}")
    bot = None
    for _ in range(3):
        token = styled_input("Bot token").strip()
        if not token:
            return
        try:
            bot = _telegram_api(token, "getMe")
            print(f"{Colors.GREEN}✔ Found your bot: @{bot['username']}{Colors.ENDC}")
            break
        except Exception as e:
            print(f"{Colors.RED}✖ That token didn't work ({e}).{Colors.ENDC}")
    if not bot:
        return

    # Find the owner's user id automatically from a message they send to the bot.
    user_id = None
    print(f"\nNow open {Colors.CYAN}https://t.me/{bot['username']}{Colors.ENDC} and send your bot any message (e.g. \"hi\").")
    for _ in range(3):
        input(f"{Colors.GREEN}?{Colors.ENDC} Press Enter after you've sent it… ")
        try:
            updates = _telegram_api(token, "getUpdates", {"timeout": 5})
        except Exception as e:
            print(f"{Colors.YELLOW}Couldn't read messages ({e}). If MIA is already running, stop it and try again.{Colors.ENDC}")
            continue
        senders = [u["message"]["from"] for u in updates if "message" in u and "from" in u["message"]]
        if not senders:
            print(f"{Colors.YELLOW}No message yet — make sure you sent it to @{bot['username']}.{Colors.ENDC}")
            continue
        who = senders[-1]
        label = " ".join(filter(None, [who.get("first_name"), who.get("last_name")])) + (f" (@{who['username']})" if who.get("username") else "")
        if _yes(f"Is this you: {label}, id {who['id']}?"):
            user_id = str(who["id"])
            break
    if not user_id:
        user_id = styled_input("Enter your Telegram user id manually (or leave empty to skip)").strip()
        if not user_id.isdigit():
            print(f"{Colors.YELLOW}Telegram not connected.{Colors.ENDC}")
            return
    _set_env("TELEGRAM_BOT_TOKEN", token)
    _set_env("ALLOWED_TELEGRAM_USER_ID", user_id)
    print(f"{Colors.GREEN}✔ Telegram connected. Only you (id {user_id}) can talk to the bot.{Colors.ENDC}")

def _write_startup_entry(enabled):
    if os.name != "nt":
        return
    if enabled:
        STARTUP_BAT.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_BAT.write_text(
            f'@echo off\ncd /d "{PROJECT_ROOT}"\nset PYTHONUTF8=1\nstart "MIA Server" /MIN "{sys.executable}" mia.py start\n',
            encoding="utf-8")
        print(f"{Colors.GREEN}✔ MIA will start when you log in to Windows.{Colors.ENDC}")
    elif STARTUP_BAT.exists():
        STARTUP_BAT.unlink()
        print(f"{Colors.YELLOW}ℹ Removed from Windows startup.{Colors.ENDC}")

def run_onboard():
    """Step-by-step first-time setup. Safe to re-run: every step keeps what's already set unless you change it."""
    print_banner()
    total = 6
    print(f"Welcome! This sets up MIA in a few steps. Press Enter to accept the {Colors.YELLOW}[default]{Colors.ENDC}.")

    _step(1, total, "Dependencies")
    if not _ensure_dependencies():
        print(f"{Colors.RED}MIA can't run without its dependencies. Fix the error above, then run {Colors.YELLOW}mia onboard{Colors.RED} again.{Colors.ENDC}")
        return

    env = _read_env()
    _step(2, total, "Login password")
    _setup_password(env)
    for key, value in (("HOST", "0.0.0.0"), ("PORT", "8765")):
        if key not in env:
            _set_env(key, value)

    _step(3, total, "AI model")
    env = _read_env()
    current = env.get("AI_PROVIDER")
    if current and _yes(f"MIA currently uses '{current}'. Keep it?"):
        pass
    else:
        print(f"{Colors.DIM}Tip: OpenRouter gives you hundreds of models (Claude, GPT, Gemini…) with one browser sign-in.{Colors.ENDC}")
        configure_ai_model()

    _step(4, total, "Telegram (optional)")
    _setup_telegram(_read_env())

    _step(5, total, "Access from your phone or another PC")
    print(f"{Colors.DIM}A Cloudflare Quick Tunnel gives MIA a temporary public https link each time it starts — no domain or router setup needed.{Colors.ENDC}")
    tunnel = _yes("Turn on remote access?", default=_read_env().get("USE_TUNNEL", "false").lower() == "true")
    _set_env("USE_TUNNEL", "true" if tunnel else "false")

    _step(6, total, "Start with Windows")
    if os.name == "nt":
        _write_startup_entry(_yes("Start MIA automatically when you log in to Windows?", default=STARTUP_BAT.exists()))
    else:
        print("Only available on Windows.")

    env = _read_env()
    port = env.get("PORT", "8765")
    print(f"\n{Colors.GREEN}{Colors.BOLD}✔ MIA is set up!{Colors.ENDC}")
    print(f"  • Web page:  {Colors.CYAN}http://localhost:{port}{Colors.ENDC}" + ("  (plus a public link printed when MIA starts)" if tunnel else ""))
    print(f"  • AI model:  {env.get('AI_PROVIDER', '?')}")
    print(f"  • Telegram:  {'connected' if env.get('TELEGRAM_BOT_TOKEN') else 'not connected'}")
    print(f"  • Check anytime with {Colors.YELLOW}mia status{Colors.ENDC}")
    print()
    if _yes("Start MIA now?"):
        start_server(tunnel=tunnel)

def run_setup():
    """Old name for the wizard (`--setup`)."""
    run_onboard()

# ── mia status ───────────────────────────────────────────────

def _server_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/login", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def run_status():
    ok, warn, bad = f"{Colors.GREEN}✔{Colors.ENDC}", f"{Colors.YELLOW}!{Colors.ENDC}", f"{Colors.RED}✖{Colors.ENDC}"
    env = _read_env()
    port = env.get("PORT", "8765")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"\n{Colors.CYAN}{Colors.BOLD}MIA status{Colors.ENDC}")
    print(f" {ok} Folder:      {PROJECT_ROOT}")
    print(f" {ok if sys.version_info >= (3, 10) else bad} Python:      {sys.version.split()[0]} {'(private environment)' if in_venv else '(system Python)'}")
    missing = _missing_modules()
    print(f" {bad if missing else ok} Packages:    {'missing ' + ', '.join(missing) + ' — run mia onboard' if missing else 'all installed'}")
    if not _env_file().exists():
        print(f" {bad} Settings:    no .env yet — run {Colors.YELLOW}mia onboard{Colors.ENDC}")
        return
    print(f" {ok if env.get('MIA_PASSWORD') and env.get('MIA_PASSWORD') != 'changeme' else bad} Password:    {'set' if env.get('MIA_PASSWORD') not in (None, '', 'changeme') else 'not set — run mia onboard'}")

    provider = env.get("AI_PROVIDER", "gemini")
    key_env = {"openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
               "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(provider)
    model = env.get({"openrouter": "OPENROUTER_MODEL", "anthropic": "ANTHROPIC_MODEL", "openai": "OPENAI_MODEL",
                     "gemini": "GEMINI_MODEL", "deepseek": "DEEPSEEK_MODEL", "ollama": "OLLAMA_MODEL"}.get(provider, ""), "default")
    connected = provider == "ollama" or (provider == "anthropic" and env.get("ANTHROPIC_AUTH") == "login") or bool(key_env and env.get(key_env))
    print(f" {ok if connected else bad} AI model:    {provider} · {model}{'' if connected else ' — not connected, run mia model'}")
    print(f" {ok if env.get('TELEGRAM_BOT_TOKEN') and env.get('ALLOWED_TELEGRAM_USER_ID') else warn} Telegram:    {'connected' if env.get('TELEGRAM_BOT_TOKEN') else 'not connected (optional)'}")
    tunnel = env.get("USE_TUNNEL", "false").lower() == "true"
    cloudflared = shutil.which("cloudflared")
    print(f" {ok if not tunnel or cloudflared else warn} Remote:      {'on' if tunnel else 'off'}{'' if not tunnel or cloudflared else ' (cloudflared gets installed on first start)'}")
    print(f" {ok} Startup:     {'starts with Windows' if STARTUP_BAT.exists() else 'manual (mia start)'}")
    automations = PROJECT_ROOT / "data" / "automations.json"
    if automations.exists():
        try:
            data = json.loads(automations.read_text(encoding="utf-8"))
            active = sum(1 for t in data.get("tasks", []) if t.get("enabled"))
            print(f" {ok} Automations: {active} active task(s), heartbeat {'on' if data.get('heartbeat', {}).get('enabled') else 'off'}")
        except Exception:
            pass
    running = _server_running(port)
    print(f" {ok if running else warn} Server:      {'running at http://localhost:' + port if running else 'not running — start it with mia start'}")

# ── mia update ───────────────────────────────────────────────

def run_update():
    print(f"{Colors.CYAN}Updating MIA in {PROJECT_ROOT}…{Colors.ENDC}")
    if (PROJECT_ROOT / ".git").exists() and shutil.which("git"):
        if subprocess.run(["git", "-C", str(PROJECT_ROOT), "pull", "--ff-only"]).returncode != 0:
            print(f"{Colors.RED}✖ git pull failed (you may have local changes). Nothing was changed.{Colors.ENDC}")
            return
    else:
        import io
        import tempfile
        import zipfile
        url = f"{REPO_URL}/archive/refs/heads/main.zip"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MIA-agent"}), timeout=120) as r:
                archive = r.read()
        except Exception as e:
            print(f"{Colors.RED}✖ Download failed: {e}{Colors.ENDC}")
            return
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(io.BytesIO(archive)).extractall(tmp)
            src = next(Path(tmp).iterdir())
            # .env and data/ aren't in the download, so settings and memory are kept
            shutil.copytree(src, PROJECT_ROOT, dirs_exist_ok=True)
    print("Updating dependencies…")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(SERVER_DIR / "requirements.txt"),
                    "--quiet", "--disable-pip-version-check"])
    print(f"{Colors.GREEN}✔ Updated.{Colors.ENDC} Restart MIA if it's running.")

def remove_from_startup():
    if os.name == 'nt':
        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        bat_path = os.path.join(startup_dir, 'mia_startup.bat')
        if os.path.exists(bat_path):
            try:
                os.remove(bat_path)
                print(f"{Colors.GREEN}✔ Successfully removed MIA from Windows Startup.{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.RED}❌ Failed to remove from Windows Startup: {e}{Colors.ENDC}")
        else:
            print(f"{Colors.YELLOW}ℹ MIA is not currently set to run on Windows Startup.{Colors.ENDC}")
    else:
        print("This feature is only available on Windows.")

def run_reset():
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- MIA Reset Utility ---{Colors.ENDC}")
    print("What would you like to reset?")
    print("  1. Reset Setup (Removes .env and pycache)")
    print("  2. Reset Memory (Clears chat history and long-term memory)")
    print("  3. Reset All (Wipes everything except installed skills)")
    
    choice = styled_input("Choose an option (1-3) or anything else to cancel", "")
    
    reset_setup = choice in ['1', '3']
    reset_memory = choice in ['2', '3']
    
    if not reset_setup and not reset_memory:
        print(f"{Colors.YELLOW}Reset cancelled.{Colors.ENDC}")
        return

    if reset_setup:
        print("\nResetting MIA configuration...")
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            env_path.unlink()
            print(f"{Colors.GREEN}✔ Removed .env file.{Colors.ENDC}")
        
        # Remove pycache
        for pycache in PROJECT_ROOT.rglob('__pycache__'):
            try:
                shutil.rmtree(pycache)
            except Exception:
                pass
        print(f"{Colors.GREEN}✔ Cleared python cache.{Colors.ENDC}")
        
    if reset_memory:
        print("\nResetting MIA memories...")
        data_dir = PROJECT_ROOT / "data"
        
        memory_file = data_dir / "memory.json"
        if memory_file.exists():
            memory_file.unlink()
            print(f"{Colors.GREEN}✔ Deleted long-term memory.{Colors.ENDC}")
            
        sessions_dir = data_dir / "sessions"
        if sessions_dir.exists():
            shutil.rmtree(sessions_dir)
            print(f"{Colors.GREEN}✔ Deleted chat history sessions.{Colors.ENDC}")
            
        error_log = data_dir / "error_log.json"
        if error_log.exists():
            error_log.unlink()
            print(f"{Colors.GREEN}✔ Cleared error logs.{Colors.ENDC}")
            
    print(f"\n{Colors.CYAN}{Colors.BOLD}Reset complete!{Colors.ENDC}")
    if reset_setup:
        print("Run 'mia onboard' to start fresh.")

def install_skill(url):
    # Try to extract a skill name from the URL, fallback to default
    parsed_url = urllib.parse.urlparse(url)
    skill_name = Path(parsed_url.path).parent.name if Path(parsed_url.path).name.lower() == 'skill.md' else Path(parsed_url.path).stem
    if not skill_name:
        skill_name = "downloaded_skill"
        
    skills_dir = PROJECT_ROOT / "data" / "skills" / skill_name
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading skill from {url} into {skill_name} folder...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            
        dest = skills_dir / 'SKILL.md'
        dest.write_text(content, encoding='utf-8')
        print(f"{Colors.GREEN}✔ Successfully installed skill '{skill_name}' to {dest}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}❌ Failed to install skill: {e}{Colors.ENDC}")

def remove_skill(skill_name):
    if skill_name.endswith('.md'):
        skill_name = skill_name[:-3]
    
    skill_path = PROJECT_ROOT / "data" / "skills" / skill_name
    if skill_path.exists() and skill_path.is_dir():
        try:
            shutil.rmtree(skill_path)
            print(f"{Colors.GREEN}[OK] Successfully removed skill: {skill_name}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.RED}[Error] Failed to remove skill: {e}{Colors.ENDC}")
    else:
        print(f"{Colors.YELLOW}ℹ Skill not found: {skill_name}{Colors.ENDC}")

COMMANDS = {
    # mia <command> [args]  ->  the equivalent --flag, so both styles work
    "onboard": "--onboard", "setup": "--onboard", "start": "--start", "status": "--status", "doctor": "--status",
    "update": "--update", "model": "--model", "tools": "--tools", "skills": "--skills",
    "install-skill": "--install-skill", "remove-skill": "--remove-skill", "reset": "--reset",
    "remove-startup": "--remove-startup",
}

def main():
    argv = sys.argv[1:]
    if argv and argv[0] in COMMANDS:
        argv = [COMMANDS[argv[0]]] + argv[1:]

    parser = argparse.ArgumentParser(
        prog="mia",
        description="MIA — your personal AI agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "commands:\n"
            "  mia onboard              step-by-step setup (safe to re-run)\n"
            "  mia start [--tunnel]     start MIA\n"
            "  mia status               check that everything is set up\n"
            "  mia model [provider]     change the AI model (openrouter, claude, gpt, gemini, deepseek, ollama)\n"
            "  mia update               update to the latest version\n"
            "  mia tools | skills       list tools / installed skills\n"
            "  mia install-skill URL    install a skill\n"
            "  mia remove-skill NAME    remove a skill\n"
            "  mia reset                reset settings and/or memory\n"
        ),
    )
    parser.add_argument("--onboard", "--setup", dest="onboard", action="store_true", help="Run the setup wizard.")
    parser.add_argument("--status", action="store_true", help="Check the installation.")
    parser.add_argument("--update", action="store_true", help="Update MIA to the latest version.")
    parser.add_argument("--reset", action="store_true", help="Reset configurations and cache.")
    parser.add_argument("--start", action="store_true", help="Start the MIA server.")
    parser.add_argument("--model", nargs="?", const="", metavar="PROVIDER",
                        help="Choose the AI model and connect it (openrouter, claude, gpt, gemini, deepseek, ollama). OpenRouter and Claude can sign in with your browser.")
    parser.add_argument("--tunnel", action="store_true", help="Use with --start to run a Cloudflare Quick Tunnel.")
    parser.add_argument("--tools", action="store_true", help="List all available tools/plugins.")
    parser.add_argument("--skills", action="store_true", help="List all installed skills.")
    parser.add_argument("--install-skill", type=str, metavar="URL", help="Download and install a skill from a URL.")
    parser.add_argument("--remove-skill", type=str, metavar="NAME", help="Remove an installed skill by its name.")
    parser.add_argument("--remove-startup", action="store_true", help="Remove MIA from Windows startup.")
    
    args = parser.parse_args(argv)
    
    if args.onboard:
        run_onboard()
    elif args.status:
        run_status()
    elif args.update:
        run_update()
    elif args.reset:
        run_reset()
    elif args.start:
        start_server(tunnel=args.tunnel)
    elif args.model is not None:
        configure_ai_model(args.model or None)
    elif args.tools:
        list_plugins()
    elif args.install_skill:
        install_skill(args.install_skill)
    elif args.remove_skill:
        remove_skill(args.remove_skill)
    elif args.remove_startup:
        remove_from_startup()
    elif args.skills:
        skills_dir = PROJECT_ROOT / "data" / "skills"
        if skills_dir.exists():
            skills = [d.name for d in skills_dir.iterdir() if d.is_dir() and (d / 'SKILL.md').exists()]
            if skills:
                print(f"Installed skills ({len(skills)}):")
                for s in sorted(skills):
                    print(f"  - {s}")
            else:
                print("No skills installed yet.")
        else:
            print("No skills installed yet.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
