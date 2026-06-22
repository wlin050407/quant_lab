# ML-P8C Expansion Owner Approval Record

**Date:** 2026-06-22  
**Stage:** ML-P8C.0  
**Owner:** Weitong Lin  
**Status:** Approved for P8C planning only  
**Prerequisite:** ML-P8B.3.8 PASS  

**Approved documents:**

- [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)
- [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)
- [`p8c1_expansion_implementation_gate.md`](p8c1_expansion_implementation_gate.md)

---

## Approval Statement

```text
Status: Approved for P8C planning only
```

This record authorizes **writing and committing P8C.0 planning documents** and **drafting P8C.1 implementation gate**. It does **not** authorize data movement, model fitting, or P8B.4.

---

## Approved Scope

| Item | Approved |
|------|----------|
| Controlled expansion plan (P8C.0) | **Yes** |
| Pre-declared date selection rules (`selection_seed=20260621`) | **Yes** |
| Staged sample targets (40 / 60 / 100 sessions) | **Yes** |
| Regime coverage goals (non-model diagnostics) | **Yes** |
| P8C.1 implementation gate drafting | **Yes** |
| P8C sub-stage roadmap (P8C.0–P8C.5) | **Yes** |
| FeatureSet_A as provisional validation target | **Yes** (unchanged from P8B.3.8) |
| FeatureSet_B sensitivity-only | **Yes** (unchanged) |

---

## Not Approved

| Item | Status |
|------|--------|
| Actual ThetaData ingest | **NOT approved** |
| Raw lake expansion | **NOT approved** |
| Dataset build | **NOT approved** |
| Feature build | **NOT approved** |
| Learned model fitting / `.fit()` | **NOT approved** |
| Hyperparameter search (P8B.4) | **NOT approved — BLOCKED** |
| Production backtest (P8B.5) | **NOT approved — BLOCKED** |
| Trading signal (P8B.6) | **NOT approved — BLOCKED** |
| Cherry-picking dates by P8B.3.7 performance | **NOT approved** |
| FeatureSet_C refit | **NOT approved** |
| FeatureSet_B as default | **NOT approved** |
| Modifying `label_spec.md` | **NOT approved** |
| Modifying `requirements.txt` | **NOT approved** |

---

## Feature Set Policy (Binding)

| Set | Decision |
|-----|----------|
| FeatureSet_A_core_stable | Provisional primary candidate for P8C validation |
| FeatureSet_B_core_plus_flow | Sensitivity-only |
| FeatureSet_C_diagnostic_full_pruned | Not approved for refit |

Manifest version: `p8b3_reduced_features_v0_proposal`

---

## Staged Expansion Approval

| Stage | Target | Planning approved | Ingest/build approved |
|-------|--------|-------------------|----------------------|
| P8C Stage 1 | 40 sessions (+21 new) | **Yes** | **No** — requires P8C.1 PASS + separate P8C.2 approval |
| P8C Stage 2 | 60 sessions (+20 new) | **Yes** (rules only) | **No** — after Stage 1 P8C.5 PASS |
| P8C Stage 3 | 100 sessions (+40 new) | **Conditional** — owner review after Stage 2 | **No** |

---

## Next Authorized Stage

```text
ML-P8C.1 — Expansion Candidate Selection and Ingest Plan
```

See [`p8c1_expansion_implementation_gate.md`](p8c1_expansion_implementation_gate.md).

P8C.1 may generate candidate date lists and cost estimates. P8C.1 **may not** ingest data.

---

## P8B.4 Status

```text
P8B.4 hyperparameter search: BLOCKED
P8B.5 production backtest: BLOCKED
P8B.6 trading signal: BLOCKED
```

P8B.4 reconsideration conditions unchanged — see [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md).

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.0 planning approval (ingest/build/fit not approved) |
