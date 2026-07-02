"""HTTP client for GEXBot v2 API (Classic / State / Orderflow / Quant hist)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests

from quant_lab.config import env_var

log = logging.getLogger(__name__)

GEXBOT_BASE_URL = "https://api.gex.bot/v2"
DEFAULT_USER_AGENT = "quantlab-terminal/1.0"
DEFAULT_TIMEOUT_SECONDS = 45.0


class GexbotConfigError(RuntimeError):
    """Raised when GEXBot credentials or configuration are missing."""


def resolve_gexbot_api_key() -> str | None:
    """Bearer token from ``GEXBOT_API_KEY`` (or legacy ``GEXBOT_BEARER_TOKEN``)."""
    return env_var("GEXBOT_API_KEY") or env_var("GEXBOT_BEARER_TOKEN")


def gexbot_ticker(terminal_symbol: str) -> str:
    """Map Terminal symbol to GEXBot index ticker."""
    normalized = terminal_symbol.replace("^", "").upper()
    if normalized == "SPX":
        return "SPX"
    return normalized


class GexbotClient:
    """Thin REST wrapper around GEXBot v2."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = GEXBOT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not api_key.strip():
            raise GexbotConfigError("GEXBot API key is empty")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        resp = requests.get(url, headers=self._headers, params=params, timeout=self._timeout)
        if resp.status_code == 401:
            raise GexbotConfigError("GEXBot API key rejected (401)")
        if resp.status_code == 403:
            raise PermissionError(f"GEXBot forbidden for {path} (403)")
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError(f"expected JSON object from GEXBot {path}, got {type(payload)}")
        return payload

    def classic(self, ticker: str, category: str = "gex_zero") -> dict[str, Any]:
        return self._get(f"{ticker}/classic/{category}")

    def classic_majors(self, ticker: str, category: str = "gex_zero") -> dict[str, Any]:
        return self._get(f"{ticker}/classic/{category}/majors")

    def state(self, ticker: str, category: str = "gamma_zero") -> dict[str, Any]:
        return self._get(f"{ticker}/state/{category}")

    def orderflow(self, ticker: str) -> dict[str, Any]:
        return self._get(f"{ticker}/orderflow/orderflow")

    def hist_download_url(
        self,
        ticker: str,
        package: str,
        category: str,
        session_date: date,
    ) -> str:
        """Return pre-signed URL for one session's historical JSON (Quant tier)."""
        path = f"hist/{ticker}/{package}/{category}/{session_date.isoformat()}"
        meta = self._get(path, params={"noredirect": "true"})
        url = meta.get("url")
        if not isinstance(url, str) or not url:
            raise FileNotFoundError(f"no GEXBot hist for {ticker} {package}/{category} on {session_date}")
        return url

    def download_hist_json(
        self,
        ticker: str,
        package: str,
        category: str,
        session_date: date,
    ) -> list[dict[str, Any]]:
        url = self.hist_download_url(ticker, package, category, session_date)
        resp = requests.get(url, timeout=self._timeout)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError(f"expected hist JSON array for {session_date}, got {type(payload)}")
        return payload


def get_gexbot_client() -> GexbotClient:
    key = resolve_gexbot_api_key()
    if key is None:
        raise GexbotConfigError(
            "GEXBot credentials missing — set GEXBOT_API_KEY in the environment"
        )
    return GexbotClient(key)
