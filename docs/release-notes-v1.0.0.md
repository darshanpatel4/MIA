## MIA v1.0.0

Personal AI agent with full remote control of a Windows PC — self-hosted, multi-model (Gemini / OpenAI / Ollama), accessible from anywhere via Cloudflare Tunnel.

### Highlights

- **Agentic chat** with real token streaming and a plugin-based tool system (shell commands, file ops, process control, clipboard, screenshots, UI automation)
- **Skills** — drop-in `SKILL.md` capabilities the agent discovers and reads on demand
- **Screen streaming** with full multi-monitor support and remote mouse/keyboard control
- **File manager**, **process manager**, **system monitor**, and a **task scheduler** (one-time or cron)
- **Telegram channel** — talk to the same agent outside the browser
- Password + JWT authentication, all served from a single FastAPI backend with a zero-build vanilla JS frontend

### Notes

- Windows-only (screen capture, input control, and process management use Windows APIs)
- Requires Python 3.10+ and an API key for your chosen AI provider (Gemini has a free tier)
- See the [Security Warning](../README.md#security-warning) in the README before exposing this to the internet — it grants full administrative control to anyone with a valid login token
