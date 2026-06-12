# 既有测试失败诊断（ML-P0.5 基线冻结）

**日期：** 2026-06-11  
**范围：** `tests/test_terminal_m4.py` 中 3 个失败用例  
**本阶段操作：** 仅诊断与文档化；**未**修改实现或测试。

---

## 摘要

| 测试 | clean HEAD | working tree | 根因类别 |
|------|------------|--------------|----------|
| `test_build_strike_heatmap_from_chain` | FAIL | FAIL | 已提交 contract 变更，测试未同步 |
| `test_heatmap_roc_pct` | FAIL | FAIL | 同上 |
| `test_api_snapshot_latest` | FAIL | FAIL | 集成测试依赖 ThetaData + 未来 session 日期 |

working tree 额外包含未提交测试 `test_recommend_short_gamma_none_flip_does_not_crash`（与上述 3 个失败无关；对应该测试 **PASS**）。

---

## 1. `test_build_strike_heatmap_from_chain`

### 现象

```text
AssertionError: assert 2 == 3
where 2 = len(([ {...}, {...} ], False))
```

### 函数定义

`src/quant_lab/terminal/snapshot.py` — `build_strike_heatmap(...) -> tuple[list[dict], bool]`

docstring 明确：

```text
Returns (rows, cohort_fallback).
```

第二个 `bool` 表示 dte≤1 过滤为空时是否回退到全链（与 dashboard `meta.cohort_fallback` 一致）。

### 调用方

| 位置 | 用法 |
|------|------|
| `snapshot.build_dashboard` L1229 | `heatmap, cohort_fallback = build_strike_heatmap(...)` ✅ 已解包 |
| `snapshot._build_trinity_panel` L860 | `heatmap, _cohort_fb = build_strike_heatmap(...)` ✅ 已解包 |
| API payload | `"heatmap": heatmap` — 仅 rows 列表进入 JSON |
| 前端 `HeatmapPanel.tsx` / `types/snapshot.ts` | 消费 `panel.heatmap: HeatmapRow[]` — 不涉及 bool |

### bool 语义

- `False`：dte≤1 cohort 非空，正常过滤。
- `True`：dte≤1 过滤结果为空，使用全链并应在 `meta.cohort_fallback` 标注。

### 判断

**有意的 contract 变更**（实现 + 生产调用方已更新），**单元测试未同步**（仍把返回值当作 bare list）。  
**不是**金融公式错误或意外破坏 GEX 计算。

### 推荐修复

仅改测试（不改 `factors/` 或 `snapshot.py` 公式）：

```python
rows, cohort_fallback = build_strike_heatmap(chain, 100.0, dte_max=1)
assert len(rows) == 3
assert cohort_fallback is False
```

`test_heatmap_roc_pct` 同理解包并断言 `len(rows) == 1`。

### 是否阻塞 ML-P1

**否** — ML-P1 为 ThetaData 能力审计，不依赖 heatmap 单元测试。

### 对 replay / Railway fallback 的影响

**无直接阻塞**；但 cohort_fallback 语义应在 ML 特征契约（ML-P5）中引用同一字段。

---

## 2. `test_heatmap_roc_pct`

与 §1 相同根因：未解包 `(rows, cohort_fallback)`。  
clean HEAD 与 working tree 均 FAIL。

---

## 3. `test_api_snapshot_latest`

### 现象

```text
TypeError: 'NoneType' object is not subscriptable
assert body["pin_playbook"]["size_multiplier"] is not None
```

`pin_playbook` 键存在，值为 `null`。

### 生成路径

```text
GET /api/snapshot
  → api_snapshot()
  → build_dashboard(symbol, date)
```

正常路径（链可用）：L1419 `build_pin_playbook(...)` → L1549 `pin_playbook_to_dict(...)`。

**Hold 路径**（链不可用 + 当日 live session）：L1164–1173 → `build_session_hold_dashboard(...)` → `"pin_playbook": None`（L1061）。

### ThetaData / 日期行为

测试使用 `/api/dates?symbol=SPY` 的 `latest` 日期（实测 **2026-06-12**，相对审计日 2026-06-11 为**未来交易日**）。

日志：

```text
ThetaData ... Start time must be less than end time
live ThetaData fetch failed ... trying fallbacks
ThetaData chain fetch failed ...
```

链拉取失败后，若 `is_live_session(asof)` 为真，进入 hold dashboard → `pin_playbook = None`。

### 测试是否依赖网络

**是** — 未 mock ThetaData；依赖本机凭证与 ThetaData gRPC。  
同时依赖本地 `data/` 中 SPY terminal 历史日期列表（含未来 session）。

### 生产 fallback 是否不完整

- **Hold 路径**：HTTP 200 + `availability: "hold"` + `pin_playbook: null` — 与 `build_session_hold_dashboard` 设计一致。
- **问题**：测试假设 `latest` 日期总能得到完整 playbook，未处理 hold / 未来 session / ThetaData 失败场景。

### 前端能否处理 `pin_playbook = null`

**能。** `PlaybookPanel.tsx` L19–28：

```tsx
if (!pb) {
  return (... "Playbook unavailable for this snapshot." ...);
}
```

TypeScript 类型：`pin_playbook?: PinPlaybook`（可选）。

### 判断

- 生产代码对 null playbook **有 intentional fallback**（hold 态 + 前端文案）。
- 测试 contract **过强**（要求非 null size_multiplier），且**不稳定**（日期 + 网络 + ThetaData 窗口）。

### 推荐修复（择一）

1. **测试侧（推荐）**：mock `_load_intraday_chain_safe` / 使用固定历史日期 + 本地 parquet；或当 `body.get("availability") == "hold"` 时断言 `pin_playbook is None`。
2. **产品侧（可选，非 ML-P0.5）**：hold dashboard 仍返回 skeleton playbook（非 null）— 需 Pin Play spec 确认，涉及产品语义。

### 是否阻塞 ML-P1

**否** — 但应在进入 ML-P4 replay 前修复或隔离此类集成测试，避免 CI 误报。

### 对 replay / Railway fallback 的影响

- 与 ML **deterministic fallback** 设计一致：模型缺失时不应 503，应降级。
- 当前 hold 路径已是降级模式；测试应显式覆盖该 contract，而非假设 playbook 永不为 null。

---

## 4. ML-P0.5 结论

| 项 | 结论 |
|----|------|
| 是否进行最小修复 | **否**（本阶段仅冻结基线并文档化） |
| clean HEAD 复现 | **是**（3/3） |
| working tree 引入 | **否**（3 个失败均来自已提交代码；working tree 仅多 1 个无关 PASS 测试） |
| 允许进入 ML-P1 | **是**（审计只读任务；建议并行排期修复上述测试） |

---

## 5. 建议修复优先级

1. **P1 — 测试解包**（2 个 heatmap 测试，5 分钟，零金融风险）
2. **P2 — snapshot 集成测试 mock**（1 个 API 测试，消除 ThetaData/日期不稳定）
3. **P3 — CI 策略**：集成测试与单元测试分 job；集成 job 需凭证或 skip marker
