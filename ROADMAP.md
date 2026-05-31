# Roadmap

**最终目标**：在 SPX 0DTE 期权上跑出有正期望、可执行、风险可控的策略。

研究路径不是一步到位。下面按阶段分解，每阶段有清晰的**产出**和**进入下一阶段的判据**。
不达成判据**不要**提前进入下一阶段——这是这个项目最容易踩的坑。

---

## 战略观察：为什么 EoD 研究是 0DTE 策略的基础

0DTE 的 alpha 主要来自三类来源：

1. **Dealer positioning 的非对称性** — dealer 被迫做流动性提供方，他们的 gamma / delta 仓位通过 OI 是可推断的。fade 他们不舒服的位置 = 散户的边缘。
2. **理论 vs 实际波动率差** — 0DTE 的 IV 在白天有结构性的均值回归 / 发散模式。
3. **流动性事件触发** — 开盘 30 分钟 / FOMC / CPI / 收盘前 30 分钟的特殊行为。

这三类信号**都需要先有 dealer 位置的日级别画像**，才能在 intraday 做决策。
**EoD 快照不是凑合，是 0DTE 策略的真基础。** 这是路线图把 positioning 因子提前到 Phase 1 的原因。

---

## 阶段图

```
[Phase 0] 数据地基（现在）
   │
   ▼  ≥ 18 年 SPY EoD 历史 + 持续 ^SPX 增量 + 质量全绿
[Phase 1] Positioning 因子（GEX / max pain / put-call）
   │
   ▼  至少 1 个信号能复现 SpotGamma / VolHub 公开方向
[Phase 2] 回测引擎 + 非期权基线
   │
   ▼  baseline Sharpe / MaxDD 跟参考实现对得上
[Phase 3] EoD 近似 0DTE 模拟
   │      3a–3d IC 研究 FAIL → 主线 pivot
   ▼  3e King 吸附 + 3f fly@King（见 docs/PIN_PLAY_SPEC.md）
[Phase 4] 付费 intraday Pin Play 真回测     ← 第一次花钱
   │
   ▼  Net Sharpe > 1.0 after fees + slippage
[Phase 5] Paper trading (tastytrade)
   │
   ▼  Paper PnL ≈ Backtest PnL（tracking error 内）
[Phase 6] Live small size
```

每个箭头是**决策门**，过不了就停在原地排错或回退。

---

## Phase 0：数据地基（现在）

**目标**：拿到一份足以做 positioning 研究的 EoD 历史 + 持续的 `^SPX` 增量。

**关键转折（2026-05）**：放弃"等 4 周 yfinance 攒数据"的慢路径，改用
[Philipp Dubach 开源 SPY 期权数据集](https://github.com/lambdaclass/options_portfolio_backtester/releases/tag/data-v1)
（MIT，2008-2025 共 18 年 EoD，**预先算好 delta/gamma/theta/vega/rho**），把
SPY 当作 SPX 0DTE 研究的**免费历史代理**。这条路径让 Phase 1 立刻可启动，
不必等四周。`^SPX` 仍然每天通过 yfinance 抓增量，用于校准 SPX vs SPY 差异。

**Deliverables**

- [x] `^SPX` 主标的可抓（已确认，2448 行 × 6 expiries → max-expiries=12 时 4679 行）
- [x] `SPY` 对照（已抓）
- [x] 每日抓取脚本 + 质量检查（已有 CLI）
- [x] 链表增加 `dte` 列（dtype `int64`，作为 `REQUIRED_OPTION_COLUMNS` 一部分）
- [x] 质量检查新增 `OPT_IV_UNRELIABLE_AT_EXPIRY`：dte ≤ 1 且 IV 在 [5%, 300%] 之外标 warn（实测捕获 ^SPX 44 行、SPY 33 行）
- [x] 跨日 snapshot 完整性检查 `check_snapshot_continuity`：`CONT_MISSING_DAY` / `CONT_FIELD_DRIFT` / `CONT_OI_JUMP` / `CONT_UNSORTED`
- [x] `scripts/daily_snapshot.ps1`：一键抓 `^SPX` + `SPY` + 复检（含跨日）
- [x] `scripts/install_daily_task.ps1`：注册 Windows 任务计划（用户在本地执行一次即可，16:35 本地时间）
- [x] `src/quant_lab/data/philippdubach_source.py`：把 18 年 SPY parquet 转成 `OptionChainSnapshot`（含 dte / Greeks，按日切片）
- [x] `scripts/import_philippdubach_history.py`：CLI 一键导入，默认 2022-01-01 起（SPY daily 期权全覆盖时代），`--full` 可拉全 18 年
- [x] 13 个 mock 测试覆盖 source 模块（不打网、用合成 parquet）
- [ ] **owner 自己运行** `scripts/install_daily_task.ps1` 注册任务计划（持续抓 ^SPX 增量）
- [x] Philipp Dubach **2008–2021** 全量导入（4515 天 SPY 链）

**出口判据**

- `data/raw/options/SPY/<date>/chain.parquet` 至少 250 个交易日（≈ 1 年）落盘
- `check_snapshot_continuity` 跨日检查 0 error
- 单日 `check_option_chain` 没有 error 级问题（warn 可接受，0DTE IV warn 是已知现象）

**这阶段不要做**：任何 GEX / 因子 / 策略 / 回测代码。

---

## Phase 1：Positioning 因子（≈ 2–3 周）

**前置**：Phase 0 出口判据满足。

**目标**：用 SPY EoD 历史（Philipp Dubach 数据）算出每日 dealer positioning 画像，
并用 `^SPX` 增量数据交叉验证 SPY → SPX 的可迁移性。

**Deliverables**

- [x] `factors/positioning.py`（max pain / PCR / OI 集中度 / oi_by_strike）
- [x] `factors/gex.py`（BS gamma + 聚合 + flip；dataset gamma cross-check median rel diff **0.67%**）
- [x] `scripts/build_gex_history.py` + `scripts/plot_gex_history.py`（**4515** 天 GEX 时间序列 + regime 图）
- [x] `scripts/analyze_gex_ic.py` + `scripts/analyze_factor_ic.py`（IC：net_gex → 次日 \|return\| = **-0.32** @ 18y）
- [x] `scripts/build_positioning_history.py`（max pain / PCR / OI 集中度历史）
- [x] `scripts/daily_positioning.py`（每日 positioning 报告）
- [x] `scripts/calibrate_spotgamma.py` + `config/spotgamma_reference.yaml`（公开叙事日 **4/4 PASS**；精确量级待 Founder Note 填入）
- [x] `factors/spx_spy_calibration.py` + `scripts/calibrate_spx_spy.py`（理论 proxy k≈(S_spx/S_spy)²；yfinance ^SPX OI 稀疏时自动回退）

**出口判据**

- GEX 计算结果与 SpotGamma / VolHub 某一天的公开图**方向一致**，量级在 ±30% 内
- 我们能稳定回答：「今天 SPX 是 long gamma 还是 short gamma regime」
- 我们能定量说明：「SPY GEX 信号 → SPX 决策」的转换函数（哪怕只是常数倍率）

**这阶段不要做**：不写策略代码，只产出因子和可视化。

---

## Phase 2：回测引擎 + 非期权基线（≈ 2 周）

**前置**：Phase 1 出口判据满足。

**目标**：写最小但正确的回测器，用一个非期权策略证明它不出 bug。

**Deliverables**

- [x] `backtest/engine.py`（signal @ t → return @ t+1，含 slippage / commission）
- [x] `strategies/baseline_zscore.py`：SPY 5 日 Z-score 均值回归
- [x] `scripts/run_baseline_backtest.py` 对账 CLI

**出口判据**

- baseline 的 Sharpe / MaxDD 跟外部参考实现（QuantConnect 教材或类似公开例子）数字对得上
- 同样输入给出同样输出（无随机种子依赖）

**这阶段不要做**：不要碰 0DTE。这阶段是**工具**，不是**策略**。

---

## Phase 3：EoD 近似 0DTE 模拟（≈ 2–3 周）

**前置**：Phase 2 出口判据满足。

**目标**：用现有 EoD 数据**粗略**回答：「如果按 Phase 1 信号在 9:30 开 0DTE，持有到收盘，历史上赚不赚」。

**重要警告**：这是**近似**，不是真回测。我们没有 intraday 链，所以：

- 入场价：用前一天 EoD close 的 ATM 0DTE 报价做 proxy（已经粗糙）
- 持有期 PnL：close-to-close 价格变化 + 用 BS76 重估剩余时间价值
- 估计误差可能 ±50%

这阶段的产出是**方向性判断**，不是策略 PnL。

**Deliverables**

- [x] `strategies/zdte_directional_eod.py`：Phase 1 信号 → ATM dte=1 call/put，hold to close
- [x] `scripts/run_zdte_eod_backtest.py`：模拟器 + IS/OOS 报告 + direction IC
- [x] `backtest/bs76.py`：EoD 定价 / intrinsic 退出

**首次 SPY 结果（默认：short_gamma + spot_vs_flip）**

- 824 笔交易（2008–2026），全样本 Sharpe **0.31**，hit **33%**
- OOS Sharpe **-0.09**，hit **28%** → **决策门 FAIL**（不进 Phase 4）
- direction IC vs 当日收益 **-0.05**（≈ 无方向 edge，符合 Phase 1 IC 结论）

**出口判据（决策门）**

- **通过**：OOS Sharpe > 0.5，hit rate > 52% → 进 Phase 4，开始花钱
- **失败**：方向没意义 → 回 Phase 1 调因子或换信号假设
- **绝对不要在这一步省略，直接跳到 Phase 4 买数据**

### Phase 3b：行业对齐的 regime 策略（2026-05）

Phase 3a（directional flip）FAIL 后，按 FlashAlpha / SpotGamma / Vilkov 共识改测
**long gamma 卖 premium**，而非 flip 方向：

- [x] `strategies/zdte_ic_eod.py`：EoD 信号 → **short iron condor**（dte=1 代理 0DTE）
- [x] `scripts/run_zdte_ic_eod_backtest.py`：IS/OOS + net_gex vs |return| IC
- [x] 跑全样本并记录结果（见脚本输出 / `data/processed/zdte_ic_eod/`）

**首次 SPY 结果（long_gamma_only + wall/EM IC）**

- 654 笔（2009–2025），hit **74%**，但全样本 Sharpe **-0.41**（尾部亏损拖累）
- OOS Sharpe **0.20**（优于 directional 的 -0.09，仍 **FAIL** 决策门）
- net_gex vs 当日 |return| IC **-0.25**（long-gamma 日确实更低波动）
- 结论：regime 假设方向对（高 hit + vol IC），EoD 近似 IC 仍不足以过 Phase 3 门 → Phase 4 前需 **conditional timing**（Vilkov 路线）或 intraday

**设计要点**：仅 `long_gamma` 日卖 IC；short strikes 优先 call/put wall，否则
`spot ± 1σ expected move`。仍是 EoD 近似，不能替代 Phase 4 intraday。

### Phase 3c–3d：Conditional / Daily IC 研究（2026-05，已归档）

- [x] `strategies/zdte_ic_conditional.py` + M3 filter / pin×regime sizing sweep
- [x] `scripts/run_zdte_ic_daily_backtest.py` — daily participation（1406 笔）
- **结论**：regime + pin sizing **减损**（OOS Sharpe +0.40），但总 PnL 仍负；filter 式 sit-out 样本过小。
- **决策**：EoD 宽 IC **不再作为主策略优化对象**；代码保留作对照。

### Phase 3e–3f：Pin Play @ King（**下一步 · 当前主线**）

**规格书**：[`docs/PIN_PLAY_SPEC.md`](./docs/PIN_PLAY_SPEC.md) — 多源验证后的 iron butterfly @ King 策略，对齐 FlashAlpha / SpotGamma / Vilkov / practitioner 共识。

**目标**：从「EoD 宽 IC」 pivot 到 **午后 pin play @ magnet** 的可验证路径；先 $0 证明 pin→King 吸附，再 EoD 粗测 fly@King vs fly@spot。

**Phase 3e — King 吸附统计（2026-05-24 完成）**

- [x] `src/quant_lab/factors/pin_king_proximity.py`
- [x] `scripts/analyze_pin_king_proximity.py`
- [x] pin≥70 + long_γ 日 close 距 King **显著小于** pin<50（p≪0.05；n=147，样本门未达 200）
- [ ] → 进 **Phase 3f**

**Phase 3f — EoD iron fly @ King（2026-05-25 完成）**

- [x] `strategies/zdte_pin_fly_eod.py` + `run_zdte_pin_fly_eod_backtest.py`
- [x] fly@King equal-weight 优于 fly@spot（-$11.5k vs -$12.4k）；仍负，未优于 IC
- [ ] → Phase 4 intraday

**Phase 3 决策门（更新）**

- 旧门（OOS IC Sharpe > 0.5）：**FAIL**，且结构不对 — 不再作为唯一出口
- 新门：3e 吸附显著 **且** 3f fly@King 相对改进 → 才进 Phase 4 intraday 完整 Pin Play
- Phase 4 门：conditional OOS net Sharpe **> 0.8**（Vilkov iron butterfly 基准）+ tail 报告

---

## Ultimate Terminal（终局产品）

详见 [`docs/ULTIMATE_TERMINAL.md`](./docs/ULTIMATE_TERMINAL.md) — 合成 Skylit / SpotGamma / FlashAlpha / Vilkov 能力。

**M1（2026-05-24，进行中）**

- [x] 规划文档 + 统一 terminal schema
- [x] `factors/gex.py`：`king_node`, `GexProfile`, dte1 cohort
- [x] `factors/positioning.py`：`pin_score`, `expected_move_1sd`
- [x] `factors/trinity.py`, `factors/regime.py`
- [x] `scripts/build_terminal_history.py`, `scripts/build_trinity_history.py`
- [x] SPY `data/processed/terminal/SPY.parquet` 全量构建（4515 行）

### M4 — Terminal UI v0（2026-05-24）

- [x] 本地 web：`scripts/run_terminal.py` → http://127.0.0.1:8765
- [x] Skylit 式 Trinity 三列 strike GEX 热力图
- [x] SpotGamma 式 Key Levels 侧栏（flip / walls / King / EM）
- [x] FlashAlpha 式 regime gate + 策略建议
- [ ] QQQ / SPX 面板数据（需扩展 daily snapshot）

**启动**

```bash
.venv\Scripts\python.exe scripts/run_terminal.py --open-browser
```

数据仍由 `build_terminal_history.py` 在后台维护；UI 只读 parquet + 链，无需手敲 build。

---

## Phase 4：付费 intraday 数据 + 真回测（≈ 1–2 月）

**前置**：Phase **3e + 3f** 完成（见 [`docs/PIN_PLAY_SPEC.md`](./docs/PIN_PLAY_SPEC.md)）。**这是项目第一次花钱**。

**目标**：实现 **Pin Play @ King** 完整 intraday spec（13:00 进场、50% 止盈、14:00/15:30 退出、spread+fee），把 EoD 粗测升级成真回测。

**供应商选项**

| 供应商 | 月费 | SPX 历史深度 | 备注 |
|---|---|---|---|
| ORATS | ~$79/mo | 2007 起 EoD + intraday Greeks | 散户友好首选 |
| Polygon Options Advanced | $79/mo | 2 年 intraday | API 文档好 |
| CBOE DataShop | 一次性，数百到数千 | 完整 OPRA tick | 量大，研究院级 |

倾向 **ORATS** 起步。

**Deliverables**

- `data/orats_source.py`（实现 `DataSource` 协议）
- 历史数据回填到 `data/raw/options/^SPX/<date>/intraday/`
- `backtest/engine.py` 扩展支持 intraday bar
- 真实回测包含：
  - SPX 期权 fee 模型（CBOE：~$0.65/contract + exchange fee）
  - bid-ask 滑点（保守取 mid → cross 半个 spread）

**出口判据**

- Conditional OOS **net** Sharpe **> 0.8**（iron butterfly，对齐 Vilkov 基准；含 spread + fee）
- Tail 指标（worst day、max DD）报告并 sign-off
- 低于 0.8 不值得做：执行风险 + 心理成本会吃掉残值

---

## Phase 5：Paper trading（tastytrade，≈ 1–2 月）

**前置**：Phase 4 通过。

**目标**：tastytrade paper account 上跑 1–2 个月，验证 backtest ≈ live。

**为什么 tastytrade 不是 IBKR**：tastytrade API 是 REST，10 倍易用度；IBKR 留到 live 阶段，那时候为了执行质量值得付学习曲线。

**Deliverables**

- `broker/base.py`：`Broker` Protocol（独立于 `DataSource`，不要塞一起）
- `broker/tastytrade.py`：paper 实现（place / cancel / positions / fills）
- daily cron：signal → place → record
- 对账系统：paper PnL vs backtest PnL，差异分解（slippage、timing、fee）

**出口判据**

- Paper PnL 在 1 sigma 内匹配 backtest
- 任何 > 1 sigma 的 bias 都能解释

---

## Phase 6：Live small size

独立决策。第一笔真钱满足：

- 用刚通过 Phase 5 的策略
- 单笔最大风险 < 总资金 1%
- 总 0DTE 仓位风险敞口 < 总资金 5%
- 有手动 kill switch

---

## 决策门汇总

| Phase | 通过判据 | 失败回退 |
|---|---|---|
| 0 | 4 周快照干净 | 修脚本 / 换源 |
| 1 | 复现 SpotGamma 方向 | 检查 dealer sign 假设 |
| 2 | 基线 Sharpe 对得上 | 排查回测 bug |
| 3e | pin 日 King 吸附显著 | 回 Phase 1 查 pin/King |
| 3f | fly@King > fly@spot | 带 3e 证据进 4 或收窄 spec |
| 4 | Conditional net SR > 0.8 + tail OK | 试 Theta Fly 或放弃卖 vol |
| 5 | Paper ≈ Backtest | 找系统性 bias |

---

## 不在路线图里的事

明确说"现在不做"，避免被引诱：

- ❌ ML / 深度学习因子：等 Phase 4 之后再考虑，先做透 linear factor
- ❌ 多标的扩展（QQQ, IWM 0DTE）：先把 SPX 做透
- ❌ 高频 / 做市：跟散户 0DTE 完全不同范式，不要混
- ❌ Crypto 期权：分散精力，pass
- ❌ 自建 OPRA feed：钱不够，没必要
