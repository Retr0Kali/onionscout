"""LLM-powered OSINT synthesis over fetched dark-web material.

Provider-agnostic: pick openai / anthropic / gemini / ollama via config. The
prompts are framed for defensive threat intelligence — summarising what was
found and flagging risk, not assisting wrongdoing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config, get_config
from .utils import truncate

MODES = {
    "threat": (
        "You are a defensive threat-intelligence analyst. Summarise the material "
        "below: what kind of site/actor it appears to be, any indicators of "
        "compromise (domains, wallets, handles, malware families), and the threat "
        "it poses to defenders. Be factual and cite which source each claim comes "
        "from. Do not provide operational guidance for committing crimes."
    ),
    "ransomware": (
        "You are tracking ransomware leak sites for a CERT. From the material "
        "below, identify the ransomware group, any named victims, claimed data, "
        "deadlines, and contact/payment indicators. Produce a structured brief. "
        "This is for victim notification and defence only."
    ),
    "exposure": (
        "You are helping an individual or organisation understand their own "
        "exposure. From the material below, identify any references to the subject "
        "and what personal or corporate data appears to be exposed, so they can "
        "take remediation steps. Do not restate sensitive values in full; redact "
        "them (e.g. show only partial emails)."
    ),
    "summary": (
        "Summarise the material below neutrally and concisely for an analyst: what "
        "each page is, key entities mentioned, and anything noteworthy. Note which "
        "source each point comes from."
    ),
}

MAX_CONTEXT_CHARS = 24_000


@dataclass
class Document:
    url: str
    title: str
    text: str


def _build_context(docs: list[Document]) -> str:
    per_doc = max(800, MAX_CONTEXT_CHARS // max(1, len(docs)))
    parts = []
    for i, d in enumerate(docs, 1):
        parts.append(
            f"[SOURCE {i}] {d.title or '(untitled)'}\nURL: {d.url}\n"
            f"{truncate(d.text, per_doc)}\n"
        )
    return "\n".join(parts)


def _call_anthropic(cfg: Config, system: str, user: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=cfg.anthropic_api_key or None)
    resp = client.messages.create(
        model=cfg.llm_model,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def _call_openai(cfg: Config, system: str, user: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key or None)
    resp = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _call_gemini(cfg: Config, system: str, user: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=cfg.gemini_api_key or None)
    model = genai.GenerativeModel(cfg.llm_model, system_instruction=system)
    return model.generate_content(user).text


def _call_ollama(cfg: Config, system: str, user: str) -> str:
    import requests

    resp = requests.post(
        f"{cfg.ollama_host}/api/chat",
        json={
            "model": cfg.llm_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}


def analyze(docs: list[Document], mode: str = "threat", cfg: Config | None = None) -> str:
    cfg = cfg or get_config()
    if mode not in MODES:
        raise ValueError(f"Unknown mode '{mode}'. Choose from {', '.join(MODES)}.")
    if not docs:
        return "No material was supplied to analyse."

    provider = cfg.llm_provider.lower()
    caller = _PROVIDERS.get(provider)
    if caller is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. Choose from {', '.join(_PROVIDERS)}."
        )

    system = MODES[mode]
    user = (
        "Analyse the following captured dark-web material.\n\n"
        + _build_context(docs)
        + "\n\nProduce your brief now."
    )
    try:
        return caller(cfg, system, user).strip()
    except ImportError as exc:
        return (
            f"The '{provider}' client library is not installed. "
            f"Install extras with: pip install -e \".[llm]\"  ({exc})"
        )
    except Exception as exc:  # surface provider/auth errors without crashing
        return f"LLM analysis failed ({provider}): {exc}"
