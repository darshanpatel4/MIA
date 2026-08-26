# 🤖 MIA — Multi-model Interactive Agentic-system

**MIA** is a self-hosted, Multi-model Interactive Agentic-system that gives you full control of your Windows PC from anywhere in the world. 

It acts as an autonomous assistant with full system authority, wrapped in a premium WhatsApp-style glassmorphism interface, securely accessible over the internet via Cloudflare Tunnels.

## Features
- **🧠 Agentic AI Brain**: Powered by Gemini (or OpenAI/Ollama) with function calling.
- **📺 30 FPS Screen Streaming**: Real-time remote desktop viewer with adaptive quality.
- **🖱️ Remote Control**: Full mouse and keyboard control directly from your browser.
- **📁 File Manager**: Browse, upload, download, and manage files remotely.
- **📊 System Monitor**: Real-time CPU, RAM, Disk, and Network monitoring.
- **⚙️ Process Manager**: View, search, and kill running processes.
- **🖥️ Terminal**: Interactive shell for raw command execution.
- **⏰ Task Scheduler**: Schedule one-time or recurring (cron) tasks.
- **🔒 Secure**: Password + JWT session authentication.

---

## 🚀 Quick Start (Windows)

### Prerequisites
1. **Python 3.10+** installed and added to PATH.
2. A free API key from Google AI Studio (if using Gemini).

### Installation & Setup

1. Open PowerShell and navigate to the MIA directory:
   ```powershell
   cd "C:\Users\DELL2\Desktop\Coding\Agentic AI"
   ```

2. Run the interactive setup script:
   ```powershell
   .\scripts\setup.ps1
   ```
   *Follow the prompts to select your AI model, enter your API key, and set a secure login password.*

3. Start the server:
   ```powershell
   .\scripts\start.ps1
   ```
   *The script will ask if you want to use a Cloudflare Quick Tunnel. If you answer `y`, it will automatically generate a public internet URL (e.g., `https://something.trycloudflare.com`) that you can use to access MIA from your phone or another PC without needing a domain name!*

---

## 🏗️ Architecture
MIA is built using a modern, performant stack:
- **Backend**: FastAPI (Python)
- **AI Core**: Google GenAI SDK (Function Calling Agentic Loop)
- **Real-time**: WebSockets (Screen stream, System stats, Terminal, Notifications)
- **Screen Capture**: MSS + OpenCV
- **Frontend**: Vanilla HTML/CSS/JS (Zero-build SPA)
- **Connectivity**: Cloudflare Tunnels (`cloudflared`)

## 🛡️ Security Warning
**This application grants FULL ADMINISTRATIVE CONTROL over your PC.**
- Do not share your Quick Tunnel URL with anyone.
- Use a strong password during setup.
- For long-term deployment, it is highly recommended to use a custom domain with Cloudflare Access (Zero Trust) for additional authentication layers (SSO, OTP, Email Auth).
