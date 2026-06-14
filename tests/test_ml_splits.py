"""Tests for ML-P6 session-grouped splits."""

from __future__ import annotations

import pytest

from quant_lab.ml.splits import (
    assert_no_session_overlap,
    assign_split_to_rows,
    expanding_walk_forward_split,
    locked_holdout_split,
    session_grouped_split,
)


def test_session_grouped_split_no_shuffle() -> None:
    with pytest.raises(ValueError, match="shuffle"):
        session_grouped_split(["2026-06-01", "2026-06-02"], shuffle=True)


def test_session_grouped_split_assigns_whole_sessions() -> None:
    sessions = [f"2026-06-{d:02d}" for d in range(1, 11)]
    manifest = session_grouped_split(sessions, train_ratio=0.6, val_ratio=0.2)
    assert_no_session_overlap(manifest)
    assigned = set(manifest.train_sessions) | set(manifest.validation_sessions) | set(manifest.test_sessions)
    assert assigned == set(sessions)


def test_expanding_walk_forward() -> None:
    sessions = [f"2026-06-{d:02d}" for d in range(1, 9)]
    folds = expanding_walk_forward_split(sessions, n_folds=3, min_train_sessions=2)
    assert len(folds) >= 1
    for fold in folds:
        assert_no_session_overlap(fold)
        assert set(fold.train_sessions).isdisjoint(set(fold.test_sessions))


def test_locked_holdout() -> None:
    sessions = [f"2026-06-{d:02d}" for d in range(1, 11)]
    holdout = ["2026-06-09", "2026-06-10"]
    manifest = locked_holdout_split(sessions, holdout)
    assert set(manifest.holdout_sessions) == set(holdout)
    assert_no_session_overlap(manifest)


def test_embargo_excludes_near_sessions() -> None:
    sessions = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-10"]
    manifest = session_grouped_split(sessions, train_ratio=0.5, val_ratio=0.25, embargo_days=5)
    if manifest.validation_sessions:
        last_train = max(manifest.train_sessions)
        for v in manifest.validation_sessions:
            assert v > last_train


def test_assign_split_to_rows() -> None:
    sessions = ["2026-06-01", "2026-06-02", "2026-06-03"]
    manifest = session_grouped_split(sessions)
    rows = [{"session_id": s, "x": 1} for s in sessions]
    tagged = assign_split_to_rows(rows, manifest)
    splits = {r["split"] for r in tagged}
    assert "train" in splits
