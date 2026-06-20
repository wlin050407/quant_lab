# ML-P8A — Baseline Modeling Harness Plan

**Phase:** ML-P8A — Baseline Modeling Harness Plan  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P7.8.4 — Owner Review for Baseline Dataset Gate (`65dcdfc`)  
**Entry approval:** [`p8a_entry_approval_record.md`](p8a_entry_approval_record.md)  
**Related protocols:**

- [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md)
- [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)
- [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md)

---

## Status

```text
ML-P8A: PLAN ONLY — no training, no model fitting, no prediction artifacts
ML-P8B: BLOCKED
Formal label_spec.md: UNCHANGED (v1.0.0)
```

---

## 1. Purpose

ML-P7.8.4 authorized **planning and harness design only**. This document defines the complete baseline modeling / evaluation harness for v1.1 draft pin-distance targets, without executing any training or feature full build.

Goals:

```text
1. Define target contracts (P0 / P1 / P2 + strict secondary zone targets)
2. Define dataset contract for P8A/P8B
3. Reference split, metrics, and baseline protocols (separate docs)
4. Define future simple model candidates (not trained in P8A)
5. Define feature contract and forbidden inputs for future P8B
6. Point to P8B training gate proposal
```

---

## 2. Target Contract

### 2.1 P0 Regression — Primary Baseline

```text
target:  labels.close_distance_to_primary_pin_em
type:    regression
role:    primary baseline regression target
filter:  labels.baseline_target_eligible == true
```

**Semantics:**

```text
positive  => close above primary pin
negative  => close below primary pin
0         => close at primary pin
normalized by remaining_expected_move_t at as_of
```

**Formula (unchanged from v1.1 draft builder):**

```python
close_distance_to_primary_pin_em = (
    official_close - primary_pin_t
) / remaining_expected_move_t
```

**Eligibility:** same as baseline track — `primary_pin_t` non-null, `remaining_expected_move_t > 0`, `official_close` non-null, `label_source_timestamp > as_of_timestamp`.

**P7.8.3 reference distribution (eligible rows):**

| Stat | Value |
|------|-------|
| count | 1390 |
| mean | 0.678 EM |
| std | 3.934 |
| p50 | 0.37 EM |

---

### 2.2 P1 Binary Preferred — First Classification Eval

```text
target:  labels.close_near_primary_pin_050
type:    binary classification
role:    preferred first binary baseline target
filter:  labels.baseline_target_eligible == true
classes: near (true) / not_near (false)
threshold: |close_distance_to_primary_pin_em| <= 0.50
```

**Rationale (P7.8 / P7.8.3 evidence):**

```text
Better class balance than 0.25 EM threshold
near ≈ 319, not_near ≈ 1071
both classes present globally and in 12/19 sessions
preferred for first binary eval per owner decision (P7.8.1)
```

---

### 2.3 P1 Binary Sensitivity

```text
target:  labels.close_near_primary_pin_025
type:    binary classification
role:    sensitivity track (not primary gate for P8B)
filter:  labels.baseline_target_eligible == true
classes: near (true) / not_near (false)
threshold: |close_distance_to_primary_pin_em| <= 0.25
```

**P7.8.3 reference:** near ≈ 152, not_near ≈ 1238; dual-class in 5/19 sessions.

Sensitivity track is **reported alongside** P1 @ 0.50 but does **not** replace it as the primary binary gate.

---

### 2.4 P2 Optional Directional — Multiclass

```text
target:  labels.close_above_below_primary_pin_050  (preferred P2)
         labels.close_above_below_primary_pin_025  (sensitivity P2)
type:    multiclass
classes: below | near | above
role:    optional directional evaluation
filter:  labels.baseline_target_eligible == true
```

**Class rules (0.50 EM example):**

```text
below  => d_em < -0.50
near   => |d_em| <= 0.50
above  => d_em > +0.50
```

**P7.8.3 reference @ 0.50 EM:** below 424, near 319, above 647.

P2 is **optional** in harness reporting. P8B may include P2 only after P0/P1 baselines are established and owner approves expanded scope.

---

### 2.5 Strict Secondary Targets — Zone Track (Unchanged)

```text
labels.close_location_vs_current_zone   — strict / secondary / Terminal-parity multiclass
labels.close_inside_current_zone        — strict / secondary binary
```

**Governance rule:**

```text
Baseline targets do not replace zone targets.
Zone labels remain unchanged.
Zone track inclusion rule unchanged (has_valid_zone at as_of).
A row may be baseline_included without zone_included.
```

**P7.8.3 zone reference:** `zone_included_total = 89` (~6.4% of anchors). Zone metrics are **reported separately** on zone-eligible rows only; they must not be used to dilute baseline primary eval.

---

## 3. Dataset Contract

### 3.1 Schema Versions

```text
label_schema_version (manifest top-level):     1.0.0 semantics preserved for zone track
baseline_label_schema_version (per-row stamp): 1.1.0-draft
feature_schema_version (future P8B):           1.0.0 (P7 feature layer)
deterministic_contract_version:                ml-p5-v1
```

### 3.2 Dataset Source

```text
source:                  P7.8.3 v1.1 draft rebuilt dataset
config:                  config/ml/pit_sample_baseline_v1_1_validation.yaml
artifact path (local):   artifacts/datasets/pit_sample_baseline_v1_1_validation/
validation report:       artifacts/reports/pit_sample_baseline_v1_1_validation/
anchor_type:             regular_5min
ingest:                  disabled (no new dates in P7.8.3)
build mode:              dataset-only (labels only; no feature join in P7.8.3)
```

### 3.3 Reference Counts (P7.8.3 PASS)

| Field | Reference |
|-------|-----------|
| row_count | 1391 |
| baseline_eligible_rows | 1390 |
| eligible_sessions | 19 |
| rebuild_dates | 19 |
| skipped_dates | 2026-06-10 (pilot fixture) |

### 3.4 Required Row Fields (Baseline Track)

Every training-ready row must expose:

```text
trade_date, session_id, as_of_timestamp, feature_cutoff_timestamp
labels.baseline_target_eligible
labels.baseline_target_exclusion_reasons
labels.baseline_label_schema_version
labels.close_distance_to_primary_pin_em
labels.close_near_primary_pin_025
labels.close_near_primary_pin_050
labels.close_above_below_primary_pin_025
labels.close_above_below_primary_pin_050
label_source_timestamp
sample_weight (baseline track weighting TBD in P8B harness code)
```

Zone fields remain present on all rows; zone-eligible subset additionally has non-null `labels.close_location_vs_current_zone`.

### 3.5 Schema Mixing Rule

```text
v1.0 and v1.1 rows must not be mixed without explicit schema handling.
Training-ready dataset must pass leakage validation before any P8B fit.
Artifacts are not committed to git.
```

**Harness guard (future P8B code):**

```python
if manifest["baseline_label_schema_version"] != "1.1.0-draft":
    raise SchemaError("Baseline harness requires v1.1 draft labels")
if not leakage_report["leakage_pass"]:
    raise LeakageError("Dataset failed leakage validation")
```

### 3.6 Future Joined Dataset (P8B Prerequisite — Not Built in P8A)

When P8B is approved, the joined dataset must:

```text
strict hash join on (trade_date, as_of_timestamp, replay_state_hash, deterministic_bundle_hash)
features with source_timestamp <= as_of_timestamp only
labels.* excluded from feature matrix
leakage module re-run on joined rows
manifest records both label and feature schema versions
```

Feature full build is **not authorized in P8A**.

---

## 4. Harness Architecture (Plan Only)

```text
┌─────────────────────────────────────────────────────────────┐
│  Dataset (v1.1 draft labels + future P7 features)           │
└──────────────────────────┬──────────────────────────────────┘
                           │
              session_grouped_split (see split protocol)
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
      train              validation           test
         │                 │                 │
         ▼                 ▼                 ▼
   model-free          model-free         model-free
   baselines            baselines          baselines
         │                 │                 │
         ▼                 ▼                 ▼
   (future P8B)      model selection    final eval only
   simple models      on val only        (no tuning)
```

**P8A deliverable:** protocol documents only. Harness **code** is a future phase after P8B owner approval.

---

## 5. Model-Free Baselines (Definitions — Not Run)

See [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md) §4 for full definitions.

**P0:**

```text
zero baseline: predict 0 EM
train median baseline: predict train-set median d_em
session prior baseline: per-session train median (train sessions only)
previous-anchor persistence: LEAKAGE-RISK — only if prior anchor label is knowable at prediction time without future official_close; default DO NOT USE until harness proves causality
```

**P1:**

```text
majority class baseline (train sessions)
constant not_near baseline
train prior probability baseline
```

**P2:**

```text
majority class baseline (train sessions)
class prior baseline
```

**Universal rule:**

```text
Any baseline requiring future official_close from same session before prediction time is disallowed.
```

---

## 6. Future Simple Model Candidates (Not Trained)

Candidates for **future P8B** only, subject to owner approval:

| Target | Candidate models |
|--------|------------------|
| P0 | linear regression, ridge regression |
| P1 | logistic regression |
| P2 | multinomial logistic regression |
| All | tree-based (e.g. sklearn `GradientBoosting*`) **only after** dependency and sample-size review |

**Constraints:**

```text
Use existing dependencies only unless future owner approval permits dependency changes.
No deep learning in first P8B wave.
No hyperparameter search until P8B approval and documented search budget.
No financial performance claims from harness eval.
No production signal publication.
```

Existing project dependencies (reference): `numpy`, `pandas`, `scikit-learn` (if already in requirements.txt at P8B time — verify before use).

---

## 7. Feature Contract for Future P8B

### 7.1 Allowed Features

```text
features with source_timestamp <= as_of_timestamp
features built under P7 feature layer (feature_catalog.md)
strict hash join keys: trade_date, as_of_timestamp, replay_state_hash, deterministic_bundle_hash
multiresolution features per multiresolution_feature_spec.md (same timestamp rule)
quality features (as-of observable only)
```

### 7.2 Forbidden Inputs

```text
official_close
future return / future high / low
post-as_of volume
final daily volume
label_source_timestamp as feature
any labels.*
normalized_close_move (outcome-derived)
zone labels as features for baseline primary track (zone may be reported as secondary eval only)
deterministic bundle fields that embed post-as_of state
```

See `feature_catalog.md` § Forbidden in feature dict.

---

## 8. Evaluation and Split References

| Topic | Document |
|-------|----------|
| Metrics | [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md) |
| Session-grouped split, embargo, calibration | [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md) |
| P8B entry gates | [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md) |

---

## 9. P8A Acceptance Gate

P8A **PASS** when:

```text
✓ modeling harness plan written (this document)
✓ target contracts documented
✓ dataset contract documented
✓ split protocol documented
✓ metric protocol documented
✓ model-free baselines defined
✓ future simple model candidates defined
✓ feature contract / forbidden inputs documented
✓ P8B training gate proposal documented
✓ no training performed
✓ no feature full build performed
✓ formal label_spec.md unchanged
✓ owner can decide whether to approve P8B
```

**P8A PASS does not authorize P8B training.**

---

## 10. Next Stages (After P8A)

| Stage | Scope | Authorization |
|-------|-------|---------------|
| ML-P8A.1 (optional) | Owner review of harness plan | Owner decision |
| ML-P8B | Harness code + feature build + model fitting | **Separate owner approval required** |
| Formal v1.1.0 spec merge | Update `label_spec.md` | **Separate owner approval** |

**Recommended next step after P8A PASS:**

```text
ML-P8A.1 — Owner Review for P8B Training Gate
```

or proceed directly to P8B approval discussion if owner accepts [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md).

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial P8A harness plan |

---

**End of harness plan.**
