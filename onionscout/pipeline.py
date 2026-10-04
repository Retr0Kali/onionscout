"""End-to-end investigation: query -> search -> scrape top hits -> analyse."""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyze import Document, analyze
from .config import Config, get_config
from .fetch import Fetcher
from .iocs import IOCSet, extract_iocs, merge_iocs
from .ranking import RankedHit
from .search import search


@dataclass
class PipelineResult:
    query: str
    mode: str
    results: list[RankedHit] = field(default_factory=list)
    scraped: list[dict] = field(default_factory=list)
    iocs: IOCSet = field(default_factory=IOCSet)
    analysis: str = ""

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "mode": self.mode,
            "results": [r.as_dict() for r in self.results],
            "scraped": self.scraped,
            "iocs": self.iocs.as_dict(),
            "analysis": self.analysis,
        }


def run_pipeline(
    query: str,
    mode: str = "threat",
    engines: list[str] | None = None,
    top: int = 5,
    search_limit: int = 20,
    check_alive: bool = True,
    do_analysis: bool = True,
    cfg: Config | None = None,
    progress=None,
) -> PipelineResult:
    """Fully automated investigation.

    `progress` is an optional callable(str) for status updates (the CLI wires
    this to a live spinner).
    """
    cfg = cfg or get_config()
    fetcher = Fetcher(cfg)

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    note(f"Searching {len(engines) if engines else 'all'} engines for “{query}”…")
    sr = search(
        query, engines=engines, limit=search_limit,
        check_alive=check_alive, cfg=cfg, fetcher=fetcher,
    )

    top_hits = sr.results[:top]
    note(f"Scraping top {len(top_hits)} results over Tor…")
    fetched = fetcher.fetch_many([h.url for h in top_hits])

    docs: list[Document] = []
    scraped: list[dict] = []
    ioc_sets: list[IOCSet] = []
    for hit, res in zip(top_hits, fetched, strict=False):
        scraped.append(res.as_dict())
        if res.ok and res.text:
            docs.append(Document(url=res.url, title=res.title or hit.title, text=res.text))
            ioc_sets.append(extract_iocs(res.text))

    note("Extracting indicators of compromise…")
    iocs = merge_iocs(ioc_sets)

    analysis = ""
    if do_analysis and docs:
        note(f"Analysing {len(docs)} pages with the LLM ({cfg.llm_provider})…")
        analysis = analyze(docs, mode=mode, cfg=cfg)
    elif do_analysis:
        analysis = "No readable pages were scraped, so there was nothing to analyse."

    return PipelineResult(
        query=query, mode=mode, results=top_hits, scraped=scraped, iocs=iocs,
        analysis=analysis,
    )
