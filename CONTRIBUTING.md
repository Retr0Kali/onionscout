# Contributing to OnionScout

Thanks for your interest! OnionScout is a defensive security / OSINT tool.
Contributions that help defenders are very welcome; anything designed to
facilitate wrongdoing is not.

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
```

## Guidelines

- **Keep the accuracy layer honest.** Changes to `ranking.py` should come with
  a unit test in `tests/test_ranking.py` showing the behaviour you intend.
- **Parsers are per-engine.** When an engine changes its markup, update its
  parser in `engines.py` and add a fixture-based test in `tests/test_engines.py`.
- **No live network in tests.** Unit tests must run offline. Mock or use HTML
  fixtures for anything that would otherwise hit Tor.
- **Don't commit secrets.** `.env` is gitignored; never hard-code keys or
  passwords.
- **Style.** `ruff` with the config in `pyproject.toml` (100-col lines).

## Adding a search engine

1. Add an `Engine(...)` entry to `DEFAULT_ENGINES` in `engines.py`.
2. Give it a realistic `trust` weight (Ahmia-class ≈ 0.9, noisy ≈ 0.5).
3. Write a parser if the generic one doesn't extract results cleanly.
4. Add a fixture test.

## Pull requests

Keep PRs focused, describe the change and its motivation, and make sure
`pytest` and `ruff` pass.
