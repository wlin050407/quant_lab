# ML-P8C.2 Ingest Owner Approval Gate

**Date:** 2026-06-22  
**Stage:** ML-P8C.2 (future — **not started**)  
**Status:** Gate defined — **owner approval required**  
**Prerequisite:** ML-P8C.1 PASS + [`p8c1_candidate_date_selection_report.md`](p8c1_candidate_date_selection_report.md)

---

## Stage Definition

```text
ML-P8C.2 — Actual Controlled Ingest / Raw Lake Expansion
```

对 P8C.1 选定的 **21 个日期**执行 ThetaData ingest，写入 `artifacts/raw_lake_sample`（或 config 指定 lake_root）。**仅** raw lake expansion — dataset/feature build 属于 P8C.3，除非 owner 明确批准合并。

**P8C.1 does not implement P8C.2.**

---

## Prerequisites

| # | Prerequisite |
|---|--------------|
| 1 | P8C.1 PASS — 21 dates selected, manifest generated |
| 2 | [`p8c1_ingest_cost_estimate.md`](p8c1_ingest_cost_estimate.md) reviewed |
| 3 | [`p8c_expansion_owner_approval_record.md`](p8c_expansion_owner_approval_record.md) — planning approved |
| 4 | **Separate P8C.2 owner approval** recorded (this gate) |
| 5 | Local ThetaData entitlement verified |
| 6 | P8B.4 / P8B.5 / P8B.6 remain blocked |

---

## Approved Dates (Frozen from P8C.1)

P8C.2 **may only ingest** these 21 dates (no substitution without new rules commit):

```text
2023-02-23, 2023-03-21, 2023-05-08, 2023-05-30, 2023-06-16,
2023-06-22, 2023-06-27, 2023-07-03, 2023-08-09, 2023-10-25,
2024-01-03, 2024-02-20, 2024-05-15, 2024-06-06, 2024-10-16,
2024-11-20, 2025-01-17, 2025-03-05, 2025-03-25, 2025-05-13,
2025-05-14
```

Plus retain existing **19** baseline sessions (no re-ingest unless corrupt).

---

## Allowed in P8C.2 (After Owner Approval)

```text
ThetaData ingest for selected dates only
Raw lake partition writes (idempotent_skip_existing)
Partition manifest validation
Ingest run manifest (local, not committed)
Retry / resume on failed partitions
early_close metadata for 2023-07-03
```

---

## Forbidden in P8C.2

```text
Date changes without owner approval + new rules commit
Performance-based replacement dates
Cherry-picking based on P8B.3.7 metrics
Dataset build (unless explicitly approved as P8C.2b)
Feature build (P8C.3)
Model fitting / .fit() (P8C.4)
Hyperparameter search (P8B.4)
Production backtest (P8B.5)
Trading signal (P8B.6)
Committing artifacts, parquet, csv, jsonl, credentials
Modifying label_spec.md or requirements.txt
```

---

## P8C.2 PASS Gate Criteria (Draft)

```text
[ ] Owner P8C.2 approval record committed
[ ] All 21 selected dates ingested OR failed with documented reason
[ ] Partition manifests complete per date
[ ] No date substitution vs P8C.1 manifest
[ ] No model fitting
[ ] Artifacts not committed to git
[ ] label_spec.md unchanged
[ ] requirements.txt unchanged
```

---

## Owner Approval Template (To Be Signed)

```text
Status: Approved / Not approved for P8C.2 actual ingest

Scope:
  - Ingest 21 dates listed above
  - Raw lake only (no dataset/feature build unless noted)
  - No date changes
  - No model fitting
  - P8B.4 remains blocked
```

---

## After P8C.2 PASS

| Outcome | Next step |
|---------|-----------|
| P8C.2 PASS | **ML-P8C.3** — Dataset + Feature Build Validation |
| Partial ingest failure | Retry failed dates; **do not** substitute dates |
| Cost overrun | Pause; owner review before continuing |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial P8C.2 gate per P8C.1 PASS |

---

**End of gate document.**
