# ML-P8C.1 Expansion Implementation Gate

**Date:** 2026-06-22  
**Stage:** ML-P8C.1 (future — **not started**)  
**Status:** Gate defined  
**Prerequisite:** ML-P8C.0 PASS + [`p8c_expansion_owner_approval_record.md`](p8c_expansion_owner_approval_record.md)  
**Parent plan:** [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)  
**Date rules:** [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)

---

## Stage Definition

```text
ML-P8C.1 — Expansion Candidate Selection and Ingest Plan
```

Apply pre-declared date selection rules to generate a **candidate date list**, verify data availability, estimate ingest/build cost and time, and produce a **proposed expansion manifest** for owner review before any P8C.2 ingest.

**P8C.0 does not implement P8C.1.**

---

## Prerequisites

| # | Prerequisite |
|---|--------------|
| 1 | P8C.0 PASS — expansion plan + date rules committed |
| 2 | [`p8c_expansion_owner_approval_record.md`](p8c_expansion_owner_approval_record.md) — planning approved |
| 3 | P8B.1 baseline 19-session list frozen |
| 4 | `selection_seed = 20260621` unchanged |
| 5 | P8B.4 / P8B.5 / P8B.6 remain blocked |

---

## Allowed in P8C.1

```text
Generate candidate date list from pre-declared rules (Stage 1: +21 → 40 total)
Query ThetaData / raw lake availability for candidates (read-only checks)
Estimate ingest wall time, API cost, storage footprint
Estimate dataset + feature build time per session
Produce proposed_expansion_manifest.json (local, not committed)
Document bucket assignment per selected date
Document spill / under-fill decisions
Unit tests for date-selection logic (deterministic, no performance inputs)
Dry-run scripts that emit candidate list only
```

**Proposed implementation (future):**

```text
config/ml/p8c_stage1_expansion.yaml
scripts/generate_p8c_candidate_dates.py
src/quant_lab/ml/harness/p8c_date_selection.py
tests/test_p8c_date_selection.py
docs/ml/p8c1_candidate_selection_report.md
```

---

## Forbidden in P8C.1

```text
Actual raw data ingest (P8C.2)
Raw lake write / partition creation
Dataset build (P8C.3)
Feature build (P8C.3)
Model fitting / .fit() (P8C.4)
Hyperparameter search (P8B.4)
Performance-based date cherry-picking
Using P8B.3.7 test metrics to add/remove dates
Using labels or official_close outcome to select dates
Production backtest (P8B.5)
Trading signal (P8B.6)
Committing artifacts, parquet, csv, jsonl
Modifying label_spec.md or requirements.txt
```

---

## P8C.1 Outputs (Required)

| Output | Description |
|--------|-------------|
| `candidate_pool_summary.json` | Pool size, exclusions, bucket counts (local) |
| `stage1_selected_dates.json` | 21 new dates + bucket tags + primary_bucket |
| `availability_report.md` | ThetaData / raw lake status per candidate |
| `build_cost_estimate.md` | Ingest + dataset + feature build time/cost |
| `p8c1_run_manifest.json` | Stage, seed, rule version, no ingest flag |

All outputs **local / gitignored** unless explicitly approved as docs-only summaries (no date-level parquet).

---

## P8C.1 PASS Gate Criteria

ML-P8C.1 PASS requires **all**:

```text
[ ] Candidate pool generated from rules in p8c_date_selection_rules.md
[ ] selection_seed = 20260621 applied; output reproducible
[ ] Exactly 21 new Stage 1 dates selected (40 total with baseline 19)
[ ] Each date has primary_bucket and audit tags documented
[ ] No overlap with existing 19 P8B.1 baseline sessions
[ ] No performance-based selection (manifest attestation)
[ ] No label/outcome-based selection
[ ] Temporal constraints met (2023/2024/2025 minima)
[ ] Regime quota targets met or spill documented
[ ] Availability check completed for all selected dates
[ ] Build cost / time estimated
[ ] Owner can approve P8C.2 actual ingest in separate record
[ ] No artifacts committed to git
[ ] label_spec.md unchanged
[ ] requirements.txt unchanged
[ ] pytest pass on date-selection tests
[ ] P8B.4 remains blocked
```

---

## After P8C.1 PASS (Not Automatic)

| Outcome | Next step |
|---------|-----------|
| P8C.1 PASS + owner P8C.2 approval | **ML-P8C.2** — Actual Controlled Ingest / Raw Lake Expansion |
| Availability gaps for ≥3 selected dates | Revise pool per spill rules; **do not** substitute high-performing dates |
| Cost estimate exceeds budget | Owner may reduce Stage 1 quota with **pre-declared** rule amendment (new commit, new seed version) |

---

## Downstream Stages (Reference)

| Stage | Name | Key constraint |
|-------|------|----------------|
| P8C.2 | Actual Controlled Ingest | Approved dates only |
| P8C.3 | Dataset + Feature Build Validation | P8B.1 leakage gates |
| P8C.4 | FeatureSet_A Locked Refit | Fixed hyperparameters; **no P8B.4** |
| P8C.5 | Expanded Result Review | P8B.4 not automatic |

---

## P8B.4 Reminder

```text
P8C.4 still uses fixed hyperparameters (same as P8B.3.7).
P8C.4 does not authorize P8B.4.
P8B.4 can only be reconsidered after P8C expanded validation PASS (P8C.5) and owner approval.
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.1 gate per P8C.0 plan |

---

**End of gate document.**
