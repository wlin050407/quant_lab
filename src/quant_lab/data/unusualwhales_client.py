"""HTTP client for Unusual Whales public REST API."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

import requests

from quant_lab.config import env_var
from quant_lab.data.base import MARKET_TZ

log = logging.getLogger(__name__)

UW_BASE_URL = "https://api.unusualwhales.com/api"
DEFAULT_TIMEOUT_SECONDS = 45.0
OCC_SYMBOL_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8,})$")


class UnusualWhalesConfigError(RuntimeError):
    """Raised when UW credentials are missing."""


def resolve_unusual_whales_api_key() -> str | None:
    return env_var("UNUSUAL_WHALES_API_KEY") or env_var("UW_API_KEY")


def uw_ticker(terminal_symbol: str) -> str:
    normalized = terminal_symbol.replace("^", "").upper()
    return normalized


def parse_occ_option_symbol(symbol: str) -> tuple[str, date, str, float]:
    """Parse OPRA symbol e.g. ``SPXW260701C07500000`` → root, expiry, right, strike."""
    m = OCC_SYMBOL_RE.match(symbol.strip().upper())
    if m is None:
        raise ValueError(f"unrecognized OCC option symbol: {symbol!r}")
    root = m.group(1)
    yymmdd = m.group(2)
    right = m.group(3)
    strike_raw = int(m.group(4))
    expiry = datetime.strptime(yymmdd, "%y%m%d").date()
    # Index options (SPXW) use 1000 divisor; equities often 1000 as well for 8-digit field.
    strike = strike_raw / 1000.0
    return root, expiry, right, strike


class UnusualWhalesClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = UW_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key.strip():
            raise UnusualWhalesConfigError("Unusual Whales API key is empty")
        self._headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Accept": "application/json",
        }
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def _get(self, path: str, *, params: dict[str, str | int] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        resp = requests.get(url, headers=self._headers, params=params, timeout=self._timeout)
        if resp.status_code == 401:
            raise UnusualWhalesConfigError("Unusual Whales API key rejected (401)")
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError(f"expected JSON object from UW {path}, got {type(payload)}")
        return payload

    def option_contracts(
        self,
        ticker: str,
        *,
        market_date: date | None = None,
        page: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"page": page, "limit": limit}
        if market_date is not None:
            params["date"] = market_date.isoformat()
        payload = self._get(f"stock/{ticker}/option-contracts", params=params)
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]

    def fetch_all_option_contracts(
        self,
        ticker: str,
        *,
        market_date: date | None = None,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Paginate option-contracts until a short page."""
        out: list[dict[str, Any]] = []
        for page in range(max_pages):
            batch = self.option_contracts(ticker, market_date=market_date, page=page, limit=500)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 500:
                break
        return out

    def flow_per_strike_intraday(
        self,
        ticker: str,
        *,
        market_date: date | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit}
        if market_date is not None:
            params["date"] = market_date.isoformat()
        payload = self._get(f"stock/{ticker}/flow-per-strike-intraday", params=params)
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]


def get_unusual_whales_client() -> UnusualWhalesClient:
    key = resolve_unusual_whales_api_key()
    if key is None:
        raise UnusualWhalesConfigError(
            "Unusual Whales credentials missing — set UNUSUAL_WHALES_API_KEY"
        )
    return UnusualWhalesClient(key)


def parse_flow_timestamp(raw: str) -> datetime:
    """Parse UW ISO timestamp to ET-aware datetime."""
    ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        return ts.replace(tzinfo=MARKET_TZ)
    return ts.astimezone(MARKET_TZ)
