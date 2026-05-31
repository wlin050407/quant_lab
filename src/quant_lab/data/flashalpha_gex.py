"""FlashAlpha GEX API client (optional external calibration source).

FlashAlpha free tier requires ``?expiration=YYYY-MM-DD`` for single-expiry GEX
(ETF full-chain needs Basic; all-expiry needs Growth). ``fetch_gex`` resolves
the nearest expiry automatically from the local chain snapshot when possible.

Docs: https://flashalpha.com/docs/lab-api-gex
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from quant_lab.config import env_var

DEFAULT_BASE_URL = "https://lab.flashalpha.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0

# FlashAlpha free tier: ETF/index full-chain needs Basic; always pass expiration.
_ETF_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "DIA", "SPX", "VIX", "RUT"})


@dataclass(frozen=True)
class FlashAlphaGEX:
    """Normalized FlashAlpha GEX quote for calibration."""

    symbol: str
    as_of: str
    spot: float
    net_gex_bn_per_1pct: float
    gamma_flip: float
    regime: str  # "long_gamma" | "short_gamma"
    call_wall: float | None
    put_wall: float | None
    raw_net_gex: float
    expiration: str | None = None


class FlashAlphaError(RuntimeError):
    """Raised when the FlashAlpha API returns an error."""


def flashalpha_api_key() -> str | None:
    """Read API key from ``FLASHALPHA_API_KEY`` (``.env`` or shell env)."""
    return env_var("FLASHALPHA_API_KEY")


def net_gex_dollars_to_bn_per_1pct(net_gex_dollars: float) -> float:
    """Convert FlashAlpha ``net_gex`` (USD per 1% move) to billions per 1%."""
    return float(net_gex_dollars / 1e9)


def next_spy_weekly_expiry(asof: date) -> date:
    """Next Mon / Wed / Fri on or after ``asof`` (SPY weeklies)."""
    for offset in range(8):
        candidate = asof + timedelta(days=offset)
        if candidate.weekday() in (0, 2, 4):
            return candidate
    raise FlashAlphaError(f"no SPY weekly expiry found within 7 days of {asof}")


def expiration_from_chain(chain: pd.DataFrame, asof: date) -> str | None:
    """Pick nearest chain expiry on or after ``asof``."""
    if chain.empty or "expiry" not in chain.columns:
        return None
    expiries = sorted({pd.Timestamp(v).date() for v in chain["expiry"].dropna()})
    if not expiries:
        return None
    future = [e for e in expiries if e >= asof]
    chosen = future[0] if future else expiries[-1]
    return chosen.isoformat()


def resolve_nearest_expiration(
    symbol: str,
    *,
    asof_date: date | None = None,
    chain: pd.DataFrame | None = None,
    snapshot_date: str | None = None,
) -> str:
    """Resolve FlashAlpha ``expiration`` query param for free-tier requests."""
    sym = symbol.upper().lstrip("^")
    asof = asof_date or date.today()

    if chain is not None:
        from_chain = expiration_from_chain(chain, asof)
        if from_chain is not None:
            return from_chain

    dates_to_try: list[str] = []
    if snapshot_date:
        dates_to_try.append(snapshot_date)
    else:
        from quant_lab.data.storage import list_option_snapshots

        snaps = list_option_snapshots(symbol)
        if snaps:
            dates_to_try.append(snaps[-1])

    for snap_date in dates_to_try:
        try:
            from quant_lab.data.storage import load_option_chain

            local_chain, _ = load_option_chain(symbol, snap_date)
            from_chain = expiration_from_chain(
                local_chain, date.fromisoformat(snap_date)
            )
            if from_chain is not None:
                return from_chain
        except FileNotFoundError:
            continue

    if sym in _ETF_SYMBOLS:
        return next_spy_weekly_expiry(asof).isoformat()

    # Individual names on free tier also need a single expiry; default ~1 week out.
    return (asof + timedelta(days=7)).isoformat()


def _regime_from_label(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in {"positive", "positive_gamma", "long_gamma"}:
        return "long_gamma"
    if normalized in {"negative", "negative_gamma", "short_gamma"}:
        return "short_gamma"
    raise FlashAlphaError(f"unknown FlashAlpha regime label: {label!r}")


def parse_gex_payload(
    payload: dict[str, Any], *, expiration: str | None = None
) -> FlashAlphaGEX:
    """Parse ``GET /v1/exposure/gex/{symbol}`` JSON into a normalized quote."""
    symbol = str(payload["symbol"])
    spot = float(payload["underlying_price"])
    as_of = str(payload.get("as_of", ""))
    raw_net = float(payload["net_gex"])
    flip = float(payload["gamma_flip"])

    label = payload.get("net_gex_label")
    if label is None:
        regime = "long_gamma" if raw_net >= 0 else "short_gamma"
    else:
        regime = _regime_from_label(str(label))

    call_wall = payload.get("call_wall")
    put_wall = payload.get("put_wall")
    if isinstance(call_wall, dict):
        call_wall = call_wall.get("strike")
    if isinstance(put_wall, dict):
        put_wall = put_wall.get("strike")

    return FlashAlphaGEX(
        symbol=symbol,
        as_of=as_of,
        spot=spot,
        net_gex_bn_per_1pct=net_gex_dollars_to_bn_per_1pct(raw_net),
        gamma_flip=flip,
        regime=regime,
        call_wall=float(call_wall) if call_wall is not None else None,
        put_wall=float(put_wall) if put_wall is not None else None,
        raw_net_gex=raw_net,
        expiration=expiration,
    )


def _request_gex(
    symbol: str,
    *,
    api_key: str,
    expiration: str | None,
    base_url: str,
    session: requests.Session,
    timeout: float,
) -> requests.Response:
    params: dict[str, str] = {}
    if expiration is not None:
        params["expiration"] = expiration
    url = f"{base_url.rstrip('/')}/exposure/gex/{symbol.upper()}"
    return session.get(
        url,
        headers={"X-Api-Key": api_key},
        params=params or None,
        timeout=timeout,
    )


def fetch_gex(
    symbol: str,
    *,
    api_key: str | None = None,
    expiration: str | None = None,
    auto_expiration: bool = True,
    snapshot_date: str | None = None,
    chain: pd.DataFrame | None = None,
    base_url: str = DEFAULT_BASE_URL,
    session: requests.Session | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> FlashAlphaGEX:
    """Fetch live GEX for ``symbol`` from FlashAlpha.

    When ``expiration`` is omitted and ``auto_expiration`` is true (default),
    picks the nearest expiry from the local chain snapshot or SPY weekly calendar.
    """
    key = api_key or flashalpha_api_key()
    if not key:
        raise FlashAlphaError(
            "FLASHALPHA_API_KEY not set — add it to .env (see .env.example) "
            "or register free at https://flashalpha.com/profile"
        )

    exp = expiration
    if exp is None and auto_expiration:
        exp = resolve_nearest_expiration(
            symbol, snapshot_date=snapshot_date, chain=chain
        )

    sess = session or requests.Session()
    resp = _request_gex(
        symbol,
        api_key=key,
        expiration=exp,
        base_url=base_url,
        session=sess,
        timeout=timeout,
    )

    if resp.status_code == 403 and exp is None and auto_expiration:
        exp = resolve_nearest_expiration(symbol, snapshot_date=snapshot_date, chain=chain)
        resp = _request_gex(
            symbol,
            api_key=key,
            expiration=exp,
            base_url=base_url,
            session=sess,
            timeout=timeout,
        )

    if resp.status_code == 403:
        raise FlashAlphaError(
            f"FlashAlpha 403 for {symbol}: tier restricted "
            f"(expiration={exp!r}; free tier needs single expiry, ETF may need Basic)"
        )
    if resp.status_code == 404:
        raise FlashAlphaError(
            f"FlashAlpha 404 for {symbol} expiration={exp!r}: no data for that expiry"
        )
    if resp.status_code == 429:
        raise FlashAlphaError(
            f"FlashAlpha 429 for {symbol}: daily API quota exceeded (free tier: 5/day)"
        )
    if not resp.ok:
        raise FlashAlphaError(
            f"FlashAlpha HTTP {resp.status_code} for {symbol}: {resp.text[:200]}"
        )

    payload = resp.json()
    return parse_gex_payload(payload, expiration=exp)
