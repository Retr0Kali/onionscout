from onionscout.engines import get_engines

AHMIA_HTML = """
<html><body>
<ol>
  <li class="result">
    <a href="/search/redirect?redirect_url=http://victim.onion/leak">ACME Leak Site</a>
    <p>Ransomware group ACME published stolen documents.</p>
  </li>
  <li class="result">
    <a href="http://direct.onion/page">Direct Result</a>
    <p>Some snippet here.</p>
  </li>
</ol>
</body></html>
"""

GENERIC_HTML = """
<html><body>
<div class="res"><a href="http://a.onion/">Alpha Market</a><span>buy stuff</span></div>
<div class="nav"><a href="#top">skip</a></div>
<a href="http://b.onion/">Beta Forum</a>
</body></html>
"""


def _engine(name):
    return next(e for e in get_engines() if e.name == name)


def test_ahmia_parser_unwraps_redirect():
    hits = _engine("ahmia-clear").parse(AHMIA_HTML)
    urls = {h.url for h in hits}
    assert "http://victim.onion/leak" in urls
    assert "http://direct.onion/page" in urls
    # Every hit is tagged with the engine name.
    assert all(h.engine == "ahmia-clear" for h in hits)


def test_ahmia_parser_captures_snippet():
    hits = _engine("ahmia-clear").parse(AHMIA_HTML)
    leak = next(h for h in hits if "victim.onion" in h.url)
    assert "ACME" in leak.snippet


def test_generic_parser_skips_fragments_and_keeps_onions():
    hits = _engine("torch").parse(GENERIC_HTML)
    urls = {h.url for h in hits}
    assert "http://a.onion/" in urls
    assert "http://b.onion/" in urls
    assert not any(h.url.endswith("#top") for h in hits)


def test_get_engines_filter():
    only = get_engines(["torch"])
    assert len(only) == 1 and only[0].name == "torch"
