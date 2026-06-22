# ML-P8C.1 Ingest Cost Estimate

**Date:** 2026-06-22  
**Stage:** ML-P8C.1  
**Prerequisite:** [`p8c1_candidate_date_selection_report.md`](p8c1_candidate_date_selection_report.md)

---

## Selected New Dates

| Item | Count |
|------|-------|
| Stage 1 new sessions | **21** |
| Existing baseline sessions | 19 |
| Target total after Stage 1 | **40** |

---

## Availability Breakdown

| Category | Count |
|----------|-------|
| Dates requiring raw lake ingest | **21** |
| Dates already in raw lake | **0** |
| Dates requiring dataset build | **21** |
| Dates requiring feature build | **21** |

所有 21 个新选日期当前 **无** 本地 raw lake partition。

---

## Runtime Estimate (Planning Bounds)

基于 P7.6 / P8B.1 经验参数（`config/ml/p8c_stage1_candidate_selection.yaml`）：

| Phase | Low (min) | Base (min) | High (min) |
|-------|-----------|------------|------------|
| Raw lake ingest (21 days) | 252 | 378 | 588 |
| Dataset build (21 days) | 84 | 147 | 252 |
| Feature build (21 days) | 168 | 294 | 462 |
| **Total** | **504** | **819** | **1302** |

**≈ 8.5 – 21.7 hours** wall time（base ≈ 13.7 h），取决于 ThetaData 速率与单日数据量。

**Disclaimer:** 估算不等于 SLA；实际 runtime 可能显著偏离。

---

## Storage Estimate

| Scenario | GB |
|----------|-----|
| Low | 8.4 |
| Base | 16.8 |
| High | 31.5 |

Per-date raw lake 约 0.4 – 1.5 GB（含 options chain + index path + greeks）。

---

## Main Operational Risks

1. **ThetaData API rate limits** — 21 日连续 ingest 可能需分批
2. **Entitlement / credentials** — 本地 entitlement 必须有效（P8C.2 前 owner 确认）
3. **Early-close session** — 2023-07-03 需正确 `early_close` metadata
4. **High-volume days** — proxy-tagged high_vol 日在 ingest 后可能较慢
5. **Feature build dominance** — feature build 可能占总时间 35–40%
6. **Proxy bucket tags** — ingest 后应以真实 index 路径复核 high_vol/trend 标签

---

## Recommended Staged Execution Order (P8C.2+)

```text
1. Owner approval for P8C.2 ingest (this document + selection report)
2. P8C.2 — ingest 21 dates to raw lake (idempotent, partition manifests)
3. P8C.3 — dataset + feature build for expanded cohort (40 sessions)
4. P8C.3 — P8B.1-style leakage / forbidden-feature validation
5. P8C.4 — FeatureSet_A fixed-hyperparameter refit (NOT P8B.4)
6. P8C.5 — expanded result review
```

**不得** 在 P8C.2 中修改已选日期（除非 owner 批准新 rules commit）。

---

## Cost Estimate Artifact

Local JSON: `artifacts/reports/p8c_candidate_selection/p8c1_cost_estimate.json`（未提交 git）

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial cost estimate for 21 Stage 1 dates |
