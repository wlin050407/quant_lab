"""Tests for .env loading via quant_lab.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from quant_lab import config


def test_env_var_reads_from_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANT_LAB_TEST_SECRET", "  abc123  ")
    assert config.env_var("QUANT_LAB_TEST_SECRET") == "abc123"


def test_load_dotenv_if_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DOTENV_TEST_KEY=from_dotenv\n", encoding="utf-8")
    monkeypatch.delenv("DOTENV_TEST_KEY", raising=False)
    monkeypatch.setattr(config, "_project_root", lambda: tmp_path)

    config.load_dotenv_if_present()
    assert os.environ.get("DOTENV_TEST_KEY") == "from_dotenv"
