"""Command-line interface for OnionScout.

Subcommands:
    check      Verify Tor connectivity and report the exit IP.
    renew      Rotate the Tor circuit (new identity).
    engines    Health-check the dark-web search engines.
    search     Query engines, rank, and print the best results.
    fetch      Retrieve one or more pages via Tor.
    analyze    Run LLM OSINT analysis over fetched/stdin text.
    pipeline   Automated end-to-end investigation.
    cache      Inspect or clear the page cache.
"""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from . import __version__, banner
from .analyze import MODES, Document, analyze
from .cache import PageCache
from .fetch import Fetcher
from .health import check_engines
from .iocs import extract_iocs, merge_iocs
from .pipeline import run_pipeline
from .search import search
from .tor import TorError, check_tor, renew_identity

console = Console()
err = Console(stderr=True)


def _emit_json(obj) -> None:
    console.print_json(json.dumps(obj, default=str))


# --- commands -------------------------------------------------------------

def cmd_check(args) -> int:
    status = check_tor()
    if args.json:
        _emit_json(status.as_dict())
        return 0 if status.is_tor else 1
    if not status.connected:
        err.print(f"[red]✗[/red] {status.detail}")
        return 2
    mark = "[green]✓[/green]" if status.is_tor else "[yellow]![/yellow]"
    console.print(f"{mark} {status.detail}")
    console.print(f"  Exit IP : [bold]{status.exit_ip}[/bold]")
    console.print(f"  Latency : {status.latency_ms} ms")
    return 0 if status.is_tor else 1


def cmd_renew(args) -> int:
    try:
        new_ip = renew_identity()
    except TorError as exc:
        err.print(f"[red]✗[/red] {exc}")
        return 2
    if args.json:
        _emit_json({"ok": True, "exit_ip": new_ip})
    else:
        console.print(f"[green]✓[/green] New circuit. Exit IP: [bold]{new_ip}[/bold]")
    return 0


def cmd_engines(args) -> int:
    _apply_engines_file(args)
    results = check_engines(names=args.only, probe_query=args.query)
    if args.json:
        _emit_json([r.as_dict() for r in results])
        return 0
    table = Table(title="Dark-web search engines")
    table.add_column("Engine")
    table.add_column("Status")
    table.add_column("HTTP")
    table.add_column("Latency")
    table.add_column("URL", overflow="fold")
    for r in results:
        status = "[green]up[/green]" if r.up else "[red]down[/red]"
        table.add_row(
            r.name, status, str(r.status or "-"),
            f"{r.latency_ms} ms" if r.latency_ms else "-", r.url,
        )
    console.print(table)
    up = sum(1 for r in results if r.up)
    console.print(f"\n{up}/{len(results)} engines reachable.")
    return 0 if up else 1


def cmd_search(args) -> int:
    _apply_engines_file(args)
    sr = search(
        args.query,
        engines=args.engines,
        limit=args.limit,
        check_alive=args.check_alive,
    )
    if args.json:
        _emit_json(sr.as_dict())
        return 0
    if not sr.results:
        err.print("[yellow]No results.[/yellow] Engine status:")
        for er in sr.engine_reports:
            flag = "[green]ok[/green]" if er.ok else f"[red]{er.error}[/red]"
            err.print(f"  {er.name}: {flag}")
        return 1
    table = Table(title=f"Results for “{args.query}”", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Result", overflow="fold")
    table.add_column("Engines")
    for i, r in enumerate(sr.results, 1):
        body = f"[bold]{r.title}[/bold]\n[dim]{r.url}[/dim]"
        if r.snippet:
            body += f"\n{r.snippet[:200]}"
        if r.alive is not None:
            body += "\n[green]● live[/green]" if r.alive else "\n[red]● dead[/red]"
        table.add_row(str(i), f"{r.score:.2f}", body, ", ".join(r.engines))
    console.print(table)
    return 0


def cmd_fetch(args) -> int:
    fetcher = Fetcher()
    results = fetcher.fetch_many(args.urls, use_cache=not args.no_cache)
    if args.json:
        _emit_json([r.as_dict(include_html=args.html) for r in results])
        return 0 if all(r.ok for r in results) else 1
    for r in results:
        if r.ok:
            tag = "[cyan](cached)[/cyan]" if r.from_cache else ""
            console.print(f"[green]✓[/green] {r.url}  [dim]HTTP {r.status}[/dim] {tag}")
            if r.title:
                console.print(f"  [bold]{r.title}[/bold]")
            if args.text:
                console.print(f"  {r.text[:2000]}")
        else:
            err.print(f"[red]✗[/red] {r.url}  [red]{r.error}[/red]")
    return 0 if all(r.ok for r in results) else 1


def cmd_analyze(args) -> int:
    docs: list[Document] = []
    if args.url:
        fetcher = Fetcher()
        for res in fetcher.fetch_many(args.url):
            if res.ok and res.text:
                docs.append(Document(res.url, res.title, res.text))
            else:
                err.print(f"[yellow]skip[/yellow] {res.url}: {res.error or 'empty'}")
    else:
        text = sys.stdin.read()
        if not text.strip():
            err.print("[red]No input.[/red] Pass --url or pipe text on stdin.")
            return 2
        docs.append(Document(url="stdin", title="stdin", text=text))

    result = analyze(docs, mode=args.mode)
    if args.json:
        _emit_json({"mode": args.mode, "sources": [d.url for d in docs], "analysis": result})
    else:
        console.print(result)
    return 0


def cmd_pipeline(args) -> int:
    _apply_engines_file(args)
    with console.status("[bold]starting…[/bold]") as status:
        result = run_pipeline(
            args.query,
            mode=args.mode,
            engines=args.engines,
            top=args.top,
            check_alive=not args.no_check_alive,
            do_analysis=not args.no_analysis,
            progress=lambda m: status.update(f"[bold]{m}[/bold]"),
        )
    if args.json:
        _emit_json(result.as_dict())
        if args.out:
            with open(args.out, "w") as fh:
                json.dump(result.as_dict(), fh, indent=2, default=str)
        return 0

    console.rule(f"OnionScout report — “{result.query}” ({result.mode})")
    console.print(f"\n[bold]Top {len(result.results)} results[/bold]")
    for i, r in enumerate(result.results, 1):
        console.print(f" {i}. [bold]{r.title}[/bold]  [dim]{r.url}[/dim]  (score {r.score:.2f})")
    console.print("\n[bold]Indicators[/bold]")
    _render_iocs(result.iocs)
    console.print("\n[bold]Analysis[/bold]")
    console.print(result.analysis or "[dim](none)[/dim]")
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result.as_dict(), fh, indent=2, default=str)
        console.print(f"\n[dim]Full report written to {args.out}[/dim]")
    return 0


def _apply_engines_file(args) -> None:
    """Expose --engines-file to the engine registry via the env var it reads."""
    import os

    path = getattr(args, "engines_file", None)
    if path:
        os.environ["ONIONSCOUT_ENGINES"] = path


def _render_iocs(iocs) -> None:
    d = iocs.as_dict()
    if iocs.total == 0:
        console.print("[dim]No indicators extracted.[/dim]")
        return
    table = Table(title="Indicators of compromise", show_lines=False)
    table.add_column("Type")
    table.add_column("Count", justify="right")
    table.add_column("Values", overflow="fold")
    rows = [
        ("onion", d["onions"]),
        ("email", d["emails"]),
        ("ipv4", d["ipv4"]),
        ("btc", d["crypto"]["btc"]),
        ("eth", d["crypto"]["eth"]),
        ("xmr", d["crypto"]["xmr"]),
        ("pgp fingerprint", d["pgp_fingerprints"]),
        ("cve", d["cves"]),
    ]
    for label, values in rows:
        if values:
            table.add_row(label, str(len(values)), ", ".join(values[:8]))
    if d["pgp_keys"]:
        table.add_row("pgp key block", str(d["pgp_keys"]), "—")
    console.print(table)


def cmd_iocs(args) -> int:
    texts: list[str] = []
    sources: list[str] = []
    if args.url:
        fetcher = Fetcher()
        for res in fetcher.fetch_many(args.url):
            if res.ok and res.text:
                texts.append(res.text)
                sources.append(res.url)
            else:
                err.print(f"[yellow]skip[/yellow] {res.url}: {res.error or 'empty'}")
    else:
        data = sys.stdin.read()
        if not data.strip():
            err.print("[red]No input.[/red] Pass --url or pipe text on stdin.")
            return 2
        texts.append(data)
        sources.append("stdin")

    merged = merge_iocs([extract_iocs(t) for t in texts])
    if args.json:
        _emit_json({"sources": sources, "iocs": merged.as_dict(), "total": merged.total})
    else:
        _render_iocs(merged)
    return 0


def cmd_cache(args) -> int:
    cache = PageCache()
    if args.clear:
        n = cache.clear()
        console.print(f"[green]✓[/green] Cleared {n} cached pages.")
    else:
        console.print(f"Cache: {'enabled' if cache.enabled else 'disabled'} "
                      f"at [bold]{cache.path}[/bold] (ttl {cache.ttl}s)")
    return 0


# --- parser ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="onionscout",
        description="Advanced Tor / dark-web OSINT toolkit.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("check", help="verify Tor connectivity")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("renew", help="rotate Tor circuit (new identity)")
    sp.set_defaults(func=cmd_renew)

    sp = sub.add_parser("engines", help="health-check search engines")
    sp.add_argument("--only", nargs="*", help="limit to these engine names")
    sp.add_argument("--query", default="test", help="probe query to send")
    sp.add_argument("--engines-file", help="JSON/YAML file of custom engines")
    sp.set_defaults(func=cmd_engines)

    sp = sub.add_parser("search", help="search dark-web engines and rank results")
    sp.add_argument("query")
    sp.add_argument("--engines", nargs="*", help="limit to these engine names")
    sp.add_argument("--engines-file", help="JSON/YAML file of custom engines")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--check-alive", action="store_true",
                    help="probe results over Tor and drop dead links")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("fetch", help="retrieve pages via Tor")
    sp.add_argument("urls", nargs="+")
    sp.add_argument("--text", action="store_true", help="print extracted text")
    sp.add_argument("--html", action="store_true", help="include raw HTML in JSON")
    sp.add_argument("--no-cache", action="store_true")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("analyze", help="LLM OSINT analysis")
    sp.add_argument("--url", nargs="*", help="fetch these URLs as input")
    sp.add_argument("--mode", choices=list(MODES), default="threat")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("iocs", help="extract indicators (wallets, emails, PGP, CVEs)")
    sp.add_argument("--url", nargs="*", help="fetch these URLs as input")
    sp.set_defaults(func=cmd_iocs)

    sp = sub.add_parser("pipeline", help="automated end-to-end investigation")
    sp.add_argument("query")
    sp.add_argument("--mode", choices=list(MODES), default="threat")
    sp.add_argument("--engines", nargs="*")
    sp.add_argument("--engines-file", help="JSON/YAML file of custom engines")
    sp.add_argument("--top", type=int, default=5, help="pages to scrape & analyse")
    sp.add_argument("--no-check-alive", action="store_true")
    sp.add_argument("--no-analysis", action="store_true")
    sp.add_argument("--out", help="write full JSON report to this path")
    sp.set_defaults(func=cmd_pipeline)

    sp = sub.add_parser("cache", help="inspect or clear the page cache")
    sp.add_argument("--clear", action="store_true")
    sp.set_defaults(func=cmd_cache)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        banner.render(console, "Advanced Tor / dark-web OSINT toolkit")
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        err.print("\n[yellow]Interrupted.[/yellow]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
