from onionscout.engines import SearchHit
from onionscout.ranking import rank

TRUST = {"ahmia-clear": 0.95, "torch": 0.6, "haystak": 0.5}


def test_relevant_result_beats_irrelevant():
    hits = [
        SearchHit("Random casino games", "http://aaa.onion/", "play now", "torch"),
        SearchHit("ACME ransomware leak site", "http://bbb.onion/",
                  "ACME ransomware group victims data leak", "ahmia-clear"),
    ]
    ranked = rank(hits, "acme ransomware leak", TRUST)
    assert ranked[0].url == "http://bbb.onion/"


def test_multi_engine_consensus_boosts_score():
    url = "http://shared.onion/"
    single = [SearchHit("Shared site", url, "data", "torch")]
    multi = [
        SearchHit("Shared site", url, "data", "torch"),
        SearchHit("Shared site", url, "data", "haystak"),
        SearchHit("Shared site", url, "data", "ahmia-clear"),
    ]
    one = rank(single, "shared site data", TRUST)[0].score
    three = rank(multi, "shared site data", TRUST)[0].score
    assert three > one


def test_duplicate_urls_are_merged():
    hits = [
        SearchHit("Site", "http://dup.onion/", "a", "torch"),
        SearchHit("Site", "http://dup.onion", "a", "haystak"),  # trailing slash diff
    ]
    ranked = rank(hits, "site", TRUST)
    assert len(ranked) == 1
    assert set(ranked[0].engines) == {"torch", "haystak"}


def test_higher_trust_engine_wins_on_a_tie():
    hits = [
        SearchHit("Thing one", "http://one.onion/", "thing", "haystak"),
        SearchHit("Thing two", "http://two.onion/", "thing", "ahmia-clear"),
    ]
    ranked = rank(hits, "thing", TRUST)
    assert ranked[0].url == "http://two.onion/"
