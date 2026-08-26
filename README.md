# MIA — Multi-model Interactive Agentic-system

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078d6.svg)](#requirements)

MIA is a self-hosted AI agent that gives you full remote control of your Windows PC from anywhere — a premium web interface, backed by an agentic AI brain (Gemini, OpenAI, or local Ollama models) with function calling, accessible over the internet via Cloudflare Tunnels.

<!--
  Add a screenshot or short screen-recording of the chat UI / screen stream here before sharing this repo —
  it's the single biggest thing that makes a repo feel real. Save it under docs/ (e.g. docs/screenshot.png)
  and uncomment the line below. Don't use a live screenshot that shows real personal file names, open
  tabs, or other identifying content — take a clean one specifically for this.

  ![MIA screenshot](docs/screenshot.png)
-->

## Features

- **Agentic AI Brain** — Gemini, OpenAI, or Ollama with function calling and a plugin-based tool system
- **Skills** — drop-in `SKILL.md` capabilities the agent can read and use, installable/listable/removable from chat
- **Screen Streaming** — real-time remote desktop viewer with adjustable quality/scale, and full multi-monitor support
- **Remote Control** — mouse and keyboard control directly from the browser
- **File Manager** — browse, upload, download, and manage files remotely
- **System Monitor** — live CPU, RAM, disk, and network stats
- **Process Manager** — view, search, and kill running processes
- **Terminal** — interactive shell for raw command execution
- **Task Scheduler** — one-time or recurring (cron) tasks
- **Telegram Channel** — talk to the same agent from Telegram
- **Auth** — password + JWT session authentication

## Architecture

- **Backend**: FastAPI (Python)
- **AI Core**: Google GenAI SDK / OpenAI SDK (agentic loop with streaming function calling)
- **Real-time**: WebSockets (screen stream, system stats, terminal, chat, notifications)
- **Screen Capture**: mss + OpenCV
- **Frontend**: Vanilla HTML/CSS/JS (zero-build SPA)
- **Connectivity**: Cloudflare Tunnels (`cloudflared`)

## Requirements

- Windows 10/11 (screen capture, input control, and process management use Windows APIs)
- Python 3.10+
- An API key from [Google AI Studio](https://aistudio.google.com/) (free tier) if using Gemini — or an OpenAI key, or a local [Ollama](https://ollama.com/) install

## Quick Start

1. Clone the repository and enter the project folder:
   ```powershell
   git clone https://github.com/darshanpatel4/MIA.git
   cd MIA
   ```
   (If you cloned somewhere else, `cd` into wherever that command put it — every step below runs from that folder, whatever your username or drive letter is.)

2. Run the interactive setup script:
   ```powershell
   .\scripts\setup.ps1
   ```
   Installs dependencies, then prompts you to pick an AI provider, enter its API key, and set a login password — writing everything to a new `.env` file.

3. Start the server:
   ```powershell
   .\scripts\start.ps1
   ```
   You'll be asked whether to start a Cloudflare Quick Tunnel. Answer `y` to get a public URL (e.g. `https://something.trycloudflare.com`) you can open from your phone or another PC — no domain required.

4. Open the printed URL (or `http://localhost:8765` if running locally) and log in with the password you set in step 2.

## Configuration

Setup writes these to `.env` (see `.env.example` for the full list with comments):

| Variable | Purpose |
|---|---|
| `AI_PROVIDER` | `gemini`, `openai`, or `ollama` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | API key for the selected provider |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | Local Ollama endpoint and model, if used |
| `MIA_PASSWORD` | Login password |
| `JWT_SECRET` | Session signing secret (auto-generated) |
| `TELEGRAM_BOT_TOKEN` / `ALLOWED_TELEGRAM_USER_ID` | Optional Telegram channel |
| `SCREEN_FPS` / `SCREEN_QUALITY` | Screen stream tuning |

## Security Warning

**This application grants full administrative control over your PC to whoever holds a valid login token.**

- Never share your tunnel URL or login password.
- Use a strong, unique password — this is your only line of defense.
- For long-term/public deployment, put a custom domain behind Cloudflare Access (Zero Trust) for a second authentication layer (SSO, OTP, email auth) in front of MIA's own login.
- Treat `.env` as a secret file — it is already excluded via `.gitignore`, but never commit it or paste its contents anywhere.

## Contributing

Issues and pull requests are welcome. If you're adding a new agent tool, follow the existing pattern in `server/plugins/*.py`; if you're adding a skill, drop a `SKILL.md` under `data/skills/<name>/`.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
