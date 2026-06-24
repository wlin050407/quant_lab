# ML-P8C.3 Dataset / Feature Build Owner Approval Record

**Date:** 2026-06-23  
**Stage:** ML-P8C.3 authorization (implementation not started)  
**Owner:** Weitong Lin  
**Prerequisite:** ML-P8C.2 PASS + [`p8c2_1_raw_lake_ingest_owner_review.md`](p8c2_1_raw_lake_ingest_owner_review.md)

---

## Approval Statement

```text
Status: Approved for ML-P8C.3 dataset + feature build validation only
```

This record authorizes **PIT dataset build** and **feature build** for the **21 successful frozen P8C.2 dates**, plus validation and expanded 40-session view assembly. It does **not** authorize model fitting, refit, hyperparameter search, P8B.4, or new ingest.

---

## Approved Scope

| Item | Approved |
|------|----------|
| Build PIT dataset rows for the **21** successful frozen P8C.2 dates | **Yes** |
| Build feature rows for the **21** successful frozen P8C.2 dates | **Yes** |
| Validate joins, manifests, leakage, forbidden inputs, feature coverage | **Yes** |
| Combine existing **19** baseline sessions + **21** P8C sessions → **40-session** expanded validation view | **Yes** |
| Carry forward temporal warning and proxy bucket warning | **Yes** |
| Recheck proxy bucket assignment using realized index metrics (P8C.3 diagnostic) | **Yes** |
| Generate reports and manifests (local artifacts; not committed) | **Yes** |
| Strict hash join validation | **Yes** |
| Forbidden feature input validation | **Yes** |

### Frozen dates (dataset / feature build scope)

Same 21 dates as P8C.1.1 / P8C.2 — see [`p8c2_1_raw_lake_ingest_owner_review.md`](p8c2_1_raw_lake_ingest_owner_review.md) §4.2.

**No substitution.** Failed dates (if any in future) are not replaced.

---

## Not Approved

| Item | Status |
|------|--------|
| Model fitting | **NOT approved** |
| Calling `.fit()` | **NOT approved** |
| FeatureSet_A refit | **NOT approved** |
| FeatureSet_B refit | **NOT approved** |
| Hyperparameter search | **NOT approved** |
| P8B.4 | **NOT approved** |
| Production backtest | **NOT approved** |
| Trading signal | **NOT approved** |
| Replacement dates | **NOT approved** |
| New raw lake ingest | **NOT approved** |
| Modifying `docs/ml/label_spec.md` | **NOT approved** |
| Modifying `requirements.txt` | **NOT approved** |
| P8C.4 expanded refit | **NOT approved** (separate gate) |

---

## P8C.3 Boundary

```text
P8C.3 = dataset + feature build + validation diagnostics only.
P8C.4 = expanded refit (blocked until P8C.3 PASS + separate owner approval).
P8B.4 = hyperparameter search (blocked).
```

---

## Related Documents

- [`p8c3_dataset_feature_build_owner_gate.md`](p8c3_dataset_feature_build_owner_gate.md)
- [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)
- [`p8c2_raw_lake_ingest_report.md`](p8c2_raw_lake_ingest_report.md)

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-23 | P8C.3 dataset + feature build validation authorized |
