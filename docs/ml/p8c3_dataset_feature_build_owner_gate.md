# ML-P8C.3 Dataset / Feature Build — Owner Gate

**Status: AUTHORIZED** — ML-P8C.2.1 owner review PASS; implementation **not started**.

**Approval record:** [`p8c3_dataset_feature_build_owner_approval_record.md`](p8c3_dataset_feature_build_owner_approval_record.md)

---

## Stage Definition

```text
ML-P8C.3 — Dataset + Feature Build Validation
```

---

## Prerequisites (satisfied)

| Condition | Status |
|-----------|--------|
| P8C.2 ingest report | PASS — [`p8c2_raw_lake_ingest_report.md`](p8c2_raw_lake_ingest_report.md) |
| P8C.2.1 owner review | PASS — [`p8c2_1_raw_lake_ingest_owner_review.md`](p8c2_1_raw_lake_ingest_owner_review.md) |
| Successful frozen dates | **21 / 21** |
| `replacement_dates_used` | **false** |
| P8C.3 approval record | Signed |

---

## P8C.3 Allowed

| Activity | Allowed |
|----------|---------|
| Build PIT dataset for **21** successful frozen dates | **Yes** |
| Build features for **21** successful frozen dates | **Yes** |
| Combine **19** baseline + **21** P8C → **40-session** expanded validation set | **Yes** |
| Leakage validation | **Yes** |
| Forbidden feature input validation | **Yes** |
| Strict hash join validation | **Yes** |
| Feature coverage diagnostics | **Yes** |
| Proxy bucket recheck using realized index metrics | **Yes** |
| Generate manifests and reports (local; not committed) | **Yes** |
| Carry forward temporal / proxy bucket warnings | **Yes** |

---

## P8C.3 Forbidden

| Activity | Forbidden |
|----------|-----------|
| Model fitting | **Yes** |
| Calling `.fit()` | **Yes** |
| P8C.4 refit | **Yes** |
| P8B.4 hyperparameter search | **Yes** |
| Production backtest | **Yes** |
| Trading signal | **Yes** |
| New raw lake ingest | **Yes** |
| Replacement dates | **Yes** |
| Modify `docs/ml/label_spec.md` | **Yes** |
| Modify `requirements.txt` | **Yes** |

---

## P8C.3 PASS Gate

P8C.3 may close **PASS** only when all of the following hold:

```text
dataset rows built for 21 P8C dates
feature rows built for 21 P8C dates
expanded 40-session row count reported
strict hash join PASS
leakage validation PASS
forbidden input validation PASS
feature coverage report generated
temporal warning carried forward
proxy bucket warning rechecked or explicitly carried forward
no model fitting
no .fit()
no P8B.4
artifacts not committed
tests pass
ruff pass
```

---

## Downstream Gates (unchanged)

| Stage | Status |
|-------|--------|
| P8C.4 — FeatureSet_A locked refit (expanded) | **BLOCKED** |
| P8C.5 — expanded result review | **BLOCKED** |
| P8B.4 — hyperparameter search | **BLOCKED** |
| P8B.5 — production backtest | **BLOCKED** |
| P8B.6 — trading signal | **BLOCKED** |

---

## Owner Review Checklist (P8C.2 — completed)

- [x] Frozen 21-day ingest status matches manifest
- [x] `replacement_dates_used = false`
- [x] `dataset_build_performed = false` during P8C.2
- [x] Temporal / proxy bucket warnings recorded
- [x] P8C.3 dataset + feature build approved (validation only)

---

## Related Documents

- [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)
- [`p8c_date_selection_rules.md`](p8c_date_selection_rules.md)
- [`p8b3_8_next_gate_decision.md`](p8b3_8_next_gate_decision.md)
- `config/ml/p8c2_raw_lake_ingest.yaml`
