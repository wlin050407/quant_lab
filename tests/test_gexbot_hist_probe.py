"""Tests for GEXBot hist probe helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from quant_lab.data.gexbot_hist_probe import probe_hist_coverage, write_coverage_manifest


def test_probe_hist_coverage_metadata_only(tmp_path: Path) -> None:
    client = MagicMock()
    client.hist_download_url.side_effect = lambda _t, _p, _c, session: (
        f"https://example/{session.isoformat()}"
        if session == date(2025, 12, 11)
        else (_ for _ in ()).throw(FileNotFoundError("missing"))
    )
    out = probe_hist_coverage(
        "SPY",
        start=date(2025, 12, 8),
        end=date(2025, 12, 12),
        client=client,
    )
    assert out["n_available"] == 1
    assert out["available_dates"] == ["2025-12-11"]
    path = write_coverage_manifest(out, path=tmp_path / "cov.json")
    assert path.is_file()
