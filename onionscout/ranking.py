"""Relevance ranking — the piece that makes results *accurate*, not just many.

Raw dark-web search engines return noisy, overlapping, often-dead links. We
merge results across engines and score each unique result by:

  1. Query–result term overlap (title weighted higher than snippet/url).
  2. Multi-engine consensus — a result several engines agree on is more
     trustworthy than one a single noisy engine returned.
  3. Engine trust — a hit from a well-maintained index outranks one from a
     spammy one.
  4. Light quality penalties for junk titles and excessive length.

The output is a single, de-duplicated, descending-score list.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .engines import SearchHit
from .utils import host_of, normalize_url

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with",
    "is", "are", "www", "com", "net", "http", "https", "onion",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1]


def _overlap_score(query_tokens: set[str], text: str) -> float:
    """Fraction of query terms present, plus a small bonus for term frequency."""
    if not query_tokens:
        return 0.0
    toks = _tokens(text)
    if not toks:
        return 0.0
    present = query_tokens & set(toks)
    coverage = len(present) / len(query_tokens)
    freq = sum(toks.count(t) for t in present)
    return coverage + 0.05 * math.log1p(freq)


@dataclass
class RankedHit:
    title: str
    url: str
    snippet: str
    engines: list[str]
    score: float
    alive: bool | None = None
    _trust: float = field(default=0.0, repr=False)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "engines": self.engines,
            "score": round(self.score, 4),
            "alive": self.alive,
        }


def _quality_penalty(title: str) -> float:
    t = title.strip()
    if not t:
        return 0.5
    penalty = 0.0
    if len(t) > 140:
        penalty += 0.15
    # Mostly-symbol / all-caps-shouting titles are usually spam.
    alpha = sum(c.isalpha() for c in t)
    if alpha and alpha / len(t) < 0.4:
        penalty += 0.2
    return penalty


def rank(
    hits: list[SearchHit],
    query: str,
    engine_trust: dict[str, float],
) -> list[RankedHit]:
    """Merge hits across engines and return them sorted by descending score."""
    query_tokens = set(_tokens(query))

    merged: dict[str, dict] = {}
    for hit in hits:
        if not hit.url:
            continue
        key = normalize_url(hit.url)
        entry = merged.get(key)
        if entry is None:
            entry = {
                "title": hit.title,
                "url": hit.url,
                "snippet": hit.snippet,
                "engines": set(),
                "trust": 0.0,
            }
            merged[key] = entry
        entry["engines"].add(hit.engine)
        entry["trust"] = max(entry["trust"], engine_trust.get(hit.engine, 0.5))
        # Prefer the longest title/snippet we've seen — usually the richest.
        if len(hit.title) > len(entry["title"]):
            entry["title"] = hit.title
        if len(hit.snippet) > len(entry["snippet"]):
            entry["snippet"] = hit.snippet

    ranked: list[RankedHit] = []
    for entry in merged.values():
        text = f"{entry['title']} {entry['snippet']} {host_of(entry['url'])}"
        relevance = _overlap_score(query_tokens, text)
        consensus = math.log1p(len(entry["engines"]))  # 0, 0.69, 1.1, ...
        trust = entry["trust"]
        penalty = _quality_penalty(entry["title"])

        score = (
            2.0 * relevance
            + 0.6 * consensus
            + 0.8 * trust
            - penalty
        )
        ranked.append(
            RankedHit(
                title=entry["title"].strip() or entry["url"],
                url=entry["url"],
                snippet=entry["snippet"].strip(),
                engines=sorted(entry["engines"]),
                score=score,
                _trust=trust,
            )
        )

    ranked.sort(key=lambda h: h.score, reverse=True)
    return ranked
