"""Tests for optional Terminal basic auth."""

from __future__ import annotations

from fastapi.testclient import TestClient

from quant_lab.terminal.api import app


def test_health_is_public_without_auth(monkeypatch) -> None:
    monkeypatch.setenv("TERMINAL_AUTH_USER", "ops")
    monkeypatch.setenv("TERMINAL_AUTH_PASSWORD", "secret")
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200


def test_index_requires_basic_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("TERMINAL_AUTH_USER", "ops")
    monkeypatch.setenv("TERMINAL_AUTH_PASSWORD", "secret")
    client = TestClient(app)
    denied = client.get("/")
    assert denied.status_code == 401

    ok = client.get("/", auth=("ops", "secret"))
    assert ok.status_code in (200, 503)
