"""ASCII logo / banner shown by the CLI."""

from __future__ import annotations

from . import __version__

LOGO = r"""
   ___        _          ____                  _
  / _ \ _ __ (_) ___  _ _/ ___|  ___ ___  _   _| |_
 | | | | '_ \| |/ _ \| '_ \___ \ / __/ _ \| | | | __|
 | |_| | | | | | (_) | | | |__) | (_| (_) | |_| | |_
  \___/|_| |_|_|\___/|_| |_|____/ \___\___/ \__,_|\__|
            . o O   tor · dark-web · osint
"""


def banner(subtitle: str = "") -> str:
    """Return the logo plus a version line (and optional subtitle)."""
    line = f"OnionScout v{__version__}"
    if subtitle:
        line += f" — {subtitle}"
    return f"{LOGO}\n  {line}\n"


def render(console, subtitle: str = "") -> None:
    """Print the banner in onion-purple using a rich Console."""
    console.print(f"[bold magenta]{LOGO}[/bold magenta]")
    line = f"OnionScout [bold]v{__version__}[/bold]"
    if subtitle:
        line += f" — [dim]{subtitle}[/dim]"
    console.print(f"  {line}\n")
