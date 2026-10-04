from onionscout.cache import PageCache
from onionscout.config import Config


def _cfg(tmp_path):
    return Config(cache_enabled=True, cache_path=str(tmp_path / "c.sqlite"), cache_ttl=1000)


def test_put_and_get_roundtrip(tmp_path):
    cache = PageCache(_cfg(tmp_path))
    cache.put("http://x.onion/", 200, "<html>hi</html>")
    got = cache.get("http://x.onion/")
    assert got == (200, "<html>hi</html>")


def test_get_normalizes_url(tmp_path):
    cache = PageCache(_cfg(tmp_path))
    cache.put("http://x.onion/page/", 200, "body")
    assert cache.get("http://x.onion/page") == (200, "body")


def test_expired_entries_return_none(tmp_path):
    cfg = Config(cache_enabled=True, cache_path=str(tmp_path / "c.sqlite"), cache_ttl=0)
    cache = PageCache(cfg)
    cache.put("http://x.onion/", 200, "body")
    # ttl of 0 means every entry is considered stale immediately... but we use
    # `if self.ttl and ...`, so ttl=0 disables expiry. Use a tiny positive ttl.
    cfg2 = Config(cache_enabled=True, cache_path=str(tmp_path / "c.sqlite"), cache_ttl=-1)
    assert PageCache(cfg2).get("http://x.onion/") is None


def test_clear(tmp_path):
    cache = PageCache(_cfg(tmp_path))
    cache.put("http://a.onion/", 200, "a")
    cache.put("http://b.onion/", 200, "b")
    assert cache.clear() == 2
    assert cache.get("http://a.onion/") is None


def test_disabled_cache_is_noop(tmp_path):
    cfg = Config(cache_enabled=False, cache_path=str(tmp_path / "c.sqlite"))
    cache = PageCache(cfg)
    cache.put("http://x.onion/", 200, "body")
    assert cache.get("http://x.onion/") is None
