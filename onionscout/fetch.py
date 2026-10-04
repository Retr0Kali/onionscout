"""Fetch .onion and clearnet pages through Tor, with retries and caching."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from .cache import PageCache
from .config import Config, get_config
from .tor import TorError, build_session, renew_identity


@dataclass
class FetchResult:
    url: str
    ok: bool
    status: int | None = None
    html: str = ""
    text: str = ""
    title: str = ""
    elapsed_ms: float | None = None
    error: str | None = None
    from_cache: bool = False
    links: list[str] = field(default_factory=list)

    def as_dict(self, include_html: bool = False) -> dict:
        data = {
            "url": self.url,
            "ok": self.ok,
            "status": self.status,
            "title": self.title,
            "text": self.text,
            "elapsed_ms": self.elapsed_ms,
            "from_cache": self.from_cache,
            "links": self.links,
            "error": self.error,
        }
        if include_html:
            data["html"] = self.html
        return data


def _extract(html: str, base_url: str) -> tuple[str, str, list[str]]:
    """Return (title, readable_text, outbound_links) from an HTML document."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    text = " ".join(soup.get_text(" ", strip=True).split())
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        if href not in seen:
            seen.add(href)
            links.append(href)
    return title, text, links


class Fetcher:
    """Reusable fetcher holding a Tor session and (optional) cache."""

    def __init__(self, cfg: Config | None = None, session: requests.Session | None = None):
        self.cfg = cfg or get_config()
        self.session = session or build_session(self.cfg)
        self.cache = PageCache(self.cfg)

    def fetch(self, url: str, use_cache: bool = True) -> FetchResult:
        if "://" not in url:
            url = "http://" + url  # .onion services are plain http far more often

        if use_cache:
            cached = self.cache.get(url)
            if cached is not None:
                status, html = cached
                title, text, links = _extract(html, url)
                return FetchResult(
                    url=url, ok=200 <= status < 400, status=status, html=html,
                    text=text, title=title, links=links, from_cache=True, elapsed_ms=0.0,
                )

        last_error: str | None = None
        for attempt in range(self.cfg.max_retries + 1):
            start = time.perf_counter()
            try:
                resp = self.session.get(
                    url, timeout=self.cfg.request_timeout, allow_redirects=True
                )
                elapsed = (time.perf_counter() - start) * 1000
                html = resp.text
                title, text, links = _extract(html, url)
                if use_cache and 200 <= resp.status_code < 400:
                    self.cache.put(url, resp.status_code, html)
                return FetchResult(
                    url=url, ok=resp.ok, status=resp.status_code, html=html,
                    text=text, title=title, links=links, elapsed_ms=round(elapsed, 1),
                )
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                # On failure, try a fresh circuit before the next attempt — a
                # dead exit node or a throttled circuit is a common cause.
                if attempt < self.cfg.max_retries:
                    try:
                        renew_identity(self.cfg)
                    except TorError:
                        time.sleep(1.0)
        return FetchResult(url=url, ok=False, error=last_error)

    def fetch_many(self, urls: list[str], use_cache: bool = True) -> list[FetchResult]:
        """Fetch several URLs concurrently, preserving input order."""
        results: dict[str, FetchResult] = {}
        workers = min(self.cfg.max_workers, max(1, len(urls)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.fetch, u, use_cache): u for u in urls}
            for fut in as_completed(futures):
                url = futures[fut]
                try:
                    results[url] = fut.result()
                except Exception as exc:  # pragma: no cover - defensive
                    results[url] = FetchResult(url=url, ok=False, error=str(exc))
        return [results[u] for u in urls]

    def is_alive(self, url: str) -> bool:
        """Cheap reachability probe used to filter dead links out of results."""
        res = self.fetch(url, use_cache=True)
        return res.ok
