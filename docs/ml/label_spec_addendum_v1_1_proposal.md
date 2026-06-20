# Label Spec Addendum v1.1 — Proposal (Not Approved)

**Document type:** Governance proposal — **not** the formal label specification  
**Status:** **Pending owner review**  
**Parent spec:** `docs/ml/label_spec.md` (`label_schema_version` **1.0.0** — unchanged)  
**Proposed addendum version:** `label_schema_addendum` **1.1.0-proposal**  
**Phase:** ML-P7.7.1  
**Branch:** `research/zdte-fusion-model`

> **Important:** This document does **not** modify, supersede, or approve changes to `docs/ml/label_spec.md`. Implementation in label builder, dataset builder, or training pipelines is **forbidden** until owner sign-off recorded in `label_target_owner_review_packet.md`.

---

## 1. Purpose

ML-P7.7 established that frozen Pin Zone targets (`close_location_vs_current_zone`, `close_inside_current_zone`) are **valid but sparse** (89 / ~1,393 anchors in P7.6.7 screening). This addendum **proposes additive baseline targets** derived from as-of `primary_pin_t`, without changing Pin Zone contract, thresholds, or existing zone label semantics.

---

## 2. Relationship to Formal Spec v1.0.0

| Item | v1.0.0 (`label_spec.md`) | This addendum (proposal) |
|------|--------------------------|---------------------------|
| Zone multiclass / binary | Defined | **Unchanged — strict secondary** |
| `close_distance_to_primary_pin_*` | Listed under close distance labels | **Elevated to baseline P0 with explicit EM definition + eligibility** |
| `close_near_primary_pin` | Boolean with `PinToleranceConfig` (default `fixed_5pt`) | **Proposed P1 with EM-relative threshold governance** |
| `close_above_below_primary_pin` | Not defined | **New optional P2 ternary (proposal)** |
| Baseline inclusion rules | Zone-centric (`has_valid_zone`) | **New parallel baseline track (proposal)** |

Upon approval, merged content would become `label_schema_version` **1.1.0** in a **future** formal spec update — not in this phase.

---

## 3. Unchanged Existing Targets (Explicit)

The following **remain unchanged** in meaning, computation, and role:

```text
close_location_vs_current_zone   — unchanged
close_inside_current_zone      — unchanged
```

```text
Zone targets remain strict / secondary targets.
No existing zone target is removed.
No Pin Zone threshold is changed.
No pin_cluster.py / GEX / Expected Move / Valid Exit formulas are changed.
```

New targets are **additive**. They do **not** replace frozen zone targets and must **not** be used to force-include no-zone rows into the zone track.

---

## 4. Proposed Baseline Track — Overview

| Priority | Target name | Type | Phase |
|----------|-------------|------|-------|
| **P0** | `close_distance_to_primary_pin_em` | Regression (float) | Required for baseline track |
| **P1** | `close_near_primary_pin` | Binary (bool) | Required for baseline classification |
| **P2** | `close_above_below_primary_pin` | Ternary (enum) | Optional; not required for first baseline |

**Proposed baseline inclusion (separate from zone inclusion):**

```text
baseline_included =
    primary_pin_t is non-null
    AND remaining_expected_move_t is finite and > 0
    AND official_close is non-null
    AND label_source_timestamp > as_of_timestamp
```

Zone track inclusion **unchanged:**

```text
zone_included =
    has_valid_zone == true
    AND close_location_vs_current_zone is non-null
```

A row may be `baseline_included` without being `zone_included`. Sample weights for each track are computed **within track per session** (proposal mirrors existing zone weighting pattern).

---

## 5. Target 1 — Regression (P0)

### 5.1 Name

```text
close_distance_to_primary_pin_em
```

### 5.2 Definition (proposal)

```python
close_distance_to_primary_pin_em = (
    official_close - primary_pin_t
) / remaining_expected_move_t
```

Where:

- `official_close`: session official close from outcome provider (label-only future information).
- `primary_pin_t`: top magnet strike from as-of deterministic bundle / pin ranking — **frozen at `as_of_timestamp`**.
- `remaining_expected_move_t`: as-of `expected_move_1sd` scaled by remaining session fraction per v1.0.0 `normalized_close_move` rules (sqrt time; **must not** use post-close IV).

### 5.3 Interpretation

```text
positive  => close above primary pin
negative  => close below primary pin
0         => close exactly at primary pin (theoretical; float equality unlikely)
```

Normalized by **remaining expected move** so magnitude is comparable across anchors and sessions.

### 5.4 Eligibility

Target is **non-null** only when **all** hold:

```text
primary_pin_t is non-null
remaining_expected_move_t is finite and > 0
official_close exists
label_source_timestamp > as_of_timestamp
```

Otherwise: target = `null`.

### 5.5 Target-specific exclusion reasons (proposal)

| Reason code | Condition |
|-------------|-----------|
| `primary_pin_missing_at_as_of` | `primary_pin_t` is null |
| `remaining_em_invalid` | EM missing, NaN, or ≤ 0 |
| `official_close_missing` | No official close in outcome |
| `label_timestamp_not_after_as_of` | Leakage guard failure |

These are **additive** to existing `exclusion_reasons`; they do not replace zone exclusion reasons.

### 5.6 Relation to v1.0.0

v1.0.0 already lists `close_distance_to_primary_pin_em` under close distance labels. This addendum **does not change the formula**; it **assigns baseline primary role**, explicit eligibility, and separate inclusion / weighting for ML-P8B entry track.

---

## 6. Target 2 — Binary Classification (P1)

### 6.1 Name

```text
close_near_primary_pin
```

### 6.2 Definition (proposal)

```python
close_near_primary_pin = (
    abs(close_distance_to_primary_pin_em) <= near_threshold_em
)
```

Where `near_threshold_em` is a **governance-selected** threshold in **EM units** (not points).

**Dependency:** Requires non-null `close_distance_to_primary_pin_em` (Target 1).

### 6.3 Threshold candidates (not finalized this phase)

Owner must choose one approach before ML-P8B:

| Candidate | Description |
|-----------|-------------|
| `0.25 EM` | Fixed: near if within 25% of remaining EM |
| `0.50 EM` | Fixed: near if within 50% of remaining EM |
| `train_calibrated` | Percentile or optimal threshold fit on **training sessions only** |

**Note:** v1.0.0 default builder tolerance is `fixed_5pt` for `close_near_primary_pin`. This addendum **proposes EM-relative threshold for baseline track** to align with Target 1 normalization. If approved, manifest must record which tolerance regime applies to baseline vs legacy column (see §9).

### 6.4 Threshold governance rules

```text
threshold must be selected using training data only
no test-set calibration
no holdout / locked-test session used for threshold fit
threshold version must be recorded in dataset manifest
calibration artifact must be versioned
calibration may not use holdout/test sessions
```

Proposed manifest fields:

```json
{
  "baseline_near_threshold_em": 0.25,
  "baseline_near_threshold_method": "fixed_em | train_calibrated",
  "baseline_near_threshold_version": "baseline-near-v1",
  "baseline_near_threshold_fit_sessions": ["2024-01-19", "..."]
}
```

(`fit_sessions` populated only when `train_calibrated`.)

### 6.5 Eligibility

Same as Target 1 eligibility, plus valid `close_distance_to_primary_pin_em`.

---

## 7. Target 3 — Directional Classification (P2, Optional)

### 7.1 Name

```text
close_above_below_primary_pin
```

### 7.2 Definition (proposal)

Uses the **same** `near_threshold_em` as Target 2:

```python
d = close_distance_to_primary_pin_em

if d < -near_threshold_em:
    label = "below"
elif abs(d) <= near_threshold_em:
    label = "near"
elif d > near_threshold_em:
    label = "above"
else:
    label = null  # d is null
```

### 7.3 Status

```text
Optional P2 target — not required for first baseline implementation.
Not required for ML-P7.8 coverage screening gate.
May be deferred to post-P8B evaluation track.
```

---

## 8. Leakage / Point-in-Time Rules

All proposed targets inherit v1.0.0 time rules and add:

```text
primary_pin_t comes from deterministic bundle at as_of_timestamp
features must remain <= as_of_timestamp
official_close is label-only future information
label_source_timestamp must be > as_of_timestamp
threshold calibration must use training split only
no same-session leakage across train/validation/test split
session-grouped split remains mandatory
no row-level random split
```

### 8.1 Threshold calibration leakage

If `train_calibrated` threshold is approved:

1. Fit threshold on **training sessions only** (session-grouped split).
2. Persist calibration artifact with version id and session list used.
3. Apply frozen threshold to validation / test / holdout — **no refit**.
4. Holdout sessions defined before any calibration (locked holdout from `split_readiness` pattern).

### 8.2 Feature / label separation

Baseline targets use the same `AsOfContext` fields as zone labels. No new feature columns are introduced by this addendum. Features continue to obey `FEATURE_CUTOFF_RULE = event_timestamp <= as_of_timestamp`.

---

## 9. Versioning and Manifest (Proposal)

Upon future implementation:

| Constant | Proposed value |
|----------|----------------|
| `label_schema_version` | `1.1.0` (formal spec update — **not this phase**) |
| `label_schema_addendum` | `1.1.0-proposal` |
| `baseline_target_track` | `primary_pin_distance_v1` |
| `zone_target_track` | `pin_zone_strict_v1` (unchanged) |

Dataset manifest must record:

- Baseline track inclusion count / exclusion reasons
- Zone track inclusion count (unchanged)
- `baseline_near_threshold_*` fields if P1 approved
- Both tracks' sample weight rules

---

## 10. Coverage Expectation (Evidence + Verification Requirement)

### 10.1 Observed zone track (P7.6.7)

```text
zone label included_total = 89 / ~1,393 anchors (~6.4%)
dates_with_any_zone = 4 / 19 screened dates
```

### 10.2 Observed primary pin availability (P7.6.1 diagnostic)

On terminal-parity sampled anchors across Stage A dates:

```text
primary_pin_t / pin_score_t / expected_move_t: ~100% non-null at as_of
```

This suggests ** materially higher baseline eligibility** than zone inclusion, but:

```text
Coverage must be verified in ML-P7.8 by running baseline target coverage screening.
```

**Do not treat P7.6.1 spot checks as final baseline coverage proof.**

---

## 11. What This Addendum Does Not Do

```text
Does NOT modify docs/ml/label_spec.md
Does NOT implement label builder changes
Does NOT change Pin Zone thresholds or pin_cluster.py
Does NOT replace zone targets with primary pin targets
Does NOT approve ML-P8B or model training
Does NOT ingest new dates or run full build
```

---

## 12. Approval Path

1. Owner completes [`label_target_owner_review_packet.md`](label_target_owner_review_packet.md)
2. If approved → formal `label_spec.md` v1.1.0 edit in a **later** phase (post-P7.7.1)
3. ML-P7.8 baseline coverage screening (no training)
4. ML-P8B only after P7.8 gates pass + implementation complete

**Status: Pending owner review**
