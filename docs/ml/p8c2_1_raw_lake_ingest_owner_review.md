# ML-P8C.2.1 Raw Lake Ingest Owner Review

**Date:** 2026-06-23  
**Stage:** ML-P8C.2.1  
**Status:** PASS (owner review only — no dataset / feature build / fit)  
**Owner:** Weitong Lin  
**Branch:** `research/zdte-fusion-model`  
**Prerequisite:** ML-P8C.2 PASS (`a9c48fa`)

**Sources:**

- [`p8c2_raw_lake_ingest_report.md`](p8c2_raw_lake_ingest_report.md)
- [`p8c2_ingest_owner_approval_record.md`](p8c2_ingest_owner_approval_record.md)
- [`p8c1_1_candidate_owner_review.md`](p8c1_1_candidate_owner_review.md)
- `config/ml/p8c2_raw_lake_ingest.yaml`
- Local manifest (gitignored): `artifacts/reports/p8c_raw_lake_ingest/p8c2_run_manifest.json`

**Approval record (P8C.3):** [`p8c3_dataset_feature_build_owner_approval_record.md`](p8c3_dataset_feature_build_owner_approval_record.md)

---

## 4.1 P8C.2 Final Status

| Field | Value |
|-------|-------|
| **P8C.2 status** | **PASS** |
| **Frozen dates** | 21 |
| **Successful** | **21 / 21** |
| **Failed** | **0** |
| **Pending** | **0** |
| **Incomplete** | **0** |
| **replacement_dates_used** | **false** |
| **actual_ingest_performed** | true |
| **dataset_build_performed** | false |
| **feature_build_performed** | false |
| **model_fitting_performed** | false |
| **p8b4_authorized** | false |
| **Final commit** | `a9c48fa` — `docs(ml): complete p8c raw lake ingest status` |
| **Lake root** | `artifacts/raw_lake_sample` |
| **Lake partition scan** | 21 / 21 complete (post-ingest verification) |

---

## 4.2 Frozen Dates Reviewed

All **21 successful ingest dates** match the P8C.1.1 frozen list exactly.

```text
All 21 successful dates are the frozen P8C.1.1 dates.
No replacement dates were used.
No dates were added.
No dates were removed.
```

| # | `trade_date` | ingest status | notes |
|---|--------------|---------------|-------|
| 1 | 2023-02-23 | success | |
| 2 | 2023-03-21 | success | |
| 3 | 2023-05-08 | success | |
| 4 | 2023-05-30 | success | |
| 5 | 2023-06-16 | success | |
| 6 | 2023-06-22 | success | |
| 7 | 2023-06-27 | success | |
| 8 | 2023-07-03 | success | early_close |
| 9 | 2023-08-09 | success | |
| 10 | 2023-10-25 | success | |
| 11 | 2024-01-03 | success | |
| 12 | 2024-02-20 | success | |
| 13 | 2024-05-15 | success | |
| 14 | 2024-06-06 | success | |
| 15 | 2024-10-16 | success | |
| 16 | 2024-11-20 | success | |
| 17 | 2025-01-17 | success | |
| 18 | 2025-03-05 | success | |
| 19 | 2025-03-25 | success | |
| 20 | 2025-05-13 | success | |
| 21 | 2025-05-14 | success | index_tick recorded |

Existing **19** baseline sessions remain unchanged; not re-ingested in P8C.2.

---

## 4.3 Raw Lake Quality Summary

| Check | Result |
|-------|--------|
| Partition manifests | **complete** — `ingestion_status=complete` per dataset family |
| SHA256 checksum | **ok** — `files[].sha256` present on all reviewed partitions |
| Quote policy | **skip_tick→1s** — `full_rth_strike_range_60_skip_tick_attempt` used consistently; `option_quote_tick` not required per tick_or_1s OR policy |
| Early close | **2023-07-03** — RTH window `09:30–13:00`; ingest success |
| Index coverage | **2025-05-14** — `index_price_tick` + `index_price_1s` both present |

### Rows summary (21 P8C dates)

| dataset | rows |
|---------|------|
| option_quote_1s | 110,701,222 |
| option_trade_tick | 9,301,945 |
| option_greeks_1m_first_order | 1,849,762 |
| derived_gamma_black76_1m | 1,844,940 |
| option_open_interest | 4,736 |
| index_price_tick | 450,370 |
| index_price_1s | 480,621 |
| session_metadata | 21 |

Storage (lake directory): ~13.2 GB used (includes baseline + P8C expansion).

---

## 4.4 Warnings Carried Forward

| Warning | Record |
|---------|--------|
| **temporal_warning** | `min_new_sessions_2024 = 6` vs target `8`; accepted in P8C.1.1; **carried forward**; no dates replaced. |
| **proxy_bucket_warning** | `high_vol` / `trend` buckets used deterministic proxy at P8C.1 selection (`selection_seed=20260621`); **must be rechecked in P8C.3** using realized index metrics from ingested data. |

---

## 4.5 Scope Attestation

```text
No dataset build was performed.
No feature build was performed.
No model fitting was performed.
No .fit() was called.
No P8B.4 approval is implied.
```

---

## Owner Decision

| Decision | Outcome |
|----------|---------|
| P8C.2 raw lake ingest gate | **PASS** — accepted |
| Approve P8C.3 dataset + feature build validation | **Yes** — see approval record |
| Approve P8C.4 refit | **No** |
| Approve P8B.4 | **No** |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-23 | P8C.2.1 owner review PASS; P8C.3 build validation authorized |
