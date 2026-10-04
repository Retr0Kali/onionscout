"""Small, dependency-free helpers shared across the toolkit."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

# v2 onion addresses are 16 base32 chars; v3 are 56. v2 is deprecated but still
# appears in old indexes, so we recognise both and let the fetcher decide.
_ONION_RE = re.compile(r"\b([a-z2-7]{16}|[a-z2-7]{56})\.onion\b", re.IGNORECASE)
_V3_RE = re.compile(r"^[a-z2-7]{56}$", re.IGNORECASE)


def is_onion(url_or_host: str) -> bool:
    """True if the string references a .onion host."""
    return ".onion" in url_or_host.lower()


def is_valid_onion_host(host: str) -> bool:
    """Strict check that `host` is a syntactically valid v2/v3 onion address."""
    host = host.lower().removesuffix(".onion")
    return bool(_ONION_RE.fullmatch(f"{host}.onion"))


def is_v3_onion(host: str) -> bool:
    host = host.lower().removesuffix(".onion")
    return bool(_V3_RE.match(host))


def extract_onions(text: str) -> list[str]:
    """Return a de-duplicated, order-preserving list of onion hosts in `text`."""
    seen: dict[str, None] = {}
    for match in _ONION_RE.finditer(text):
        seen.setdefault(f"{match.group(0).lower()}", None)
    return list(seen)


def normalize_url(url: str) -> str:
    """Canonicalise a URL so duplicates collapse to one key.

    Lowercases the scheme/host, drops default ports, strips fragments and any
    trailing slash on the path. Query strings are preserved (they can be
    meaningful on search/listing pages).
    """
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    host = host.lower()
    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def host_of(url: str) -> str:
    if "://" not in url:
        url = "http://" + url
    return (urlparse(url).hostname or "").lower()


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
