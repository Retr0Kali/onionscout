"""Health-check the configured search engines over Tor."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .config import Config, get_config
from .engines import Engine, get_engines
from .fetch import Fetcher


@dataclass
class EngineHealth:
    name: str
    url: str
    up: bool
    status: int | None
    latency_ms: float | None
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__


def check_engines(
    names: list[str] | None = None,
    probe_query: str = "test",
    cfg: Config | None = None,
) -> list[EngineHealth]:
    cfg = cfg or get_config()
    fetcher = Fetcher(cfg)
    engines = get_engines(names)

    def probe(engine: Engine) -> EngineHealth:
        url = engine.query_url(probe_query)
        start = time.perf_counter()
        # Bypass the cache so health reflects the live service.
        res = fetcher.fetch(url, use_cache=False)
        latency = round((time.perf_counter() - start) * 1000, 1) if res.ok else None
        return EngineHealth(
            name=engine.name,
            url=engine.base,
            up=res.ok,
            status=res.status,
            latency_ms=latency,
            error=res.error,
        )

    results: list[EngineHealth] = []
    with ThreadPoolExecutor(max_workers=min(cfg.max_workers, len(engines) or 1)) as pool:
        futures = [pool.submit(probe, e) for e in engines]
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda h: (not h.up, h.name))
    return results
