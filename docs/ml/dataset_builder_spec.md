# Dataset Builder Specification (ML-P6)

Leakage-proof point-in-time supervised dataset builder for 0DTE ML research.

## Scope

This phase delivers:

1. Label specification (see `label_spec.md`)
2. Dataset row schema + manifest
3. Sample anchor generator
4. Outcome provider contract
5. Leakage checks
6. Session-grouped splits
7. Sample weighting
8. Synthetic / pilot dataset build

**Not in scope:** multi-resolution features (ML-P7), model training, multi-year backfill.

## Row schema

Each row includes version stamps, as-of context, label block, weights, and exclusion metadata.

Key context fields (features only):

```text
dataset_schema_version, label_schema_version, feature_schema_version
deterministic_contract_version
trade_date, as_of_timestamp, feature_cutoff_timestamp
expiration, root, session_id, anchor_type
replay_state_hash, deterministic_bundle_hash, source_partition_hashes
quality_score
spot_t, primary_pin_t, secondary_pin_t
zone_low_t, zone_high_t, zone_center_t
pin_score_t, expected_move_t
gamma_source, oi_semantics_status, spot_zone_state_at_as_of
sample_weight, exclusion_reasons, warning_codes
```

Labels stored as `labels.*` prefixed columns (separate from features).

Implementation: `quant_lab.ml.schemas.DatasetRow.row_dict()`.

## Build pipeline

```text
anchors → replay_state(as_of) → deterministic bundle → pin zone at as_of
       → outcome_provider.get_outcome() → compute_all_labels()
       → session sample weights → manifest + parquet
```

Entry points:

```python
from quant_lab.ml.datasets.point_in_time import (
    BuildConfig,
    SyntheticOutcomeProvider,
    build_dataset_rows,
    build_pilot_dataset_if_available,
)
```

## Sample anchors

| Type | Status |
|------|--------|
| `regular_5min` | Implemented — 09:35 … close−5min |
| `regular_1min` | Implemented — pilot only, not default backfill |
| `manual` | Implemented — explicit timestamps |
| `event_driven` | Interface only; returns empty (future: zone_edge_cross, pin_change, gamma_flip, iv/volume shock) |

## Outcome providers

| Provider | Use |
|----------|-----|
| `SyntheticOutcomeProvider` | Unit tests, adversarial fixtures |
| `PilotIndexOutcomeProvider` | Reads pilot lake `index_price_1s` |

`outcome_source_hash` enters dataset manifest.

## Leakage checks

Module: `quant_lab.ml.leakage`

Checks:

1. Feature timestamps `<= as_of_timestamp`
2. Label source timestamp `> as_of_timestamp`
3. No final daily volume in features
4. No future quote/trade/Greek/gamma/index/OI in features
5. Label zone matches as-of bundle zone
6. Session-grouped splits (no row-level random split)
7. Labels stored separately from features

## Split rules

Module: `quant_lab.ml.splits`

- `session_grouped_split` — chronological, `shuffle=False` enforced
- `expanding_walk_forward_split` — expanding train, disjoint test sessions
- `locked_holdout_split` — reserved holdout dates

Group key: `session_id` / `trade_date`. Embargo configurable via `embargo_days`.

## Sample weights

Default:

```text
sample_weight = 1 / count(included_samples_in_session)
```

Excluded rows (no valid zone → no primary label): weight `0`, not counted in denominator.

Optional hooks (`time_of_day_weight`, `quality_weight`) reserved for ML-P7; **no label-outcome weighting**.

## Output locations

| Path | Committed |
|------|-----------|
| `artifacts/datasets/pit_pilot/` | No (gitignored) |
| `docs/ml/label_dataset_builder_report.md` | Yes (summary only) |

## Manifest

See `build_dataset_manifest()` — includes schema versions, outcome hash, anchor config, date range, exclusion counts, split config, cutoff rules, open questions, `code_commit`.

No secrets or raw market rows in manifest.
