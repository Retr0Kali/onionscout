"""Dark-web search-engine definitions and their result parsers.

Each engine knows how to build a query URL and how to pull (title, url, snippet)
tuples out of the returned HTML. Engines carry a `trust` weight (0..1) that the
ranker folds into scoring — well-known, long-lived indexes score higher than
noisy ones. Onion addresses drift over time; treat these as sensible defaults
and override via a local engines file if needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""
    engine: str = ""

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "engine": self.engine,
        }


@dataclass
class Engine:
    name: str
    query_template: str  # must contain "{q}"
    base: str
    trust: float = 0.5
    onion: bool = True
    parser: Callable[[str, Engine], list[SearchHit]] | None = field(default=None)
    enabled: bool = True

    def query_url(self, query: str) -> str:
        return self.query_template.format(q=quote_plus(query))

    def parse(self, html: str) -> list[SearchHit]:
        parser = self.parser or _generic_parser
        hits = parser(html, self)
        for h in hits:
            h.engine = self.name
        return hits


# --- Parsers --------------------------------------------------------------

def _absolute(base: str, href: str) -> str:
    href = href.strip()
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)


def _generic_parser(html: str, engine: Engine) -> list[SearchHit]:
    """Heuristic parser: every anchor that points at an onion/clearnet result.

    Works as a fallback for engines whose markup we don't model precisely. It
    favours links sitting inside result-like containers and skips obvious nav.
    """
    soup = BeautifulSoup(html, "html.parser")
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = _absolute(engine.base, href)
        if ".onion" not in url and engine.onion:
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 3:
            continue
        if url in seen:
            continue
        seen.add(url)
        parent = a.find_parent(["li", "div", "article", "p"])
        snippet = ""
        if parent is not None:
            snippet = parent.get_text(" ", strip=True)
            snippet = snippet.replace(title, "", 1).strip()
        hits.append(SearchHit(title=title, url=url, snippet=snippet[:400]))
    return hits


def _ahmia_parser(html: str, engine: Engine) -> list[SearchHit]:
    """Ahmia renders results as <li class="result"> with an <a> and a cite."""
    soup = BeautifulSoup(html, "html.parser")
    hits: list[SearchHit] = []
    for li in soup.select("li.result"):
        a = li.find("a", href=True)
        if not a:
            continue
        # Ahmia wraps the real target in a redirect: /search/redirect?...&redirect_url=
        href = a["href"]
        url = href
        if "redirect_url=" in href:
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(href).query)
            url = qs.get("redirect_url", [href])[0]
        title = a.get_text(" ", strip=True)
        snippet_tag = li.find("p")
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
        if title and url:
            hits.append(SearchHit(title=title, url=url, snippet=snippet[:400]))
    return hits


# --- Registry -------------------------------------------------------------
# Trust weights are deliberately conservative. Ahmia is the most reliable and
# best-maintained index (and has a clearnet mirror), so it leads.

DEFAULT_ENGINES: list[Engine] = [
    Engine(
        name="ahmia-clear",
        query_template="https://ahmia.fi/search/?q={q}",
        base="https://ahmia.fi",
        trust=0.95,
        onion=False,
        parser=_ahmia_parser,
    ),
    Engine(
        name="ahmia-onion",
        query_template=(
            "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"
            "/search/?q={q}"
        ),
        base="http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
        trust=0.9,
        parser=_ahmia_parser,
    ),
    Engine(
        name="torch",
        query_template=(
            "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion"
            "/cgi-bin/omega/omega?P={q}"
        ),
        base="http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion",
        trust=0.6,
    ),
    Engine(
        name="onionland",
        query_template=(
            "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion"
            "/search?q={q}"
        ),
        base="http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion",
        trust=0.55,
    ),
    Engine(
        name="haystak",
        query_template=(
            "http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion"
            "/?q={q}"
        ),
        base="http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion",
        trust=0.5,
    ),
]


def load_engines_file(path: str) -> list[Engine]:
    """Load custom engine definitions from a JSON or YAML file.

    The file is a list of objects with keys: name, query_template (containing
    "{q}"), base, and optionally trust (0..1), onion (bool), enabled (bool).
    Custom engines use the generic parser. YAML needs PyYAML installed; JSON is
    always supported.
    """
    import json
    import os

    with open(path) as fh:
        raw = fh.read()
    if os.path.splitext(path)[1].lower() in {".yml", ".yaml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyYAML is required to load .yaml engine files.") from exc
        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)

    if not isinstance(data, list):
        raise ValueError("Engines file must contain a list of engine objects.")

    engines: list[Engine] = []
    for item in data:
        if "{q}" not in item.get("query_template", ""):
            raise ValueError(f"Engine '{item.get('name')}' query_template must contain '{{q}}'.")
        engines.append(
            Engine(
                name=item["name"],
                query_template=item["query_template"],
                base=item.get("base", ""),
                trust=float(item.get("trust", 0.5)),
                onion=bool(item.get("onion", True)),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return engines


def get_engines(
    only: list[str] | None = None,
    extra_file: str | None = None,
) -> list[Engine]:
    """Return enabled engines, optionally filtered to `only` names.

    If `extra_file` (or the ONIONSCOUT_ENGINES env var) points at an engines
    file, those definitions are appended to the built-in registry; a custom
    engine whose name matches a built-in one overrides it.
    """
    import os

    registry = list(DEFAULT_ENGINES)
    path = extra_file or os.getenv("ONIONSCOUT_ENGINES")
    if path:
        by_name = {e.name: e for e in registry}
        for custom in load_engines_file(path):
            by_name[custom.name] = custom
        registry = list(by_name.values())

    engines = [e for e in registry if e.enabled]
    if only:
        wanted = {name.lower() for name in only}
        engines = [e for e in engines if e.name.lower() in wanted]
    return engines
