"""Tor plumbing: proxied HTTP sessions, connectivity checks, circuit rotation."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .config import Config, get_config


class TorError(RuntimeError):
    """Raised when Tor is unreachable or misconfigured."""


def build_session(cfg: Config | None = None) -> requests.Session:
    """A requests.Session routed through the Tor SOCKS proxy.

    Uses socks5h:// so DNS (including .onion resolution) happens inside Tor
    rather than leaking to the local resolver.
    """
    cfg = cfg or get_config()
    session = requests.Session()
    session.proxies.update(cfg.proxies)
    session.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "close",
        }
    )
    return session


@dataclass
class TorStatus:
    connected: bool
    is_tor: bool
    exit_ip: str | None
    latency_ms: float | None
    detail: str

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "is_tor": self.is_tor,
            "exit_ip": self.exit_ip,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


def check_tor(cfg: Config | None = None) -> TorStatus:
    """Confirm traffic is flowing through Tor and report the exit IP.

    Queries the official Tor Project check endpoint, which returns whether the
    requesting IP is a known Tor exit node.
    """
    cfg = cfg or get_config()
    session = build_session(cfg)
    url = "https://check.torproject.org/api/ip"
    start = time.perf_counter()
    try:
        resp = session.get(url, timeout=cfg.request_timeout)
        latency = (time.perf_counter() - start) * 1000
        resp.raise_for_status()
        data = resp.json()
        is_tor = bool(data.get("IsTor"))
        exit_ip = data.get("IP")
        detail = "Traffic is exiting through Tor." if is_tor else (
            "Reachable, but the exit IP is NOT a Tor node — check your proxy."
        )
        return TorStatus(True, is_tor, exit_ip, round(latency, 1), detail)
    except requests.exceptions.RequestException as exc:
        return TorStatus(
            connected=False,
            is_tor=False,
            exit_ip=None,
            latency_ms=None,
            detail=f"Could not reach Tor at {cfg.socks_url}: {exc}",
        )


def renew_identity(cfg: Config | None = None) -> str:
    """Request a fresh Tor circuit via the ControlPort (NEWNYM signal).

    Returns the new exit IP on success. Requires a running ControlPort with a
    password configured. Tor rate-limits NEWNYM, so callers that rotate in a
    loop should pause between requests.
    """
    cfg = cfg or get_config()
    try:
        from stem import Signal
        from stem.control import Controller
    except ImportError as exc:  # pragma: no cover
        raise TorError("The 'stem' package is required for circuit rotation.") from exc

    try:
        with Controller.from_port(address=cfg.control_host, port=cfg.control_port) as controller:
            if cfg.control_password:
                controller.authenticate(password=cfg.control_password)
            else:
                controller.authenticate()
            controller.signal(Signal.NEWNYM)
            # Give Tor a moment to establish the new circuit before we probe it.
            time.sleep(controller.get_newnym_wait())
    except Exception as exc:  # stem raises a variety of connection errors
        raise TorError(
            f"Could not talk to the Tor ControlPort at "
            f"{cfg.control_host}:{cfg.control_port}: {exc}"
        ) from exc

    status = check_tor(cfg)
    if not status.connected:
        raise TorError(status.detail)
    return status.exit_ip or "unknown"
