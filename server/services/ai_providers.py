"""
MIA AI Providers — pick the model MIA thinks with, save API keys, and sign in to Claude with a browser.

Keys are stored in .env (the same place as before) and applied live, so switching models
never needs a restart. Keys are never sent back to the browser — only the last 4 characters.
Used by both the web UI (server/routes/api.py) and the CLI (`python mia.py --model`).
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from dotenv import set_key, unset_key

from server.config import ENV_PATH, config

PROVIDERS = {
    "openrouter": {
        "label": "OpenRouter (all models)",
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "models": ["anthropic/claude-opus-5", "anthropic/claude-sonnet-5", "openai/gpt-4o",
                   "google/gemini-3.8-flash", "deepseek/deepseek-v4.1-flash", "x-ai/grok-4.6"],
        "key_url": "https://openrouter.ai/settings/keys",
        "browser_login": True,
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "models": ["claude-opus-5", "claude-fable-5-1", "claude-sonnet-5", "claude-haiku-4-5"],
        "key_url": "https://platform.claude.com/settings/keys",
        "browser_login": True,
    },
    "openai": {
        "label": "GPT (OpenAI)",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "models": ["gpt-4o"],
        "key_url": "https://platform.openai.com/api-keys",
        "browser_login": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "key_url": "https://platform.deepseek.com/api_keys",
        "browser_login": False,
    },
    "gemini": {
        "label": "Gemini (Google)",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "models": ["gemini-3.5-flash", "gemini-2.5-flash"],
        "key_url": "https://aistudio.google.com/apikey",
        "browser_login": False,
    },
    "ollama": {
        "label": "Ollama (local, free)",
        "key_env": None,
        "model_env": "OLLAMA_MODEL",
        "models": ["llama3"],
        "key_url": None,
        "browser_login": False,
    },
}

ANT_INSTALL_HINT = (
    "Browser sign-in needs Anthropic's official CLI (`ant`). MIA can download it for you "
    "(about 10 MB, from https://github.com/anthropics/anthropic-cli/releases)."
)
ANT_RELEASES_API = "https://api.github.com/repos/anthropics/anthropic-cli/releases/latest"
BIN_DIR = config.DATA_DIR / "bin"  # write-protected from MIA's own tools (see server/selfmod/paths.py)
ANT_EXE = "ant.exe" if os.name == "nt" else "ant"


DEEPSEEK_API = "https://api.deepseek.com"
OPENROUTER_API = "https://openrouter.ai/api/v1"
OPENROUTER_AUTH_URL = "https://openrouter.ai/auth"
OPENROUTER_HEADERS = {"X-Title": "MIA"}  # app attribution shown in the OpenRouter dashboard


class ProviderError(ValueError):
    pass


def _provider(provider_id: str) -> dict:
    if provider_id not in PROVIDERS:
        raise ProviderError(f"Unknown provider: {provider_id}")
    return PROVIDERS[provider_id]


def _persist(name: str, value: str | None):
    """Write a setting to .env, the live environment and the config object."""
    ENV_PATH.touch(exist_ok=True)
    if value is None:
        unset_key(str(ENV_PATH), name)
        os.environ.pop(name, None)
        setattr(config, name, "")
    else:
        set_key(str(ENV_PATH), name, value, quote_mode="never")
        os.environ[name] = value
        setattr(config, name, value)


def _hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "saved"


def ant_path() -> str | None:
    """The Anthropic CLI: the copy MIA installed, one on PATH, or where `go install` puts it."""
    candidates = [
        BIN_DIR / ANT_EXE,
        shutil.which("ant"),
        Path(os.environ.get("GOPATH") or Path.home() / "go") / "bin" / ANT_EXE,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MIA-agent"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def install_ant() -> str:
    """Download the latest official `ant` release for this OS, verify its SHA-256 checksum, install to data/bin."""
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64",
            "x86": "386", "i386": "386", "i686": "386"}.get(platform.machine().lower())
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    if not arch:
        raise ProviderError(f"No `ant` download for this processor ({platform.machine()}).")
    suffix = f"_{system}_{arch}" + (".tar.gz" if system == "linux" else ".zip")

    try:
        release = json.loads(_download(ANT_RELEASES_API))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        archive_name = next((n for n in assets if n.endswith(suffix)), None)
        sums_name = next((n for n in assets if n.endswith("_checksums.txt")), None)
        if not archive_name or not sums_name:
            raise ProviderError(f"The latest `ant` release has no {system}/{arch} download.")
        archive = _download(assets[archive_name])
        sums = _download(assets[sums_name]).decode("utf-8", errors="replace")
    except ProviderError:
        raise
    except Exception as e:
        raise ProviderError(f"Couldn't download `ant`: {e}")

    expected = next((line.split()[0] for line in sums.splitlines() if line.strip().endswith(archive_name)), None)
    if not expected or hashlib.sha256(archive).hexdigest() != expected.lower():
        raise ProviderError("Downloaded `ant` failed its checksum check, so it was not installed.")

    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            member = next((n for n in z.namelist() if Path(n).name == ANT_EXE), None)
            binary = z.read(member) if member else None
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = next((m for m in tar.getmembers() if Path(m.name).name == ANT_EXE and m.isfile()), None)
            binary = tar.extractfile(member).read() if member else None
    if not binary:
        raise ProviderError(f"{archive_name} doesn't contain {ANT_EXE}.")

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / ANT_EXE
    staging = target.with_suffix(".download")
    staging.write_bytes(binary)
    os.replace(staging, target)
    if os.name != "nt":
        target.chmod(0o755)
    return str(target)


def make_deepseek_client():
    """OpenAI-compatible client pointed at DeepSeek."""
    from openai import OpenAI
    if not config.DEEPSEEK_API_KEY:
        raise ValueError("no DeepSeek API key saved — add it in Settings or run `mia model deepseek`")
    return OpenAI(base_url=DEEPSEEK_API, api_key=config.DEEPSEEK_API_KEY)


def make_openrouter_client():
    """OpenAI-compatible client pointed at OpenRouter."""
    from openai import OpenAI
    if not config.OPENROUTER_API_KEY:
        raise ValueError("no OpenRouter key saved — connect OpenRouter in Settings or run `python mia.py --model openrouter`")
    return OpenAI(base_url=OPENROUTER_API, api_key=config.OPENROUTER_API_KEY, default_headers=OPENROUTER_HEADERS)


# ── OpenRouter: model catalogue and browser sign-in (OAuth PKCE) ──

_models_cache: dict = {"at": 0.0, "models": []}
_MODELS_TTL = 3600


def _http_json(url: str, body: dict | None = None, token: str | None = None) -> dict:
    headers = {"User-Agent": "MIA-agent", **OPENROUTER_HEADERS}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def openrouter_models(refresh: bool = False) -> list[dict]:
    """Chat models on OpenRouter that support tool calling (MIA needs tools), cached for an hour."""
    if refresh or not _models_cache["models"] or time.time() - _models_cache["at"] > _MODELS_TTL:
        try:
            raw = _http_json(f"{OPENROUTER_API}/models")["data"]
        except Exception as e:
            if _models_cache["models"]:
                return _models_cache["models"]
            raise ProviderError(f"Couldn't load the OpenRouter model list: {e}")
        models = []
        for m in raw:
            if m["id"].endswith(":batch") or "tools" not in (m.get("supported_parameters") or []):
                continue
            pricing = m.get("pricing") or {}
            models.append({
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "context": m.get("context_length"),
                "input_per_m": round(float(pricing.get("prompt") or 0) * 1_000_000, 3),
                "output_per_m": round(float(pricing.get("completion") or 0) * 1_000_000, 3),
            })
        models.sort(key=lambda m: m["id"])
        _models_cache.update(at=time.time(), models=models)
    return _models_cache["models"]


def search_openrouter_models(query: str, limit: int = 12) -> list[dict]:
    """Models matching every word of the query, best matches first (exact id, then whole-word matches)."""
    query = query.lower().strip()
    words = query.split()

    def score(m):
        text = f"{m['id']} {m['name']}".lower()
        if not all(w in text for w in words):
            return None
        tokens = set(re.split(r"[^a-z0-9.]+", text))
        points = 100 if query == m["id"] else 0
        points += 50 if "-".join(words) in m["id"] else 0
        points += sum(5 if w in tokens else 1 for w in words)
        return points

    scored = [(s, m) for m in openrouter_models() if (s := score(m)) is not None]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [m for _, m in scored[:limit]]


_pkce: dict = {"verifier": None, "at": 0.0}
_PKCE_TTL = 15 * 60


def openrouter_auth_start(callback_url: str | None) -> str:
    """Begin browser sign-in. Returns the URL to open. Without callback_url, OpenRouter shows a code to paste back."""
    verifier = base64.urlsafe_b64encode(os.urandom(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    _pkce.update(verifier=verifier, at=time.time())  # the verifier never leaves the server
    params = {"code_challenge": challenge, "code_challenge_method": "S256", "key_label": "MIA"}
    if callback_url:
        params["callback_url"] = callback_url
    return f"{OPENROUTER_AUTH_URL}?{urllib.parse.urlencode(params)}"


def openrouter_auth_finish(code: str):
    """Exchange the code from the sign-in page for an API key and save it."""
    code = (code or "").strip()
    if not code:
        raise ProviderError("No code received.")
    if not _pkce["verifier"] or time.time() - _pkce["at"] > _PKCE_TTL:
        raise ProviderError("The sign-in expired. Start it again.")
    try:
        result = _http_json(f"{OPENROUTER_API}/auth/keys",
                            body={"code": code, "code_verifier": _pkce["verifier"], "code_challenge_method": "S256"})
    except urllib.error.HTTPError as e:
        raise ProviderError(f"OpenRouter didn't accept that code ({e.code}). Start the sign-in again.")
    except Exception as e:
        raise ProviderError(f"Couldn't reach OpenRouter: {e}")
    _pkce.update(verifier=None, at=0.0)
    key = result.get("key")
    if not key:
        raise ProviderError("OpenRouter didn't return a key.")
    save_api_key("openrouter", key)


def make_anthropic_client():
    """Claude client for the configured auth mode: API key, or the browser sign-in profile."""
    import anthropic

    if config.ANTHROPIC_AUTH == "login":
        # A set key (even an empty one) silently wins over the signed-in profile, so drop it.
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            os.environ.pop(var, None)
        return anthropic.AsyncAnthropic()
    if not config.ANTHROPIC_API_KEY:
        raise ValueError("no Claude API key saved and not signed in with the browser")
    return anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


# ── Status ───────────────────────────────────────────────────

def provider_status() -> dict:
    from server.agent.core import agent

    providers = []
    for provider_id, info in PROVIDERS.items():
        key = getattr(config, info["key_env"], "") if info["key_env"] else ""
        entry = {
            "id": provider_id,
            "label": info["label"],
            "model": getattr(config, info["model_env"]),
            "models": info["models"],
            "key_url": info["key_url"],
            "needs_key": info["key_env"] is not None,
            "key_saved": bool(key),
            "key_hint": _hint(key) if key else None,
            "browser_login": info["browser_login"],
            "active": provider_id == config.AI_PROVIDER,
        }
        if provider_id == "anthropic":
            entry["auth_mode"] = config.ANTHROPIC_AUTH
            entry["ant_installed"] = ant_path() is not None
            entry["ant_install_hint"] = ANT_INSTALL_HINT
        if provider_id == "ollama":
            entry["base_url"] = config.OLLAMA_BASE_URL
        if provider_id == "openrouter":
            entry["recommended"] = True
        entry["ready"] = _is_ready(provider_id, entry)
        providers.append(entry)

    return {
        "active": config.AI_PROVIDER,
        "active_model": agent.model,
        "agent_ready": agent.init_error is None and agent._client is not None,
        "agent_error": agent.init_error,
        "providers": providers,
    }


def _is_ready(provider_id: str, entry: dict) -> bool:
    if provider_id == "ollama":
        return True
    if provider_id == "anthropic" and config.ANTHROPIC_AUTH == "login":
        return True
    return entry["key_saved"]


# ── Changes ──────────────────────────────────────────────────

def save_api_key(provider_id: str, api_key: str):
    info = _provider(provider_id)
    api_key = (api_key or "").strip()
    if not info["key_env"]:
        raise ProviderError(f"{info['label']} doesn't use an API key.")
    if len(api_key) < 16 or any(c.isspace() for c in api_key):
        raise ProviderError("That doesn't look like a valid API key.")
    _persist(info["key_env"], api_key)
    if provider_id == "anthropic":
        _persist("ANTHROPIC_AUTH", "api_key")
    _reload_if_active(provider_id)


def remove_api_key(provider_id: str):
    info = _provider(provider_id)
    if not info["key_env"]:
        raise ProviderError(f"{info['label']} doesn't use an API key.")
    _persist(info["key_env"], None)
    _reload_if_active(provider_id)


def set_active(provider_id: str, model: str | None):
    info = _provider(provider_id)
    model = (model or "").strip() or getattr(config, info["model_env"])
    if not re.fullmatch(r"[\w.:\-/@]{1,100}", model):
        raise ProviderError("Invalid model name.")
    _persist(info["model_env"], model)
    _persist("AI_PROVIDER", provider_id)
    _reload_agent()


def set_claude_auth_mode(mode: str):
    """Switch Claude between the saved API key and the browser sign-in profile."""
    if mode not in ("api_key", "login"):
        raise ProviderError("Auth mode must be 'api_key' or 'login'.")
    if mode == "api_key" and not config.ANTHROPIC_API_KEY:
        raise ProviderError("Save a Claude API key first.")
    _persist("ANTHROPIC_AUTH", mode)
    _reload_if_active("anthropic")


def _reload_if_active(provider_id: str):
    if config.AI_PROVIDER == provider_id:
        _reload_agent()


def _reload_agent():
    """Apply changes to the running agent. From the CLI no agent is loaded, so there's nothing to do."""
    core = sys.modules.get("server.agent.core")
    if core is not None and hasattr(core, "agent"):
        core.agent.reload()


# ── Connection test ──────────────────────────────────────────

async def test_provider(provider_id: str, model: str | None = None) -> dict:
    """Make a cheap authenticated call (look up the model) to check credentials and model name."""
    info = _provider(provider_id)
    model = (model or "").strip() or getattr(config, info["model_env"])
    try:
        if provider_id == "openrouter":
            if not config.OPENROUTER_API_KEY:
                raise ProviderError("No key saved — connect OpenRouter first.")
            key_info = (await asyncio.to_thread(_http_json, f"{OPENROUTER_API}/key", None, config.OPENROUTER_API_KEY))["data"]
            models = {m["id"]: m for m in await asyncio.to_thread(openrouter_models)}
            if model not in models:
                close = ", ".join(m["id"] for m in search_openrouter_models(model.split("/")[-1].split("-")[0], 5))
                raise ProviderError(f"Key works, but '{model}' isn't an OpenRouter model with tool support."
                                    + (f" Did you mean: {close}?" if close else ""))
            credit = key_info.get("limit_remaining")
            credit_text = f", ${credit:.2f} credit left on this key" if isinstance(credit, (int, float)) else ""
            m = models[model]
            detail = f"{m['name']} (${m['input_per_m']}/${m['output_per_m']} per 1M tokens in/out{credit_text})"
        elif provider_id == "anthropic":
            client = make_anthropic_client()
            found = await client.models.retrieve(model)
            detail = found.display_name
        elif provider_id == "deepseek":
            if not config.DEEPSEEK_API_KEY:
                raise ProviderError("No API key saved.")
            names = [m.id for m in await asyncio.to_thread(lambda: list(make_deepseek_client().models.list()))]
            if model not in names:
                raise ProviderError(f"Key works, but '{model}' isn't available. Available: {', '.join(names)}")
            detail = model
        elif provider_id == "openai":
            from openai import OpenAI
            if not config.OPENAI_API_KEY:
                raise ProviderError("No API key saved.")
            found = await asyncio.to_thread(OpenAI(api_key=config.OPENAI_API_KEY).models.retrieve, model)
            detail = found.id
        elif provider_id == "gemini":
            from google import genai
            if not config.GEMINI_API_KEY:
                raise ProviderError("No API key saved.")
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            found = await asyncio.to_thread(client.models.get, model=model)
            detail = found.display_name or found.name
        else:
            from openai import OpenAI
            client = OpenAI(base_url=f"{config.OLLAMA_BASE_URL}/v1", api_key="ollama")
            names = [m.id for m in await asyncio.to_thread(lambda: list(client.models.list()))]
            if model not in names and f"{model}:latest" not in names:
                raise ProviderError(f"Ollama is running but model '{model}' isn't pulled. Available: {', '.join(names) or 'none'}")
            detail = model
        return {"ok": True, "message": f"Connected — {detail} is available."}
    except Exception as e:
        return {"ok": False, "message": _friendly_error(provider_id, e)}


def _friendly_error(provider_id: str, error: Exception) -> str:
    name = type(error).__name__
    text = str(error)
    if isinstance(error, ProviderError):
        return text
    if "Authentication" in name or "401" in text or "resolve authentication" in text:
        if provider_id == "anthropic" and config.ANTHROPIC_AUTH == "login":
            return "Not signed in, or the sign-in expired. Sign in with your browser again."
        return "The API key was rejected. Check it and save it again."
    if "NotFound" in name or "404" in text:
        return "Credentials work, but that model name wasn't found."
    if "PermissionDenied" in name or "403" in text:
        return "This key/account doesn't have access to that model."
    if "Connection" in name:
        return "Couldn't reach the provider. Check your internet connection (or that Ollama is running)."
    return f"{name}: {text[:300]}"


# ── Claude browser sign-in (`ant auth login`) ────────────────

URL_RE = re.compile(r"https://[^\s\"'<>]+")
OUTPUT_LIMIT = 20000


class ClaudeLogin:
    """Runs `ant auth login` and relays its output (and any pasted code) to the web UI."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._output = ""
        self._started_at = 0.0
        self._applied = False
        self._lock = threading.Lock()

    def start(self, no_browser: bool) -> dict:
        executable = ant_path()
        if not executable:
            raise ProviderError(ANT_INSTALL_HINT)
        if self._proc and self._proc.poll() is None:
            return self.status()

        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        cmd = [executable, "auth", "login"] + (["--no-browser"] if no_browser else [])
        self._output = ""
        self._applied = False
        self._started_at = time.time()
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read_output, daemon=True).start()
        return self.status()

    def _read_output(self):
        stream = self._proc.stdout
        while True:
            chunk = stream.read1(4096)  # returns what's available, so prompts without a newline still show
            if not chunk:
                break
            with self._lock:
                self._output = (self._output + chunk.decode("utf-8", errors="replace"))[-OUTPUT_LIMIT:]

    def send_input(self, text: str) -> dict:
        if not self._proc or self._proc.poll() is not None:
            raise ProviderError("Sign-in isn't running.")
        self._proc.stdin.write((text.strip() + "\n").encode("utf-8"))
        self._proc.stdin.flush()
        return self.status()

    def cancel(self) -> dict:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        return self.status()

    def status(self) -> dict:
        if not self._proc:
            return {"state": "idle", "output": "", "urls": []}
        code = self._proc.poll()
        with self._lock:
            output = self._output
        if code is None:
            state = "running"
        elif code == 0:
            state = "success"
            if not self._applied:
                self._applied = True
                _persist("ANTHROPIC_AUTH", "login")
                _reload_if_active("anthropic")
        else:
            state = "failed"
        return {"state": state, "exit_code": code, "output": output, "urls": sorted(set(URL_RE.findall(output)))}


claude_login = ClaudeLogin()
