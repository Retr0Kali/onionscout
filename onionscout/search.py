"""Multi-engine search: query engines concurrently, merge, rank, filter."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .config import Config, get_config
from .engines import Engine, SearchHit, get_engines
from .fetch import Fetcher
from .ranking import RankedHit, rank


@dataclass
class EngineReport:
    name: str
    ok: bool
    hits: int
    error: str | None = None


@dataclass
class SearchResults:
    query: str
    results: list[RankedHit]
    engine_reports: list[EngineReport] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "count": len(self.results),
            "results": [r.as_dict() for r in self.results],
            "engines": [er.__dict__ for er in self.engine_reports],
        }


def _query_engine(
    engine: Engine, query: str, fetcher: Fetcher
) -> tuple[Engine, list[SearchHit], str | None]:
    url = engine.query_url(query)
    res = fetcher.fetch(url, use_cache=True)
    if not res.ok:
        return engine, [], res.error or f"HTTP {res.status}"
    try:
        hits = engine.parse(res.html)
    except Exception as exc:  # a parser failing shouldn't kill the whole search
        return engine, [], f"parse error: {exc}"
    return engine, hits, None


def search(
    query: str,
    engines: list[str] | None = None,
    limit: int = 20,
    check_alive: bool = False,
    cfg: Config | None = None,
    fetcher: Fetcher | None = None,
) -> SearchResults:
    """Run `query` across engines, rank the merged results, return the top `limit`.

    If `check_alive` is set, the top candidates are probed over Tor and dead
    links are dropped — slower, but the surviving results are ones you can
    actually open.
    """
    cfg = cfg or get_config()
    fetcher = fetcher or Fetcher(cfg)
    active = get_engines(engines)

    all_hits: list[SearchHit] = []
    reports: list[EngineReport] = []
    trust = {e.name: e.trust for e in active}

    workers = min(cfg.max_workers, max(1, len(active)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_query_engine, e, query, fetcher): e for e in active}
        for fut in as_completed(futures):
            engine, hits, error = fut.result()
            all_hits.extend(hits)
            reports.append(
                EngineReport(engine.name, ok=error is None, hits=len(hits), error=error)
            )

    ranked = rank(all_hits, query, trust)

    if check_alive and ranked:
        # Probe a generous over-fetch so we can still return `limit` live ones.
        candidates = ranked[: limit * 3]
        urls = [r.url for r in candidates]
        alive_map = {}
        with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
            futs = {pool.submit(fetcher.is_alive, u): u for u in urls}
            for f in as_completed(futs):
                alive_map[futs[f]] = f.result()
        for r in candidates:
            r.alive = alive_map.get(r.url)
        ranked = [r for r in candidates if r.alive] + [
            r for r in ranked[limit * 3:]
        ]

    reports.sort(key=lambda r: r.name)
    return SearchResults(query=query, results=ranked[:limit], engine_reports=reports)
