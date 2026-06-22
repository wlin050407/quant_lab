# ML-P8C Dataset Expansion Entry Gate

**Date:** 2026-06-22  
**Stage:** ML-P8C (future — **planning only, not started**)  
**Status:** Entry gate defined  
**Prerequisite:** ML-P8B.3.8 PASS + [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md)  
**Provisional candidate:** FeatureSet_A_core_stable (27 features)

---

## Stage Definition

```text
ML-P8C — Controlled Dataset Expansion for Reduced-Feature Validation
```

Expand the evaluation dataset using **pre-declared date selection rules**, reuse the existing no-leak dataset/feature pipeline, and validate **FeatureSet_A** on broader regimes under the **same fixed-hyperparameter train-only protocol** as P8B.3.7.

**P8B.3.8 does not implement P8C.** This document defines entry requirements only.

---

## Motivation

P8B.3.7 showed FeatureSet_A materially reduces OOS degradation vs P8B.3.2 full-feature models and beats model-free majority on P1 test, but evidence is limited to:

- **19 sessions** (11 train + 3 validation + 5 test)
- **One** pre-declared chronological split
- **2024-01 → 2025-05** calendar window

Before reconsidering P8B.4 hyperparameter search, FeatureSet_A must be stress-tested on expanded, pre-declared data.

---

## P8C Objectives

```text
Expand sessions using pre-declared date selection rules
Reuse no-leak dataset / feature pipeline (P8B.1 contract)
Validate FeatureSet_A on broader regimes
Keep FeatureSet_B sensitivity-only (optional parallel eval, not default)
No hyperparameter search
No production backtest
No trading signal generation
```

---

## Allowed in P8C

```text
Pre-declared date expansion plan (committed before ingest)
Controlled ingest / dataset build / feature build for new sessions only
Reuse FeatureSet_A column list from p8b3_reduced_features_v0_proposal manifest
Session-grouped split design (pre-declared before any fit)
Train-only fixed-hyperparameter evaluation (same specs as P8B.3.7)
Comparison vs model-free baselines on expanded OOS splits
Leakage and forbidden-feature validation gates
Local evaluation reports and run manifests (not committed)
Unit tests for expansion / split / no-leak gates
```

---

## Forbidden in P8C

```text
Cherry-picking dates based on P8B.3.7 or prior model performance
Adding sessions because test metrics were weak/strong on specific dates
Test-set tuning or test-set model selection
P8B.4 hyperparameter search (alpha, class_weight, threshold grids)
FeatureSet_C fitting without separate owner approval
Target-based feature selection or re-pruning on validation/test
Production backtest (P8B.5)
Trading signal generation (P8B.6)
Modifying label_spec.md or requirements.txt without separate approval
Committing artifacts, parquet, csv, jsonl, or raw market data
Promoting FeatureSet_B to default based on expanded eval without owner review
```

---

## Feature Set Policy (Inherited from P8B.3.8)

| Set | P8C role |
|-----|----------|
| **FeatureSet_A_core_stable** | **Required** primary validation target |
| **FeatureSet_B_core_plus_flow** | **Optional** sensitivity-only parallel eval |
| **FeatureSet_C_diagnostic_full_pruned** | **Not approved** unless separate owner decision |

Column list must be loaded from the approved reduced feature manifest — **no hand-edited feature lists** unless manifest version is explicitly updated under P8B.3.4 governance rules.

---

## Protocol Inheritance (From P8B.3.7)

Until P8C planning explicitly revises split ratios, the following remain binding defaults:

| Item | Default |
|------|---------|
| Preprocessing | `SimpleImputer(median)` + `StandardScaler`, train-only fit |
| P0 models | LinearRegression, Ridge(α=1.0) |
| P1 model | LogisticRegression(C=1.0, max_iter=1000, class_weight=None, threshold=0.5) |
| Split type | Session-grouped chronological (ratios pre-declared in P8C plan) |
| Test split use | Monitoring only — no tuning |
| Baseline comparison | P8B.2-style model-free baselines on same expanded splits |

---

## P8C Entry Gate Checklist

P8C implementation may begin only after **all** items are satisfied:

```text
[ ] P8C planning document written (date list, split design, sample targets)
[ ] Date selection rules pre-declared and committed BEFORE any new ingest
[ ] Expanded sample size target defined (minimum session count)
[ ] Regime coverage target defined (e.g. volatility / calendar diversity criteria)
[ ] No-leak gates preserved (session split, forbidden features, no target in X)
[ ] FeatureSet_A manifest version pinned
[ ] Owner approval recorded before ingest / build / fit
[ ] P8B.4 remains blocked during P8C planning and execution
```

---

## Proposed Planning Deliverables (Future)

Not part of P8B.3.8 — listed for traceability:

```text
docs/ml/p8c_dataset_expansion_plan.md          — date rules, session targets, split design
config/ml/p8c_dataset_expansion.yaml           — paths, date ranges, split config
docs/ml/p8c_owner_approval_record.md           — owner sign-off before ingest
```

---

## PASS Criteria (Future — P8C Completion)

P8C PASS will require (draft — to be finalized in P8C plan):

```text
Expanded dataset built under pre-declared dates
Feature build + leakage validation PASS
FeatureSet_A fixed-hyperparameter train-only eval PASS on expanded split
Primary tracks compared vs model-free baselines on OOS test
FeatureSet_B sensitivity eval optional
No hyperparameter search
No test tuning
Artifacts not committed
Owner review of expanded validation results
```

Failure on expanded OOS vs model-free → **do not** proceed to P8B.4; revisit feature governance or pause learned path.

---

## Relationship to P8B.4

```text
P8B.4 hyperparameter search    BLOCKED until P8C PASS + separate owner approval
P8B.5 production backtest      BLOCKED
P8B.6 trading signal           BLOCKED
```

See [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md) for full P8B.4 reconsideration conditions.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C entry gate per P8B.3.8 owner decision |

---

**End of entry gate document.**
