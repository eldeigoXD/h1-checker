"""
ollama_client.py
================
Thin wrapper around the Ollama local LLM HTTP API.

Usage:
    from ollama_client import ask_ollama, is_ollama_available

    if is_ollama_available():
        result = ask_ollama("Your prompt here", model="phi3:mini")

Design:
  - All calls are fire-and-forget safe: if Ollama is not running, functions
    return None / False and the caller falls back to deterministic logic.
  - Responses are expected in JSON format. ask_ollama_json() parses and returns
    a dict, returning {} on any parse error.
  - The model is configurable via OLLAMA_MODEL env var, defaulting to phi3:mini.
  - Connection is checked once per server session and cached.
"""

import os
import json
import time
import threading
import requests
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL   = os.getenv("OLLAMA_MODEL", "phi3:mini")
DEFAULT_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "45"))   # seconds

# ---------------------------------------------------------------------------
# Availability cache — checked once, re-checked every 5 minutes
# ---------------------------------------------------------------------------
_availability_cache: Optional[bool] = None
_availability_lock  = threading.Lock()
_last_check_ts: float = 0.0
_RECHECK_INTERVAL   = 300  # seconds


def is_ollama_available(force_recheck: bool = False) -> bool:
    """
    Returns True if the local Ollama server is reachable.
    Result is cached for 5 minutes to avoid hammering the endpoint.
    """
    global _availability_cache, _last_check_ts

    with _availability_lock:
        now = time.time()
        if (
            not force_recheck
            and _availability_cache is not None
            and (now - _last_check_ts) < _RECHECK_INTERVAL
        ):
            return _availability_cache

        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            _availability_cache = resp.status_code == 200
        except Exception:
            _availability_cache = False

        _last_check_ts = now
        if _availability_cache:
            print(f"[OllamaClient] OK - Ollama is available at {OLLAMA_BASE_URL}")
        else:
            print(f"[OllamaClient] WARNING - Ollama not reachable at {OLLAMA_BASE_URL} -- LLM features disabled.")
        return _availability_cache


def list_models() -> list[str]:
    """Returns list of locally pulled model names."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ask_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    system: str = "",
) -> Optional[str]:
    """
    Sends a prompt to Ollama and returns the raw string response.
    Returns None if Ollama is unavailable or an error occurs.
    """
    if not is_ollama_available():
        return None

    payload: dict = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        print(f"[OllamaClient] Timeout after {timeout}s for model={model}")
        return None
    except Exception as e:
        print(f"[OllamaClient] Error: {e}")
        return None


def ask_ollama_json(
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
    system: str = "",
    default: Optional[dict] = None,
) -> dict:
    """
    Like ask_ollama() but parses the response as JSON.
    Returns `default` (or {}) if parsing fails or Ollama is unavailable.

    IMPORTANT: Always include instructions to respond in JSON in your prompt.
    Ollama with format="json" only enforces valid JSON structure, not schema.
    """
    if default is None:
        default = {}

    if not is_ollama_available():
        return default

    payload: dict = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "format": "json",   # Forces valid JSON output
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        return json.loads(raw) if raw else default
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[OllamaClient] JSON parse error: {e}")
        return default
    except Exception as e:
        print(f"[OllamaClient] Error: {e}")
        return default


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Checking Ollama...")
    avail = is_ollama_available(force_recheck=True)
    print(f"Available: {avail}")

    if avail:
        models = list_models()
        print(f"Pulled models: {models}")

        result = ask_ollama_json(
            prompt=(
                'You are a JSON API. Reply ONLY with valid JSON.\n'
                'Respond with: {"status": "ok", "message": "Hello from Ollama"}'
            ),
            model=DEFAULT_MODEL,
        )
        print(f"Test response: {result}")
    else:
        print("Install Ollama from https://ollama.com and run: ollama pull phi3:mini")
