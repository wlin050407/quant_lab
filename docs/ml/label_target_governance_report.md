# ML-P7.7 Label Target Governance Report

**Phase:** ML-P7.7 — Label Target Governance and Expansion Decision  
**Branch:** `research/zdte-fusion-model`  
**Evidence base:** ML-P7.6.1 – ML-P7.6.7  
**Status:** Governance proposal only — **未修改** `docs/ml/label_spec.md`，**未修改** label builder

---

## Executive Summary

P7.6.7 regular_5min screening 证明：**frozen Pin Zone contract 下的 zone label 语义正确、可复现、与 full build 一致**，但在当前 20 日 raw lake 中**极度稀疏**（19 日 screened，仅 4 日有 included，合计 89 rows）。稀疏主因是 **deterministic contract gate**（short-γ regime、secondary strength、pin distance），不是数据缺失或 replay bug。

**结论：**

1. **Zone label 应保留**，作为 strict / secondary / Terminal-parity 研究 target，**不宜**作为第一版 ML baseline 的唯一 primary target。
2. 若坚持 zone-only 路线达到 P8B 最低门槛（included ≥ 300），需约 **+45–65 个 screened trade dates** 或 **+8–12 个「高 yield」正样本日**（区间估算）。
3. **建议先做 label governance（Option B proposal）**，并行、从属地扩展 raw lake 以 enrichment zone target；**禁止** Option D（改 threshold）或 Option C（fallback zone）在未签字前实施。
4. **仍禁止 ML-P8B**。

---

## 一、核心问题回答

### Q1. Zone label 是否适合继续作为 primary ML target？

**部分适合，但不适合作为唯一 primary target。**

| 维度 | 评估 |
|------|------|
| 语义 / Terminal parity | ✅ 与 frozen contract 一致；P7.6.7 screening = full build label 阶段 |
| Leakage / join | ✅ P7.6.3–7.6.6 均 PASS |
| 类别多样性 | ✅ 跨日合并有 above / inside / below 三类 |
| 样本量 | ❌ included_total=89 << P8B 300 |
| 日期覆盖 | ❌ 19 日中 15 日 included=0（79% negative dates） |
| 单日类别 | ❌ 无单日同时含多类（pin 行为 session-stable） |

**建议角色：** `close_location_vs_current_zone` 保留为 **strict secondary target**（Phase 2 评估、zone 专用模型），第一版 baseline 改用已有 spec 中的 pin-distance 族 target（见 Recommendation 2）。

### Q2. 坚持 zone label 时，还需多少日期才可能达到 P8B 最低样本量？

P8B 最低门槛（沿用 P7.6.x 判据）：

```text
row_count >= 1000
included_rows >= 300
valid_zone_ratio >= 20%
至少两个 label 类别（最好三个）
leakage PASS / strict join PASS
```

**当前（P7.6.7 screening，19 dates）：**

| 指标 | 值 |
|------|-----|
| total anchors (screened) | ~1,393 |
| included_total | **89** |
| valid_zone_ratio (anchor-level) | **6.4%** (89/1,393) |
| dates_with_any_zone | **4** / 19 (21%) |
| dates_with_meaningful_zone (included ≥ 10) | **2** / 19 |

**缺口：**

| 门槛 | 当前 | 缺口 |
|------|------|------|
| included_rows | 89 | **−211** (to 300) |
| row_count (若 full build 19 日) | ~1,393 | 已 > 1000 ✅ |
| valid_zone_ratio (anchor-level) | 6.4% | **−13.6 pp** (to 20%) |

**区间估算（非精确预测）：**

| 估算方法 | 假设 | 额外需求 |
|----------|------|----------|
| 按 screened date 平均 yield | 89/19 ≈ **4.7 included/date** | (300−89)/4.7 ≈ **45 extra screened dates** |
| 按 positive date 平均 yield | 89/4 ≈ **22.2 included/positive day** | (300−89)/22.2 ≈ **9–10 extra high-yield days** |
| 按 meaningful day (≥10 included) | 87/2 ≈ **43.5 included/meaningful day** | (300−89)/43.5 ≈ **5 extra opex-style days** |

**现实约束：** 当前 20 日 complete lake 中仅 4 日有信号；继续 ingest **同类随机日期** 大概率复现 79% zero-yield。**盲目扩日期不能替代 governance。**

### Q3. Zone label 稀疏的主要原因？

**Frozen deterministic contract gates**（P7.6.1 已证实，P7.6.7 量化确认）：

| Gate | 19 日 anchor-weighted 占比 | 说明 |
|------|---------------------------|------|
| `short_gamma_regime` | **~49.8%** | net GEX < 0 → `detect_pin_cluster` 不 merge |
| `pin_distance_too_wide` | **~37.2%** | primary/secondary strike 距离 > 0.3% spot |
| `secondary_strength_too_low` | **~6.7%** | strength ratio < 70% |
| `low_pin_reliability_gate` | **~0%** | adapter fix 后非主因 |

**不是主因：**

- Raw lake 分区缺失（20/20 complete）
- Replay 覆盖不足（quote/greek/gamma ~0.79–1.0）
- Strike range=60 过窄（P7.6.1 已排除）
- Composite long-γ ranking 选日（P7.6.4–7.6.6 已证伪）

**结构特征：** SPX 0DTE 大量 session 处于 short-γ；Pin Zone 是 **long-γ conditional label**，稀疏是 contract 设计结果，不是 pipeline bug。

### Q4. 是否应该新增 first-baseline target？

**是。** 在 zone target 未达 P8B 样本量前，应新增 **first-baseline target proposal**（governance 签字后实施），理由：

- `primary_pin_t` / pin magnet ranking 在 **绝大多数 anchor 非 null**（P7.6.1: pin_score / primary_pin 100% on sampled anchors）
- 不修改 Pin Zone formula
- 允许 ML-P8B 以 **pin-behavior baseline** 启动，zone label 并行保留为 strict track

### Q5. 新 target：`primary_pin_distance` vs `close_near_primary_pin`？

**正式 spec 中已有相关字段**（`docs/ml/label_spec.md`）：

| 字段 | 类型 | 覆盖 | 用途 |
|------|------|------|------|
| `close_distance_to_primary_pin_points` / `_em` | 连续（signed） | primary_pin 非 null 时 | **推荐 first regression baseline** |
| `close_near_primary_pin` | 二元（tolerance） | 同上 | 分类 baseline / 衍生 |
| `close_location_vs_current_zone` | 三分类 | 仅 valid zone | strict secondary |

**推荐优先级：**

1. **Primary baseline（回归）：** `close_distance_to_primary_pin_em`（EM-normalized，跨 regime 可比）
2. **Secondary baseline（分类）：** 由 distance 导出 `close_above_below_primary_pin`（proposal 新字段，见 §五）
3. **辅助：** `close_near_primary_pin`（default `fixed_5pt`）— 适合 pin-hit rate，但对 opex 大 spot 可能过宽/过窄

**不推荐**把 `close_near_primary_pin` 作为唯一 primary target：tolerance 选择影响 label 分布，需 governance 固定 config；distance 更连续、更可诊断。

### Q6. 新 target 如何不破坏 deterministic contract？

| 原则 | 做法 |
|------|------|
| 不修改 `pin_cluster.py` / GEX / EM 公式 | ✅ |
| 不修改 zone merge gates | ✅ |
| 不修改 `close_location_vs_current_zone` 定义 | ✅ |
| 使用 as-of frozen `primary_pin_t` + official_close | 已在 `compute_all_labels()` 实现 |
| 新 target 作为 **parallel column** + governance addendum | 需 owner sign-off 后写入 spec v1.1 |
| Feature cutoff 不变 | `event_timestamp <= as_of_timestamp` |
| Zone label 行仍 excluded when no zone | baseline target 行 **included when primary_pin non-null**（新 inclusion rule proposal） |

**关键：** baseline target 的 inclusion 与 zone inclusion **解耦**——不改变 zone 行权重逻辑，仅新增可训练子集定义。

### Q7. 下一步：扩数据 vs label governance？

**先做 label governance（必须），并行从属扩数据（可选 enrichment）。**

| 顺序 | 动作 | 原因 |
|------|------|------|
| 1 | 完成 label target governance proposal + owner sign-off | P8B 无法仅靠扩日期解决 valid_zone_ratio |
| 2 | Spec addendum v1.1（baseline target + inclusion rules） | 不修改现有 zone 语义 |
| 3 | Screening 驱动的 raw lake 扩展（新 dates，非 top8 blind） | 仅 enrich zone strict track |
| 4 | 可选：2025-01-03 单日 full build | 验证 screening 1-row 信号 |
| ✗ | top8 full build / ML-P8B | 禁止 |

---

## 二、量化分析（§4 要求）

### 4.1 当前 Zone Target 统计

**来源：** `artifacts/reports/valid_zone_candidate_screening_v1/per_date/*.json`（19 dates，P7.6.7）

| 指标 | 值 |
|------|-----|
| screened_dates | **19** |
| skipped_dates | **1** (`2026-06-10`, pilot NaN) |
| complete raw lake dates | **20** |
| dates_with_any_zone (included > 0) | **4** |
| dates_with_meaningful_zone (included ≥ 10) | **2** |
| negative dates (included = 0) | **15** |
| included_total | **89** |
| valid_zone_ratio_total (anchor-level) | **6.4%** (89 / ~1,393 anchors) |
| full-build included_total (top5 复用) | **88**（与 screening 89 差 1：`2025-01-03` 为 screening 新发现） |

**included_by_date：**

| Date | included | valid_zone_ratio | inside | below | above | full-built? |
|------|----------|------------------|--------|-------|-------|-------------|
| 2024-01-19 | 48 | 62.3% | 0 | 0 | 48 | ✅ |
| 2024-10-04 | 39 | 50.6% | 39 | 0 | 0 | ✅ |
| 2025-05-02 | 1 | 1.3% | 0 | 1 | 0 | ✅ |
| 2025-01-03 | 1 | 1.3% | 0 | 0 | 1 | ❌ |
| 其余 15 日 | 0 | 0% | — | — | — | 部分 |

**跨日 label 类别：** above (2 dates) / inside (1) / below (1) — **3 类齐全但极度不平衡**。

### 4.2 P8B 样本缺口

| P8B 判据 | 当前 | 达标? |
|----------|------|-------|
| row_count ≥ 1000 | ~1,393 (19d screening anchors) | ✅（若 full build） |
| included_rows ≥ 300 | **89** | ❌ gap **211** |
| valid_zone_ratio ≥ 20% | **6.4%** anchor-level | ❌ |
| ≥ 2 类别 | 3 类 | ✅ |
| leakage / join | PASS（已 built 日） | ✅ |

**估算额外需求（区间）：**

```text
included gap to 300:           211 rows
avg included / positive date:  ~22  (range 1–48)
avg included / screened date:  ~4.7
positive date hit rate:        ~21% (4/19)

→ 额外 screened dates（同命中率）:  ~40–50 日
→ 额外 high-yield 正样本日:        ~8–12 日（opex / long-γ pinning 风格）
→ 达到 20% valid_zone_ratio:       需 materially 提高正样本日占比，非线性扩日期
```

### 4.3 Zone 稀疏原因（Gate 分布）

P7.6.7 全量 screening anchor-weighted failure 占比：

```text
short_gamma_regime:          ~50%
pin_distance_too_wide:       ~37%
secondary_strength_too_low:  ~7%
low_pin_reliability_gate:    ~0%
```

这些是 **`pin_cluster.py` frozen contract** 的有意 gate，**不是** ingest 缺口。降低 threshold（Option D）或 fallback zone（Option C）会改变 Terminal parity 语义。

### 4.4 路线对比 Option A / B / C / D

#### Option A — 继续 zone label，扩更多日期

| | |
|---|---|
| **优点** | 不改 label spec / contract；strict Terminal parity 研究路径清晰 |
| **缺点** | 正样本日稀缺（~21% hit rate）；需大量 ingest + screening + full build；6% anchor-level valid_zone 难推到 20% |
| **适合** | Zone 专用 Phase 2 模型；opex / long-γ 日期 enrichment |
| **P7.7 建议** | **并行从属执行**，不作为 P8B 唯一前置 |

#### Option B — 新增 pin-distance / near-pin baseline target

| | |
|---|---|
| **优点** | 字段已在 label builder 计算；primary_pin 覆盖高；可立即定义 inclusion rule |
| **缺点** | 新 primary target 需 governance 签字；不能直接替代 zone 研究 |
| **适合** | **第一版 ML baseline（P8B entry）** |
| **P7.7 建议** | **推荐主路线** |

#### Option C — Pin-centered fallback zone

| | |
|---|---|
| **优点** | 提高 classification 覆盖率 |
| **缺点** | 改变 label 语义；与 Terminal Pin Zone 不等价；污染 strict zone track |
| **适合** | 仅在有明确 ML-only 语义文档 + owner 签字时 |
| **P7.7 建议** | **暂不推荐** |

#### Option D — 修改 Pin Zone threshold

| | |
|---|---|
| **优点** | 直接提高 zone coverage |
| **缺点** | 修改 deterministic contract；影响 Terminal + replay + ML |
| **适合** | 需 owner + 全链路回归 |
| **P7.7 建议** | **禁止当前阶段执行** |

---

## 三、正式建议（Proposal Only — 未实施）

### Recommendation 1

**保留** `close_location_vs_current_zone` 作为 **strict / secondary target**：

- 继续用于 Terminal parity 评估、zone 专用模型、leakage-safe strict track
- **不再**作为 P8B 唯一 primary supervised target

### Recommendation 2

**新增 first-baseline target proposal**（spec addendum v1.1，签字后实施）：

| 优先级 | Target | 说明 |
|--------|--------|------|
| P0 | `close_distance_to_primary_pin_em` | 连续回归 baseline；primary_pin 非 null 即 included |
| P1 | `close_near_primary_pin` | 二元分类（固定 `fixed_5pt` 或 governance 选定 tolerance） |
| P2 | `close_above_below_primary_pin` | 三分类 proposal：`below` / `at_pin` / `above` relative to primary_pin_t ± tolerance |

**Inclusion rule proposal（baseline track）：**

```text
included_baseline = primary_pin_t is not null AND official_close is not null
sample_weight_baseline = 1 / count(included_baseline per session)
```

Zone track inclusion **不变**：`has_valid_zone AND close_location non-null`。

### Recommendation 3

**下一阶段先完成 label spec governance proposal + owner sign-off，不直接训练。**

建议子阶段：

```text
ML-P7.7.1 — Label spec addendum draft (v1.1 proposal)
ML-P7.8  — Baseline target coverage screening (reuse P7.6.7 pipeline, pin fields only)
ML-P8B   — 仅在 baseline included ≥ 300 AND governance signed 后进入
```

### Recommendation 4

**数据扩展继续，但角色调整：**

- Raw lake 扩展 → **zone-target enrichment**（找更多 opex / long-γ pinning 日）
- **不是** P8B 唯一前置条件
- 禁止 blind top8 full build；新 dates 必须先 regular_5min screening
- 可选：2025-01-03 单日 full build（验证 1-row 信号）

---

## 四、与历史阶段对照

| 阶段 | 关键结论 |
|------|----------|
| P7.6.1 | Adapter fix；valid_zone=0% 主因 short-γ gate |
| P7.6.2 | Hourly scan 仅 2 日 valid_zone>0 |
| P7.6.3 | 2024-01-19 full build：48 included, above only |
| P7.6.5 | Top3 valid-zone：88 included, 3 类 |
| P7.6.6 | Top5 tie-break 无效；仍为 88 included |
| P7.6.7 | 19 日 screening：89 included，4 正样本日 |
| **P7.7** | **Zone strict track 保留；baseline target governance 优先** |

---

## 五、限制遵守

- 未修改 `docs/ml/label_spec.md`
- 未修改 label builder / pin_cluster / financial formulas
- 未运行 full build / top8 / ingest
- 未训练模型
- 未进入 ML-P8B
- 未提交 artifacts

---

## 六、下一阶段建议（ML-P7.7 出口）

| # | 动作 | 阻塞 P8B? |
|---|------|-----------|
| 1 | Owner review 本报告 + `label_target_governance_decision.md` | 是 |
| 2 | Draft `label_spec` addendum v1.1（baseline inclusion + targets） | 是 |
| 3 | ML-P7.8 baseline coverage screening（pin fields，无需 zone） | 是 |
| 4 | 并行：raw lake 扩展 + regular_5min screening（zone enrichment） | 否 |
| 5 | ML-P8B baseline training | 仅 governance + coverage 达标后 |

**ML-P8B：仍禁止。**
