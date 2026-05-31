"""Deploy Quantlab Terminal to Railway (after ``railway login``).

Reads ThetaData credentials from local ``.env`` / creds file, sets Railway
variables, uploads Dockerfile build, and prints the public URL + basic auth.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from quant_lab.data.thetadata_client import ThetaDataConfigError, resolve_email_password
from quant_lab.terminal.deploy import DEFAULT_HISTORY_DAYS

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_NOTES = ROOT / ".railway-deploy.local"


def _resolve_railway() -> str:
    """Return Railway CLI path (Windows needs ``railway.cmd``, not bare ``railway``)."""
    for name in ("railway.cmd", "railway"):
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            cmd = Path(appdata) / "npm" / "railway.cmd"
            if cmd.is_file():
                return str(cmd)
    raise FileNotFoundError(
        "Railway CLI not found. Install: npm install -g @railway/cli"
    )


RAILWAY = _resolve_railway()


def _railway_args(*parts: str) -> list[str]:
    return [RAILWAY, *parts]


def _print_cmd(args: list[str]) -> None:
    secret_keys = {
        "THETADATA_EMAIL",
        "THETADATA_PASSWORD",
        "TERMINAL_AUTH_USER",
        "TERMINAL_AUTH_PASSWORD",
    }
    parts: list[str] = []
    for arg in args:
        if "=" in arg:
            key = arg.split("=", 1)[0]
            if key in secret_keys or key.endswith(("PASSWORD", "TOKEN", "SECRET")):
                parts.append(f"{key}=***")
                continue
        parts.append(arg)
    print("+", " ".join(parts))


def _run(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    _print_cmd(args)
    proc = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        if proc.stdout:
            print(proc.stdout, file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        proc.check_returncode()
    return proc


def _railway_logged_in() -> bool:
    proc = _run(_railway_args("whoami"), check=False)
    if proc.returncode != 0:
        return False
    return "Unauthorized" not in (proc.stderr or "") and "Unauthorized" not in (proc.stdout or "")


def _linked_project() -> bool:
    proc = _run(_railway_args("status", "--json"), check=False)
    if proc.returncode != 0:
        return False
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(payload.get("id") or payload.get("projectId") or payload.get("name"))


def _ensure_project() -> None:
    if _linked_project():
        return
    _run(_railway_args("init", "--name", "quantlab-terminal"))


def _has_service() -> bool:
    proc = _run(_railway_args("service", "list", "--json"), check=False)
    if proc.returncode != 0:
        return False
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return False
    if isinstance(payload, list):
        return len(payload) > 0
    services = payload.get("services", {})
    if isinstance(services, dict):
        edges = services.get("edges", [])
        return len(edges) > 0
    return False


def _ensure_service() -> None:
    if _has_service():
        _run(_railway_args("service", "link", "quantlab-terminal"), check=False)
        return
    _run(_railway_args("add", "--service", "quantlab-terminal", "--json"))
    _run(_railway_args("service", "link", "quantlab-terminal"), check=False)


def _set_variables(email: str, password: str, auth_user: str, auth_password: str) -> None:
    pairs = {
        "THETADATA_EMAIL": email,
        "THETADATA_PASSWORD": password,
        "TERMINAL_AUTH_USER": auth_user,
        "TERMINAL_AUTH_PASSWORD": auth_password,
        "TERMINAL_HISTORY_DAYS": str(DEFAULT_HISTORY_DAYS),
    }
    for key, value in pairs.items():
        _run(
            _railway_args(
                "variable",
                "set",
                f"{key}={value}",
                "--service",
                "quantlab-terminal",
                "--skip-deploys",
            )
        )


def _public_domain() -> str | None:
    proc = _run(_railway_args("domain", "--json"), check=False)
    if proc.returncode != 0:
        proc = _run(_railway_args("domain"), check=False)
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip()
        return line or None
    try:
        payload = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        return (proc.stdout or "").strip() or None
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return payload.get("domain") or payload.get("url")
    return None


def main() -> int:
    if not _railway_logged_in():
        print("Not logged in to Railway. Run: railway login", file=sys.stderr)
        return 1

    try:
        creds = resolve_email_password()
    except ThetaDataConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    if creds is None:
        print("ThetaData credentials missing locally (.env or creds file).", file=sys.stderr)
        return 1

    email, theta_password = creds
    auth_user = "quantlab"
    auth_password = secrets.token_urlsafe(16)

    _ensure_project()
    _ensure_service()
    _set_variables(email, theta_password, auth_user, auth_password)
    _run(_railway_args("up", "--detach", "--service", "quantlab-terminal"))

    domain = _public_domain()
    if domain is None:
        _run(_railway_args("domain"), check=False)

    notes = [
        f"auth_user={auth_user}",
        f"auth_password={auth_password}",
    ]
    if domain:
        url = domain if domain.startswith("http") else f"https://{domain}"
        notes.append(f"url={url}")
    DEPLOY_NOTES.write_text("\n".join(notes) + "\n", encoding="utf-8")

    print("\nDeploy started.")
    print(f"Basic auth saved to {DEPLOY_NOTES} (gitignored).")
    if domain:
        print(f"Open: https://{domain.removeprefix('https://').removeprefix('http://')}")
    else:
        print("Run `railway domain` and `railway open` for the public URL.")
    print("Tail logs: railway logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
