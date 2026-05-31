"""Configuration loader.

All paths and default knobs come from `config/settings.yaml`. Code never hardcodes
paths or magic constants — they live in YAML so the human (or another agent) can
tweak without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    """Project root = parent of `src/` in dev; ``QUANT_LAB_ROOT`` in Docker/deploy."""
    override = os.environ.get("QUANT_LAB_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


def load_dotenv_if_present() -> None:
    """Load ``<project_root>/.env`` into ``os.environ`` (does not override existing)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = _project_root() / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def env_var(name: str, *, default: str | None = None) -> str | None:
    """Read a secret / override from the environment (after ``.env`` load)."""
    raw = os.environ.get(name, default)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


@dataclass(frozen=True)
class Paths:
    project_root: Path
    data_root: Path
    raw: Path
    processed: Path

    def ensure(self) -> None:
        for p in (self.data_root, self.raw, self.processed):
            p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class UnderlyingDefaults:
    period: str
    interval: str


@dataclass(frozen=True)
class OptionChainDefaults:
    max_expiries: int
    skip_zero_volume_and_oi: bool


@dataclass
class Settings:
    """Top-level settings container.

    Intentionally NOT frozen: tests (and ad-hoc overrides) need to swap
    `paths` to redirect data I/O to a temp dir. The nested `Paths` /
    `UnderlyingDefaults` / `OptionChainDefaults` dataclasses stay frozen,
    so individual fields are still immutable — you have to replace the
    whole sub-object, which is the right granularity.
    """

    paths: Paths
    underlying: UnderlyingDefaults
    option_chain: OptionChainDefaults
    data_source_active: str
    data_source_config: dict[str, Any]


def _resolve(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (root / p)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    root = _project_root()
    cfg_path = root / "config" / "settings.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    paths_cfg = raw["paths"]
    paths = Paths(
        project_root=root,
        data_root=_resolve(root, paths_cfg["data_root"]),
        raw=_resolve(root, paths_cfg["raw"]),
        processed=_resolve(root, paths_cfg["processed"]),
    )
    paths.ensure()

    defaults = raw["defaults"]
    underlying = UnderlyingDefaults(**defaults["underlying"])
    option_chain = OptionChainDefaults(**defaults["option_chain"])

    ds = raw["data_source"]
    active = ds["active"]
    ds_cfg = ds.get(active, {})

    return Settings(
        paths=paths,
        underlying=underlying,
        option_chain=option_chain,
        data_source_active=active,
        data_source_config=ds_cfg,
    )


load_dotenv_if_present()
settings = load_settings()
