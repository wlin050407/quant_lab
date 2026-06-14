# ML-P7.6 Controlled ThetaData Ingest Report

**Phase:** ML-P7.6 — Controlled Real ThetaData Ingestion and 20-Day Sample Build  
**Branch:** `research/zdte-fusion-model`  
**Config:** `config/ml/pit_sample_ingest_v1.yaml`

## Executive summary

Full-RTH ThetaData ingest and 3-day Stage A smoke build **completed for all 3 dates** (231 rows). **Stage A gate FAIL** — no valid pin-cluster zone labels (`valid_zone_ratio=0%`), early-close leakage on first build (fixed in code for future runs). **Stage B not executed.** **Not ready for ML-P8B.**

## Stage A dates

| Date | day_type | Ingest | Build |
|------|----------|--------|-------|
| 2024-01-05 | normal | complete (idempotent skip on rebuild) | 77 anchors |
| 2024-07-03 | early_close | complete | 77 anchors (41 after early-close anchor fix) |
| 2025-04-04 | monthly_opex | complete | 77 anchors |

## Dry-run (3 dates)

- **Total anchors:** 231 (77×3; early_close should be 41 after fix)
- **Estimated API calls:** 27 total (~9/date with tick_or_1s)
- **Quote policy:** `tick_or_1s` with explicit `full_rth_strike_range_60_skip_tick_attempt` → `option_quote_1s`
- **Output paths:** `artifacts/raw_lake_sample/`, `artifacts/datasets/pit_sample_v1/`, etc.

## Stage A build results

| Metric | Value |
|--------|-------|
| Successful dates | 3/3 |
| Failed dates | 0 |
| Row count | 231 |
| Included rows | 0 |
| Excluded rows | 231 |
| valid_zone_ratio | 0.0 |
| Leakage (first run) | FAIL (early_close anchors past 13:00 ET) |
| ThetaData requests (incremental) | 1 (2025-04-04 quote 1s on rebuild) |
| raw_lake size | ~121 MB |
| joined size | ~400 KB |
| Replay speed | ~11.9 s/anchor |
| Feature speed | ~15.1 s/row |

### Quote resolution manifest

- **2025-04-04:** `option_quote_1s`, reason `full_rth_strike_range_60_skip_tick_attempt`
- **2024-01-05 / 2024-07-03:** ingested in prior long run; quote tick attempt exceeded 46M rows → fallback to 1s (logged)

### Zone label analysis (no formula changes)

All 231 rows excluded with `no_valid_zone_at_as_of` / `close_location_skipped_no_zone`:

- `primary_pin_t` populated; `pin_score_t` mean ~54
- `zone_low_t` / `zone_high_t` **always null** → pin **cluster** never valid
- `spot_zone_state_at_as_of` = `unknown` for all rows

**Likely cause:** deterministic pin-cluster validity threshold not met on these sessions with `strike_range=60` + quote_1s chain; not a ingest/replay join bug.

### Early-close leakage fix (code)

`AnchorConfig.session_close_time` + `day_type=early_close` → anchors end 12:55 ET (not 15:55). Prevents post-close anchors where `label_source_timestamp` equals 13:00 close.

## Stage B

**Not run** — Stage A gate failed (`valid_zone_ratio`, leakage on first run).

## ML-P8B readiness

**NOT READY**

| Criterion | Status |
|-----------|--------|
| row_count ≥ 1000 | FAIL (231) |
| included_rows ≥ 300 | FAIL (0) |
| valid_zone_ratio ≥ 20% | FAIL (0%) |
| zone categories ≥ 2 | FAIL |
| leakage PASS | FAIL (first run; fix pending re-build) |

## ML-P7.6.1 Update (Stage A Rerun)

- **Leakage:** PASS after early-close anchor fix (195 rows, 2024-07-03 latest anchor 12:55 ET)
- **Adapter fix:** replay path now passes `regime` + `pin_reliability` to `detect_pin_cluster()` (Terminal parity)
- **valid_zone_ratio:** still **0%** — root cause is frozen contract gates (`short_gamma_regime`, `secondary_too_weak`), not missing ingest
- See [`pin_zone_coverage_diagnosis.md`](pin_zone_coverage_diagnosis.md)

## ML-P7.6.2 Update (Long-Gamma Candidate Discovery)

- **Discovery config:** `config/ml/pit_long_gamma_candidates_v1.yaml` (19 candidate dates)
- **Dry-run (3 lake dates):** `valid_zone_anchor_ratio_mean=0%`; 2024-07-03 is 100% long-γ but secondary_strength_too_low
- **Full scan:** controlled ingest for 16 missing dates via `discover_long_gamma_candidates.py --ingest-missing`
- **Stage A+ config:** `config/ml/pit_sample_long_gamma_v1.yaml` → separate outputs under `pit_sample_long_gamma_v1/`
- **Governance proposal:** `docs/ml/label_spec_governance_options.md` (not implemented)
- See [`long_gamma_candidate_report.md`](long_gamma_candidate_report.md)

## Next Step Recommendation

1. Complete long-γ discovery ingest + Stage A+ rebuild
2. If `valid_zone_ratio >= 20%` → expand to 20-day long-γ-aware sample
3. If still ~0% → label spec governance (Option B) before ML-P8B
4. **Do not** run ML-P8B until zone coverage or governance resolved

## Commands

```bash
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_ingest_v1.yaml --max-dates 3 --dry-run
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_ingest_v1.yaml --stage a --max-dates 3
# Stage B only after stage_a_gate.json passed:
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_ingest_v1.yaml --stage b --max-dates 20 --require-stage-a
```
