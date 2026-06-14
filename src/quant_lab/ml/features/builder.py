"""Point-in-time feature row and dataset builder (ML-P7)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.data.intraday_lake import PILOT_LAKE_ROOT
from quant_lab.data.intraday_time import SESSION_CLOSE, session_datetime
from quant_lab.data.point_in_time_replay import (
    DeterministicBundle,
    PointInTimeState,
    compute_deterministic_bundle,
    default_pilot_data_root,
    deterministic_input_to_factor_chain,
    replay_state,
    to_deterministic_input_frame,
)
from quant_lab.ml.datasets.point_in_time import build_as_of_context
from quant_lab.ml.features.chain_summary import compute_chain_summary_features
from quant_lab.ml.features.context import compute_context_features
from quant_lab.ml.features.deterministic import compute_deterministic_features
from quant_lab.ml.features.index_path import compute_index_path_features
from quant_lab.ml.features.leakage import check_feature_row_leakage
from quant_lab.ml.features.manifest import build_feature_manifest
from quant_lab.ml.features.microstructure import (
    compute_greeks_iv_features,
    compute_quote_microstructure_features,
    compute_trade_flow_features,
)
from quant_lab.ml.features.multiresolution import compute_multiresolution_features
from quant_lab.ml.features.raw_frames import (
    FeatureRawFrames,
    load_feature_raw_frames,
    max_source_timestamp,
)
from quant_lab.ml.features.schemas import (
    FEATURE_CATALOG_BY_NAME,
    FEATURE_SCHEMA_VERSION,
    FeatureConfig,
    FeatureDatasetBuildResult,
    FeatureRow,
)
from quant_lab.ml.schemas import AsOfContext, DatasetRow, LabelRow

PILOT_FEATURE_ROOT = Path("artifacts/features/pit_pilot")
PILOT_DATASET_ROOT = Path("artifacts/datasets/pit_pilot")


def build_feature_row(
    dataset_row: DatasetRow,
    replay_state_obj: PointInTimeState,
    deterministic_bundle: DeterministicBundle,
    *,
    ctx: AsOfContext | None = None,
    raw_frames: FeatureRawFrames | None = None,
    config: FeatureConfig | None = None,
) -> FeatureRow:
    """Build one leakage-safe feature row."""
    cfg = config or FeatureConfig()
    as_of = dataset_row.context.as_of_timestamp
    ctx = ctx or dataset_row.context

    if raw_frames is None:
        request = replay_state_obj.request
        raw_frames = load_feature_raw_frames(request)

    spot = ctx.spot_t
    input_df = to_deterministic_input_frame(replay_state_obj.option_chain, spot=spot)
    hours = (session_datetime(ctx.trade_date, SESSION_CLOSE) - as_of).total_seconds() / 3600.0
    factor_chain = deterministic_input_to_factor_chain(
        input_df,
        spot=spot,
        symbol="^SPX",
        dte=0,
        hours_to_close=max(hours, 0.0),
    )

    chain_feats, call_gex, put_gex = compute_chain_summary_features(
        replay_state_obj,
        factor_chain=factor_chain,
        spot=spot,
        expected_move=ctx.expected_move_t,
    )
    det_feats = compute_deterministic_features(ctx, deterministic_bundle, call_gex=call_gex, put_gex=put_gex)
    ctx_feats = compute_context_features(replay_state_obj)
    quote_feats = compute_quote_microstructure_features(raw_frames, as_of, cfg)
    trade_feats = compute_trade_flow_features(
        raw_frames,
        replay_state_obj,
        as_of,
        cfg,
        spot=spot,
        primary_pin=ctx.primary_pin_t,
    )
    greek_feats = compute_greeks_iv_features(raw_frames, replay_state_obj, as_of, spot=spot)
    index_feats = compute_index_path_features(raw_frames, replay_state_obj, as_of, cfg, spot=spot)

    quote_rate = quote_feats.get("quote_30s_quote_update_rate")
    trade_count = trade_feats.get("trade_300s_trade_count")
    iv_atm = greek_feats.get("iv_atm")
    mr_feats = compute_multiresolution_features(
        raw_frames,
        as_of,
        cfg,
        spot=spot,
        base_quote_rate_30s=quote_rate,
        base_trade_count_300s=float(trade_count) if trade_count is not None else None,
        base_iv_atm=iv_atm,
    )

    all_feats: dict[str, Any] = {}
    all_feats.update({k: v for k, v in ctx_feats.items() if k not in {"trade_date", "as_of_timestamp"}})
    all_feats.update(det_feats)
    all_feats.update(chain_feats)
    all_feats.update(quote_feats)
    all_feats.update(trade_feats)
    all_feats.update(greek_feats)
    all_feats.update(index_feats)
    all_feats.update(mr_feats)

    if cfg.strict_unknown_features:
        unknown = set(all_feats) - set(FEATURE_CATALOG_BY_NAME)
        if unknown:
            raise ValueError(f"unknown features: {sorted(unknown)}")

    warnings: list[str] = list(replay_state_obj.warnings)
    exclusions: list[str] = []
    if not ctx.has_valid_zone:
        exclusions.append("no_valid_zone_at_as_of")
    if ctx.oi_semantics_status == "unconfirmed":
        warnings.append("oi_semantics_unconfirmed")

    null_count = sum(1 for v in all_feats.values() if v is None)
    quality_feats = {
        "replay_quality_score": replay_state_obj.quality.quality_score,
        "feature_quality_score": 1.0 - null_count / max(len(all_feats), 1),
        "quote_duplicate_ratio": raw_frames.duplicate_ratio,
        "quote_out_of_order_ratio": raw_frames.out_of_order_ratio,
        "missing_feature_count": null_count,
        "nullable_feature_count": null_count,
        "stale_quote_ratio": replay_state_obj.quality.stale_quote_ratio,
        "stale_greek_ratio": replay_state_obj.quality.stale_greek_ratio,
        "stale_index": replay_state_obj.quality.stale_index,
        "oi_semantics_unconfirmed": ctx.oi_semantics_status == "unconfirmed",
        "gamma_is_derived_black76": ctx.gamma_source == "derived_black76_precomputed",
        "source_partition_count": len(ctx.source_partition_hashes),
    }
    all_feats.update(quality_feats)

    frames_for_max = [
        f for f in (
            raw_frames.quote_tick,
            raw_frames.trade_tick,
            raw_frames.greeks_1m,
            raw_frames.index_1s,
            raw_frames.index_tick,
        )
        if f is not None
    ]
    src_max = max_source_timestamp(frames_for_max)

    row = FeatureRow(
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        trade_date=ctx.trade_date,
        as_of_timestamp=as_of,
        replay_state_hash=ctx.replay_state_hash,
        deterministic_bundle_hash=ctx.deterministic_bundle_hash,
        features=all_feats,
        feature_warnings=warnings,
        feature_exclusion_reasons=exclusions,
        source_timestamp_max=src_max,
        source_partition_hashes=ctx.source_partition_hashes,
    )

    leak = check_feature_row_leakage(
        row.row_dict(),
        as_of,
        source_timestamp_max=src_max,
    )
    if not leak.passed:
        exclusions.extend([v.violation_type.value for v in leak.violations])
        row.feature_exclusion_reasons = exclusions

    return row


def build_feature_dataset(
    dataset_rows: Sequence[DatasetRow],
    data_root: Path,
    config: FeatureConfig | None = None,
    *,
    dataset_manifest: dict[str, Any] | None = None,
) -> FeatureDatasetBuildResult:
    cfg = config or FeatureConfig()
    feature_rows: list[FeatureRow] = []
    for ds_row in dataset_rows:
        ctx = ds_row.context
        state = replay_state(
            ctx.trade_date,
            ctx.as_of_timestamp,
            data_root=data_root,
        )
        input_df = to_deterministic_input_frame(state.option_chain, spot=ctx.spot_t)
        hours = (session_datetime(ctx.trade_date, SESSION_CLOSE) - ctx.as_of_timestamp).total_seconds() / 3600.0
        bundle = compute_deterministic_bundle(
            input_df,
            ctx.spot_t,
            symbol="^SPX",
            asof=ctx.trade_date,
            hours_to_close=max(hours, 0.0),
            use_precomputed_gamma=True,
        )
        raw = load_feature_raw_frames(state.request)
        feature_rows.append(
            build_feature_row(ds_row, state, bundle, ctx=ctx, raw_frames=raw, config=cfg)
        )

    manifest = build_feature_manifest(
        feature_rows,
        feature_config={
            "quote_windows_sec": list(cfg.quote_windows_sec),
            "trade_windows_sec": list(cfg.trade_windows_sec),
            "resolutions": list(cfg.resolutions),
        },
        dataset_manifest=dataset_manifest,
    )
    return FeatureDatasetBuildResult(rows=feature_rows, manifest=manifest)


def write_feature_dataset(
    result: FeatureDatasetBuildResult,
    output_root: Path = PILOT_FEATURE_ROOT,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    records = [r.row_dict() for r in result.rows]
    pd.DataFrame(records).to_parquet(output_root / "features.parquet", index=False)
    (output_root / "manifest.json").write_text(json.dumps(result.manifest, indent=2), encoding="utf-8")
    result.output_path = output_root
    return output_root


def build_pilot_feature_dataset_if_available() -> dict[str, Any] | None:
    """Build pilot features when dataset + raw lake exist."""
    lake = PILOT_LAKE_ROOT if PILOT_LAKE_ROOT.is_dir() else default_pilot_data_root()
    dataset_path = PILOT_DATASET_ROOT / "dataset.parquet"
    if not lake.is_dir() or not dataset_path.is_file():
        return None

    df = pd.read_parquet(dataset_path)

    dataset_rows: list[DatasetRow] = []
    for _, r in df.iterrows():
        raw_hashes = r.get("source_partition_hashes")
        if raw_hashes is None:
            part_hashes: tuple[str, ...] = ()
        elif isinstance(raw_hashes, (list, tuple)):
            part_hashes = tuple(str(h) for h in raw_hashes)
        else:
            part_hashes = tuple(str(h) for h in list(raw_hashes))

        ctx = AsOfContext(
            trade_date=pd.Timestamp(r["trade_date"]).date(),
            as_of_timestamp=pd.Timestamp(r["as_of_timestamp"]).to_pydatetime(),
            spot_t=float(r["spot_t"]),
            primary_pin_t=r.get("primary_pin_t"),
            secondary_pin_t=r.get("secondary_pin_t"),
            zone_low_t=r.get("zone_low_t"),
            zone_high_t=r.get("zone_high_t"),
            zone_center_t=r.get("zone_center_t"),
            zone_break_up=None,
            zone_break_down=None,
            pin_score_t=float(r["pin_score_t"]),
            expected_move_t=float(r["expected_move_t"]),
            gamma_source=str(r["gamma_source"]),
            oi_semantics_status=r.get("oi_semantics_status"),
            spot_zone_state_at_as_of=str(r.get("spot_zone_state_at_as_of", "unknown")),
            has_valid_zone=r.get("zone_low_t") is not None and pd.notna(r.get("zone_low_t")),
            quality_score=float(r.get("quality_score", 0.0)),
            replay_state_hash=str(r["replay_state_hash"]),
            deterministic_bundle_hash=str(r["deterministic_bundle_hash"]),
            source_partition_hashes=part_hashes,
        )
        excl = r.get("exclusion_reasons")
        if excl is None or (isinstance(excl, float) and pd.isna(excl)):
            exclusion_reasons: list[str] = []
        elif isinstance(excl, (list, tuple)):
            exclusion_reasons = list(excl)
        else:
            exclusion_reasons = list(excl)

        labels = LabelRow(exclusion_reasons=exclusion_reasons)
        dataset_rows.append(
            DatasetRow(context=ctx, labels=labels, anchor_type="manual", session_id=str(r.get("session_id", "")))
        )

    ds_manifest_path = PILOT_DATASET_ROOT / "manifest.json"
    ds_manifest = json.loads(ds_manifest_path.read_text(encoding="utf-8")) if ds_manifest_path.is_file() else None

    result = build_feature_dataset(dataset_rows, lake, dataset_manifest=ds_manifest)
    write_feature_dataset(result)

    quality_scores = [row.features.get("feature_quality_score") for row in result.rows]
    src_ok = all(
        row.source_timestamp_max is None or row.source_timestamp_max <= row.as_of_timestamp
        for row in result.rows
    )

    return {
        "row_count": len(result.rows),
        "feature_count": result.manifest["feature_count"],
        "feature_groups": result.manifest["feature_groups"],
        "missing_feature_count_mean": result.manifest["missing_feature_count_mean"],
        "quality_score_range": [min(quality_scores), max(quality_scores)] if quality_scores else None,
        "source_max_leq_as_of": src_ok,
        "output": str(PILOT_FEATURE_ROOT),
    }


def build_feature_row_from_replay(
    trade_date,
    as_of_timestamp,
    data_root: Path,
    config: FeatureConfig | None = None,
) -> FeatureRow:
    """Convenience: build feature row without pre-existing dataset row."""
    ctx, _, bundle = build_as_of_context(trade_date, as_of_timestamp, data_root=data_root)
    state = replay_state(trade_date, as_of_timestamp, data_root=data_root)
    ds = DatasetRow(context=ctx, labels=LabelRow(), anchor_type="manual")
    return build_feature_row(ds, state, bundle, ctx=ctx, config=config)
