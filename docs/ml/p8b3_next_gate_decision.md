# ML-P8B.3 Next-Gate Decision

**Date:** 2026-06-21  
**Branch:** `research/zdte-fusion-model`  
**Stage:** ML-P8B.3.3  
**Review:** [`p8b3_3_learned_baseline_result_review.md`](p8b3_3_learned_baseline_result_review.md)

---

## Decision Summary

```text
Decision: Do NOT proceed to P8B.4 hyperparameter search.
P8B.4 remains BLOCKED.
P8B.5 production backtest remains BLOCKED.
P8B.6 trading signal generation remains BLOCKED.
Additional train-only learned fitting remains BLOCKED until preconditions below are met.
```

Negative OOS learned baseline (P8B.3.2) does not meet any criterion that would unlock search, backtest, or signals.

---

## Rationale

| Finding | Gate implication |
|---------|------------------|
| P0 learned test MAE > `zero_em` | No evidence that tuning would help before feature/data work |
| P1 learned test balanced_acc < 0.5, ROC-AUC < 0.5 | Overfit; search would likely amplify leakage risk |
| 19 sessions / 198 features | Sample too small for current feature dimensionality |
| P8B.3.2 fulfilled its purpose | Reference learned floor documented; not a progression signal |

Hyperparameter search on this dataset would **not** be scientifically justified without feature governance and/or material session expansion.

---

## Recommended Next Path

**Primary recommendation: Option B first, then Option A.**

Before spending effort expanding data, diagnose whether the 198-feature matrix is too noisy/sparse and define a smaller **governed feature set**.

### Option B — Feature governance / dimensionality reduction (PRIMARY)

```text
ML-P8B.3.4 — Feature Reduction and Stability Diagnostic Plan
```

**Allowed:**

- Correlation / missingness / stability diagnostics (read-only on existing artifacts)
- Pre-declared reduced feature groups (documentation + config)
- Session-level stability reports

**Not allowed without separate approval:**

- Model fitting (`.fit()`)
- Hyperparameter search
- Test-set tuning
- New ingest

### Option A — Controlled dataset expansion (SECONDARY, after B)

```text
ML-P8C — Controlled Dataset Expansion for Learned Models
```

**Goals:**

- Increase session count before any new learned fitting
- Improve regime coverage (pre-declared session selection rules)
- Keep same no-leak / session-grouped split rules
- No hyperparameter search in initial expansion tranche

**Constraints if authorized:**

- New sessions selected by **pre-declared rules** only
- **No cherry-picking** based on test performance
- Artifacts not committed to git

### Option C — Pause learned modeling (FALLBACK)

```text
Keep P8B.2 model-free baselines as current reference.
Return to data coverage / label quality / zone sparsity work.
```

Use if Option B diagnostics show no viable reduced feature set without structural label/feature changes.

---

## Gate Criteria for Any Future Learned Fitting

All must be satisfied before another P8B.3.x train-only fit stage:

| # | Condition |
|---|-----------|
| 1 | Feature set reduction **or** feature governance plan completed and approved |
| 2 | No-leak validators pass (`validate_session_split`, `detect_row_level_random_split`, `validate_forbidden_features`) |
| 3 | Session-grouped split remains mandatory (no row-level random split) |
| 4 | P1 class distribution reviewed **by split** before fitting |
| 5 | All candidate models pre-declared (no post-hoc model addition) |
| 6 | No hyperparameter search without **separate owner approval** (P8B.4 gate) |
| 7 | Test set not used for model selection or threshold tuning |
| 8 | Model-free baseline comparison mandatory on same split |
| 9 | Run manifest + evaluation report generated; artifacts not committed |

### If dataset expansion (Option A) is pursued

```text
new sessions must be selected by pre-declared rules
no cherry-picking based on test performance
expansion manifest documents session inclusion criteria
artifacts not committed
split protocol re-validated after expansion
```

---

## Explicitly Blocked Stages

| Stage | Status | Unlock requires |
|-------|--------|-----------------|
| **P8B.4** Hyperparameter search | **BLOCKED** | New owner approval + satisfied preconditions above + positive diagnostic from P8B.3.4 |
| **P8B.5** Production backtest | **BLOCKED** | P8B.4+ and separate execution approval |
| **P8B.6** Trading signal generation | **BLOCKED** | P8B.5+ and broker-phase gate |

---

## Current Reference Baselines

Until a future learned fit passes OOS gates, use **P8B.2 model-free** as primary reference:

| Track | Test reference |
|-------|----------------|
| P0 | `zero_em` (test MAE 2.01 EM) |
| P1 @ 0.50 | majority / constant / train_prior (test balanced_acc 0.50) |

P8B.3.2 learned metrics remain archived in local artifacts for comparison only.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-21 | Initial next-gate decision post P8B.3.3 review |

---

**End of decision record.**
