# ML-P8A — Baseline Evaluation Protocol

**Phase:** ML-P8A — Baseline Modeling Harness Plan  
**Branch:** `research/zdte-fusion-model`  
**Parent plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**Split rules:** [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)

---

## Status

```text
Protocol definition only — no metrics computed in P8A
ML-P8B: BLOCKED until separate owner approval
```

---

## 1. Reporting Rules

```text
Metrics must be reported by split (train / validation / test) and aggregate where meaningful.
No metric can be used to tune on test split.
Validation is for model/threshold selection only.
Test is for final locked evaluation only.
All reports include baseline_label_schema_version and split manifest hash.
Zone track metrics reported separately from baseline primary track.
```

**Minimum report sections:**

```text
1. Dataset summary (eligible rows, sessions, schema version)
2. Split summary (dates per split, row counts)
3. P0 metrics (per split)
4. P1 @ 0.50 metrics (primary binary)
5. P1 @ 0.25 metrics (sensitivity)
6. P2 @ 0.50 / 0.25 metrics (optional)
7. Zone secondary metrics (zone-eligible rows only)
8. Model-free baseline comparison table
9. Leakage attestation
```

---

## 2. Eligibility Filter

All baseline primary metrics computed on:

```text
labels.baseline_target_eligible == true
```

Zone secondary metrics computed on:

```text
labels.close_location_vs_current_zone is non-null
(equivalently zone track included rows)
```

Report **raw eligible counts** alongside every metric.

---

## 3. P0 Regression Metrics

**Target:** `labels.close_distance_to_primary_pin_em`

| Metric | Definition | Notes |
|--------|------------|-------|
| MAE | mean(\|y − ŷ\|) | primary error metric |
| RMSE | sqrt(mean((y − ŷ)²)) | penalizes large errors |
| Median absolute error | median(\|y − ŷ\|) | robust to outliers |
| R² | optional | report with caution on small val/test |
| Sign accuracy | fraction sign(y) == sign(ŷ) | y=0 excluded or counted neutral |
| within_0.25_EM accuracy | fraction \|y − ŷ\| ≤ 0.25 | EM-normalized tolerance band |
| within_0.50_EM accuracy | fraction \|y − ŷ\| ≤ 0.50 | EM-normalized tolerance band |
| Outlier rate | fraction \|y − ŷ\| > 3.0 EM | flags heavy-tail misses |

**Reporting:** per split + pooled train+val (never test for tuning decisions).

**Reference P0 distribution (P7.8.3, eligible):** mean 0.678 EM, std 3.934, p50 0.37 EM.

---

## 4. P1 Binary Metrics

**Primary target:** `labels.close_near_primary_pin_050`  
**Sensitivity target:** `labels.close_near_primary_pin_025`

For each target, report on each split:

| Metric | Definition | Condition |
|--------|------------|-----------|
| Class distribution | count near / not_near, ratio | always |
| Majority baseline | predict train majority class | reference baseline |
| Balanced accuracy | (sens + spec) / 2 | always |
| F1 | F1 for positive class `near` | always |
| Precision / recall | per class | always |
| ROC-AUC | area under ROC | **only if both classes exist in eval split** |
| PR-AUC | area under precision-recall | **only if valid** (both classes, sufficient positives) |
| Brier score | mean((p − y)²) | requires probabilistic predictions |
| Calibration / ECE | expected calibration error | binned; report bin count |
| Confusion matrix | TN, FP, FN, TP | always |

**P7.8.3 global reference @ 0.50 EM:** near 319, not_near 1071, ratio ~23%.

**P7.8.3 global reference @ 0.25 EM:** near 152, not_near 1238, ratio ~11%.

**Session-level reporting (optional but recommended):** count sessions where both classes appear in split for P1 @ 0.50.

---

## 5. P2 Multiclass Optional Metrics

**Targets:** `labels.close_above_below_primary_pin_050`, `labels.close_above_below_primary_pin_025`

| Metric | Definition |
|--------|------------|
| Class distribution | count below / near / above per split |
| Majority class baseline | predict train majority class |
| Macro F1 | unweighted mean F1 across classes |
| Balanced accuracy | sklearn `balanced_accuracy_score` |
| Per-class precision / recall | one-vs-rest |
| Confusion matrix | 3×3 |

**P7.8.3 reference @ 0.50 EM:** below 424, near 319, above 647.

P2 metrics are **optional** in first P8B report. If reported, use same split discipline as P0/P1.

---

## 6. Zone Secondary Metrics (Strict Secondary Track)

**Targets:** `labels.close_location_vs_current_zone`, `labels.close_inside_current_zone`

Report **only on zone-eligible rows** (~89 total in P7.8.3 reference):

| Metric | Notes |
|--------|-------|
| Class distribution | below / inside / above |
| Macro F1 | zone multiclass |
| Balanced accuracy | zone multiclass |
| Confusion matrix | 3×3 |
| Binary F1 | for `close_inside_current_zone` |

Zone metrics **must not** be presented as primary success criterion for baseline harness. They validate Terminal-parity secondary track preservation.

---

## 7. Model-Free Baseline Definitions

Baselines are **mandatory** in first P8B eval report. Definitions only here — **not run in P8A**.

### 7.1 P0 Model-Free Baselines

| Baseline | Prediction | Fit data | Leakage status |
|----------|------------|----------|----------------|
| Zero | ŷ = 0 EM always | none | **Safe** |
| Train median | ŷ = median(y_train) | train eligible rows | **Safe** |
| Session prior | ŷ = median(y) per session from train sessions | train sessions only | **Safe** if train-only |
| Previous-anchor persistence | ŷ = d_em from prior anchor same session | prior anchor label at t−1 | **LEAKAGE-RISK** — use only if prior anchor label is causally available without future official_close; default **DO NOT USE** in P8B v1 |

### 7.2 P1 Model-Free Baselines

| Baseline | Prediction | Fit data |
|----------|------------|----------|
| Majority class | always predict majority train class | train sessions |
| Constant not_near | always predict `not_near` | none |
| Train prior probability | P(near) = train near rate | train sessions |

### 7.3 P2 Model-Free Baselines

| Baseline | Prediction | Fit data |
|----------|------------|----------|
| Majority class | always predict most frequent train class | train sessions |
| Class prior | sample from train class frequencies | train sessions |

### 7.4 Universal Baseline Rule

```text
Any baseline requiring future official_close from same session before prediction time is disallowed.
Any baseline using test or validation labels for prediction on train is disallowed.
Any baseline using full-session label aggregates before session close is disallowed.
```

---

## 8. Future Simple Model Candidates (Metrics Only — Not Fit)

When P8B is approved, simple models report the **same metric tables** as above plus:

```text
model name, hyperparameters (fixed defaults first), fit duration
feature count, missingness rate
calibration plot data (reliability diagram bins)
residual plot summary for P0 (not committed as artifacts to git)
```

**No hyperparameter search in first P8B wave** unless owner approves search budget in P8B gate.

---

## 9. Comparison and Success Criteria (P8B — Proposal)

P8A does **not** set numeric beat-the-baseline thresholds. Proposed P8B **minimum reporting bar**:

```text
P0: report all model-free baselines; any model must beat zero and train median on validation before test peek
P1 @ 0.50: beat majority baseline balanced accuracy on validation
P1: ROC-AUC reported if valid; not required if val split lacks dual class
No financial PnL claims in harness eval
```

Owner may tighten gates at P8B approval time.

---

## 10. Artifacts Policy

```text
Eval reports (JSON / markdown): local artifacts/reports/ — gitignore
Prediction parquet/csv: gitignore
Calibration plots: gitignore
Model pickles: gitignore
Run manifest (metadata only): may be referenced in docs without committing predictions
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial evaluation protocol |

---

**End of evaluation protocol.**
