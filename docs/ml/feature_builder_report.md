# Feature Builder Report (ML-P7)

**Phase:** ML-P7 — Multi-Resolution Feature Construction  
**Branch:** `research/zdte-fusion-model`  
**Status:** Complete (tabular feature layer, no model training)

## Summary

Built leakage-safe multi-resolution tabular feature layer on top of ML-P6 dataset anchors:

- Feature catalog (219 features, 9 groups)
- Point-in-time feature row builder
- Quote/trade/index window features (at-or-before only)
- Quality + multi-resolution audit summaries
- Feature manifest + extended leakage checks

**No model training. No ThetaData network. No label/financial formula changes.**

## Pilot feature build

| Item | Value |
|------|-------|
| Label dataset | `artifacts/datasets/pit_pilot/` (3 rows) |
| Raw lake | `artifacts/raw_lake_pilot/` |
| Output | `artifacts/features/pit_pilot/` |
| Rows | 3 |
| Feature count (catalog) | 219 |
| Populated per row | ~218 (avg 1 null) |
| `source_max <= as_of` | Verified ✅ |
| Feature quality score range | 0.903 – 0.909 |

### Feature groups (catalog)

```json
{
  "context": 9,
  "deterministic": 33,
  "chain_summary": 20,
  "quote_microstructure": 36,
  "trade_flow_proxy": 44,
  "greeks_iv": 10,
  "index_path": 35,
  "quality": 12,
  "multiresolution": 20
}
```

### Missingness

- Zone distance features null when pilot lacks valid pin cluster (expected)
- Short index horizon → some forward-looking index windows sparse
- Average `missing_feature_count` ≈ 1.0 per row

## Synthetic fixture build

- `tests/test_ml_features_builder.py` builds from minimal replay fixture lake
- Validates context, deterministic, chain, quality, join keys, manifest

## Tests

| Suite | Tests | Result |
|-------|-------|--------|
| `test_ml_features_schema.py` | 6 | PASS |
| `test_ml_features_builder.py` | 6 | PASS |
| `test_ml_features_microstructure.py` | 4 | PASS |
| `test_ml_features_leakage.py` | 8 | PASS |
| Full `pytest -q` | 507 | PASS |
| Ruff (ML-P7 paths) | — | PASS |

## Modules added

```text
src/quant_lab/ml/features/
  __init__.py
  schemas.py
  raw_frames.py
  context.py
  deterministic.py
  chain_summary.py
  microstructure.py
  index_path.py
  multiresolution.py
  leakage.py
  manifest.py
  builder.py
```

## Acceptance gate

| Criterion | Status |
|-----------|--------|
| Feature catalog documented | PASS |
| All feature groups implemented | PASS |
| Multi-resolution 1s/10s/1m/5m summaries | PASS (10s audit-labeled) |
| Feature manifest | PASS |
| Leakage checks extended | PASS |
| No label columns in features | PASS |
| Synthetic + pilot build | PASS |
| No training / no ThetaData / no formula changes | PASS |

## ML-P8 readiness

**Allowed to enter ML-P8** (GBDT baseline on tabular join of features + labels). ML-P8 must:

- Join via exact hash keys (no nearest merge)
- Use ML-P6 splits/weights unchanged
- Not embed labels into feature parquet

## Open questions

- OI semantics not officially confirmed
- Pin score internal gamma recomputation
- True 10s native resampling deferred
- Pilot needs wider strike coverage for richer zone/distance features
