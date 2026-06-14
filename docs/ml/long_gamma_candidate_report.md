# ML-P7.6.2 Long-Gamma Candidate Discovery Report

**Phase:** ML-P7.6.2 — Long-Gamma Candidate Discovery and Zone Coverage Rebuild  
**Branch:** `research/zdte-fusion-model`  
**ML-P7.6.1 commit:** `295ae3a`

## Objective

Verify whether **long-γ / high pin-reliability** sessions produce valid Pin Zone labels under the frozen deterministic contract.

## Candidate Date Sources

| Source | Count | Notes |
|--------|-------|-------|
| Config `pit_long_gamma_candidates_v1.yaml` | 19 | normal, range, opex, early_close, high_vol |
| Raw lake already present | 3 | 2024-01-05, 2024-07-03, 2025-04-04 |
| Newly ingested (in progress) | up to 16 | controlled `--ingest-missing` |

## Scan Method

Per date, **6 hourly anchors** (3 on early_close):

```text
10:00, 11:00, 12:00, 13:00, 14:00, 15:00 ET
```

Per anchor (terminal parity path):

- `replay_state` → `compute_deterministic_bundle` → `detect_pin_cluster`
- Collect: net_gex, regime, pin_reliability, pins, zone, failure reason
- **No** full dataset build, **no** model training

## Dry-Run Results (Existing Lake Only)

| Date | day_type | long_γ ratio | valid zone ratio | Dominant failure |
|------|----------|-------------|------------------|------------------|
| 2024-07-03 | early_close | **100%** | 0% | secondary_strength_too_low |
| 2024-01-05 | normal | 0% | 0% | short_gamma_regime |
| 2025-04-04 | monthly_opex | 0% | 0% | short_gamma_regime |

**Aggregate (3 scannable dates):**

- `long_gamma_anchor_ratio_mean`: 33%
- `valid_zone_anchor_ratio_mean`: **0%**
- `dates_with_any_valid_zone`: **0**

### Dry-Run Top Candidates (lake-only)

1. `2024-07-03` — long-γ but secondary too weak  
2. `2025-04-04` — short-γ  
3. `2024-01-05` — short-γ  

> Ranking by composite score favors long-γ even without valid zone. Full scan with ingest pending.

## Full Scan Status

```bash
python scripts/discover_long_gamma_candidates.py \
  --config config/ml/pit_long_gamma_candidates_v1.yaml \
  --max-dates 19 \
  --ingest-missing \
  --top-n 10
```

Output: `artifacts/reports/pit_long_gamma_candidates_v1/candidate_ranking.json`

## Stage A+ Rebuild

Config: `config/ml/pit_sample_long_gamma_v1.yaml`

Outputs (separate from Stage A v1):

```text
artifacts/datasets/pit_sample_long_gamma_v1/
artifacts/features/pit_sample_long_gamma_v1/
artifacts/reports/pit_sample_long_gamma_v1/
```

```bash
python scripts/build_pit_dataset_sample.py \
  --config config/ml/pit_sample_long_gamma_v1.yaml \
  --max-dates 8
```

## Preliminary Conclusion (Dry-Run)

**Case 2 trajectory:** Even the only long-γ date (2024-07-03) fails on **secondary_strength_too_low**, not short-γ gate. Zone label may remain sparse until:

- More range/low-vol long-γ dates ingested, OR
- Label spec governance (see `docs/ml/label_spec_governance_options.md`)

## Restrictions Honored

- No ML-P8B / no model training
- No Pin/GEX/VEX/Expected Move formula changes
- No label spec mutation
- No raw/dataset artifacts committed

## Commands

```bash
# Dry-run (lake-only scan)
python scripts/discover_long_gamma_candidates.py --config config/ml/pit_long_gamma_candidates_v1.yaml --max-dates 19 --dry-run

# Full discovery + controlled ingest
python scripts/discover_long_gamma_candidates.py --config config/ml/pit_long_gamma_candidates_v1.yaml --max-dates 19 --ingest-missing

# Stage A+ build
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_long_gamma_v1.yaml --max-dates 8
```
