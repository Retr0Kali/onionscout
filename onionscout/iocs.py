"""Indicator-of-compromise (IOC) / entity extraction from scraped text.

Pulls structured indicators out of dark-web pages so an analyst gets machine-
readable intel instead of a wall of text: onion links, crypto wallets, emails,
IPs, PGP material, and CVE references. Extraction is regex-based and heuristic —
it is tuned to minimise obvious false positives but should be treated as leads
to verify, not ground truth.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .utils import extract_onions

# --- Patterns -------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
_ETH_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_BTC_LEGACY_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
_BTC_BECH32_RE = re.compile(r"\bbc1[a-z0-9]{11,71}\b")
_XMR_RE = re.compile(r"\b[48][0-9AB][a-zA-Z0-9]{93}\b")
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_PGP_BLOCK_RE = re.compile(r"-----BEGIN PGP (?:PUBLIC|PRIVATE) KEY BLOCK-----")
# 40-hex PGP fingerprints, optionally spaced in groups of 4.
_PGP_FPR_RE = re.compile(r"\b(?:[0-9A-F]{4}\s?){10}\b")

# Hosts that pollute email/domain extraction — common CDNs / schema noise.
_EMAIL_NOISE = re.compile(r"@(?:example\.com|email\.com|domain\.com|sentry\.io)$", re.I)


@dataclass
class IOCSet:
    onions: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    ipv4: list[str] = field(default_factory=list)
    btc: list[str] = field(default_factory=list)
    eth: list[str] = field(default_factory=list)
    xmr: list[str] = field(default_factory=list)
    pgp_keys: int = 0
    pgp_fingerprints: list[str] = field(default_factory=list)
    cves: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "onions": self.onions,
            "emails": self.emails,
            "ipv4": self.ipv4,
            "crypto": {"btc": self.btc, "eth": self.eth, "xmr": self.xmr},
            "pgp_keys": self.pgp_keys,
            "pgp_fingerprints": self.pgp_fingerprints,
            "cves": self.cves,
        }

    @property
    def total(self) -> int:
        return (
            len(self.onions) + len(self.emails) + len(self.ipv4) + len(self.btc)
            + len(self.eth) + len(self.xmr) + self.pgp_keys
            + len(self.pgp_fingerprints) + len(self.cves)
        )


def _dedupe(values) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        seen.setdefault(v, None)
    return list(seen)


def _looks_like_btc(candidate: str) -> bool:
    # Legacy base58 addresses are 26–35 chars; trim obvious hash/ID lookalikes.
    return 26 <= len(candidate) <= 35


def extract_iocs(text: str) -> IOCSet:
    """Extract a de-duplicated IOCSet from a block of text."""
    emails = [e for e in _EMAIL_RE.findall(text) if not _EMAIL_NOISE.search(e)]
    btc = [b for b in _BTC_LEGACY_RE.findall(text) if _looks_like_btc(b)]
    btc += _BTC_BECH32_RE.findall(text)
    fprs = ["".join(m.split()) for m in _PGP_FPR_RE.findall(text)]

    return IOCSet(
        onions=extract_onions(text),
        emails=_dedupe(emails),
        ipv4=_dedupe(_IPV4_RE.findall(text)),
        btc=_dedupe(btc),
        eth=_dedupe(_ETH_RE.findall(text)),
        xmr=_dedupe(_XMR_RE.findall(text)),
        pgp_keys=len(_PGP_BLOCK_RE.findall(text)),
        pgp_fingerprints=_dedupe(fprs),
        cves=_dedupe(c.upper() for c in _CVE_RE.findall(text)),
    )


def merge_iocs(sets: list[IOCSet]) -> IOCSet:
    """Union several IOCSets into one de-duplicated set."""
    buckets: dict[str, list] = defaultdict(list)
    pgp_keys = 0
    for s in sets:
        buckets["onions"] += s.onions
        buckets["emails"] += s.emails
        buckets["ipv4"] += s.ipv4
        buckets["btc"] += s.btc
        buckets["eth"] += s.eth
        buckets["xmr"] += s.xmr
        buckets["pgp_fingerprints"] += s.pgp_fingerprints
        buckets["cves"] += s.cves
        pgp_keys += s.pgp_keys
    return IOCSet(
        onions=_dedupe(buckets["onions"]),
        emails=_dedupe(buckets["emails"]),
        ipv4=_dedupe(buckets["ipv4"]),
        btc=_dedupe(buckets["btc"]),
        eth=_dedupe(buckets["eth"]),
        xmr=_dedupe(buckets["xmr"]),
        pgp_keys=pgp_keys,
        pgp_fingerprints=_dedupe(buckets["pgp_fingerprints"]),
        cves=_dedupe(buckets["cves"]),
    )
