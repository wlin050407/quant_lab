"""ThetaData v3 Python client factory (no local Terminal required).

Credentials (first match wins):

1. ``THETADATA_CREDENTIALS_FILE`` → path to two-line ``creds.txt`` (email, password)
2. ``THETADATA_EMAIL`` + ``THETADATA_PASSWORD`` in environment / ``.env``
3. ``creds.txt`` in project root (discouraged — keep secrets outside the repo)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from quant_lab.config import _project_root, env_var

log = logging.getLogger(__name__)

DataFrameType = Literal["pandas", "polars"]

DEFAULT_OPTION_ROOT = "SPXW"
DEFAULT_INDEX_SYMBOL = "SPX"


class ThetaDataConfigError(RuntimeError):
    """Raised when ThetaData credentials are missing or invalid."""


def resolve_credentials_file() -> Path | None:
    """Return path to ``creds.txt`` if configured and exists."""
    explicit = env_var("THETADATA_CREDENTIALS_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ThetaDataConfigError(f"THETADATA_CREDENTIALS_FILE not found: {path}")
        return path

    fallback = _project_root() / "creds.txt"
    if fallback.is_file():
        log.warning("using project-root creds.txt — prefer THETADATA_CREDENTIALS_FILE outside repo")
        return fallback
    return None


def resolve_email_password() -> tuple[str, str] | None:
    email = env_var("THETADATA_EMAIL")
    password = env_var("THETADATA_PASSWORD")
    if email and password:
        return email, password
    creds_path = resolve_credentials_file()
    if creds_path is None:
        return None
    lines = creds_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
        raise ThetaDataConfigError(f"creds file must have email + password on two lines: {creds_path}")
    return lines[0].strip(), lines[1].strip()


@lru_cache(maxsize=1)
def get_thetadata_client(*, dataframe_type: DataFrameType = "pandas"):
    """Return an authenticated ``ThetaClient`` (cached singleton)."""
    try:
        from thetadata import ThetaClient
    except ImportError as exc:
        raise ThetaDataConfigError(
            "thetadata package not installed — run: pip install thetadata"
        ) from exc

    creds_path = resolve_credentials_file()
    email_password = resolve_email_password()

    if creds_path is not None and email_password is None:
        raise ThetaDataConfigError("credentials file exists but could not be parsed")

    if email_password is not None:
        email, password = email_password
        log.info("ThetaData client: authenticating as %s", email)
        return ThetaClient(email=email, password=password, dataframe_type=dataframe_type)

    if creds_path is not None:
        return ThetaClient(creds_file=str(creds_path), dataframe_type=dataframe_type)

    raise ThetaDataConfigError(
        "ThetaData credentials missing. Set THETADATA_CREDENTIALS_FILE or "
        "THETADATA_EMAIL + THETADATA_PASSWORD in .env"
    )


def reset_client_cache() -> None:
    """Clear cached client (tests)."""
    get_thetadata_client.cache_clear()


def refresh_thetadata_client(*, dataframe_type: DataFrameType = "pandas"):
    """Drop cached session and return a fresh authenticated client."""
    reset_client_cache()
    return get_thetadata_client(dataframe_type=dataframe_type)
