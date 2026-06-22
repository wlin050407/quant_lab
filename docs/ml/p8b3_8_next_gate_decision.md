# ML-P8B.3.8 Next Gate Decision

**Date:** 2026-06-22  
**Stage:** ML-P8B.3.8  
**Status:** Owner decision recorded  
**Reviewer:** Weitong Lin (owner)  
**Prerequisite:** ML-P8B.3.7 PASS + [`p8b3_8_reduced_feature_refit_result_review.md`](p8b3_8_reduced_feature_refit_result_review.md)

---

## Gate Decision

```text
Decision: Do not proceed to P8B.4.
P8B.4 remains BLOCKED.
P8B.5 remains BLOCKED.
P8B.6 remains BLOCKED.
```

P8B.3.7 PASS and this review **do not** constitute approval for hyperparameter search, production backtest, or trading signal generation.

---

## Owner Decision — Feature Sets

| Set | Decision |
|-----|----------|
| **FeatureSet_A_core_stable** (27 features) | **Accepted** as the **provisional reduced-feature learned baseline candidate** for continued research |
| **FeatureSet_B_core_plus_flow** (82 features) | **Remains sensitivity-only** — **not promoted** to default |
| **FeatureSet_C_diagnostic_full_pruned** (92 features) | **Remains not approved** for refit |

### Rationale (FeatureSet_A provisional acceptance)

- Material test improvement vs P8B.3.2 full-feature learned baselines (P0 MAE −1.61 vs full Ridge; P1 balanced_acc +0.281 vs full Logistic).
- P1 @ 0.50 test balanced accuracy **beats** P8B.2 majority baseline (+0.084).
- P0 Ridge test MAE **approximately matches** `zero_em` (+0.035) — insufficient to claim learned P0 superiority, but no longer catastrophically worse than model-free.
- Provisional only: **19 sessions**, one **11/3/5** split — not sufficient for P8B.4 or production path.

### Rationale (FeatureSet_B not promoted)

- P0 Ridge test MAE 3.37 > A (2.04) and `zero_em` (2.01).
- P1 @ 0.50 test balanced_acc 0.410 < A (0.584) and majority (0.500).
- Adding flow/microstructure/greeks groups did not improve primary-track OOS under fixed protocol.

---

## Recommended Next Path

```text
Primary next stage: ML-P8C — Controlled Dataset Expansion for Reduced-Feature Validation
```

**Entry gate document:** [`p8c_dataset_expansion_entry_gate.md`](p8c_dataset_expansion_entry_gate.md)

### Reason

FeatureSet_A improved materially relative to full-feature learned baselines and partially vs model-free baselines on P1, but current evidence is still based on **only 19 sessions** and **one chronological split**. Before P8B.4, the FeatureSet_A protocol should be validated on a **larger pre-declared dataset** under unchanged no-leak rules.

---

## Explicitly Blocked (Until Separate Owner Approval)

| Stage | Scope | Status |
|-------|-------|--------|
| **P8B.4** | Hyperparameter search (alpha, class_weight, threshold tuning) | **BLOCKED** |
| **P8B.5** | Production backtest | **BLOCKED** |
| **P8B.6** | Trading signal generation | **BLOCKED** |

---

## Future P8B.4 Reconsideration Conditions

P8B.4 can only be reconsidered **after all** of the following:

1. **P8C expanded dataset validation PASS** — FeatureSet_A evaluated on pre-declared expanded sessions with no-leak gates intact.
2. **FeatureSet_A remains competitive vs model-free baselines** on expanded OOS evaluation (primary tracks: P0 vs `zero_em`, P1 @ 0.50 vs majority).
3. **No-leak validators PASS** — session-grouped split, forbidden features, no target in X, no test tuning.
4. **Owner explicitly approves hyperparameter search** in a separate decision record (not inferred from P8B.3.7 or P8B.3.8).
5. **Test tuning remains prohibited** — even if P8B.4 is approved, validation-only search scope must be pre-declared; test split stays monitoring-only.

---

## What P8B.3.8 Authorizes

```text
Planning and owner approval workflow for ML-P8C
Continued use of FeatureSet_A as provisional research candidate (no production)
Documentation updates to staged execution plan and governance
```

## What P8B.3.8 Does NOT Authorize

```text
P8B.4 hyperparameter search
P8B.5 production backtest
P8B.6 trading signal generation
FeatureSet_B or FeatureSet_C as default
Cherry-picked date expansion based on P8B.3.7 test metrics
Retraining / refitting in the P8B.3.8 stage itself
```

---

## Compliance (This Stage)

| Item | Status |
|------|--------|
| Model training | **No** |
| `.fit()` called | **No** |
| Artifacts committed | **No** |
| `label_spec.md` modified | **No** |
| `requirements.txt` modified | **No** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial next-gate decision; P8B.4–P8B.6 blocked; P8C authorized for planning |
