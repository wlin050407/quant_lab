"""Session-grouped split utilities for ML-P6 (no row-level random split)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

SplitName = Literal["train", "validation", "test", "holdout"]


@dataclass(frozen=True)
class SplitManifest:
    split_config: dict[str, Any]
    train_sessions: tuple[str, ...]
    validation_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]
    holdout_sessions: tuple[str, ...] = field(default_factory=tuple)
    date_ranges: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "split_config": self.split_config,
            "train_sessions": list(self.train_sessions),
            "validation_sessions": list(self.validation_sessions),
            "test_sessions": list(self.test_sessions),
            "holdout_sessions": list(self.holdout_sessions),
            "date_ranges": self.date_ranges,
        }


def _session_dates(sessions: Iterable[str]) -> tuple[date, ...]:
    out: list[date] = []
    for s in sessions:
        out.append(date.fromisoformat(s))
    return tuple(sorted(out))


def _date_range_for_sessions(sessions: tuple[str, ...]) -> dict[str, str | None]:
    if not sessions:
        return {"min": None, "max": None}
    dates = _session_dates(sessions)
    return {"min": dates[0].isoformat(), "max": dates[-1].isoformat()}


def session_grouped_split(
    session_ids: list[str],
    *,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    shuffle: bool = False,
    embargo_days: int = 0,
) -> SplitManifest:
    """Assign whole sessions to train/val/test. ``shuffle`` must be False."""
    if shuffle:
        raise ValueError("shuffle=True forbidden for session_grouped_split")
    unique = sorted(set(session_ids))
    n = len(unique)
    if n == 0:
        return SplitManifest(
            split_config={"method": "session_grouped", "train_ratio": train_ratio, "val_ratio": val_ratio},
            train_sessions=(),
            validation_sessions=(),
            test_sessions=(),
        )
    n_train = max(1, int(n * train_ratio)) if n >= 3 else max(1, n - 2)
    n_val = max(1, int(n * val_ratio)) if n >= 3 else (1 if n > 1 else 0)
    if n_train + n_val >= n:
        n_val = max(0, n - n_train - 1)
    train = tuple(unique[:n_train])
    val = tuple(unique[n_train : n_train + n_val])
    test = tuple(unique[n_train + n_val :])
    if embargo_days > 0 and train and val:
        last_train = max(_session_dates(train))
        val = tuple(s for s in val if date.fromisoformat(s) > last_train + timedelta(days=embargo_days))
    return SplitManifest(
        split_config={
            "method": "session_grouped",
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "embargo_days": embargo_days,
            "shuffle": False,
        },
        train_sessions=train,
        validation_sessions=val,
        test_sessions=test,
        date_ranges={
            "train": _date_range_for_sessions(train),
            "validation": _date_range_for_sessions(val),
            "test": _date_range_for_sessions(test),
        },
    )


def expanding_walk_forward_split(
    session_ids: list[str],
    *,
    n_folds: int = 3,
    min_train_sessions: int = 2,
    embargo_days: int = 0,
) -> list[SplitManifest]:
    """Expanding-window walk-forward folds; each fold assigns disjoint test sessions."""
    unique = sorted(set(session_ids))
    if len(unique) < min_train_sessions + 1:
        return []
    folds: list[SplitManifest] = []
    test_size = max(1, (len(unique) - min_train_sessions) // n_folds)
    for fold in range(n_folds):
        test_start = min_train_sessions + fold * test_size
        test_end = min(test_start + test_size, len(unique))
        if test_start >= len(unique):
            break
        train = tuple(unique[:test_start])
        test = tuple(unique[test_start:test_end])
        if embargo_days > 0 and train:
            last_train = max(_session_dates(train))
            test = tuple(s for s in test if date.fromisoformat(s) > last_train + timedelta(days=embargo_days))
        folds.append(
            SplitManifest(
                split_config={
                    "method": "expanding_walk_forward",
                    "fold": fold,
                    "min_train_sessions": min_train_sessions,
                    "embargo_days": embargo_days,
                },
                train_sessions=train,
                validation_sessions=(),
                test_sessions=test,
                date_ranges={
                    "train": _date_range_for_sessions(train),
                    "test": _date_range_for_sessions(test),
                },
            )
        )
    return folds


def locked_holdout_split(
    session_ids: list[str],
    holdout_sessions: list[str],
    *,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> SplitManifest:
    """Reserve locked holdout sessions; split remaining chronologically."""
    unique = sorted(set(session_ids))
    holdout = tuple(sorted(set(holdout_sessions)))
    pool = [s for s in unique if s not in holdout]
    manifest = session_grouped_split(pool, train_ratio=train_ratio, val_ratio=val_ratio)
    return SplitManifest(
        split_config={
            **manifest.split_config,
            "method": "locked_holdout",
            "holdout_sessions": list(holdout),
        },
        train_sessions=manifest.train_sessions,
        validation_sessions=manifest.validation_sessions,
        test_sessions=manifest.test_sessions,
        holdout_sessions=holdout,
        date_ranges={
            **manifest.date_ranges,
            "holdout": _date_range_for_sessions(holdout),
        },
    )


def assign_split_to_rows(
    rows: list[dict[str, Any]],
    manifest: SplitManifest,
    session_key: str = "session_id",
) -> list[dict[str, Any]]:
    """Tag each row with split membership via session_id."""
    session_to_split: dict[str, SplitName] = {}
    for s in manifest.train_sessions:
        session_to_split[s] = "train"
    for s in manifest.validation_sessions:
        session_to_split[s] = "validation"
    for s in manifest.test_sessions:
        session_to_split[s] = "test"
    for s in manifest.holdout_sessions:
        session_to_split[s] = "holdout"
    out = []
    for row in rows:
        r = dict(row)
        sid = r.get(session_key, r.get("trade_date"))
        r["split"] = session_to_split.get(str(sid), "unassigned")
        out.append(r)
    return out


def assert_no_session_overlap(manifest: SplitManifest) -> None:
    """Verify train/val/test/holdout session sets are disjoint."""
    sets = [
        set(manifest.train_sessions),
        set(manifest.validation_sessions),
        set(manifest.test_sessions),
        set(manifest.holdout_sessions),
    ]
    for i, a in enumerate(sets):
        for j, b in enumerate(sets):
            if i >= j:
                continue
            overlap = a & b
            if overlap:
                raise ValueError(f"Session overlap between split groups: {overlap}")
