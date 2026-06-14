# Label Dataset Builder Report (ML-P6)

**Phase:** ML-P6 — Label Specification and Leakage-Proof Dataset Builder  
**Branch:** `research/zdte-fusion-model`  
**Status:** Complete (skeleton + pilot build)

## Summary

Implemented a leakage-proof point-in-time supervised dataset builder:

- Label functions with as-of zone / future outcome separation
- Typed row schema + manifest
- Anchor generator (5min / 1min / manual; event-driven stub)
- Outcome providers (synthetic + pilot index)
- Leakage checks + adversarial test hooks
- Session-grouped / walk-forward / locked-holdout splits
- Per-session sample weighting

**No model training. No ThetaData network. No financial formula changes.**

## Pilot dataset build

| Item | Value |
|------|-------|
| Raw lake | `artifacts/raw_lake_pilot/` (exists) |
| Trade date | 2026-06-10 |
| Anchors | 13:00:30, 13:01:00, 13:01:30 ET |
| Output | `artifacts/datasets/pit_pilot/` (gitignored) |
| Rows | 3 |
| Sessions | 1 |

### Pilot observations

- Pilot lake has **8 contracts** but magnet cluster merge gates did not form a valid zone at the three anchors → primary close-location labels null, all rows `excluded_row_count=3` with weight 0.
- Forward realized vol labels null: pilot index window ends ~13:02 ET — insufficient 5m/15m/30m horizon after anchors.
- Exit labels partially computable when path exists but zone-dependent labels skipped.
- This is **expected** for minimal pilot fixtures; ML-P7 feature work does not require relabeling until multi-strike cluster fixtures expand.

### Outcome source

- `PilotIndexOutcomeProvider` reads `index_price_1s` partition from pilot lake.
- `official_close` = last index price in partition (synthetic pilot session, not live RTH close).
- `outcome_source_hash` recorded in manifest.

## Synthetic fixture build

- `tests/test_ml_point_in_time_dataset.py` builds one row from minimal replay fixture lake + `SyntheticOutcomeProvider`.
- Validates replay/bundle hashes, schema fields, manifest generation.

## Tests

| Suite | Result |
|-------|--------|
| `test_ml_labels.py` | PASS |
| `test_ml_leakage.py` | PASS |
| `test_ml_splits.py` | PASS |
| `test_ml_point_in_time_dataset.py` | PASS |
| Full `pytest -q` | PASS (483 tests) |
| Ruff (ML paths) | PASS |

## Modules added

```text
src/quant_lab/ml/
  __init__.py
  schemas.py
  labels.py
  leakage.py
  splits.py
  datasets/
    __init__.py
    point_in_time.py
```

## Acceptance gate

| Criterion | Status |
|-----------|--------|
| Label spec documented | PASS |
| Primary labels implemented + tested | PASS |
| Exit labels implemented (zone-dependent nullable) | PASS |
| Normalized close move | PASS |
| Anchor generator | PASS |
| Dataset row schema | PASS |
| Manifest | PASS |
| Leakage checks | PASS |
| Session-grouped split | PASS |
| Walk-forward split | PASS |
| Sample weights | PASS |
| Synthetic build | PASS |
| Pilot build | PASS (zone null expected on minimal pilot) |
| No ThetaData / no training / no formula changes | PASS |

## ML-P7 readiness

**Allowed to enter ML-P7** (multi-resolution feature construction) — dataset/label contract is frozen for this schema version. ML-P7 must consume `AsOfContext` + replay hashes without altering label time rules.

## Open questions (carried forward)

- OI semantics not officially confirmed
- Pin score internal gamma recomputation (OQ-1)
- Event-driven anchors: interface only until feature detectors exist
- Pilot needs wider strike coverage for non-null zone labels in acceptance demos
