# ML-P8C.3 Dataset / Feature Build — Owner Gate

**Status: BLOCKED** — 须待 owner 审阅 P8C.2 ingest 报告后方可进入。

## Gate 声明

1. **P8C.3 remains blocked until owner reviews P8C.2 ingest report.**
2. **P8C.3 may build dataset/features only for successfully ingested frozen dates.**
3. **P8C.3 must not replace failed dates.**
4. **P8C.3 must not train models.**
5. **P8C.3 must not authorize P8B.4.**

## 前置条件

| 条件 | 要求 |
|------|------|
| P8C.2 报告 | `docs/ml/p8c2_raw_lake_ingest_report.md` 经 owner 签收 |
| 可用 session | 仅 `p8c2_run_manifest.json` 中 `successful_dates` + 既有 19 日 baseline |
| 失败日期 | 记录保留，**不得**用替代日期补齐 |
| 模型训练 | **禁止** — 含 `.fit()`、hyperparameter search |
| P8B.4 | **继续 BLOCKED** |

## Owner 审阅清单

- [ ] 确认 frozen 21 日 ingest 状态表与 manifest 一致
- [ ] 确认 `replacement_dates_used = false`
- [ ] 确认 `dataset_build_performed = false`（P8C.2 阶段）
- [ ] 确认 temporal / proxy bucket 警告已记录且未用于换日
- [ ] 批准仅对 **success** 日期执行 dataset + feature build

## 下一阶段授权范围（待批准）

P8C.3 若获批准，允许：

- PIT dataset build（仅 successful frozen dates）
- Feature build（同一日期集合）
- 质量检查与 manifest 更新

P8C.3 **不允许**：

- 新增或替换日期
- 模型训练 / refit
- P8B.4 生产回测授权
- 修改 `docs/ml/label_spec.md`

## 相关文档

- `docs/ml/p8c2_raw_lake_ingest_report.md`
- `docs/ml/p8c2_ingest_owner_approval_record.md`（P8C.2 授权记录）
- `docs/ml/p8c_controlled_dataset_expansion_plan.md`
- `config/ml/p8c2_raw_lake_ingest.yaml`
