"""Data quality checks.

Returns structured reports rather than raising — the caller decides whether
to abort or proceed. Checks are intentionally cheap so they can run on every
fetch.

Conventions:
    severity = "info"  -> noteworthy but expected (e.g., FX/holiday gap)
    severity = "warn"  -> human should look (e.g., 20%+ price jump)
    severity = "error" -> pipeline should refuse downstream use
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd


Severity = Literal["info", "warn", "error"]


@dataclass
class QualityIssue:
    code: str
    severity: Severity
    message: str
    rows: int = 0


@dataclass
class QualityReport:
    target: str
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def add(self, code: str, severity: Severity, message: str, rows: int = 0) -> None:
        self.issues.append(QualityIssue(code, severity, message, rows))

    def as_dataframe(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(columns=["code", "severity", "message", "rows"])
        return pd.DataFrame([i.__dict__ for i in self.issues])

    def render(self) -> str:
        if not self.issues:
            return f"[{self.target}] OK (no issues)"
        lines = [f"[{self.target}] {len(self.issues)} issue(s):"]
        for i in self.issues:
            lines.append(f"  [{i.severity:>5}] {i.code}: {i.message} (rows={i.rows})")
        return "\n".join(lines)


def check_underlying(df: pd.DataFrame, *, symbol: str) -> QualityReport:
    rep = QualityReport(target=f"underlying:{symbol}")

    if df.empty:
        rep.add("UND_EMPTY", "error", "empty dataframe", 0)
        return rep

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        rep.add("UND_MISSING_COLS", "error", f"missing columns: {sorted(missing)}")
        return rep

    if not df.index.is_monotonic_increasing:
        rep.add("UND_NOT_SORTED", "error", "datetime index is not monotonically increasing")

    dup_n = int(df.index.duplicated().sum())
    if dup_n:
        rep.add("UND_DUP_INDEX", "error", "duplicate timestamps", rows=dup_n)

    nan_close = int(df["close"].isna().sum())
    if nan_close:
        rep.add("UND_NAN_CLOSE", "warn", "NaN close values", rows=nan_close)

    nonpos = int((df["close"] <= 0).sum())
    if nonpos:
        rep.add("UND_NONPOS_CLOSE", "error", "non-positive close values", rows=nonpos)

    bad_hl = int((df["high"] < df["low"]).sum())
    if bad_hl:
        rep.add("UND_HL_INVERTED", "error", "rows where high < low", rows=bad_hl)

    ret = df["close"].pct_change().abs()
    jumps = int((ret > 0.20).sum())
    if jumps:
        rep.add(
            "UND_LARGE_JUMP",
            "warn",
            ">20% absolute daily move (check for split/dividend not adjusted)",
            rows=jumps,
        )

    if len(df) >= 5:
        deltas = df.index.to_series().diff().dropna()
        median_delta = deltas.median()
        gaps = int((deltas > median_delta * 5).sum())
        if gaps:
            rep.add(
                "UND_INDEX_GAPS",
                "info",
                f"index gaps > 5x median spacing ({median_delta})",
                rows=gaps,
            )

    zero_vol = int((df["volume"] == 0).sum())
    if zero_vol and zero_vol > len(df) * 0.05:
        rep.add(
            "UND_ZERO_VOLUME",
            "warn",
            f"zero-volume bars exceed 5% (n={zero_vol}/{len(df)})",
            rows=zero_vol,
        )

    return rep


def check_option_chain(chain: pd.DataFrame, *, symbol: str, spot: float) -> QualityReport:
    rep = QualityReport(target=f"options:{symbol}")

    if chain.empty:
        rep.add("OPT_EMPTY", "error", "empty option chain")
        return rep

    for col in (
        "expiry",
        "strike",
        "right",
        "bid",
        "ask",
        "implied_volatility",
        "open_interest",
    ):
        if col not in chain.columns:
            rep.add("OPT_MISSING_COL", "error", f"missing column: {col}")

    if rep.has_errors:
        return rep

    bad_right = int((~chain["right"].isin(["C", "P"])).sum())
    if bad_right:
        rep.add("OPT_BAD_RIGHT", "error", "right not in {C,P}", rows=bad_right)

    bad_strike = int((chain["strike"] <= 0).sum() + chain["strike"].isna().sum())
    if bad_strike:
        rep.add("OPT_BAD_STRIKE", "error", "non-positive or NaN strike", rows=bad_strike)

    spread = chain["ask"] - chain["bid"]
    crossed = int(((spread < 0) & chain["bid"].notna() & chain["ask"].notna()).sum())
    if crossed:
        rep.add("OPT_CROSSED_QUOTES", "warn", "ask < bid", rows=crossed)

    iv_bad = int(
        ((chain["implied_volatility"] <= 0) | (chain["implied_volatility"] > 5.0)).sum()
    )
    if iv_bad:
        rep.add(
            "OPT_IV_OUT_OF_RANGE",
            "warn",
            "implied vol <=0 or >500% (likely junk row)",
            rows=iv_bad,
        )

    bad_oi = int((chain["open_interest"] < 0).sum())
    if bad_oi:
        rep.add("OPT_NEG_OI", "error", "negative open_interest", rows=bad_oi)

    if np.isfinite(spot) and spot > 0:
        far = int((chain["strike"] > spot * 5).sum() + (chain["strike"] < spot / 5).sum())
        if far:
            rep.add(
                "OPT_FAR_STRIKES",
                "info",
                "strikes more than 5x away from spot (often illiquid)",
                rows=far,
            )

    # "Expired" means expired RELATIVE TO THE SNAPSHOT, not relative to today.
    # If we use today's date, a 5-day-old snapshot will falsely flag every
    # contract whose expiry has passed since (even though they were live at
    # snapshot time). The `dte` column already bakes in the snapshot's asof.
    if "dte" in chain.columns:
        expired = int((chain["dte"] < 0).sum())
    else:
        today = pd.Timestamp.now(tz="UTC").date()
        expired = int((pd.to_datetime(chain["expiry"]).dt.date < today).sum())
    if expired:
        rep.add(
            "OPT_EXPIRED",
            "warn",
            "rows with expiry before snapshot asof (yfinance shouldn't return these)",
            rows=expired,
        )

    if "dte" in chain.columns:
        iv = chain["implied_volatility"]
        near_expiry = chain["dte"] <= 1
        iv_suspect = iv.notna() & ((iv < 0.05) | (iv > 3.0))
        n_unreliable = int((near_expiry & iv_suspect).sum())
        if n_unreliable:
            rep.add(
                "OPT_IV_UNRELIABLE_AT_EXPIRY",
                "warn",
                "implied_volatility outside [5%, 300%] on dte<=1 rows "
                "(yfinance 0DTE IV is fragile — use mid price instead of IV "
                "for factors on these rows)",
                rows=n_unreliable,
            )

    return rep


def check_snapshot_continuity(
    symbol: str,
    snapshots: list[tuple[str, pd.DataFrame, pd.DataFrame]],
    *,
    max_calendar_gap_days: int = 4,
    oi_jump_ratio: float = 5.0,
) -> QualityReport:
    """Cross-day sanity check on a sequence of stored option-chain snapshots.

    Catches problems that single-day `check_option_chain` can't see:
    1. Missing trading days (gap > `max_calendar_gap_days`).
    2. Column-set drift (yfinance silently dropping/renaming a field).
    3. Total-OI day-over-day jumps > `oi_jump_ratio` (data corruption proxy).

    Args:
        symbol: Symbol being checked (only used for the report target label).
        snapshots: List of (asof_date_str, chain_df, meta_df) tuples, ordered
            ascending by date. Caller is responsible for loading from storage.
        max_calendar_gap_days: Gap > this triggers `CONT_MISSING_DAY`. Default 4
            allows Fri→Mon plus one US holiday.
        oi_jump_ratio: total_OI[t] / total_OI[t-1] outside [1/r, r] triggers warn.

    Notes:
        We tolerate small column variation by checking against the union of
        REQUIRED_OPTION_COLUMNS — that's the contract; extra fields from the
        provider (e.g. yfinance's `contract_symbol`) can come and go.
    """
    from quant_lab.data.base import REQUIRED_OPTION_COLUMNS

    rep = QualityReport(target=f"continuity:{symbol}")

    if not snapshots:
        rep.add("CONT_NO_SNAPSHOTS", "info", "no snapshots to check")
        return rep
    if len(snapshots) == 1:
        rep.add("CONT_SINGLE_SNAPSHOT", "info", "only one snapshot; nothing to compare")
        return rep

    dates = [pd.Timestamp(d).date() for d, _, _ in snapshots]
    sorted_dates = sorted(dates)
    if dates != sorted_dates:
        rep.add(
            "CONT_UNSORTED",
            "error",
            "snapshots passed in non-ascending date order",
        )
        return rep

    for prev, curr in zip(dates[:-1], dates[1:], strict=False):
        gap = (curr - prev).days
        if gap > max_calendar_gap_days:
            rep.add(
                "CONT_MISSING_DAY",
                "warn",
                f"calendar gap of {gap} days between {prev} and {curr} "
                f"(threshold {max_calendar_gap_days})",
            )

    required = set(REQUIRED_OPTION_COLUMNS)
    for asof_date, chain, _ in snapshots:
        missing = required - set(chain.columns)
        if missing:
            rep.add(
                "CONT_FIELD_DRIFT",
                "error",
                f"snapshot {asof_date} missing required columns: {sorted(missing)}",
            )

    if rep.has_errors:
        return rep

    total_oi = []
    for asof_date, chain, _ in snapshots:
        if "open_interest" in chain.columns and not chain.empty:
            total_oi.append((asof_date, int(chain["open_interest"].sum())))
        else:
            total_oi.append((asof_date, 0))

    for (prev_d, prev_oi), (curr_d, curr_oi) in zip(
        total_oi[:-1], total_oi[1:], strict=False
    ):
        if prev_oi == 0 or curr_oi == 0:
            continue
        ratio = curr_oi / prev_oi
        if ratio > oi_jump_ratio or ratio < (1.0 / oi_jump_ratio):
            rep.add(
                "CONT_OI_JUMP",
                "warn",
                f"total OI jumped {ratio:.2f}x between {prev_d} ({prev_oi:,}) "
                f"and {curr_d} ({curr_oi:,}); threshold {oi_jump_ratio}x",
            )

    return rep
