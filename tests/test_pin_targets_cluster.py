"""build_pin_targets includes pinning zone payload when magnets merge."""

from __future__ import annotations

from quant_lab.terminal.snapshot import build_pin_targets


def test_build_pin_targets_cluster_payload() -> None:
    heatmap = [
        {"strike": 7600.0, "net_gex": 2.0e9, "net_gex_bn": 2.0, "total_oi": 1000.0},
        {"strike": 7615.0, "net_gex": 1.9e9, "net_gex_bn": 1.9, "total_oi": 980.0},
        {"strike": 7550.0, "net_gex": -1.0e9, "net_gex_bn": -1.0, "total_oi": 500.0},
    ]
    out = build_pin_targets(
        heatmap,
        spot=7600.0,
        king=7600.0,
        max_pain=7550.0,
        pin_score=75.0,
        oi_concentration_top3=0.4,
        regime="long_gamma",
        symbol="^SPX",
        macro_blocked=False,
    )
    cluster = out["pin_cluster"]
    assert cluster["is_cluster"] is True
    assert cluster["lower"] == 7600.0
    assert cluster["upper"] == 7615.0
    assert cluster["up_break_level"] == 7620.0
    assert cluster["down_break_level"] == 7595.0
    assert cluster["spot_zone_state"] == "inside_zone"
    tagged = [r for r in out["rankings"] if "cluster" in r["tags"]]
    assert len(tagged) == 2


def test_build_pin_targets_no_cluster_when_far_apart() -> None:
    heatmap = [
        {"strike": 7600.0, "net_gex": 2.0e9, "net_gex_bn": 2.0, "total_oi": 1000.0},
        {"strike": 7700.0, "net_gex": 1.9e9, "net_gex_bn": 1.9, "total_oi": 980.0},
    ]
    out = build_pin_targets(
        heatmap,
        spot=7600.0,
        king=7600.0,
        max_pain=7550.0,
        pin_score=75.0,
        oi_concentration_top3=0.4,
        regime="long_gamma",
        symbol="^SPX",
    )
    assert out["pin_cluster"]["is_cluster"] is False
