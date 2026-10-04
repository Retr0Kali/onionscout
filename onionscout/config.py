"""Runtime configuration, loaded from the environment (and an optional .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is a hard dependency, but degrade gracefully.
    pass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # Tor SOCKS proxy
    socks_host: str = "127.0.0.1"
    socks_port: int = 9050
    # Tor control port
    control_host: str = "127.0.0.1"
    control_port: int = 9051
    control_password: str = ""
    # Networking
    request_timeout: int = 30
    max_retries: int = 2
    max_workers: int = 8
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; rv:115.0) Gecko/20100101 Firefox/115.0"
    )
    # Cache
    cache_enabled: bool = True
    cache_path: str = ".onionscout_cache.sqlite"
    cache_ttl: int = 86_400
    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-5"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    ollama_host: str = "http://127.0.0.1:11434"

    @property
    def socks_url(self) -> str:
        return f"socks5h://{self.socks_host}:{self.socks_port}"

    @property
    def proxies(self) -> dict[str, str]:
        return {"http": self.socks_url, "https": self.socks_url}


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        socks_host=os.getenv("TOR_SOCKS_HOST", "127.0.0.1"),
        socks_port=_int("TOR_SOCKS_PORT", 9050),
        control_host=os.getenv("TOR_CONTROL_HOST", "127.0.0.1"),
        control_port=_int("TOR_CONTROL_PORT", 9051),
        control_password=os.getenv("TOR_CONTROL_PASSWORD", ""),
        request_timeout=_int("REQUEST_TIMEOUT", 30),
        max_retries=_int("MAX_RETRIES", 2),
        max_workers=_int("MAX_WORKERS", 8),
        cache_enabled=_bool("CACHE_ENABLED", True),
        cache_path=os.getenv("CACHE_PATH", ".onionscout_cache.sqlite"),
        cache_ttl=_int("CACHE_TTL", 86_400),
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
        llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4-5"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
