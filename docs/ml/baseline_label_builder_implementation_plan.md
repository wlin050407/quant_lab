# Baseline Label Builder Implementation Plan

**Phase:** ML-P7.8.1 — Plan only; **implementation in ML-P7.8.2**  
**Status:** Approved plan — **no code in P7.8.1**  
**Approval:** [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md)  
**Parent spec:** `docs/ml/label_spec.md` (`label_schema_version` **1.0.0** — unchanged this phase)  
**Addendum reference:** [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)  
**Screening reference:** [`baseline_target_coverage_screening_report.md`](baseline_target_coverage_screening_report.md)

---

## 1. Purpose

ML-P7.8 demonstrated that additive primary-pin baseline targets achieve **99.9% eligibility** (1390 / 1391 anchors) with leakage PASS and session-grouped split readiness, while zone labels remain sparse (89 rows). ML-P7.8.2 will implement these targets **additively** in the dataset label layer without modifying zone semantics, financial formulas, or formal `label_spec.md`.

**This document is the implementation blueprint for P7.8.2 only.**

---

## 2. Scope Boundaries

### In scope (P7.8.2)

- Additive label field computation in label builder path
- Eligibility and exclusion reason recording
- Unit tests (formula, eligibility, thresholds, leakage guards)
- Schema / manifest draft fields for v1.1

### Out of scope (P7.8.2)

- ML-P8B training
- Full feature build
- Joined dataset build for training
- Formal `label_spec.md` v1.1.0 merge (requires separate owner approval)
- Pin Zone threshold changes
- Production deployment

### Forbidden file changes (unless import-only compatibility)

```text
src/quant_lab/factors/**
quant_lab/terminal/**
docs/ml/label_spec.md (formal merge — not P7.8.2)
```

Planned touch points (P7.8.2):

```text
src/quant_lab/ml/labels.py              — additive baseline label functions
src/quant_lab/ml/datasets/sample_builder.py — emit new label columns + manifest
src/quant_lab/ml/schemas.py             — DatasetRow label block extension (if needed)
tests/test_baseline_labels.py           — new unit tests (name TBD)
```

Reuse screening logic from `baseline_target_screening.py` where possible (pure functions already validated in P7.8).

---

## 3. Proposed New Label Fields

All fields live under the existing `labels.*` namespace in dataset rows.

| Field | Type | Description |
|-------|------|-------------|
| `labels.close_distance_to_primary_pin_points` | float \| null | Signed point distance: `official_close - primary_pin_t` |
| `labels.close_distance_to_primary_pin_em` | float \| null | EM-normalized distance (P0 regression target) |
| `labels.close_near_primary_pin_025` | bool \| null | P1 binary @ 0.25 EM threshold |
| `labels.close_near_primary_pin_050` | bool \| null | P1 binary @ 0.50 EM threshold |
| `labels.close_above_below_primary_pin_025` | enum \| null | P2 ternary @ 0.25 EM: `below` / `near` / `above` |
| `labels.close_above_below_primary_pin_050` | enum \| null | P2 ternary @ 0.50 EM |
| `labels.baseline_target_eligible` | bool | True when baseline inclusion rule satisfied |
| `labels.baseline_target_exclusion_reasons` | list[str] | Empty when eligible; else reason codes |
| `labels.baseline_label_schema_version` | string | Per-row stamp, e.g. `1.1.0-draft` |

### 3.1 Formulas

```text
close_distance_to_primary_pin_points = official_close - primary_pin_t

close_distance_to_primary_pin_em =
    close_distance_to_primary_pin_points / remaining_expected_move_t
```

P1 (per threshold `τ` ∈ {0.25, 0.50}):

```text
close_near_primary_pin_{τ} = abs(close_distance_to_primary_pin_em) <= τ
```

P2 (per threshold `τ`):

```text
d = close_distance_to_primary_pin_em
if d < -τ:  close_above_below_primary_pin_{τ} = "below"
elif abs(d) <= τ:  close_above_below_primary_pin_{τ} = "near"
elif d > τ:  close_above_below_primary_pin_{τ} = "above"
else:  null
```

**Existing v1.0.0 fields unchanged:**

```text
close_location_vs_current_zone
close_inside_current_zone
close_near_primary_pin  (legacy fixed_5pt tolerance — do not repurpose)
```

Legacy `close_distance_to_primary_pin_points` / `_em` in v1.0 builder may already exist; P7.8.2 must **align formulas** with screening-validated definitions and add explicit eligibility + dual-threshold P1/P2 columns without breaking existing zone output.

---

## 4. Eligibility

Baseline targets are computed only when **all** hold:

```text
primary_pin_t is non-null
remaining_expected_move_t is finite and > 0
official_close exists
label_source_timestamp > as_of_timestamp
```

When ineligible:

- P0 / P1 / P2 label values → `null`
- `baseline_target_eligible` → `false`
- `baseline_target_exclusion_reasons` → populated (see §4.1)
- **Builder must not crash** on invalid rows

When eligible:

- `baseline_target_eligible` → `true`
- `baseline_target_exclusion_reasons` → `[]`
- P0 / P1 / P2 computed per formulas above

### 4.1 Exclusion reason codes

Reuse P7.8 screening codes (aligned with addendum proposal):

| Code | Condition |
|------|-----------|
| `primary_pin_missing_at_as_of` | `primary_pin_t` is null |
| `remaining_em_invalid` | EM missing, NaN, or ≤ 0 |
| `official_close_missing` | No official close in outcome |
| `label_timestamp_not_after_as_of` | Leakage guard failure |
| `label_source_timestamp_missing` | Outcome provider missing timestamp |

These are **additive** to existing zone `exclusion_reasons`; zone exclusion logic is untouched.

### 4.2 Inclusion tracks (dual-track)

```text
zone_included     = has_valid_zone AND close_location_vs_current_zone is non-null
                  (unchanged v1.0.0 rule)

baseline_included = baseline_target_eligible == true
                  (new parallel track)
```

A row may be `baseline_included` without `zone_included`. Sample weights for each track computed **within track per session** (mirror existing zone weighting pattern in P7.8.3 rebuild).

---

## 5. Thresholds

Both fixed EM thresholds are **implemented and stored**:

```text
0.25 EM  → close_near_primary_pin_025, close_above_below_primary_pin_025
0.50 EM  → close_near_primary_pin_050, close_above_below_primary_pin_050
```

**Do not select final production threshold in P7.8.2.**

Governance statement:

```text
0.50 EM is preferred for first baseline evaluation candidate.
0.25 EM remains tracked for sensitivity analysis.
Future train-calibrated threshold requires training-split-only calibration artifact.
```

Train-calibrated threshold (if ever approved):

- Fit on **training sessions only** (session-grouped split)
- Persist versioned calibration artifact with session list
- Apply frozen threshold to val / test / holdout — no refit
- Manifest records `baseline_near_threshold_method = train_calibrated`

---

## 6. Leakage Controls

Must preserve all v1.0.0 time rules plus baseline-specific guards:

```text
primary_pin_t from as-of deterministic bundle (frozen at as_of_timestamp)
official_close only from label future source (outcome provider)
label_source_timestamp > as_of_timestamp
features <= as_of_timestamp (FEATURE_CUTOFF_RULE unchanged)
session-grouped split only
no row-level random split
threshold calibration (if ever used) — training sessions only
```

Implementation requirements:

1. Reuse `quant_lab.ml.leakage.check_label_timestamp_after_as_of` in builder tests.
2. Baseline functions take `AsOfContext` + outcome — **no feature columns** as inputs.
3. Unit tests assert: ineligible when `label_source_timestamp <= as_of`.
4. Screening module `baseline_target_screening.py` remains reference implementation; builder output must match screening formulas on shared fixtures.

---

## 7. Manifest / Schema Requirements

Dataset manifest (P7.8.3 rebuild) must record:

```json
{
  "label_schema_version": "1.1.0-draft",
  "baseline_target_thresholds": [0.25, 0.50],
  "baseline_target_approval_record": "baseline_target_implementation_approval.md v1.0",
  "baseline_target_addendum": "label_spec_addendum_v1_1_proposal.md",
  "baseline_implementation_commit": "<P7.8.2 commit hash>",
  "baseline_leakage_validation": "PASS",
  "baseline_preferred_binary_threshold_em": 0.50,
  "zone_target_track": "pin_zone_strict_v1",
  "baseline_target_track": "primary_pin_distance_v1"
}
```

After formal owner approval of v1.1.0 spec merge, `label_schema_version` may become `1.1.0-approved`.

Per-row `labels.baseline_label_schema_version` must match manifest for audit.

---

## 8. Implementation Steps (P7.8.2)

| Step | Task | Deliverable |
|------|------|-------------|
| 1 | Extract / share pure functions from `baseline_target_screening.py` | Shared module or import from screening |
| 2 | Add `compute_baseline_primary_pin_labels()` in `labels.py` | Returns dict of new label fields |
| 3 | Integrate into `compute_all_labels()` **additively** | Zone labels unchanged |
| 4 | Extend `DatasetRow` / sample_builder manifest | New columns + manifest fields |
| 5 | Unit tests | Formula, eligibility, both thresholds, leakage, zone unchanged |
| 6 | Regression test | Screening vs builder output match on synthetic fixture |
| 7 | Document P7.8.2 completion report | Gates checklist |

**No dataset rebuild in P7.8.2** — rebuild deferred to P7.8.3.

---

## 9. P7.8.2 Acceptance Gate

P7.8.2 passes when **all** hold:

```text
baseline targets implemented as additive labels
existing zone labels unchanged
label_spec.md either unchanged or updated only after explicit approval
unit tests for formula, eligibility, thresholds, leakage
no full feature build
no training
no artifacts committed
full pytest pass
ruff pass
```

---

## 10. P7.8.3 Acceptance Gate (Preview)

P7.8.3 dataset rebuild + coverage validation:

```text
dataset rebuilt with v1.1 draft labels
baseline_eligible_rows >= 300
eligible_sessions >= 10
P1 0.50 has both classes
leakage PASS
session-grouped split readiness PASS
zone labels still present
no training
no artifacts committed
```

See [`label_schema_v1_1_migration_plan.md`](label_schema_v1_1_migration_plan.md) for rebuild and rollback details.

---

## 11. What P7.8.2 Does Not Do

```text
Does NOT train models
Does NOT enter ML-P8B
Does NOT modify Pin Zone thresholds or pin_cluster.py
Does NOT replace zone labels
Does NOT merge formal label_spec.md v1.1.0
Does NOT commit artifacts or parquet
Does NOT run full feature / joined build
```

---

**End of implementation plan.**
