"""Optional HTTP basic auth for public Terminal deploys."""

from __future__ import annotations

import base64
import secrets
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from quant_lab.terminal.deploy import basic_auth_credentials

_PUBLIC_PATHS = frozenset({"/api/health"})


def _unauthorized() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Quantlab Terminal"'},
        content="Authentication required",
        media_type="text/plain",
    )


class TerminalBasicAuthMiddleware(BaseHTTPMiddleware):
    """Protect the Terminal UI/API when ``TERMINAL_AUTH_*`` env vars are set."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        credentials = basic_auth_credentials()
        if credentials is None or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return _unauthorized()

        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return _unauthorized()

        if ":" not in decoded:
            return _unauthorized()

        user, password = decoded.split(":", 1)
        expected_user, expected_password = credentials
        if not (
            secrets.compare_digest(user, expected_user)
            and secrets.compare_digest(password, expected_password)
        ):
            return _unauthorized()

        return await call_next(request)
