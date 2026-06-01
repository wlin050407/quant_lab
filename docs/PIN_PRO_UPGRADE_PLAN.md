# Pin / Live Terminal 专业对齐 — 临时实施计划

> **状态**：进行中（2026-05-24）  
> **目标**：在 Live 30s 路径上逼近 FlashAlpha / SpotGamma 的 pin + magnet 语义，不阻塞历史 rebuild。  
> **原则**：算法改 Live 立刻生效；数值标定等 Standard 历史链 rebuild 完成后再做。

---

## 已对齐（无需重做）

| 项 | 说明 |
|----|------|
| Magnet / King | argmax \|NetGEX\|，0DTE cohort |
| Pin 四因子权重 | 30 / 25 / 25 / 20（OI / proximity / time / gamma） |
| Effective OI 框架 | settled + confidence × flow → clamp ≥ 0 |
| Live 刷新 | REST 30s，`time=live` follow 模式 |
| Regime | net GEX → long_γ / short_γ |
| 0DTE T | 剩余 session 小时 → BS76 |

---

## P0 — 算法 + Live 产品（当前 sprint）

### P0-1 有符号 trade flow → effective OI

**差距**：现用 `0.43 × \|volume\|`；FlashAlpha 用逐笔买卖分类后的 **signed delta**。

**实现**：

- [x] `factors/trade_flow.py` — Lee-Ready（price vs NBBO）+ tick-rule fallback
- [x] `thetadata_intraday.fetch_0dte_signed_flow_at_time` — trades + quotes asof 合并
- [x] `effective_oi` — `flow_signed=True` 时不用 `abs(flow)`
- [x] `build_0dte_chain_snapshot` — Standard tier 优先 signed flow
- [x] `flow_source=trade_signed`；meta `volume_source=trade_signed`
- [x] rebuild 完成后历史链也带 signed flow（build script 已统一 snapshot builder，随 rebuild 自动）

**验收**：单测手算 3 笔买 / 2 买 1 卖；Live Terminal badge 显示 signed trades。

### P0-2 Regime × Pin 联合解读

**差距**：Pro 强调「pin≥70 + long γ = 干净」；「high pin + short γ = 假 pin 风险」。

**实现**：

- [x] `pin_reliability()` + `pin_score_regime_adjusted()`（`factors/regime.py`）
- [x] API：`pin_targets.pin_reliability` / `pin_score_adjusted`
- [x] UI：PinPanel reliability 灯 + 调整分显示

**验收**：short_γ + pin≥70 → `caution`；long_γ + pin≥70 → `high`。

### P0-3 Magnet 跳变追踪

**差距**：FlashAlpha 产品级 magnet shift alert。

**实现**：

- [x] `terminal/magnet_state.py` — session 内上一拍 King
- [x] API meta：`magnet_shift`, `magnet_previous`, `magnet_delta_pts`
- [x] UI：Primary magnet 旁跳变提示（仅 live follow）

**验收**：Live 下 King 换 strike → 下一 poll 出现 shift 元数据。

---

## P1 — rebuild 完成后

### P1-1 Intraday IC 重标定

- [ ] `evaluate_intraday_pin.py` 跑 506×3 Standard 链
- [ ] 调 `DEFAULT_FLOW_OI_CONFIDENCE`（0.43）、`PIN_OI_SATURATION`、`PIN_GAMMA_REF_BN`
- [ ] 记录 IC 报告到 `data/processed/pin_eval/`

### P1-2 时间因子细化为「小时」

- [x] `pin_time_remaining_score(hours_to_close)` — 末 2h 加速（Pin Play 窗口）
- [x] Terminal / pin_score 全链路传 `hours_to_close`（分钟精度）

### P1-3 宏观日历 gate

- [x] `data/macro_calendar.py` — FOMC / CPI 2024–2027 embedded
- [x] Playbook check #5 → macro 日 **0×**
- [ ] 可选扩展：`data/raw/calendar/macro_events.parquet`

### P1-4 可选 FlashAlpha Growth 对照

- [ ] 1 个月 `/v1/flow/pin-risk` 作 label，校准 confidence（非日常数据源）

---

## P2 — 研究线（Phase 1 出口 / Phase 4 前）

| 项 | 说明 |
|----|------|
| Charm 进 pin | 0DTE 末小时 secondary |
| Dealer sign 日度检验 | Philipp Dubach / SPXW 18y |
| Live 30s chain 归档 | 取消 Theta 前 bulk parquet |
| Credit / wing 实时过滤 | Phase 4 execution |

---

## 文件索引

| 模块 | 路径 |
|------|------|
| Signed flow | `src/quant_lab/factors/trade_flow.py` |
| Effective OI | `src/quant_lab/factors/effective_oi.py` |
| Theta fetch | `src/quant_lab/data/thetadata_intraday.py` |
| Chain build | `src/quant_lab/data/thetadata_chain.py` |
| Pin score | `src/quant_lab/factors/positioning.py` |
| Regime × pin | `src/quant_lab/factors/regime.py` |
| Magnet state | `src/quant_lab/terminal/magnet_state.py` |
| Dashboard | `src/quant_lab/terminal/snapshot.py` |
| UI | `src/quant_lab/terminal/web/src/components/PinPanel.tsx` |

---

## 不做（本计划外）

- WebSocket tick 流（30s REST 对 pin 足够）
- 第二存储格式 / DB
- LongPort OPRA
- ML pin 模型

---

*完成 P0 后更新本文件 checkbox；P1 依赖 `data/logs/rebuild_standard_chains.log` 完成。*
