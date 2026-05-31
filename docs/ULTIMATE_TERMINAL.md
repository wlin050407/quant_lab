# Ultimate Terminal — 终极 0DTE Positioning 平台规划

**目标**：把 Skylit / SpotGamma / FlashAlpha / Vilkov 的核心能力合成一套系统——  
同一套 positioning 数学，贯通 **research → backtest → live terminal**。

这不是「再做一个热力图订阅」，而是 `quant_lab` 的终局产品形态。

---

## 1. 产品愿景

| 维度 | 商业产品现状 | Ultimate Terminal |
|---|---|---|
| 实时 levels | Skylit / SpotGamma 各自一套 | 统一 schema，GEX + VEX + King + walls |
| 跨标的对齐 | Skylit Trinity 三列 UI | **Trinity Score** 可回测、可 API |
| 0DTE 专用 | FlashAlpha zero-dte endpoint | EoD `dte≤1` cohort + Phase 4 intraday |
| 策略建议 | 各平台文档 / 人工读图 | **Regime → Strategy 决策树**（可测） |
| 历史验证 | 几乎没有 | **18y Philipp Dubach + OOS 协议** |
| 执行 | 各平台不提供 | Phase 5+ paper / live |

**差异化**：别人卖地图，我们卖 **地图 + 指南针 + 行车记录仪**。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  L6  Execution (Phase 5+)                                      │
│      paper / live · tastytrade · 风控状态机                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  L5  Terminal UI (M4–M5)                                         │
│      Trinity 三列热力图 · Levels 面板 · Regime badge · 策略建议    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  L4  Strategy Selector (M2–M3)                                   │
│      FlashAlpha 五策略 + Vilkov multi-leg · conditional filter    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  L3  Regime + Trinity (M1–M2)                                    │
│      long/short gamma · should_trade · Trinity Score · node life  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  L2  Positioning Analytics (M1) ← 当前阶段                        │
│      GEX/VEX · flip · walls · King · pin_score · expected move    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│  L1  Data (Phase 0–4)                                            │
│      EoD 18y SPY · ^SPX 增量 · Phase 4 intraday · optional flow    │
└─────────────────────────────────────────────────────────────────┘
```

**模块边界**（与 `AGENTS.md` 一致）：

| 模块 | 职责 |
|---|---|
| `data/` | 抓取 + 落盘 |
| `factors/` | 干净链 → 因子（本规划 L2–L3 的纯函数部分） |
| `quality/` | 只读检查 |
| `strategies/` | 因子组合 → 仓位 / 结构建议 |
| `backtest/` | 因子 + 价格 → PnL |

---

## 3. 能力映射表

### 3.1 Skylit / Heatseeker / Trinity

| Skylit 概念 | 我们的实现 | 模块 | 里程碑 |
|---|---|---|---|
| King Node | `king_node()` — `\|net_gex\|` 最大 strike | `factors/gex.py` | **M1** |
| Floor / Ceiling | `strongest_floor()` / `strongest_ceiling()` | `factors/gex.py` | **M1** |
| Gatekeeper | spot 与 King 之间最大次级节点 | `factors/gex.py` | M2 |
| Node lifecycle (80/66/33%) | Fresh / Tested / Delivered 状态机 | `factors/nodes.py` | M6 (intraday) |
| Rate of Change | 相邻 snapshot exposure diff | `factors/nodes.py` | M2 (EoD 近似) |
| Trinity 三列对齐 | `trinity_score()` | `factors/trinity.py` | **M1** |
| GEX / VEX 切换 | `bs_vanna` + `compute_vex_profile` + Terminal toggle | `factors/gex.py` | **M2.5** ✅ |

### 3.2 SpotGamma

| SpotGamma 概念 | 我们的实现 | 里程碑 |
|---|---|---|
| Gamma Flip | `gamma_flip_level()` | Phase 1 ✅ |
| Call / Put Wall | `call_wall()` / `put_wall()` | Phase 1 ✅ |
| HIRO flow | 需 tick/options flow | M6 |
| TRACE 0DTE | `GexProfile(dte_max=1)` | **M1** |
| Expected Move | `expected_move_1sd()` | **M1** |
| Calibration | `calibration.py` + FlashAlpha | Phase 1 ✅ |

### 3.3 FlashAlpha

| FlashAlpha 字段 | 我们的实现 | 里程碑 |
|---|---|---|
| `regime.label` | `regime_from_net_gex()` | **M1** |
| `exposures.pct_of_total_gex` | `pct_dte1_of_total_gex` | **M1** |
| `pin_risk.pin_score` | `pin_score()` (EoD 近似) | **M1** |
| `expected_move.*` | `expected_move_1sd()` | **M1** |
| `should_trade_0dte()` | `should_trade_zdte()` | M2 |
| 五策略决策树 | `strategies/regime_selector.py` | M2 |
| zero-dte API | `flashalpha_gex.py` 扩展 | M5 (Growth tier) |

### 3.4 Vilkov 学术

| 概念 | 我们的实现 | 里程碑 |
|---|---|---|
| Multi-leg structures | IC / iron fly / spreads | Phase 3b ✅ |
| Conditional timing | feature filter + OOS | M3 |
| Tail risk diagnostics | max loss / CVaR on trades | M3 |
| 10:00 entry protocol | intraday bar | M6 |

---

## 4. 统一日频 Schema

输出路径：`data/processed/terminal/<symbol>.parquet`

| 列 | 类型 | 说明 |
|---|---|---|
| `date` | date | 快照日 |
| `symbol` | str | SPY / _SPX |
| `spot` | float | 标的现价 |
| `regime` | str | `long_gamma` / `short_gamma` / `undetermined` |
| `net_gex_all` | float | 全链 net GEX ($/ $1 move) |
| `net_gex_dte1` | float | dte≤1 cohort net GEX |
| `pct_gex_dte1` | float | dte1 占全链 GEX % |
| `flip_all` / `flip_dte1` | float | gamma flip |
| `call_wall_all` / `put_wall_all` | float | 全链 walls |
| `call_wall_dte1` / `put_wall_dte1` | float | 0DTE cohort walls |
| `king_all` / `king_dte1` | float | King node strike |
| `floor_dte1` / `ceiling_dte1` | float | spot 下/上最强节点 |
| `max_pain_dte1` | float | dte≤1 max pain |
| `pin_score` | float | 0–100 合成 pin 风险 |
| `expected_move_1sd` | float | 1σ 预期波动 ($) |
| `pcr_oi` | float | Put/Call OI 比 |
| `oi_conc_dte1` | float | top-3 strike OI 占比 |
| `spot_vs_king_pct` | float | spot 距 King % |
| `spot_vs_flip_pct` | float | spot 距 flip % |
| `net_vex_all` / `net_vex_dte1` | float | 全链 / dte≤1 net VEX ($ per 1% IV) |
| `pct_vex_dte1` | float | dte1 VEX 占全链 % |
| `king_vex_dte1` | float | VEX King strike |
| `vanna_interp_dte1` | str | `vol_down_dealers_buy` 等 |

Trinity 对齐（多标的）：`data/processed/trinity/<date>.parquet` 或合入 wide table

| 列 | 说明 |
|---|---|
| `date` | 交易日 |
| `trinity_score` | 0–100 |
| `trinity_direction` | `support` / `resistance` / `mixed` |
| `n_symbols` | 参与对齐的标的数 |
| `spy_king` / `spx_king` | 各标的 King（有则填） |

---

## 5. 里程碑与出口判据

### M1 — Positioning Analytics（当前，$0）

**交付**

- [x] 规划文档（本文）
- [x] `king_node`, `GexProfile`, dte1 cohort GEX
- [x] `pin_score`, `expected_move_1sd`
- [x] `trinity_score`, `regime_from_net_gex`
- [x] `scripts/build_terminal_history.py`
- [x] `scripts/build_trinity_history.py`
- [x] 单元测试
- [x] SPY terminal parquet 全量构建（**4515** 行 → `data/processed/terminal/SPY.parquet`）

**出口判据**

- SPY terminal parquet ≥ 4000 行，schema 稳定
- King / walls / flip 与 Phase 1 gex_history 方向一致
- pin_score 与 `\|next-day return\|` IC 可计算（不要求显著，先能跑）

### M2 — Regime + Strategy Selector（$0）

- [ ] `should_trade_zdte()` 门控
- [ ] `strategies/regime_selector.py` — FlashAlpha 五策略决策树
- [ ] `node_roc` — EoD 相邻日 exposure 变化率
- [ ] Gatekeeper 检测

**出口判据**：决策树对任意 `GexProfile` + `pin_score` 输出唯一 strategy label + structure hint

### M3 — Pin Play 回测（$0）→ 见 [`PIN_PLAY_SPEC.md`](./PIN_PLAY_SPEC.md)

- [x] Phase 3e：`analyze_pin_king_proximity.py` — pin 日 close 距 King（统计 PASS，n=147）
- [x] Phase 3f：`zdte_pin_fly_eod.py` — iron fly @ King（King>spot equal-weight；仍负）
- [ ] Tail diagnostics（max loss per trade, CVaR）
- [x] ~~Phase 3c conditional IC~~ — 已归档，非主线

**出口判据**：3e 吸附显著；3f fly@King 优于 fly@spot / 3d IC

### M4 — Terminal UI v0 ✅

- [x] `src/quant_lab/terminal/` — FastAPI + static UI
- [x] `scripts/run_terminal.py`
- [ ] QQQ / 实时 intraday 刷新（M5/M6）

**出口判据**

- [x] 本地打开即可浏览 SPY 历史 strike 热力图 + levels + 策略 hint
- [x] 不依赖外部 SaaS；读 `terminal/*.parquet` + raw chain

### M5 — Trinity UI + Live 校准（$0–$40/mo）

- [ ] 三列 SPXW / SPY / QQQ 热力图
- [ ] FlashAlpha zero-dte archive（Growth tier 或免费 GEX 校准）
- [ ] QQQ 数据抓取（扩展 Phase 0）

### M6 — Intraday（Phase 4，$40–79/mo）

- [ ] ThetaData / ORATS intraday 链
- [ ] Node lifecycle（Fresh/Tested/Delivered）
- [ ] HIRO 近似（volume-weighted delta flow）
- [ ] Vilkov 10:00 entry 真回测

**出口判据**：Phase 4 ROADMAP 门 — conditional net Sharpe > 0.8 + tail（见 PIN_PLAY_SPEC）

---

## 6. 策略决策树（M2 目标）

**完整规则**：[`PIN_PLAY_SPEC.md`](./PIN_PLAY_SPEC.md) §3、§6。

```
regime?
├── undetermined / should_trade=False → SIT OUT
├── positive_gamma
│   ├── pin_score > 70 & time_to_close < 2h → PIN PLAY (iron fly @ king_dte1)
│   ├── spot between put_wall and call_wall → GAMMA FADE / IC（非主线）
│   ├── theta window (intraday) → THETA HARVEST（Phase 4 可选）
│   └── iv_ratio > 1.0 post-event → VOL SPIKE FADE
└── negative_gamma
    ├── pct_gex_dte1 > 50 & flip break → BREAKOUT (debit spread)
    └── else → SIT OUT (do NOT sell premium)
```

Phase 3 教训：**负 gamma 日卖 IC 是反行业共识的**；决策树必须 hard-code 这一点。

---

## 7. 与 ROADMAP 的关系

| ROADMAP Phase | Ultimate Terminal 里程碑 |
|---|---|
| Phase 0 数据地基 | L1 |
| Phase 1 Positioning | L2 大部分 ✅ |
| Phase 2 回测引擎 | L4 研究层基础 ✅ |
| Phase 3 EoD 近似 | M3（3a–3d IC FAIL → **Pin Play 主线**） |
| Phase 4 付费 intraday | M6 — Pin Play 完整 spec |
| Phase 5–6 执行 | L6 |

**Phase 3 决策门未过 ≠ 停止 Ultimate Terminal**。  
M1–M3 在 EoD 上把「地图」和「决策树」建完；M6 再用 intraday 升级精度。

---

## 8. 当前行动项（M1 sprint）

1. 实现 `factors/gex.py` 扩展（King, GexProfile, dte1）
2. 实现 `factors/positioning.py` 扩展（pin_score, expected_move）
3. 新增 `factors/trinity.py`, `factors/regime.py`
4. `scripts/build_terminal_history.py` → `data/processed/terminal/SPY.parquet`
5. `scripts/build_trinity_history.py` → SPY + ^SPX 对齐历史
6. 测试 + 全量构建

---

## 9. 参考链接

- [Skylit Trinity Mode](https://www.skylit.ai/learn/trinity-mode)
- [Skylit King Nodes / Node Lifecycle](https://www.skylit.ai/learn/node-lifecycle)
- [FlashAlpha 0DTE API](https://flashalpha.com/docs/lab-api-zero-dte)
- [FlashAlpha 5 Strategies](https://flashalpha.com/articles/guide-to-0dte-trading-strategies-real-time-data)
- [SpotGamma 0DTE Guide](https://support.spotgamma.com/hc/en-us/articles/15298463039251)
- [Vilkov 0DTE Strategies (GitHub)](https://github.com/vilkovgr/0dte-strategies)

---

*Last updated: 2026-05-24 — M1 sprint started.*
