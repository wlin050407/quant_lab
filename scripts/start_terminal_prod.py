"""Production entrypoint for Railway / Render / Docker."""

from __future__ import annotations

import logging

import uvicorn

from quant_lab.terminal.chain_provider import (
    TerminalDataConfigError,
    any_terminal_data_credentials_configured,
)
from quant_lab.terminal.deploy import basic_auth_credentials, listen_port

log = logging.getLogger(__name__)


def _preflight() -> None:
    if not any_terminal_data_credentials_configured():
        log.error(
            "Terminal intraday credentials missing — set GEXBOT_API_KEY (vendor mode) "
            "or THETADATA_EMAIL + THETADATA_PASSWORD (legacy ThetaData mode). "
            "See docs/terminal/GEXBOT_MIGRATION_PLAN.md"
        )
        raise SystemExit(1)

    try:
        from quant_lab.terminal.chain_provider import resolve_terminal_chain_provider

        provider = resolve_terminal_chain_provider()
        log.info("Terminal intraday provider: %s", provider)
    except TerminalDataConfigError as exc:
        log.error("%s", exc)
        raise SystemExit(1) from exc

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
