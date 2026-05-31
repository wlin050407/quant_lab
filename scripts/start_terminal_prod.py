"""Production entrypoint for Railway / Render / Docker."""

from __future__ import annotations

import logging
import sys

import uvicorn

from quant_lab.data.thetadata_client import ThetaDataConfigError, resolve_email_password
from quant_lab.terminal.deploy import basic_auth_credentials, listen_port

log = logging.getLogger(__name__)


def _preflight() -> None:
    if resolve_email_password() is None:
        log.error(
            "ThetaData credentials missing — set THETADATA_EMAIL + THETADATA_PASSWORD "
            "(or THETADATA_CREDENTIALS_FILE) before starting the Terminal."
        )
        raise SystemExit(1)

    auth = basic_auth_credentials()
    if auth is None:
        log.warning(
            "TERMINAL_AUTH_USER / TERMINAL_AUTH_PASSWORD not set — "
            "Terminal is publicly reachable; set basic auth for production."
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _preflight()
    port = listen_port()
    log.info("starting Quantlab Terminal on 0.0.0.0:%s", port)
    uvicorn.run(
        "quant_lab.terminal.api:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
