# ML-P8B Training Gate Proposal

**Phase:** ML-P8A — Baseline Modeling Harness Plan (gate proposal for future P8B)  
**Branch:** `research/zdte-fusion-model`  
**Harness plan:** [`p8a_baseline_modeling_harness_plan.md`](p8a_baseline_modeling_harness_plan.md)  
**Split protocol:** [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md)  
**Eval protocol:** [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md)

---

## Status

```text
UPDATED post-P8A.1 — Staged P8B preparation approved (P8B.0–P8B.2 only)
P8B.3 learned model fitting: NOT authorized
P8A PASS does not authorize full P8B training
See: p8b_execution_approval_record.md, p8b_staged_execution_plan.md
```

---

## 1. Purpose

This document defines the **entry conditions** for a future ML-P8B phase that would implement the harness in code, build joined feature datasets, and run model fitting. Nothing in this proposal grants permission to start P8B.

---

## 2. Explicit Non-Authorization

```text
P8A PASS does not authorize P8B.3 learned model fitting.
P8A.1 approves staged preparation only: P8B.0, P8B.1, P8B.2.
P8B.3+ requires separate owner approval (p8b_model_fitting_approval_record.md).
No sklearn/xgboost/lightgbm/torch model fitting until P8B.3 approved.
```

---

## 3. P8B Entry Conditions (All Required)

### 3.1 Governance

| Gate | Requirement |
|------|-------------|
| Owner approval | Written sign-off for ML-P8B training scope |
| P8A complete | Harness plan + protocols PASS |
| Formal spec | `label_spec.md` may remain v1.0.0; training uses v1.1 draft with schema guard |
| Zone governance | Zone labels remain strict secondary; not replaced |

### 3.2 Dataset

| Gate | Requirement |
|------|-------------|
| v1.1 validation | P7.8.3 dataset rebuild PASS reproduced or manifest hash pinned |
| baseline_eligible_rows | ≥ 300 |
| eligible_sessions | ≥ 10 |
| P1 0.50 dual class | both classes present in **train and validation** splits |
| leakage | `leakage_pass == true` on label dataset and joined dataset |
| schema guard | no mixing v1.0 and v1.1 rows without explicit handling |

### 3.3 Features (P8B Build — Not P8A)

| Gate | Requirement |
|------|-------------|
| Feature dataset | Built under P7 feature layer for same 19 sessions (or approved superset) |
| Feature leakage | All features `source_timestamp <= as_of_timestamp` |
| Strict hash join | PASS on `(trade_date, as_of_timestamp, replay_state_hash, deterministic_bundle_hash)` |
| Forbidden inputs | No `labels.*`, `official_close`, future path, final volume in X |
| Feature manifest | Records `feature_schema_version`, build commit, date list |

### 3.4 Split

| Gate | Requirement |
|------|-------------|
| Protocol | [`p8a_no_leak_split_protocol.md`](p8a_no_leak_split_protocol.md) implemented |
| Session grouping | no `trade_date` in multiple splits |
| Split manifest | train/val/test dates documented and reproducible |
| Test policy | test untouched until final eval |

### 3.5 Evaluation

| Gate | Requirement |
|------|-------------|
| Metrics | [`p8a_evaluation_protocol.md`](p8a_evaluation_protocol.md) implemented |
| Baselines | all safe model-free baselines reported before any fitted model |
| No test tuning | enforced in harness code or review checklist |

### 3.6 Operations

| Gate | Requirement |
|------|-------------|
| Model cards | planned template for each fitted model |
| Run manifests | git commit, config hash, split hash, dataset manifest hash |
| Artifacts | **not committed** to git (parquet/csv/jsonl/pickles gitignore) |
| No production | no trading signals, no production backtest |
| No formula changes | Pin/GEX/VEX/EM/Valid Exit / zone thresholds frozen |

---

## 4. P8B Approved Scope (Staged — P8A.1)

Per [`p8b_execution_approval_record.md`](p8b_execution_approval_record.md):

### Approved now (P8B.0–P8B.2)

```text
P8B.0: Harness code (metrics, split validators, forbidden-input checks, manifest)
P8B.1: Feature dataset build + strict hash join + leakage validation
P8B.2: Model-free baseline evaluation (zero, train median, majority, train prior)
```

### Not approved (P8B.3+)

```text
P8B.3: Simple model fitting (linear, logistic, multinomial logistic)
P8B.4: Hyperparameter search
P8B.5: Production backtest
P8B.6: Trading signals
```

Full staged gates: [`p8b_staged_execution_plan.md`](p8b_staged_execution_plan.md).

---

## 4.1 Original Full-P8B Scope (Proposal — P8B.3+ Only)

If owner approves P8B.3 after P8B.0–P8B.2 PASS, proposed **additional** scope:

```text
Implement harness code (split, baselines, metrics, run manifest)
Build feature dataset for approved date list (same 19 dates initially)
Strict hash join labels + features
Fit model-free baselines and report metrics
Fit simple models: linear/ridge (P0), logistic (P1), multinomial logistic (P2 optional)
Fixed default hyperparameters only (no search in v1)
Session-grouped eval on train/val/test
Local artifacts under artifacts/ — gitignore
```

---

## 5. P8B Forbidden Scope (Always)

```text
ML-P8B does NOT authorize (unless future separate approval):
- Production deployment or live trading signals
- Financial performance / PnL backtest claims as primary gate
- Deep learning models
- Hyperparameter search / AutoML
- Row-level random split
- Modifying docs/ml/label_spec.md without owner approval
- Modifying deterministic financial formulas
- Replacing or removing zone labels
- Committing artifacts, raw data, credentials
- Ingest of new dates without separate authorization
- xgboost/lightgbm/torch unless dependency approval granted
```

---

## 6. P8B PASS Criteria (Proposal)

P8B phase **PASS** when:

```text
✓ All §3 entry conditions satisfied at start
✓ Feature + label joined dataset built and leakage PASS
✓ Split manifest created per protocol
✓ Model-free baselines computed on train/val/test
✓ Simple model candidates fit with fixed defaults (if in scope)
✓ Evaluation report per p8a_evaluation_protocol.md
✓ No leakage violations in harness run
✓ No test-set tuning detected
✓ Model cards + run manifests produced (local)
✓ No artifacts committed to git
✓ Owner review of P8B results completed
```

P8B PASS does **not** authorize production use or automatic progression to deep learning phases.

---

## 7. Dependency Policy

```text
Use existing dependencies only unless owner approves additions.
First P8B wave: numpy, pandas, scikit-learn (verify requirements.txt at approval time).
Tree-based models: require sample-size review + dependency approval.
No new ML framework without explicit owner sign-off.
```

---

## 8. Owner Approval Records

| Document | Scope | Status |
|----------|-------|--------|
| [`p8b_execution_approval_record.md`](p8b_execution_approval_record.md) | P8B.0–P8B.2 staged preparation | **Approved (P8A.1)** |
| `p8b_model_fitting_approval_record.md` | P8B.3+ learned fitting | **Not created — BLOCKED** |

Legacy template (superseded for P8B.0–P8B.2 by execution approval record):

When owner is ready to authorize **P8B.3 learned fitting**, record in `p8b_model_fitting_approval_record.md`:

```text
Owner:     [name]
Date:      [ISO date]
Decision:  Approved for ML-P8B training (limited scope)
Scope:     [date list, model list, feature build authorized]
Excluded:  [production, DL, hyperparam search, ...]
Dataset manifest hash: [hash]
Split manifest hash: [hash]
Git commit: [commit at approval time]
```

Until P8B.3 approval record exists, **learned model fitting remains BLOCKED** (P8B.0–P8B.2 may proceed).

---

## 9. Phase Progression

| Phase | Status |
|-------|--------|
| ML-P7.8.3 | Dataset rebuild PASS |
| ML-P7.8.4 | Owner gate + P8A entry PASS |
| **ML-P8A** | Harness plan | **PASS** |
| **ML-P8A.1** | Staged P8B execution approval | **PASS** |
| **ML-P8B.0** | Harness implementation | **Authorized** |
| **ML-P8B.1** | Feature build + join | **Authorized after P8B.0** |
| **ML-P8B.2** | Model-free baselines | **Authorized after P8B.1** |
| ML-P8B.3 | Simple model fitting | **BLOCKED** |
| ML-P8B.4+ | Search / production / signals | **BLOCKED** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial P8B gate proposal |
| 1.1 | 2026-06-20 | Updated post-P8A.1 staged approval (P8B.0–P8B.2) |

---

**End of P8B training gate proposal.**
