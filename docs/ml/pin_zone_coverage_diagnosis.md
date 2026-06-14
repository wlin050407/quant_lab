# ML-P7.6.1 Pin Zone Coverage Diagnosis

**Phase:** ML-P7.6.1 — Stage A Rerun and Pin Zone Coverage Diagnosis  
**Branch:** `research/zdte-fusion-model`

## Stage A Rerun Summary

| Metric | Before (ML-P7.6) | After (ML-P7.6.1) |
|--------|------------------|-------------------|
| Row count | 231 (77+77+77) | **195** (77+41+77) |
| Early-close latest anchor | 15:55 ET ❌ | **12:55 ET** ✅ |
| Leakage validation | FAIL (36 violations) | **PASS** ✅ |
| valid_zone_ratio | 0% | **0%** (unchanged) |
| included rows | 0 | 0 |
| Ingest requests | — | 0 (idempotent skip) |

## Part 1: Leakage Fix — VERIFIED

- `2024-07-03` anchor count reduced **77 → 41** (`session_close_time=13:00:00`)
- Latest anchor: `2024-07-03T12:55:00-04:00`
- `leakage_validation.json`: **passed=true**, violations=[]

## Part 2: Pin Zone Root Cause Analysis

### 2.1 Adapter Bug (FIXED)

**Symptom:** Replay path called `detect_pin_cluster()` with default `pin_reliability="unknown"` and `regime="undetermined"`, triggering merge gate:

```text
if pin_reliability in ("low", "unknown") and regime != "long_gamma":
    → merge_reason = "low_pin_reliability"
```

**Fix (adapter only, no formula change):** `build_as_of_context()` now passes `regime_from_net_gex(bundle.net_gex)` and `pin_reliability(bundle.pin_score, regime)` — same as Terminal `build_pin_targets()`.

**Evidence:** Diagnosis sampled anchors show **100% `low_pin_reliability_gate`** on `replay_default` path vs terminal parity path using real regime/reliability.

### 2.2 After Adapter Fix — Why valid_zone_ratio Still 0%

Diagnosis on Stage A lake (`sample_every_n=5`):

| Date | day_type | Sampled | Parity valid | Dominant failure reason |
|------|----------|---------|--------------|-------------------------|
| 2024-01-05 | normal | 16 | **0** | `short_gamma_regime` (15), `pin_distance_too_wide` (1) |
| 2024-07-03 | early_close | 9 | **0** | `secondary_strength_too_weak` (9) |
| 2025-04-04 | monthly_opex | 16 | **0** | `short_gamma_regime` (16) |

**Conclusion:** Zone absence is **not** primarily missing data — it is **frozen contract gating**:

1. **`short_gamma_regime`** — `pin_cluster.py` returns no cluster when `regime == "short_gamma"` (net GEX < 0). Both normal and monthly_opex dates show deeply negative net GEX (e.g. 2024-01-05 @ 13:00: net GEX ≈ −8.1e11).
2. **`secondary_too_weak`** — Early-close day: top-2 magnet strength ratio < 70% threshold.
3. **`pin_distance_too_wide`** — Occasional: primary/secondary strikes > 0.3% spot apart.

### 2.3 Replay State Coverage (adequate)

Per-date sampled means:

| Metric | 2024-01-05 | 2024-07-03 | 2025-04-04 |
|--------|------------|------------|------------|
| contract_count | 240 | 230 | 240 |
| greeks_coverage | 1.0 | 1.0 | 1.0 |
| gamma_coverage | 0.79 | 0.75 | 0.84 |
| oi_coverage | 0.94 | 0.84 | 0.82 |
| replay_quality | 0.93 | 0.92 | 0.93 |

Chain width ~625 pts (4395–5020) vs spot ~4693 — **covers spot ± expected_move (~±36 pts)**. Strike range=60 is **not** the primary blocker.

### 2.4 Deterministic Bundle Field Coverage

On sampled anchors (terminal parity path):

- `primary_pin_t` / `pin_score_t` / `expected_move_t`: **100% non-null**
- `secondary_pin_t`: present when ≥2 magnets ranked
- `zone_low_t` / `zone_high_t`: **0%** — cluster never merges

### 2.5 Live vs Replay Path

| Path | Regime / reliability | Zone on 2024-01-05 @ 13:00 |
|------|---------------------|------------------------------|
| replay_default (old) | undetermined / unknown | ❌ low_pin_reliability |
| terminal_parity (fixed) | short_gamma / caution | ❌ short_gamma_regime |
| Terminal production | same as parity | ❌ (same contract gates) |

**Not an adapter omission for zone helper** — replay calls same `detect_pin_cluster()` as Terminal. Difference was missing regime/reliability inputs (now fixed).

### 2.6 Label Design Impact

ML-P6 primary zone label requires `has_valid_zone=true`. With frozen Pinning Zone contract:

> **Zone-based primary label is structurally sparse on short-γ sessions** — by design, not data bug.

## Governance Options (NOT executed this phase)

| Option | Description | This phase |
|--------|-------------|------------|
| A | Keep zone label; expand dates/strikes; re-evaluate | Recommended next |
| B | Add `primary_pin_distance` baseline target | Open question |
| C | Pin-centered zone fallback label | Open question |
| D | Change Pin Zone contract thresholds | **Forbidden** without owner sign-off |

## Next Step Recommendation

1. ✅ **Adapter fix merged** — keep for all future builds  
2. ❌ **Do not run Stage B / ML-P8B** — valid_zone_ratio still 0%  
3. **ML-P7.6.2:** Long-γ candidate discovery — see `docs/ml/long_gamma_candidate_report.md`
4. **Expand date sample** biased toward long-γ sessions OR pursue label spec governance (Option A/B) before baseline training

## ML-P7.6.2 Update

Dry-run scan (3 existing lake dates):

| Date | long_γ anchor ratio | valid zone ratio |
|------|---------------------|------------------|
| 2024-07-03 | 100% | 0% (secondary_strength_too_low) |
| 2024-01-05 | 0% | 0% (short_gamma_regime) |
| 2025-04-04 | 0% | 0% (short_gamma_regime) |

Full discovery with controlled ingest: `scripts/discover_long_gamma_candidates.py --ingest-missing`

## Commands

```bash
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_ingest_v1.yaml --stage a --max-dates 3 --dry-run
python scripts/build_pit_dataset_sample.py --config config/ml/pit_sample_ingest_v1.yaml --stage a --max-dates 3
python scripts/diagnose_pin_zone_coverage.py --config config/ml/pit_sample_ingest_v1.yaml --max-dates 3
```
