"""Build the React Terminal UI (Vite) into static/dist/."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _web_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "quant_lab" / "terminal" / "web"


def _npm() -> str:
    portable = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "node"
        / "node-v22.16.0-win-x64"
        / "npm.cmd"
    )
    if portable.exists():
        return str(portable)
    return "npm.cmd" if sys.platform == "win32" else "npm"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="run npm ci when node_modules is missing",
    )
    args = parser.parse_args(argv)

    web = _web_dir()
    if not (web / "package.json").exists():
        print(f"missing {web / 'package.json'}", file=sys.stderr)
        return 1

    npm = _npm()
    node_modules = web / "node_modules"
    if args.install or not node_modules.exists():
        if (web / "package-lock.json").exists():
            subprocess.run([npm, "ci"], cwd=web, check=True)
        else:
            subprocess.run([npm, "install"], cwd=web, check=True)

    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_terminal_favicon.py")],
        check=True,
    )

    subprocess.run([npm, "run", "build"], cwd=web, check=True)

    dist = web.parent / "static" / "dist"
    if not (dist / "index.html").exists():
        print(f"build failed: no {dist / 'index.html'}", file=sys.stderr)
        return 1

    print(f"built UI → {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
