# Pin Play @ King — 策略规格书

**状态**：已批准 · **下一步实现目标**（Phase 3e → 3f → Phase 4）

**版本**：v1.0 · 2026-05-24

**关联**：[ROADMAP.md](../ROADMAP.md) · [ULTIMATE_TERMINAL.md](./ULTIMATE_TERMINAL.md) · [AGENTS.md](../AGENTS.md)

---

## 0. 为什么换方向

Phase 3a–3d 的 EoD **iron condor** 研究结论：

| 实验 | 结果 | 含义 |
|---|---|---|
| 3a directional flip | OOS Sharpe **-0.09** | 方向 edge 不存在 |
| 3b long-γ IC @ wall/EM | hit **74%**，Sharpe **-0.41** | regime 对、结构/时间错 |
| 3c conditional IC（filter） | 样本 **68 天** | 统计无意义，用户拒绝 sit-out |
| 3d daily IC + pin×regime sizing | OOS Sharpe **+0.40**，总 PnL 仍负 | 减损有效，非 live-ready |

**根因**：用户真实 workflow 是 **0DTE SPX iron butterfly @ King、午后 theta**；EoD 宽 IC 与行业共识及 practitioner 做法不对齐。

本 spec 取代 EoD IC 作为 **Phase 3 后续主线的唯一策略目标**。IC 相关代码保留作研究对照，不再作为主 alpha 优化对象。

---

## 1. 多源验证摘要

以下结论来自 **FlashAlpha、SpotGamma、Vilkov (SSRN)、Options Cafe 实盘、Fly on the Wall、0DTE Quant Lab** 的交叉对照（2026-05 调研）。

| 命题 | 共识 |
|---|---|
| 0DTE 卖 vol 首选结构 | **Iron butterfly**（短 ATM call+put + 对称 wing），优于宽 iron condor |
| 何时卖 premium | **Long gamma / 正 GEX** |
| Short gamma 日 | **不卖 vol**（debit 或 sit out） |
| Pin play 时机 | **pin 高 + long γ**，多在 **午后、距收盘 ≤2h** |
| 中心 strike | **Magnet / King / 高 GEX strike**（非任意 ATM） |
| 无条件每日交易 | **弱**；需 **conditional timing** |
| 学术基准 | Vilkov conditional OOS：iron butterfly net Sharpe **~0.82**；组合 **1.0–1.3** |

### 参考文献

| 来源 | URL | 用途 |
|---|---|---|
| FlashAlpha 五策略 | https://flashalpha.com/articles/guide-to-0dte-trading-strategies-real-time-data | Pin play 条件、magnet、午后窗口 |
| FlashAlpha 0dte analytics | https://github.com/FlashAlpha-lab/0dte-options-analytics | pin_score、magnet_strike API 语义 |
| SpotGamma 0DTE 说明 | https://support.spotgamma.com/hc/en-us/articles/15298463039251 | Regime、wall、containment |
| SpotGamma 风控 | https://spotgamma.com/0dte-risk-management-guide/ | 2% 单笔、14:00 退出 |
| Vilkov 0DTE Trading Rules | https://ssrn.com/abstract=4641356 | Conditional OOS、10:00 信息集、tail risk |
| Vilkov replication | https://github.com/vilkovgr/0dte-strategies | PnL 尺度 sanity check（可选） |
| Options Cafe 实盘 | https://options.cafe/blog/zero-dte-spx-iron-butterfly-strategy/ | 30pt wing、credit 过滤、2× stop |
| Fly on the Wall | https://flyonthewall.ai/iron-butterfly-options-strategy/ | Body @ high-GEX、50–75% 止盈 |
| 0DTE Quant Lab | https://0dteoption.com/research/delta-neutral-0dte-strategy/ | Iron fly 为核心、delta 带 |

---

## 2. 两种蝴蝶策略（勿混用）

公开资料存在两条独立产品线；**本项目优先 B**。

| | **A. 上午 Theta Fly** | **B. 午后 Pin Play**（主目标） |
|---|---|---|
| 时间 | 9:45–10:30 ET | **13:00–14:00 ET** 进场 |
| 中心 | 当前 spot（取整 5 点） | **`king_dte1` / magnet** |
| 触发 | long γ + 开盘稳定 + credit 够 | **pin_score ≥ 70 + long γ** |
| 目标 | 50% credit / 11:00 前出 | pin 到 magnet、午后 theta |
| 代表 | Options Cafe、Vilkov 10:00 基准 | FlashAlpha Strategy 2 |
| quant_lab 阶段 | Phase 4 可选第二条腿 | **Phase 3e/3f/4 主线** |

---

## 3. Pin Play @ King — 完整规则（Live 目标）

### 3.1 硬门槛

以下用于 **仓位分档**；默认哲学：**每日参与，用 sizing 表达 conviction，不用 filter 把样本砍到几十天**。

| # | 条件 | 不满足时 |
|---|---|---|
| 1 | `terminal_regime == long_gamma` | 仓位 **0×**（不卖 vol） |
| 2 | `pin_score >= 70` | 仓位 **0.25×**（mid pin 档） |
| 3 | `pct_gex_dte1 >= 30` | 仓位 **0.5×** |
| 4 | spot 在 put_wall 与 call_wall 之间，或 `\|spot - king\| <= 0.5 × expected_move_1sd` | 仓位 **0.25×** |
| 5 | 非 FOMC / CPI / 重大宏观日（日历过滤） | 仓位 **0×** 或 **0.25×**（实现时二选一，默认 0×） |

**Short gamma**：不做 pin play 卖 vol → **0×**。

### 3.2 结构（SPX / SPXW）

四腿 **iron butterfly**（credit 构造；与同行权价 long debit fly PnL 等价）：

```
Short 1× Call @ K
Short 1× Put  @ K          ← K = king_dte1
Long  1× Call @ K + W
Long  1× Put  @ K - W

W = max(15, min(30, round(expected_move_1sd)))   # SPX 点；SPY 回测按 1/10 缩放
```

- **King 缺失**：fallback `max_pain_dte1`；仍缺失则跳过该 leg（记 fill reason，不 silent pass）。
- SPX：**欧式、现金结算**；SPY 为 Phase 3 免费代理，notional 约 10:1。

### 3.3 时间与执行（Phase 4 intraday）

| 时刻 (ET) | 动作 |
|---|---|
| 09:00–09:45 | 只读 map：regime、King、pin、EM、walls |
| **13:00–14:00** | 满足 3.1 → **进场**（FlashAlpha：`time_to_close < 2h`） |
| 持仓中 | 监控 spot vs King、gamma flip；破 **EM 或 flip** → 价位止损 |
| — | **50% max profit** → 止盈 |
| **14:00** | thesis 未兑现 → 平仓（SpotGamma） |
| **15:30** | 强制全平（Power Hour gamma 加速） |

**Credit 质量过滤**（Options Cafe）：credit ≥ **0.5 × wing width**（指数点），否则 **0.25×** 或不做。

### 3.4 风控

| 规则 | 参数 | 来源 |
|---|---|---|
| 单笔最大风险 | ≤ **2%** 账户 | SpotGamma |
| 止损 | **2× credit** 或 **破 EM/flip**（先触发者） | Options Cafe + SpotGamma |
| 日损上限 | **-3%** 账户停手 | 常见 prop 规则 |
| 定价 | **禁止**用 yfinance 0DTE IV 定 wing | 项目实测 |

### 3.5 仓位分档（默认，可 walk-forward 调参）

在硬门槛通过的前提下，**pin × regime** 乘法 sizing（与 Phase 3d 哲学一致）：

**Pin 档**

| pin_score | 倍数 |
|---|---|
| ≥ 70 | **1.0×** |
| 50–69 | **0.5×** |
| < 50 | **0.25×** |

**Regime 档**

| regime | 倍数 |
|---|---|
| long_gamma | **1.0×** |
| undetermined | **0.75×** |
| short_gamma | **0×**（不卖 vol） |

最终仓位 = base_contracts × pin_mult × regime_mult，再 cap 单笔 2% risk。

---

## 4. 实现路线图（quant_lab）

这是 **当前仓库的下一步**，按顺序执行；**未完成上一子阶段出口判据，不启动下一子阶段**。

```
Phase 3e  King 吸附统计（$0，无新策略代码）
   │
   ▼  pin≥70 日 close 距 King 显著小于对照组
Phase 3f  EoD iron fly @ King 粗回测
   │
   ▼  fly@King 优于 fly@spot；样本量足够
Phase 4   intraday 完整 spec（13:00 进、50% 出、spread+fee）
   │
   ▼  conditional OOS net Sharpe > 0.8（Vilkov iron fly 基准）
Phase 5   paper trading
```

### Phase 3e — King 吸附验证（下一步 **立即开始**）

**目标**：用现有 18y SPY EoD + terminal，验证 **pin 因子是否预测 close 靠近 King**（方向性证据，非 PnL）。

**Deliverables**

- [x] `scripts/analyze_pin_king_proximity.py`
- [x] `src/quant_lab/factors/pin_king_proximity.py`
- [x] 输出：`data/processed/pin_play/SPY_king_proximity_{same_day,next_session}.parquet`
- [x] 分层：pin≥70 vs pin<50 vs long_γ；指标：`|close - king| / spot`、`within_EM`

**出口判据**

- pin≥70 + long_γ 日，close 距 King 的 median **显著小于** pin<50 日（IC 或 Mann-Whitney，p < 0.05）
- 样本：pin≥70 日 **≥ 200**（避免 3c 式小样本陷阱）

**2026-05-24 SPY 首次结果**

| 模式 | pin≥70+long_γ n | median \|dist\| high | median \|dist\| low | Mann-Whitney p | IC(pin, -dist) |
|---|---:|---:|---:|---:|---:|
| same_day | 147 | 0.132% | 1.122% | 3.5e-62 | +0.77 |
| next_session | 147 | 0.336% | 1.415% | 3.3e-28 | +0.35 |

- **统计门：PASS**（high-pin 显著更靠近 King）
- **样本门：FAIL**（147 < 200；dte≤1 链有效日仅 ~1542，2010 年代稀疏）
- **决策**：统计证据足够进 **Phase 3f**；3f 回测需 daily participation 扩大有效样本，并在报告中继续跟踪 n

**不做**：期权结构 PnL、intraday 进场。

### Phase 3f — EoD iron fly @ King 粗回测

**目标**：在 EoD 近似下，比较 **iron fly @ King** vs **@ spot** vs 旧 **IC**，证明 **结构选择** 比继续调 IC 参数更重要。

**Deliverables**

- [x] `src/quant_lab/strategies/zdte_pin_fly_eod.py`
- [x] `scripts/run_zdte_pin_fly_eod_backtest.py`
- [x] 复用 Phase 3d 的 daily participation + pin×regime sizing（short_gamma **0×**）
- [x] 5 个手算 / 链上单元测试（`tests/test_zdte_pin_fly_eod.py`）

**2026-05-25 SPY 首次结果**

| 书 | 笔数 | equal-weight total PnL | sized OOS Sharpe |
|---|---:|---:|---:|
| fly@King | 1478 | **-$11,516** | +0.23 |
| fly@spot | 1476 | -$12,408 | +0.83 |
| IC (3d) | 1406 | -$10,338 | +0.40 |

- **King vs spot（equal-weight）**：**PASS**（King 少亏 $892）
- **King vs IC**：**FAIL**（King 多亏 $1,178）
- **OOS n=613**：**PASS**
- **决策**：pin 吸附成立，但 EoD 卖 fly 仍无正期望 → **Phase 4 intraday** 是下一决策点

**EoD 近似限制（必须写在 docstring 与报告里）**

- 进场：前日 EoD 信号 → 次日 **close intrinsic** 结算（proxy 午后 pin）
- **不能**测：theta 路径、50% 止盈、13:00 进场、credit 过滤
-  wing 宽度用 `expected_move_1sd` 固定规则，不用链上 mid（除非 Phase 4）

**出口判据**

- fly @ King 全样本 PnL / Sharpe **优于** fly @ spot（同 wing、同 sizing）
- fly @ King **优于** 3d daily IC（同参与哲学）—— 若仍全负，记录 honestly，带 **pin 吸附统计** 进 Phase 4 决策
- OOS 段样本 **≥ 100 笔**（禁止 3c 式 34 笔 Sharpe 叙事）

### Phase 4 — Intraday 完整 Pin Play

**前置**：Phase 3f 完成且 King 吸附有统计证据；**第一次花钱买 intraday 数据**。

**Deliverables**

- [ ] ORATS / Polygon `DataSource` intraday
- [ ] `zdte_pin_fly_intraday.py`：13:00 entry、50% profit、14:00/15:30 exit、2× credit stop
- [ ] Vilkov 式 conditional OOS 协议（predictors ≤ 10:00 或 13:00 信息集，按实验设计）
- [ ] Tail 报告：worst day、max DD、CVaR（不能只报 Sharpe）

**出口判据**

- Conditional OOS **net Sharpe > 0.8**（iron butterfly，含 spread + fee）— 对齐 Vilkov Table 基准
- Worst-day / tail 可接受（团队定义阈值前，至少报告并人工 sign-off）

---

## 5. 明确不做的事

1. **Short gamma 卖 premium** — 与 SpotGamma / FlashAlpha / 本项目 IC 数据一致
2. **无条件每日同一结构** — Vilkov：无条件弱
3. **继续把 EoD 宽 IC 当主策略优化** — 仅保留对照实验
4. **Filter 式 sit-out 把样本砍到 <100 天** — 用户已拒绝
5. **ML 调参** — walk-forward grid + Pareto（Phase 3d 已验证路径）
6. **用 yfinance 0DTE IV** 定 wing 或 filter
7. **无 tail 报告只报 Sharpe** — Options Cafe 77% 胜率仍可能两年 flat

---

## 6. Terminal / 策略选择器对齐

Ultimate Terminal 的策略 hint 应对齐本 spec：

```
long_gamma AND pin_score >= 70 AND time_to_close < 2h
  → PIN PLAY: iron fly @ king_dte1, wing ≈ EM, 50% profit / 14:00 exit

short_gamma
  → NO SELL VOL; directional debit or sit out
```

实现位置（待做）：`strategies/regime_selector.py`（M2/M3），读取 `data/processed/terminal/*.parquet`。

---

## 7. 模块与文件规划

| 路径 | 职责 |
|---|---|
| `docs/PIN_PLAY_SPEC.md` | 本文档 — 唯一策略规格来源 |
| `scripts/analyze_pin_king_proximity.py` | Phase 3e |
| `strategies/zdte_pin_fly_eod.py` | Phase 3f 模拟器 |
| `scripts/run_zdte_pin_fly_eod_backtest.py` | Phase 3f CLI |
| `strategies/zdte_pin_fly_intraday.py` | Phase 4 |
| `strategies/regime_selector.py` | Terminal 决策树 |

**废弃为主线的代码**（保留对照，不删）：

- `strategies/zdte_ic_eod.py` / `zdte_ic_conditional.py` 的 **参数优化**
- `scripts/sweep_m3_ic_conditional.py` 作为主 workflow

---

## 8. 决策门（Pin Play 专用）

| 阶段 | 通过 | 失败 |
|---|---|---|
| 3e | pin 日 King 吸附显著 | 回 Phase 1 查 pin_score / King 定义 |
| 3f | fly@King > fly@spot；样本够 | 带 3e 证据进 Phase 4，或收窄 spec |
| 4 | OOS net SR > 0.8 + tail OK | 试上午 Theta Fly（策略 A）或放弃卖 vol |
| 5 | Paper ≈ backtest | 查 execution bias |

---

## 9. 变更记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-05-24 | v1.0 | 多源调研后首版；定为 Phase 3 后续主线 |
| 2026-05-24 | v1.1 | Phase 3e 实现；SPY 统计 PASS（n=147），样本门 FAIL |
| 2026-05-25 | v1.2 | Phase 3f EoD fly@King 回测；King>spot，仍负 vs IC |
