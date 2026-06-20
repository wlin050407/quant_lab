"""Tests for ML-P8B.0 harness split validators."""

from __future__ import annotations

from quant_lab.ml.harness.splits import detect_row_level_random_split, validate_session_split


def _row(trade_date: str, split: str | None = None, near: bool = False) -> dict[str, object]:
    r: dict[str, object] = {"trade_date": trade_date, "session_id": trade_date}
    if split is not None:
        r["split"] = split
    r["labels.close_near_primary_pin_050"] = near
    return r


def test_valid_session_split_passes() -> None:
    rows = [
        _row("2024-01-05"),
        _row("2024-01-19"),
        _row("2024-02-13"),
        _row("2024-03-08"),
        _row("2024-04-05"),
    ]
    result = validate_session_split(
        rows,
        train_sessions={"2024-01-05", "2024-01-19", "2024-02-13"},
        validation_sessions={"2024-03-08"},
        test_sessions={"2024-04-05"},
        target_key="labels.close_near_primary_pin_050",
    )
    assert result.passed is True
    assert result.train_session_count == 3
    assert result.validation_session_count == 1
    assert result.train_row_count == 3


def test_duplicate_trade_date_fails() -> None:
    result = validate_session_split(
        [],
        train_sessions={"2024-01-05"},
        validation_sessions={"2024-01-05"},
        test_sessions={"2024-02-13"},
    )
    assert result.passed is False
    assert any("duplicate trade_date" in e for e in result.errors)


def test_empty_validation_fails() -> None:
    result = validate_session_split(
        [],
        train_sessions={"2024-01-05"},
        validation_sessions=set(),
        test_sessions={"2024-02-13"},
    )
    assert result.passed is False
    assert any("validation_sessions is empty" in e for e in result.errors)


def test_row_level_random_split_detected() -> None:
    rows = [
        _row("2024-01-05", split="train"),
        _row("2024-01-05", split="validation"),
    ]
    errors = detect_row_level_random_split(rows)
    assert len(errors) == 1
    result = validate_session_split(
        rows,
        train_sessions={"2024-01-05"},
        validation_sessions=set(),
        test_sessions=set(),
        require_non_empty_validation=False,
    )
    assert result.passed is False
