<p align="center">
  <img src="assets/logo.svg" alt="OnionScout" width="440">
</p>

<p align="center">
  <strong>Advanced Tor / dark-web OSINT toolkit for threat intelligence and security research.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Tests" src="https://img.shields.io/badge/tests-passing-brightgreen">
  <img alt="Status" src="https://img.shields.io/badge/status-beta-orange">
</p>

OnionScout routes everything through Tor to **search dark-web indexes, scrape
`.onion` and clearnet pages, and synthesise findings with an LLM** — built for
defenders doing threat intelligence, leak monitoring, and exposure checks.

It is a modernised take on the single-script "onion search" tools: the same
workflow, but with **ranked, de-duplicated, liveness-filtered results** instead
of a raw dump of half-dead links, plus concurrency, caching, and a clean,
testable package layout.

---

> ⚖️ **Legal & ethical use only.** OnionScout is a defensive security and
> research tool. Use it only against targets you are authorised to investigate,
> in line with your local laws and your organisation's policy. The authors take
> no responsibility for misuse. It does not bypass authentication, defeat
> CAPTCHAs, or facilitate any illegal transaction — it reads public pages.

---

## ✨ Why it's more accurate

Raw dark-web search engines are noisy: they overlap, return dead links, and rank
by nothing useful. OnionScout adds a dedicated ranking layer
([`ranking.py`](onionscout/ranking.py)) that merges results across every engine
and scores each unique hit by:

| Signal | What it does |
| --- | --- |
| **Query relevance** | Term overlap between your query and the result's title / snippet / host (title weighted highest). |
| **Multi-engine consensus** | A result several engines agree on outranks one a single noisy engine returned. |
| **Engine trust** | Well-maintained indexes (e.g. Ahmia) carry more weight than spammy ones. |
| **Quality penalties** | Junk / all-symbol / overlong titles are demoted. |
| **Liveness filter** | `--check-alive` probes candidates over Tor and drops dead `.onion` links so what you get back actually opens. |

The result is **one ranked, de-duplicated list** — not a pile of overlapping
links.

## 🧰 Features

- **`check`** — confirm traffic exits through Tor and report the exit IP.
- **`renew`** — rotate the Tor circuit (new identity) via the ControlPort.
- **`engines`** — concurrent health-check of every configured search engine.
- **`search`** — query all engines in parallel, rank, de-dupe, optionally filter dead links.
- **`fetch`** — retrieve one or many pages concurrently, with retries + circuit rotation on failure.
- **`analyze`** — LLM OSINT synthesis in four modes (threat / ransomware / exposure / summary).
- **`iocs`** — extract structured indicators: `.onion` links, BTC / ETH / XMR wallets, emails, IPv4, PGP key blocks & fingerprints, CVEs.
- **`pipeline`** — fully automated: *query → search → scrape → extract IOCs → analyse → report*.
- **Custom engines** from a JSON/YAML file, **SQLite page cache**, **JSON output everywhere**, and a **multi-provider LLM** backend (Anthropic / OpenAI / Gemini / Ollama).

## 📦 Install

```bash
git clone https://github.com/yourname/onionscout.git
cd onionscout
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # core
pip install -e ".[llm]"     # + LLM providers (optional)
pip install -e ".[dev]"     # + test tooling
```

### Set up Tor

OnionScout needs a running Tor daemon exposing a SOCKS proxy (and a ControlPort
for `renew`).

```bash
# Debian / Ubuntu
sudo apt install tor
sudo systemctl enable --now tor
```

To enable identity rotation, add to `/etc/tor/torrc`:

```
ControlPort 9051
HashedControlPassword <paste output of: tor --hash-password "yourpassword">
```

Then copy the config template and fill it in:

```bash
cp .env.example .env
# set TOR_CONTROL_PASSWORD and, for `analyze`, your LLM key
```

## 🚀 Usage

```bash
# 1. Are we actually on Tor?
onionscout check

# 2. Which search engines are alive right now?
onionscout engines

# 3. Search — ranked, de-duped, dead links removed
onionscout search "acme corp data leak" --check-alive --limit 15

# 4. Fetch pages (concurrent, cached) and print extracted text
onionscout fetch http://example.onion/ --text

# 5. Extract indicators from a page (or pipe any text in)
onionscout iocs --url http://leak.onion/post
cat dump.txt | onionscout --json iocs | jq '.iocs.crypto'

# 6. LLM analysis over specific pages
onionscout analyze --url http://leak.onion/post --mode ransomware

# 7. Full automated investigation → JSON report on disk
onionscout pipeline "acme corp ransomware" --mode threat --top 5 --out report.json

# Everything speaks JSON for piping into other tools:
onionscout --json search "query" | jq '.results[].url'
```

### Custom search engines

Onion addresses for public indexes rot over time. Point OnionScout at your own
engine list (JSON or YAML) to add private indexes or refresh stale ones — a
custom entry whose `name` matches a built-in one overrides it:

```bash
onionscout search "query" --engines-file examples/engines.sample.json
# or, persistently:
export ONIONSCOUT_ENGINES=examples/engines.sample.json
```

### Analysis modes

| Mode | Use case |
| --- | --- |
| `threat` | General threat-intel brief with indicators of compromise. |
| `ransomware` | Leak-site triage: group, victims, deadlines, contacts. |
| `exposure` | Your own org/identity exposure (redacts sensitive values). |
| `summary` | Neutral, sourced summary of the material. |

## 🏗️ Architecture

```
onionscout/
├── config.py     # env-driven settings (frozen dataclass)
├── tor.py        # proxied sessions, connectivity check, NEWNYM rotation
├── cache.py      # SQLite page cache
├── fetch.py      # concurrent fetch w/ retries + circuit rotation + extraction
├── engines.py    # search-engine registry + parsers + custom-engine loader
├── ranking.py    # relevance / consensus / trust scoring  ← the accuracy layer
├── search.py     # orchestrates engines → rank → liveness filter
├── health.py     # engine health checks
├── iocs.py       # IOC / entity extraction (wallets, emails, PGP, CVEs)
├── analyze.py    # multi-provider LLM synthesis
├── pipeline.py   # query → search → scrape → iocs → analyse
├── banner.py     # ASCII logo
└── cli.py        # argparse CLI + rich output
```

Engine onion addresses drift over time — edit the registry in
[`engines.py`](onionscout/engines.py) to add your own or update stale ones.

## 🧪 Development

```bash
pip install -e ".[dev]"
pytest -q          # unit tests (ranking, cache, parsers, utils — all offline)
ruff check .       # lint
```

The ranking, cache, URL-normalisation, and engine parsers are all covered by
offline unit tests, so you can hack on the accuracy logic without a live Tor
connection.

## 🗺️ Roadmap

- [x] Pluggable engine definitions from a user JSON/YAML file
- [x] Entity extraction (wallets, emails, PGP keys, CVEs) into structured IOCs
- [ ] Multi-instance Tor pool for higher-throughput scraping
- [ ] Export IOCs to STIX / MISP
- [ ] Scheduled re-scans with change diffing

## 👤 Author

Built and maintained by **Retr0** ([@Retr0Kali](https://github.com/Retr0Kali)).

## 📄 License

[MIT](LICENSE). Use responsibly.
