"""Deterministic replay quality heuristics (ML-P4)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ReplayQuality:
    """Rule-based quality summary — not an ML score."""

    quote_coverage_ratio: float
    trade_coverage_ratio: float
    greeks_coverage_ratio: float
    gamma_coverage_ratio: float
    oi_coverage_ratio: float
    index_available: bool
    stale_quote_ratio: float
    stale_greek_ratio: float
    stale_index: bool
    duplicate_ratio: float
    out_of_order_ratio: float
    missing_contract_count: int
    active_contract_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)
    quality_score: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "quote_coverage_ratio": self.quote_coverage_ratio,
            "trade_coverage_ratio": self.trade_coverage_ratio,
            "greeks_coverage_ratio": self.greeks_coverage_ratio,
            "gamma_coverage_ratio": self.gamma_coverage_ratio,
            "oi_coverage_ratio": self.oi_coverage_ratio,
            "index_available": self.index_available,
            "stale_quote_ratio": self.stale_quote_ratio,
            "stale_greek_ratio": self.stale_greek_ratio,
            "stale_index": self.stale_index,
            "duplicate_ratio": self.duplicate_ratio,
            "out_of_order_ratio": self.out_of_order_ratio,
            "missing_contract_count": self.missing_contract_count,
            "active_contract_count": self.active_contract_count,
            "warnings": list(self.warnings),
            "quality_score": self.quality_score,
        }


def _coverage(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.notna().mean())


def compute_replay_quality(
    option_chain: pd.DataFrame,
    *,
    index_available: bool,
    stale_index: bool,
    duplicate_ratio: float,
    out_of_order_ratio: float,
    warnings: list[str],
) -> ReplayQuality:
    """Simple deterministic heuristic documented in ``docs/ml/point_in_time_spec.md``."""
    active = int(len(option_chain))
    if active == 0:
        return ReplayQuality(
            quote_coverage_ratio=0.0,
            trade_coverage_ratio=0.0,
            greeks_coverage_ratio=0.0,
            gamma_coverage_ratio=0.0,
            oi_coverage_ratio=0.0,
            index_available=index_available,
            stale_quote_ratio=0.0,
            stale_greek_ratio=0.0,
            stale_index=stale_index,
            duplicate_ratio=duplicate_ratio,
            out_of_order_ratio=out_of_order_ratio,
            missing_contract_count=0,
            active_contract_count=0,
            warnings=tuple(warnings),
            quality_score=0.0,
        )

    quote_cov = _coverage(option_chain["latest_bid"])
    trade_cov = _coverage(option_chain["last_trade_price"])
    greek_cov = _coverage(option_chain["delta"])
    gamma_cov = _coverage(option_chain["gamma"])
    oi_cov = _coverage(option_chain["open_interest"])

    stale_quote_ratio = float(
        option_chain.get("data_quality_flags", pd.Series(dtype=object))
        .astype(str)
        .str.contains("stale_quote", na=False)
        .mean()
    ) if "data_quality_flags" in option_chain.columns else 0.0

    stale_greek_ratio = float(
        option_chain.get("data_quality_flags", pd.Series(dtype=object))
        .astype(str)
        .str.contains("stale_greek", na=False)
        .mean()
    ) if "data_quality_flags" in option_chain.columns else 0.0

    missing_contract_count = int(
        option_chain["data_quality_flags"]
        .astype(str)
        .str.contains("missing_quote", na=False)
        .sum()
    ) if "data_quality_flags" in option_chain.columns else 0

    score = 1.0
    score -= (1.0 - quote_cov) * 0.25
    score -= (1.0 - greek_cov) * 0.20
    score -= (1.0 - gamma_cov) * 0.10
    if not index_available:
        score -= 0.15
    if stale_index:
        score -= 0.05
    score -= stale_quote_ratio * 0.15
    score -= stale_greek_ratio * 0.10
    if any("oi_semantics_unconfirmed" in w for w in warnings):
        score -= 0.05
    score = float(max(0.0, min(1.0, score)))

    return ReplayQuality(
        quote_coverage_ratio=quote_cov,
        trade_coverage_ratio=trade_cov,
        greeks_coverage_ratio=greek_cov,
        gamma_coverage_ratio=gamma_cov,
        oi_coverage_ratio=oi_cov,
        index_available=index_available,
        stale_quote_ratio=stale_quote_ratio,
        stale_greek_ratio=stale_greek_ratio,
        stale_index=stale_index,
        duplicate_ratio=duplicate_ratio,
        out_of_order_ratio=out_of_order_ratio,
        missing_contract_count=missing_contract_count,
        active_contract_count=active,
        warnings=tuple(warnings),
        quality_score=score,
    )
