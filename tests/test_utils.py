from onionscout.utils import (
    extract_onions,
    is_onion,
    is_v3_onion,
    normalize_url,
)

V3 = "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd"


def test_normalize_collapses_trailing_slash_and_case():
    a = normalize_url("HTTP://Example.ONION/path/")
    b = normalize_url("http://example.onion/path")
    assert a == b


def test_normalize_drops_default_ports():
    assert normalize_url("http://x.onion:80/") == normalize_url("http://x.onion/")


def test_is_onion():
    assert is_onion("http://foo.onion/bar")
    assert not is_onion("https://example.com")


def test_is_v3_onion():
    assert is_v3_onion(V3)
    assert is_v3_onion(f"{V3}.onion")
    assert not is_v3_onion("short.onion")


def test_extract_onions_dedupes():
    text = f"visit {V3}.onion and again {V3}.onion plus xmh57jrknzkhv6y3.onion"
    found = extract_onions(text)
    assert f"{V3}.onion" in found
    assert len(found) == len(set(found))
