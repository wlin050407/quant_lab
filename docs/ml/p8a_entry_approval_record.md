# ML-P8A Entry Approval Record

**Phase:** ML-P7.8.4 — Owner Review for Baseline Dataset Gate and P8A Entry  
**Branch:** `research/zdte-fusion-model`  
**Prior phase:** ML-P7.8.3 — Dataset Rebuild and Coverage Validation (`1b45e72`)  
**Gate review:** [`baseline_dataset_gate_review.md`](baseline_dataset_gate_review.md)  
**Dataset validation:** [`baseline_dataset_rebuild_validation_report.md`](baseline_dataset_rebuild_validation_report.md)  
**Governance:** [`label_target_governance_decision.md`](label_target_governance_decision.md)

---

## Status

```text
Status: Approved for ML-P8A planning/harness only
```

This approval **does not** constitute ML-P8B training authorization, production deployment, or formal `label_spec.md` v1.1.0 merge.

---

## P7.8.3 Gate Evidence (Prerequisite PASS)

| Metric | Result |
|--------|--------|
| row_count | **1391** |
| baseline_eligible_rows | **1390 / 1391** (99.9%) |
| eligible_sessions | **19 / 19** |
| P1 0.25 near / not_near | **152 / 1238** |
| P1 0.50 near / not_near | **319 / 1071** |
| P2 0.50 below / near / above | **424 / 319 / 647** |
| zone_included_total | **89** |
| leakage | **PASS** (violation_count = 0) |
| session-grouped split | **PASS** (11 / 3 / 5 suggested) |
| screening consistency | **PASS** |
| feature full build | **NOT run** |
| training | **NOT run** |

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-20
Decision:  Approved for ML-P8A planning/harness only
Notes:     P7.8.3 dataset gate PASS. Baseline v1.1 draft labels validated.
           Zone labels remain strict secondary. No training in P8A.
           ML-P8B requires separate owner approval after P8A plan review.
```

---

## Approved Scope

The following are **approved** for ML-P8A:

```text
Approved:
- Proceed to ML-P8A Baseline Modeling Harness Plan.
- Design baseline modeling/evaluation harness.
- Define dataset contracts for v1.1 draft labels.
- Define session-grouped split protocol.
- Define metrics for P0 regression, P1 binary, P2 optional directional targets.
- Define no-leak calibration protocol.
- Define model-free baselines and simple model candidates.
- Define acceptance gates for future ML-P8B training.
```

---

## Not Approved (Explicit)

The following remain **not approved**:

```text
Not approved:
- ML-P8B training.
- Running model fitting.
- Publishing trading signals.
- Production use.
- Changing deterministic financial formulas.
- Replacing zone labels.
- Modifying official label_spec.md.
- Feature full build for training purposes.
- Ingest of new trade dates (unless separately authorized).
- Row-level random split for evaluation.
```

---

## ML-P8A — Baseline Modeling Harness Plan Direction

P8A is **planning only**. No code implementation or training in P8A unless a future phase explicitly authorizes harness code (still without model fitting).

### Targets

| Priority | Field | Role |
|----------|-------|------|
| P0 | `close_distance_to_primary_pin_em` | Primary regression baseline |
| P1 preferred | `close_near_primary_pin_050` | First binary eval (0.50 EM) |
| P1 sensitivity | `close_near_primary_pin_025` | Sensitivity track (0.25 EM) |
| P2 optional | `close_above_below_primary_pin_050` / `_025` | Optional directional |

**Eligibility filter:** `baseline_target_eligible == true` only.

### Splits

```text
session-grouped only
no row-level random split
train / val / test candidate = 11 / 3 / 5 sessions (19 eligible sessions)
split assignment must be documented and reproducible
```

### Metrics

| Target | Metrics |
|--------|---------|
| P0 regression | MAE, RMSE, median absolute error, sign accuracy |
| P1 binary | ROC-AUC (if valid), PR-AUC, balanced accuracy, F1, Brier, calibration/ECE |
| P2 optional | macro F1, balanced accuracy, confusion matrix |

### Baselines (model-free first)

```text
majority class
pin-distance naive baseline
previous-anchor persistence
simple linear / logistic candidate — only after explicit approval in P8B gate
```

### Leakage Controls

```text
features <= as_of_timestamp
labels use official_close only as future label information
threshold calibration from training sessions only (no val/test leakage)
label_source_timestamp > as_of_timestamp enforced
no feature columns in label-only validation path
```

---

## P8A Acceptance Gate

P8A **PASS** means:

```text
- modeling harness plan written
- target contracts documented
- split protocol documented
- metric protocol documented
- no training performed
- owner can decide whether to approve P8B
```

P8B still requires **separate owner approval** after P8A plan review. P8A PASS does not auto-unblock P8B.

---

## Phase Progression

| Phase | Scope | Status |
|-------|-------|--------|
| ML-P7.8 | Baseline coverage screening | **PASS** |
| ML-P7.8.1 | Implementation approval + plan | **Complete** |
| ML-P7.8.2 | Additive label builder | **PASS** |
| ML-P7.8.3 | Dataset rebuild + validation | **PASS** |
| **ML-P7.8.4** | Owner gate review + P8A entry (this document) | **Complete** |
| **ML-P8A** | Baseline Modeling Harness Plan | **Next — authorized (planning only)** |
| ML-P8B | Model training | **BLOCKED** |

---

## Rollback

If P8A planning reveals insufficient dataset coverage, leakage risk in proposed harness, or conflict with zone track governance:

1. Halt P8A progression; do not proceed to P8B.
2. v1.0 datasets and zone track remain valid; v1.1 draft does not enter training without schema guard.
3. This approval remains valid for **revised P8A plan** after fixes; does not auto-approve P8B.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial P8A entry approval post-P7.8.3 PASS |

---

**End of approval record.**
