# ML-P8C.2 Ingest Owner Approval Gate

**Date:** 2026-06-22  
**Stage:** ML-P8C.2  
**Status:** **AUTHORIZED** (raw lake ingest only — implementation not started)  
**Prerequisite:** ML-P8C.1.1 PASS + [`p8c2_ingest_owner_approval_record.md`](p8c2_ingest_owner_approval_record.md)

**Related:**

- [`p8c1_1_candidate_owner_review.md`](p8c1_1_candidate_owner_review.md)
- [`p8c1_candidate_date_selection_report.md`](p8c1_candidate_date_selection_report.md)
- [`p8c1_ingest_cost_estimate.md`](p8c1_ingest_cost_estimate.md)

---

## Stage Definition

```text
ML-P8C.2 — Actual Controlled Ingest / Raw Lake Expansion
```

对 P8C.1 冻结的 **21 个日期**执行 ThetaData ingest，写入 `artifacts/raw_lake_sample`。**仅** raw lake expansion。

```text
P8C.2 is approved only after P8C.1.1 owner approval.
P8C.2 allowed dates = frozen 21-date list.
P8C.2 may ingest raw lake partitions only.
P8C.2 must not build dataset/features.
P8C.2 must not train models.
```

**P8C.3 = dataset + feature build validation** (separate gate, not approved in P8C.1.1).

---

## Prerequisites

| # | Prerequisite | Status |
|---|--------------|--------|
| 1 | P8C.1 PASS — 21 dates selected | Done |
| 2 | P8C.1.1 owner review PASS | Done |
| 3 | [`p8c2_ingest_owner_approval_record.md`](p8c2_ingest_owner_approval_record.md) committed | Done |
| 4 | [`p8c1_ingest_cost_estimate.md`](p8c1_ingest_cost_estimate.md) reviewed | Done |
| 5 | Local ThetaData entitlement verified | **Required before execute** |
| 6 | P8B.4 / P8B.5 / P8B.6 remain blocked | Enforced |

---

## Approved Dates (Frozen — No Substitution)

P8C.2 **may only ingest** these 21 dates:

```text
2023-02-23, 2023-03-21, 2023-05-08, 2023-05-30, 2023-06-16,
2023-06-22, 2023-06-27, 2023-07-03, 2023-08-09, 2023-10-25,
2024-01-03, 2024-02-20, 2024-05-15, 2024-06-06, 2024-10-16,
2024-11-20, 2025-01-17, 2025-03-05, 2025-03-25, 2025-05-13,
2025-05-14
```

Existing **19** baseline sessions: retain; re-ingest only if documented corruption (separate owner note).

---

## Allowed in P8C.2

```text
ThetaData ingest for frozen 21 dates only
Raw lake partition writes (idempotent_skip_existing)
Partition manifest validation
Checksum verification
Per-date success/failure recording
Ingest run manifest (local, not committed)
Retry / resume on failed partitions (same dates)
early_close metadata for 2023-07-03
Temporal warning carry-forward in run report
```

---

## Forbidden in P8C.2

```text
Date changes or replacement dates
Performance-based or cherry-picked substitutions
Temporal-warning-driven date swaps
Dataset build
Feature build
Model fitting / .fit()
Hyperparameter search (P8B.4)
Production backtest (P8B.5)
Trading signal (P8B.6)
Committing artifacts, parquet, csv, jsonl, credentials
Modifying label_spec.md or requirements.txt
```

---

## P8C.2 PASS Gate Criteria

ML-P8C.2 PASS requires **all**:

```text
[ ] Raw ingest attempted for all frozen 21 dates
[ ] Per-date success/failure recorded
[ ] Manifest completeness verified per partition
[ ] Checksums verified where applicable
[ ] No replacement dates vs P8C.1 manifest
[ ] No dataset build
[ ] No feature build
[ ] No model fitting
[ ] Temporal warning documented in run report
[ ] Artifacts not committed to git
[ ] label_spec.md unchanged
[ ] requirements.txt unchanged
[ ] P8C.3 gate referenced for next stage
```

---

## Carried Warnings (From P8C.1.1)

| Warning | P8C.2 action |
|---------|------------|
| `min_new_sessions_2024` 6 vs 8 | Document in run report; **no** date replacement |
| Proxy high_vol/trend tags | Note for P8C.3 index-metric recheck; **no** date replacement |

---

## After P8C.2 PASS

| Outcome | Next step |
|---------|-----------|
| P8C.2 PASS | **ML-P8C.3** — Dataset + Feature Build Validation (owner gate) |
| Partial failure | Retry same dates; document failures |
| P8C.2 FAIL | Halt; owner review |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.2 gate per P8C.1 PASS |
| 1.1 | 2026-06-22 | P8C.1.1 approval; P8C.2 authorized (raw lake only) |

---

**End of gate document.**
