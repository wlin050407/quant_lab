"""Start the local Ultimate Terminal web UI.

Examples:

    python scripts/build_terminal_ui.py --install   # first-time UI build
    python scripts/run_terminal.py
    python scripts/run_terminal.py --port 8765 --open-browser
    python scripts/run_terminal.py --build          # rebuild UI then serve
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path


def _build_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "build_terminal_ui.py"), "--install"],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--reload", action="store_true", help="dev auto-reload (API only)")
    parser.add_argument("--build", action="store_true", help="npm build React UI before serve")
    args = parser.parse_args(argv)

    if args.build:
        _build_ui()

    url = f"http://{args.host}:{args.port}/"
    if args.open_browser:
        webbrowser.open(url)

    import uvicorn

    uvicorn.run(
        "quant_lab.terminal.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
