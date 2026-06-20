# ML-P8A — No-Leak Session-Grouped Split Protocol

**Phase:** ML-P8A — Baseline Modeling Harness Plan  
**Branch:** `research/zdte-fusion-model`  
**Parent plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**Dataset reference:** P7.8.3 — 19 sessions, 1390 baseline-eligible rows

---

## Status

```text
Protocol definition only — no split artifacts generated in P8A
ML-P8B: BLOCKED until separate owner approval
```

---

## 1. Principles

```text
session-grouped split only
no row-level random split
same trade_date cannot appear in more than one split
features <= as_of_timestamp at prediction time
labels use official_close only as future outcome
threshold calibration uses train sessions only
model selection uses validation sessions only
test sessions are untouched until final evaluation
```

Any violation of these principles is a **hard FAIL** for P8B harness acceptance.

---

## 2. Group Key

```text
primary group key: trade_date (equivalently session_id for 0DTE single-expiry sessions)
```

All rows sharing `trade_date` belong to the **same split**. No row from a session may appear in train and validation simultaneously.

**Forbidden:**

```text
sklearn train_test_split on rows without grouping
random shuffle split across anchors within mixed sessions
k-fold CV that places anchors from same session in different folds
```

**Allowed module reference (existing):** `quant_lab.ml.splits.session_grouped_split` with `shuffle=False`.

---

## 3. Recommended Split (19 Eligible Sessions)

Based on P7.8.3 session-grouped split readiness:

```text
train      = 11 sessions
validation = 3 sessions
test       = 5 sessions
total      = 19 sessions
```

**Approximate row counts (baseline-eligible, P7.8.3 reference):**

| Split | Sessions | ~Rows (eligible) |
|-------|----------|------------------|
| train | 11 | ~805 |
| validation | 3 | ~219 |
| test | 5 | ~366 |
| **total** | **19** | **1390** |

Exact session assignment must be **documented in split manifest** at P8B time. P8A does not fix final session lists — only the protocol.

---

## 4. Split Assignment Strategies

### 4.1 Preferred: Chronological Holdout

When enough sessions exist (≥ 19), **chronological holdout is preferred**:

```text
Sort sessions by trade_date ascending
Assign earliest 11 → train
Next 3 → validation
Latest 5 → test
```

**Rationale:** mimics forward deployment; reduces accidental correlation from adjacent market regimes within split.

**Requirement:** report exact `trade_date` lists in split manifest JSON.

### 4.2 Alternative: Stratified Session Split

If chronological split yields **zero dual-class sessions** in validation for P1 @ 0.50, a stratified session split is permitted **only if**:

```text
grouping remains by trade_date (never by row)
stratification target: session-level P1 0.50 class presence (near vs not_near only)
validation must retain ≥ 1 session with near class and ≥ 1 without (if globally possible)
test assignment is fixed before any model tuning
split seed and assignment recorded in manifest
```

Stratified session split is **second choice** to chronological. Owner must approve if used.

### 4.3 Locked Holdout

Optional reserved holdout dates (future expansion):

```text
locked_holdout_split — dates never used in train or validation
only evaluated once at end of program
document in manifest as locked_holdout_dates[]
```

Not required for initial 19-session P8B wave.

---

## 5. Embargo and Holdout Policy

### 5.1 Same-Session Leakage

```text
No same-session leakage.
All anchors from trade_date D must share one split label.
```

Within-session anchor ordering must **not** leak future anchor labels into earlier anchor predictions unless explicitly modeled as a **causal sequential task** with proven no-leak feature availability — **not in scope for first P8B wave**.

### 5.2 Cross-Session Embargo

For expanding walk-forward (future):

```text
embargo_days >= 0 (default 0 for 0DTE daily sessions)
no overlap of trade_date between train and test in walk-forward fold
```

Reference: `quant_lab.ml.splits.expanding_walk_forward_split`.

### 5.3 Test Set Touch Policy

```text
test sessions: evaluate once with frozen model + frozen calibration
no hyperparameter tuning on test
no threshold selection on test
no early stopping using test metrics
no repeated test peeking
```

---

## 6. Threshold Calibration Protocol

Applies to P1 near thresholds and any score → class calibration in P8B.

```text
Step 1: Fit / compute baselines on train sessions only
Step 2: If probability calibration needed (Platt / isotonic), fit calibrator on train only
        OR use train+val with nested CV — prefer train-only for first P8B wave
Step 3: Select operating threshold (if not fixed at 0.25/0.50 EM label definition) on validation only
Step 4: Report final metrics on test without further adjustment
```

**Fixed EM thresholds (0.25 / 0.50):** label definition is **pre-specified** in v1.1 draft builder — no train-set threshold tuning required for P1 **label construction**. Any **decision threshold on model scores** (distinct from label EM bands) must be chosen on validation only.

---

## 7. Sample Weights

Per `dataset_builder_spec.md`:

```text
default: sample_weight = 1 / count(included_samples_in_session)
computed within track (baseline vs zone) per session
excluded rows: weight 0
```

**P8B harness must:**

```text
apply sample_weight in train loss / aggregation where supported
report unweighted metrics alongside weighted metrics for transparency
never upweight using future label outcomes
```

---

## 8. Leakage Checks Before Split Use

Before any P8B fit, re-run on joined dataset:

| Check | Rule |
|-------|------|
| Feature timestamps | `source_timestamp <= as_of_timestamp` |
| Label source | `label_source_timestamp > as_of_timestamp` |
| No label columns in X | `labels.*` absent from feature matrix |
| No official_close in X | absent from features |
| Zone label zone match | label zone == as-of bundle zone (zone track only) |
| Split integrity | no `trade_date` in multiple splits |

Module: `quant_lab.ml.leakage` + dataset validation from P7.8.3 reporting.

---

## 9. Split Manifest Schema (Future P8B)

Split manifest (local artifact, gitignore) must record:

```json
{
  "split_protocol_version": "p8a-v1",
  "split_strategy": "chronological | stratified_session",
  "train_dates": ["YYYY-MM-DD", "..."],
  "validation_dates": ["..."],
  "test_dates": ["..."],
  "locked_holdout_dates": [],
  "baseline_label_schema_version": "1.1.0-draft",
  "row_counts": {"train": 0, "validation": 0, "test": 0},
  "eligible_row_counts": {"train": 0, "validation": 0, "test": 0},
  "p1_050_dual_class_sessions": {"train": 0, "validation": 0, "test": 0},
  "created_at": "ISO-8601",
  "git_commit": "..."
}
```

---

## 10. P8B Split Readiness Gates

Before P8B training, split must satisfy:

```text
eligible_sessions >= 10
baseline_eligible_rows >= 300
P1 0.50 both classes present in train AND validation (session-level or row-level as documented)
no trade_date appears in multiple splits
leakage_pass == true on joined dataset
split manifest committed to run metadata (not necessarily git)
```

See [`p8b_training_gate_proposal.md`](p8b_training_gate_proposal.md) for full P8B gates.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial split protocol |

---

**End of split protocol.**
