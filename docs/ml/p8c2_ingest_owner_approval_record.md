# ML-P8C.2 Ingest Owner Approval Record

**Date:** 2026-06-22  
**Stage:** ML-P8C.2 authorization (implementation not started)  
**Owner:** Weitong Lin  
**Prerequisite:** ML-P8C.1.1 PASS + [`p8c1_1_candidate_owner_review.md`](p8c1_1_candidate_owner_review.md)

---

## Approval Statement

```text
Status: Approved for ML-P8C.2 actual controlled ingest only
```

This record authorizes **raw lake ingest** for the frozen P8C.1 Stage 1 date list. It does **not** authorize dataset build, feature build, model fitting, or P8B.4.

---

## Approved Scope

| Item | Approved |
|------|----------|
| Ingest only the frozen **21** selected Stage 1 dates | **Yes** |
| Write raw lake partitions to `artifacts/raw_lake_sample` | **Yes** |
| Write per-partition manifests | **Yes** |
| Validate manifest completeness and checksums | **Yes** |
| Record per-date success/failure without replacing dates | **Yes** |
| Retry failed partitions (same dates) | **Yes** |
| `early_close` metadata for 2023-07-03 | **Yes** |
| Idempotent skip for already-complete partitions | **Yes** |

### P8C.2 scope boundary (conservative)

```text
P8C.2 = raw lake ingest only.
P8C.3 = dataset + feature build validation.
```

Dataset build and feature build are **explicitly not** part of this approval.

---

## Frozen Ingest Dates (21)

```text
2023-02-23
2023-03-21
2023-05-08
2023-05-30
2023-06-16
2023-06-22
2023-06-27
2023-07-03
2023-08-09
2023-10-25
2024-01-03
2024-02-20
2024-05-15
2024-06-06
2024-10-16
2024-11-20
2025-01-17
2025-03-05
2025-03-25
2025-05-13
2025-05-14
```

**No substitution.** Failures are retried or documented; dates are not replaced based on performance, temporal warnings, or post-ingest metrics.

Existing **19** baseline sessions: retain; re-ingest only if documented corruption (separate owner note required).

---

## Not Approved

| Item | Status |
|------|--------|
| Changing selected dates | **NOT approved** |
| Replacement dates | **NOT approved** |
| Performance-based selection | **NOT approved** |
| Cherry-picking for temporal warning | **NOT approved** |
| Dataset build | **NOT approved** (P8C.3) |
| Feature build | **NOT approved** (P8C.3) |
| Learned model fitting / `.fit()` | **NOT approved** (P8C.4) |
| P8B.4 hyperparameter search | **NOT approved — BLOCKED** |
| P8B.5 production backtest | **NOT approved — BLOCKED** |
| P8B.6 trading signal | **NOT approved — BLOCKED** |
| Modifying `label_spec.md` | **NOT approved** |
| Modifying `requirements.txt` | **NOT approved** |
| Committing artifacts / credentials | **NOT approved** |

---

## Carried Warnings (Binding for P8C.2 / P8C.3)

1. **Temporal:** `min_new_sessions_2024` got 6 vs target 8 — accepted without date replacement; report in P8C.2/P8C.3 manifests.
2. **Proxy buckets:** high_vol/trend tags from deterministic proxy — recheck with realized index metrics after ingest (P8C.3); **not** grounds for date swap in P8C.2.

---

## Prerequisites Before P8C.2 Execute

```text
[ ] Local ThetaData entitlement verified
[ ] Disk space ≥ 20 GB headroom recommended
[ ] This approval record committed
[ ] Frozen date list matches P8C.1 manifest
```

---

## After P8C.2 (Not Automatic)

| Outcome | Next step |
|---------|-----------|
| P8C.2 PASS | Owner gate for **ML-P8C.3** — dataset + feature build validation |
| Partial failure | Retry failed dates; document; **no** date substitution |
| P8C.2 FAIL | Halt; owner review before retry |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Approve P8C.2 raw lake ingest only; freeze 21 dates |
