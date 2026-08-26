# MIA — Setup & Startup Scripts

This folder contains the scripts needed to install dependencies, configure your environment, and launch MIA.

## `setup.ps1`
Run this script once to initialize the project. It will:
1. Install Python dependencies (`pip install -r requirements.txt`).
2. Generate a secure `JWT_SECRET`.
3. Interactively prompt you for your chosen AI Provider (Gemini, OpenAI, or Ollama), the respective API Key, and your login password.
4. Generate the `.env` configuration file automatically.

## `start.ps1`
Run this script to start the MIA server. It will:
1. Ensure the Python server runs using Uvicorn.
2. (Optional) Start a Cloudflare quick tunnel to expose your server securely to the internet.

## `tunnel_config.yml`
Template configuration for Cloudflare tunnels. (Used if you want to configure a persistent tunnel with a custom domain later).
