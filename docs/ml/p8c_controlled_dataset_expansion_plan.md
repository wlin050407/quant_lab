# ML-P8C Controlled Dataset Expansion Plan

**Date:** 2026-06-22  
**Stage:** ML-P8C.0  
**Status:** PASS (planning only — no ingest / build / fit)  
**Branch:** `research/zdte-fusion-model`  
**Prerequisite:** ML-P8B.3.8 PASS  

**Related documents:**

- [`p8c_dataset_expansion_entry_gate.md`](p8c_dataset_expansion_entry_gate.md)
- [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md)
- [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)
- [`p8c_expansion_owner_approval_record.md`](p8c_expansion_owner_approval_record.md)
- [`p8c1_expansion_implementation_gate.md`](p8c1_expansion_implementation_gate.md)

---

## 4.1 Objective

### Primary goal

**P8C 目标不是调参，而是扩大样本以验证 FeatureSet_A 是否在更多 sessions / regimes 上仍然 competitive。**

P8B.3.7 表明 FeatureSet_A（27 features）在固定超参下显著优于 P8B.3.2 全特征 learned baseline，并在 P1 @ 0.50 test 上优于 model-free majority。但证据仅来自：

- **19 sessions**（P8B.1 baseline validation cohort）
- **单一** configured chronological 11/3/5 split
- **2024-01 → 2025-05** 日历窗口

P8C 在 **pre-declared date selection rules** 下扩展 session 覆盖，复用 P8B.1 no-leak dataset/feature pipeline，并在扩展数据上对 **FeatureSet_A** 执行与 P8B.3.7 相同的 **fixed-hyperparameter train-only** 协议（最终在 P8C.4 执行，非本阶段）。

### What P8C is NOT

```text
P8C does not authorize P8B.4 hyperparameter search.
P8C does not authorize production backtest (P8B.5).
P8C does not authorize trading signal generation (P8B.6).
P8C does not authorize cherry-picking dates based on P8B.3.7 model performance.
P8C does not authorize FeatureSet_B as default or FeatureSet_C refit.
```

### Provisional candidate (unchanged from P8B.3.8)

| Set | Role |
|-----|------|
| **FeatureSet_A_core_stable** (27) | Primary validation target |
| **FeatureSet_B_core_plus_flow** (82) | Sensitivity-only (optional parallel eval in P8C.4) |
| **FeatureSet_C** (92) | Not approved |

Manifest version pinned: `p8b3_reduced_features_v0_proposal`

---

## Current Baseline Cohort (P8B.1 / P8B.3.7)

| Item | Value |
|------|-------|
| Sessions | **19** |
| Joined rows | 1391 |
| Baseline-eligible | 1390 |
| Feature columns | 198 |
| Split | 11 train / 3 validation / 5 test |

**Existing session dates (frozen — not re-selected):**

| Split | Dates |
|-------|-------|
| Train (11) | 2024-01-05, 2024-01-19, 2024-02-13, 2024-03-08, 2024-04-05, 2024-05-03, 2024-06-07, 2024-07-03, 2024-08-02, 2024-09-06, 2024-10-04 |
| Validation (3) | 2024-11-01, 2024-11-29, 2024-12-06 |
| Test (5) | 2025-01-03, 2025-02-07, 2025-03-07, 2025-04-04, 2025-05-02 |

New P8C sessions **add to** this cohort; existing 19 sessions are **not** dropped or re-weighted based on model performance.

---

## 4.2 Expansion Targets (Staged)

| Stage | Total sessions target | New sessions | Gate to proceed |
|-------|----------------------|--------------|-----------------|
| **Current (P8B.1)** | 19 | — | P8B.3.8 PASS |
| **P8C Stage 1** | **40** | +21 | P8C.0 PASS + P8C.1 PASS + owner P8C.2 approval |
| **P8C Stage 2** | **60** | +20 | P8C Stage 1 build PASS + P8C.5 review PASS |
| **P8C Stage 3** | **100** | +40 | Stage 1/2 gates PASS + owner approval + cost review |

**Default execution path:** Start with **Stage 1 only**. Stage 2 and Stage 3 require separate gate PASS and owner approval — not automatic.

If ThetaData ingest cost or feature build time exceeds budget after P8C.1 cost estimate, owner may defer Stage 2/3 without invalidating Stage 1.

---

## 4.3 Regime Coverage Goals

Each expansion stage must improve **regime diversity** using **pre-declared non-model diagnostics** only. Target coverage dimensions:

| Regime dimension | Selection basis (allowed) | Notes |
|------------------|---------------------------|-------|
| Normal low-vol days | Realized intraday range / RV bucket (low tercile) | From index path, not labels |
| High-vol days | Realized intraday range / RV bucket (high tercile) | |
| Trend-up days | Session spot return from open > +0.3% (pre-declared threshold) | Threshold fixed in date rules |
| Trend-down days | Session spot return from open < −0.3% | |
| Range-bound days | \|session return\| ≤ 0.15% and low range bucket | |
| Monthly OPEX / expiration-heavy | Third-Friday SPXW calendar rule + adjacent sessions | Fixed calendar rule |
| Early-close days | `early_close` session metadata | Quota-capped |
| Recent dates | Calendar year ≥ 2025 (Stage 1 quota) | Temporal diversity |
| Older dates | Calendar year ≤ 2023 (Stage 2+ emphasis) | Backfill history |
| Long-gamma / short-gamma | Pre-existing `short_gamma_regime` gate flags from label/dataset diagnostics | **Not** selected by model performance |
| Zone-valid / zone-invalid | Pre-declared `baseline_target_eligible` / pin-zone gate rates from P8B.1 quality screen | Data-quality stratification only |

**Forbidden:** selecting dates because P8B.3.7 test MAE / balanced_acc was good or bad on that session.

Detailed bucket quotas: [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)

---

## P8C Sub-Stage Roadmap

| Sub-stage | Name | Scope |
|-----------|------|-------|
| **P8C.0** | Controlled Dataset Expansion Plan | **This document** — rules, targets, governance |
| **P8C.1** | Candidate Date Selection and Ingest Plan | Generate candidate list, availability check, cost estimate — **no ingest** |
| **P8C.2** | Actual Controlled Ingest / Raw Lake Expansion | ThetaData ingest for approved dates only |
| **P8C.3** | Dataset + Feature Build Validation | P8B.1-style build + leakage validation on expanded cohort |
| **P8C.4** | FeatureSet_A Locked Refit on Expanded Dataset | Fixed hyperparameters; train-only; compare vs model-free |
| **P8C.5** | Expanded Result Review | Owner review; P8B.4 reconsideration **not** automatic |

### P8C.4 protocol (future — binding default)

```text
Same models and hyperparameters as P8B.3.7
FeatureSet_A only (required); FeatureSet_B optional sensitivity
Session-grouped split pre-declared before fit
Preprocessing fit on train only
test_not_used_for_tuning = true
P8C.4 does NOT authorize P8B.4
```

### P8B.4 reconsideration (unchanged)

P8B.4 can only be reconsidered after **P8C expanded validation PASS** (through P8C.5) **and** separate owner hyperparameter-search approval. See [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md).

---

## Split Design (Expanded Cohort — Pre-declared Principle)

Split ratios remain **session-grouped chronological** unless P8C.3 planning explicitly revises with owner approval **before** any fit:

| Cohort size | Proposed split (draft) |
|-------------|------------------------|
| 40 sessions | ~23 train / ~7 validation / ~10 test (ratios ≈ 11/3/5 scaled) |
| 60 sessions | ~35 train / ~10 validation / ~15 test |
| 100 sessions | ~58 train / ~16 validation / ~26 test |

Exact session lists assigned in P8C.3 **before** P8C.4 — never by test performance.

---

## Success Criteria (P8C Program — Draft)

P8C program PASS (after P8C.5) requires:

```text
Expanded dataset built under pre-declared dates only
P8B.1-style leakage + forbidden-feature validation PASS
FeatureSet_A fixed-hyperparameter eval on expanded OOS test
P0 competitive vs zero_em; P1 competitive vs majority (primary tracks)
No hyperparameter search; no test tuning
Owner review recorded
```

Failure on expanded OOS vs model-free → pause learned path; **do not** proceed to P8B.4.

---

## P8C.0 Compliance

| Item | Status |
|------|--------|
| Ingest | **No** |
| Dataset build | **No** |
| Feature build | **No** |
| Model fitting / `.fit()` | **No** |
| Artifacts committed | **No** |
| `label_spec.md` modified | **No** |
| `requirements.txt` modified | **No** |
| P8B.4 authorized | **No — BLOCKED** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.0 controlled expansion plan (PASS) |
