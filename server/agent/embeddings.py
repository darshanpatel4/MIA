"""
MIA Embeddings — unified text embedding across AI providers.

Uses whichever provider is already configured (config.AI_PROVIDER) so
long-term memory works with no extra setup or API keys beyond what's
already required for chat.
"""

from server.config import config

# Kept small/stable model choices per provider — not the newest/priciest option.
_GEMINI_EMBED_MODEL = "gemini-embedding-001"
_OPENAI_EMBED_MODEL = "text-embedding-3-small"
_OLLAMA_EMBED_MODEL = "nomic-embed-text"


def embed_text(text: str) -> list[float] | None:
    """Embed a piece of text using the configured AI provider.

    Returns None on failure (e.g. provider unreachable, model missing) so
    callers can degrade gracefully instead of crashing the agent loop.
    """
    if not text or not text.strip():
        return None

    try:
        if config.AI_PROVIDER == "gemini":
            return _embed_gemini(text)
        elif config.AI_PROVIDER == "openai":
            return _embed_openai(text)
        elif config.AI_PROVIDER == "ollama":
            return _embed_ollama(text)
    except Exception as e:
        print(f"  ⚠️  Embedding failed ({config.AI_PROVIDER}): {e}")
        return None

    return None


def _embed_gemini(text: str) -> list[float]:
    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    result = client.models.embed_content(model=_GEMINI_EMBED_MODEL, contents=text)
    return list(result.embeddings[0].values)


def _embed_openai(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    result = client.embeddings.create(model=_OPENAI_EMBED_MODEL, input=text)
    return list(result.data[0].embedding)


def _embed_ollama(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI(base_url=f"{config.OLLAMA_BASE_URL}/v1", api_key="ollama")
    result = client.embeddings.create(model=_OLLAMA_EMBED_MODEL, input=text)
    return list(result.data[0].embedding)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Assumes numpy is available."""
    import numpy as np
    va, vb = np.array(a), np.array(b)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
