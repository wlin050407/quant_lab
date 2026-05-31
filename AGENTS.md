# AGENTS.md

给以后接手这个仓库的 AI 助手（Cursor / Claude / Codex）的规则。**人类阅读也适用。**

## 项目目标

**在 SPX 0DTE 期权上跑出有正期望、可执行、风险可控的策略。**

这不是「先做个量化平台再说」——所有架构决策都为这个目标服务。
非这个方向的"通用化"建议（比如「我们也支持加密货币吧」）默认拒绝。

## 项目阶段

- **当前**：Phase 0 数据地基。
- 阶段路线图、出口判据、决策门见 `ROADMAP.md`。
- **没达成当前阶段出口判据**之前，**不要**碰下一阶段的代码。
  这是这个项目最容易踩的坑，比任何技术 bug 都贵。

## 关于"为什么 GEX / positioning 不是远期任务"

旧版本路线图把 GEX 放在 P3。现在它是 Phase 1 的核心产出。原因：
**0DTE 的 alpha 主要来自 dealer positioning 的非对称，而 dealer 位置是 EoD 决定的**。
没有 positioning 画像，0DTE 就是赌运气。

所以工作顺序是：**先数据地基（Phase 0） → 再 positioning 因子（Phase 1）**，
不是先回测引擎。

## 编码约定

1. **类型注解必加**。所有公开函数必须有返回类型。
2. **路径用 `pathlib.Path`**，绝不拼字符串。
3. **配置走 `quant_lab.config.settings`**，不要在脚本里写死路径。
4. **新依赖必须写进 `requirements.txt`** 并标注用途。
5. **不要随手 `pd.read_parquet(...)`**，统一走 `quant_lab.data.storage`。
6. **不要新增第二种数据存储格式**（如 csv / pickle / sqlite）。Parquet 已经够用，多格式只会让管线碎掉。
7. **错误处理优先用显式抛异常**，不要 `except Exception: pass`。

## 模块边界

| 模块 | 职责 | 禁止 |
|---|---|---|
| `data/` | 抓取 + 落盘 | 任何因子计算 |
| `quality/` | 只读检查 | 修改数据 |
| `factors/` | 干净数据 → 因子张量 | 抓网络、写盘 |
| `backtest/` | 因子 + 价格 → PnL / 指标 | 调网络、动数据源 |
| `strategies/`（Phase 2 起） | 因子组合 → 仓位 series | 写盘、抓网络 |
| `broker/`（Phase 5 起） | 仓位 series → 真实下单 | 跟 `DataSource` 共享代码 |

**特别强调**：`broker/` 和 `data/` 是**两个独立协议**。
不要把研究用的 `DataSource` 拓展成「也能下单」。
研究和执行的范式差太多（pull vs push、状态机、错误处理），硬合并必废。

## 数据源约定

- 默认：yfinance（免费、有延迟、`^SPX` 能拿链、`^GSPC` 拿不到链）。
- **历史 SPY**：Philipp Dubach 数据集（MIT，2008-2025 共 18 年 EoD，**预先算好 Greeks**），
  通过 `src/quant_lab/data/philippdubach_source.py` 转成 `OptionChainSnapshot`，
  落到和 yfinance 一样的 `data/raw/options/SPY/<date>/chain.parquet` 布局。
  这不是实时 `DataSource`，是**一次性历史导入器**。
- **SPY 作为 SPX 0DTE 研究的免费代理**：notional 10:1，但 dealer positioning 形态高度
  相关。Phase 1 的 GEX 信号先在 SPY 18 年历史上跑，`^SPX` 增量用于校准。
- Phase 4 起接入付费源（ORATS / Polygon），用 `DataSource` 协议，**不**改上层代码。
- **yfinance 的 0DTE IV 不可信**（已实测）。因子里用 IV 之前先过滤 `dte > 1`。
- **Philipp Dubach 数据集自带的 Greeks（delta/gamma/theta/vega/rho）** 可以做 Phase 1
  的 BS76 实现的 sanity reference（实测 0 nulls，2024-01-15 的 MLK Day 2 行明显是合成
  placeholder，已被 `MIN_ROWS_PER_SNAPSHOT=50` 过滤）。

## 测试

- 任何新增数据源实现 → 必须有 mock 测试（不打网络）。
- 任何因子函数 → 必须有 1–2 个手算样例做断言。
- 任何回测组件 → 必须有「常数信号 + 常数收益 = 已知 PnL」的回归测试。

## 关于 0DTE positioning 因子（Phase 1 实现指南）

`src/quant_lab/factors/gex.py` 当前是占位。被要求实现时按以下顺序：

1. **先单合约 gamma 封闭解**：SPX 是欧式、现金结算、指数，用 **BS76（Black-76）**，不要用普通 BS。
2. **用 Philipp Dubach 数据集自带的 gamma 做内部 sanity check**：随机抽 100 行，自己算 vs dataset 算，差异 > 5% 就停下来排查。这一步**不可跳过**——是单合约公式正确性的最强证据。
3. **再用公开样例校准聚合 GEX**：SpotGamma / VolHub / GammaLabs 的某天截图，方向一致 + 量级 ±30%。
4. **链聚合**：`GEX = Σ gamma × OI × 100 × spot² × dealer_sign / 1e9`（输出单位：billion $ per 1% move）。
5. **dealer sign 假设必须写在 docstring 顶部**：主流（SpotGamma / 多数 sell-side 报告）假设 **dealer LONG calls (+1) + SHORT puts (-1)**——对应"retail 卖 covered calls、机构买 protective puts"的 flow 假设。这是**假设**不是事实，0DTE 时代 retail 也在大量买 calls（meme + lottery 行情），convention 可能在某些日期反转。docstring 必须明确写出当前使用的 convention，并允许调用方按 `dealer_sign` 参数翻转。
6. **gamma flip level**：净 GEX = 0 时的 spot 价位，是 0DTE 策略最常引用的关键阈值。

其他 positioning 因子（在 `factors/positioning.py`）：

- Max pain：minimize total dealer ITM payout 的 strike
- Put-Call ratio：volume 版 + OI 版，两个都要
- 0DTE OI 集中度：前 N 大 strike 占总 OI 的比例

## 关于 SPX 期权的常见坑

写代码时容易踩：

- **SPX vs SPY**：notional 10:1，且 SPX 是欧式 + 现金结算 + Section 1256 税务，SPY 是美式 + 实物 + 普通税务。**不要假设 SPX 信号能直接 1:1 套到 SPY**。
- **SPXW vs SPX**：日常 0DTE 全是 SPXW（PM-settled weeklies）。月度第三个周五同时存在 AM-settled 的 SPX 和 PM-settled 的 SPXW，行为不一样。
- **0DTE 的"T"**：BS 公式里 T 不能用整数天，要用 fraction of trading hours remaining，否则 IV / gamma 全错。
- **现金结算**：SPX 期权到期不交付股票，只结算现金差额。回测时不要按"行权 → 拿股票"建模。

## 不要做的事

- 不要在没有质量检查的数据上跑回测。
- 不要把 yfinance 的延迟数据当实时数据用。
- 不要用 yfinance 的 0DTE IV 算任何东西（已实测：失真严重）。
- 不要为了"看起来更厉害"加 CuPy / Numba / Cython，除非有 benchmark 证明值得。
- 不要建第二个 venv 或换包管理器，除非 owner 明确要求。
- 不要在 Phase 3 的判据不达标时强行进 Phase 4（要花钱了）。
- 不要把策略代码写到 `factors/` 里——因子是无状态计算，策略才有时序逻辑。
- 不要为「将来扩展」预留代码（YAGNI）——`broker/` 在用到之前不创建。
- 不要主动建议加 ML / 深度学习因子，等 Phase 4 之后再说。
- 不要建议扩展到 QQQ / IWM / crypto——先把 SPX 做透。
