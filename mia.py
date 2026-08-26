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

def run_setup():
    import secrets
    import getpass
    
    print_banner()
    
    env_path = PROJECT_ROOT / ".env"
    current_config = {}
    if env_path.exists():
        choice = styled_input(".env file already exists. Update while keeping current settings?", "y", "y")
        if choice.lower() != 'y':
            print(f"{Colors.RED}Setup aborted.{Colors.ENDC}")
            return
        
        # Parse existing config
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                current_config[k.strip()] = v.strip()
            
    print(f"\n{Colors.CYAN}{Colors.BOLD}➜ [1/2] Installing Dependencies{Colors.ENDC}")
    print(f"{Colors.DIM}This may take a moment...{Colors.ENDC}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(SERVER_DIR / "requirements.txt")])
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}➜ [2/2] Configuration{Colors.ENDC}")
    
    # AI Provider
    prev_provider = current_config.get("AI_PROVIDER", "gemini")
    provider_map = {"gemini": "1", "openai": "2", "ollama": "3"}
    provider_default = provider_map.get(prev_provider, "1")
    provider_choice = styled_input("Select AI Provider (1: Gemini, 2: OpenAI, 3: Ollama)", provider_default, provider_default)
    
    provider = "gemini"
    gemini_key = current_config.get("GEMINI_API_KEY", "")
    openai_key = current_config.get("OPENAI_API_KEY", "")
    ollama_url = current_config.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = current_config.get("OLLAMA_MODEL", "llama3")
    
    if provider_choice == "2":
        provider = "openai"
        openai_key = styled_input("Enter OpenAI API Key", openai_key[:5] + '...' if openai_key else "", openai_key)
    elif provider_choice == "3":
        provider = "ollama"
        ollama_url = styled_input("Enter Ollama Base URL", ollama_url, ollama_url)
        ollama_model = styled_input("Enter Ollama Model", ollama_model, ollama_model)
    else:
        provider = "gemini"
        print(f"{Colors.DIM}Get your free API key at: https://aistudio.google.com/{Colors.ENDC}")
        gemini_key = styled_input("Enter Gemini API Key", gemini_key[:5] + '...' if gemini_key else "", gemini_key)
        
    password_prompt = "Enter a secure login password for MIA (leave blank to keep current)" if "MIA_PASSWORD" in current_config else "Enter a secure login password for MIA"
    pwd_input = getpass.getpass(f"{Colors.GREEN}?{Colors.ENDC} {password_prompt}: ")
    password = pwd_input if pwd_input else current_config.get("MIA_PASSWORD", "")
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- Network ---{Colors.ENDC}")
    prev_tunnel = current_config.get("USE_TUNNEL", "false").lower() == "true"
    tunnel_default = 'y' if prev_tunnel else 'n'
    use_tunnel_input = styled_input("Use Cloudflare Quick Tunnel by default to access this PC remotely? (y/n)", tunnel_default, tunnel_default)
    use_tunnel = "true" if use_tunnel_input.lower() == 'y' else "false"
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- Telegram Integration (Optional) ---{Colors.ENDC}")
    prev_telegram = current_config.get("TELEGRAM_BOT_TOKEN", "")
    telegram_token = styled_input("Enter Telegram Bot Token (leave blank to keep/skip)", prev_telegram[:5] + '...' if prev_telegram else "", prev_telegram)
    telegram_user_id = current_config.get("ALLOWED_TELEGRAM_USER_ID", "")
    if telegram_token:
        telegram_user_id = styled_input("Enter your personal Telegram User ID", telegram_user_id, telegram_user_id)
        
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- System Startup ---{Colors.ENDC}")
    if os.name == 'nt':
        startup_dir = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
        bat_path = os.path.join(startup_dir, 'mia_startup.bat')
        startup_default = 'y' if os.path.exists(bat_path) else 'n'
            
        start_on_boot_input = styled_input("Start MIA automatically when Windows starts? (y/n)", startup_default, startup_default)
        if start_on_boot_input.lower() == 'y':
            bat_content = f"""@echo off\ncd /d "{PROJECT_ROOT}"\nstart "MIA Server" /MIN python mia.py --start\n"""
            try:
                with open(bat_path, 'w') as f:
                    f.write(bat_content)
                print(f"{Colors.GREEN}✔ Added to Windows Startup.{Colors.ENDC}")
            except Exception as e:
                print(f"{Colors.RED}Failed to add to startup: {e}{Colors.ENDC}")
        else:
            if os.path.exists(bat_path):
                try:
                    os.remove(bat_path)
                    print(f"{Colors.YELLOW}ℹ Removed from Windows Startup.{Colors.ENDC}")
                except Exception as e:
                    pass
                    
    jwt_secret = current_config.get("JWT_SECRET", secrets.token_hex(32))
    tunnel_hostname = current_config.get("TUNNEL_HOSTNAME", "")
    
    env_content = f"""# ============================================
# MIA — Configuration
# Generated by mia.py setup
# ============================================

# --- AI Model Configuration ---
AI_PROVIDER={provider}
GEMINI_API_KEY={gemini_key}
OPENAI_API_KEY={openai_key}
OLLAMA_BASE_URL={ollama_url}
OLLAMA_MODEL={ollama_model}

# --- Security ---
MIA_PASSWORD={password}
JWT_SECRET={jwt_secret}
SESSION_EXPIRY_HOURS=24

# --- Server ---
HOST=0.0.0.0
PORT=8765

# --- Screen Streaming ---
SCREEN_FPS=30
SCREEN_QUALITY=50
SCREEN_AUTO_RESOLUTION=true

# --- Cloudflare Tunnel ---
USE_TUNNEL={use_tunnel}
TUNNEL_HOSTNAME={tunnel_hostname}

# --- Telegram Channel ---
TELEGRAM_BOT_TOKEN={telegram_token}
ALLOWED_TELEGRAM_USER_ID={telegram_user_id}
"""
    env_path.write_text(env_content, encoding="utf-8")
    print(f"\n{Colors.GREEN}{Colors.BOLD}✔ Setup Complete!{Colors.ENDC} .env file updated.")
    print(f"You can now run {Colors.YELLOW}python mia.py --start{Colors.ENDC} to launch MIA.")

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
        print("Run 'python mia.py --setup' to start fresh.")

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

def main():
    parser = argparse.ArgumentParser(description="MIA AI Control CLI")
    parser.add_argument("--setup", action="store_true", help="Run the interactive first-time setup.")
    parser.add_argument("--reset", action="store_true", help="Reset configurations and cache.")
    parser.add_argument("--start", action="store_true", help="Start the MIA server.")
    parser.add_argument("--tunnel", action="store_true", help="Use with --start to run a Cloudflare Quick Tunnel.")
    parser.add_argument("--tools", action="store_true", help="List all available tools/plugins.")
    parser.add_argument("--skills", action="store_true", help="List all installed skills.")
    parser.add_argument("--install-skill", type=str, metavar="URL", help="Download and install a skill from a URL.")
    parser.add_argument("--remove-skill", type=str, metavar="NAME", help="Remove an installed skill by its name.")
    parser.add_argument("--remove-startup", action="store_true", help="Remove MIA from Windows startup.")
    
    args = parser.parse_args()
    
    if args.setup:
        run_setup()
    elif args.reset:
        run_reset()
    elif args.start:
        start_server(tunnel=args.tunnel)
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
