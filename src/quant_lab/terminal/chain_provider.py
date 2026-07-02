"""Terminal intraday chain provider selection (ThetaData vs GEXBot+UW)."""

from __future__ import annotations

import logging
from typing import Literal

from quant_lab.config import env_var
from quant_lab.data.gexbot_client import GexbotConfigError, resolve_gexbot_api_key
from quant_lab.data.thetadata_client import resolve_email_password

log = logging.getLogger(__name__)

TerminalChainProvider = Literal["thetadata", "vendor"]
TERMINAL_CHAIN_PROVIDER_ENV = "TERMINAL_CHAIN_PROVIDER"


class TerminalDataConfigError(RuntimeError):
    """No usable intraday credentials for Terminal."""


def resolve_terminal_chain_provider() -> TerminalChainProvider:
    """Resolve active intraday provider.

    ``TERMINAL_CHAIN_PROVIDER``:
    - ``vendor`` / ``gexbot`` → GEXBot (+ UW when key present)
    - ``thetadata`` → legacy ThetaData
    - ``auto`` (default) → vendor if ``GEXBOT_API_KEY`` set, else ThetaData
    """
    explicit = (env_var(TERMINAL_CHAIN_PROVIDER_ENV) or "auto").strip().lower()
    if explicit in ("vendor", "gexbot"):
        _require_vendor_credentials()
        return "vendor"
    if explicit == "thetadata":
        _require_thetadata_credentials()
        return "thetadata"
    if explicit != "auto":
        raise ValueError(
            f"invalid {TERMINAL_CHAIN_PROVIDER_ENV}={explicit!r}; "
            "use auto, vendor, or thetadata"
        )
    if resolve_gexbot_api_key():
        return "vendor"
    if resolve_email_password():
        return "thetadata"
    raise TerminalDataConfigError(
        "No intraday credentials — set GEXBOT_API_KEY (vendor) or THETADATA_EMAIL/PASSWORD"
    )


def any_terminal_data_credentials_configured() -> bool:
    return resolve_gexbot_api_key() is not None or resolve_email_password() is not None


def _require_vendor_credentials() -> None:
    if resolve_gexbot_api_key() is None:
        raise GexbotConfigError("GEXBOT_API_KEY required for vendor provider")


def _require_thetadata_credentials() -> None:
    if resolve_email_password() is None:
        raise TerminalDataConfigError("ThetaData credentials required for thetadata provider")
