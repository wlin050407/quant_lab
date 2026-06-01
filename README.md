# quant_lab

Research workspace and live terminal for **SPX 0DTE dealer positioning** — the hypothesis that intraday edge comes from inferring market-maker gamma exposure from open interest, then trading the asymmetry when spot interacts with magnet levels (King, flip, walls, max pain).

The repo is organized as a **phase-gated pipeline**: data foundation → positioning factors → backtest → execution. The **Quantlab Terminal** is the research-facing product layer on top of that stack: it turns option chains into auditable positioning analytics and multi-horizon equity research, with a path to paper and live trading later.

Roadmap: [`ROADMAP.md`](./ROADMAP.md) · Terminal design: [`docs/ULTIMATE_TERMINAL.md`](./docs/ULTIMATE_TERMINAL.md) · Equity module: [`docs/EQUITY_LIVE_MODULE_PLAN.md`](./docs/EQUITY_LIVE_MODULE_PLAN.md)

> **Private repository.** Never commit `.env`, credentials, or anything under `data/`. ThetaData and terminal basic-auth secrets belong in environment variables only.

---

## What the terminal does

Quantlab Terminal is a FastAPI + React application with two modes:

| Mode | Route | Question it answers |
|------|-------|---------------------|
| **Index 0DTE** | `#/index` | Where is dealer gamma concentrated today, what is the regime, and where are pin magnets? |
| **Equity research** | `#/stock?t=TICKER` | For a single US name, what do **short / mid / long** horizons imply, and what is the weakest evidence link? |

Both modes share the same engineering rules: typed Python factors, Parquet or ephemeral fetch → compute → JSON, explicit provenance, and no blended “black box” scores without layer disclosure.

---

## How we analyze — Index 0DTE terminal

### Data inputs

- **Live / recent sessions**: ThetaData intraday 0DTE option quotes (SPXW root), pulled at a session clock (`live` = now ET, or pin-play slots such as 13:00 ET).
- **Historical EoD**: Processed factor rows + option chains on disk (yfinance EoD, Philipp Dubach SPY history for research).
- **Cohort**: Analytics default to **`dte ≤ 1`** (0DTE proxy). If that filter is empty, the UI falls back to the full chain and flags `cohort_fallback`.

### Positioning math (L2–L3)

All chain-level metrics are computed in `src/quant_lab/factors/` from clean snapshots:

1. **Per-contract gamma (Black-76)** — index options are European, cash-settled; we use Black-76, not equity Black–Scholes.
2. **Dealer sign convention** — documented and overridable: dealer **long calls (+1), short puts (−1)** (SpotGamma-style). This is an **assumption**, not ground truth.
3. **GEX aggregation** — per strike:
   `GEX = 0.01 × Σ (dealer_sign × Γ × OI × 100 × S²)`  
   Display unit: **billion USD per 1% spot move** (`bn_per_1pct`).
4. **VEX (vanna exposure)** — same sign convention on vanna × OI; used for vol-spot coupling context.
5. **Structural levels** — gamma flip, call/put walls, King (max |net GEX| strike), floor/ceiling nodes, max pain, 1σ expected move from ATM IV.

### Regime and pin framework (L3)

- **Regime** — derived from net 0DTE GEX (long-gamma vs short-gamma environment).
- **Pin score** — composite of distance to magnet, 0DTE GEX concentration, OI concentration, and **hours-to-close** (steeper weight inside the final two hours).
- **Gate** — `should_trade_zdte()` combines regime, pin score, and 0DTE GEX share; surfaced as playbook pass/fail with reason.
- **Strategy hint** — regime-conditioned structure suggestion (research language, not execution).

### Trinity alignment

SPX, SPY, and QQQ 0DTE panels are compared via **King distance** alignment (`trinity_from_kings`). Trinity Score (0–100) and direction summarize cross-index magnet agreement — the same primitive intended for later backtest, not just UI decoration.

### Pin Playbook & targets

The playbook encodes a **checklist** (regime, gate, trinity, distance to King/walls, expected move) and projects **pin targets** from the strike heatmap. Magnet shift tracking compares live King movement across polls when `time=live`.

### API surface

`GET /api/snapshot?symbol=^SPX&date=YYYY-MM-DD&time=live|HH:MM:SS` returns the full dashboard JSON: heatmap, gamma profile, levels, metrics, trinity, panels, playbook, pin targets, and metadata (`data_mode`, `oi_mode`, `live_follow`, etc.).

---

## How we analyze — Equity research terminal

### Design stance

Equity mode is **on-demand research**, not a second data warehouse. Each request fetches bars in memory, computes factors, and returns JSON (optional TTL cache). It deliberately does **not** reuse 0DTE pin/gamma fields unless the options overlay is available.

### Evidence layers (L0–L6)

| Layer | Content | Grade drivers |
|-------|---------|----------------|
| **L0** Liquidity | 20d ADV, Amihud λ, eligibility floor | Execution risk (<$5M ADV), elevated Amihud vs own p75 history |
| **L1** Context | Vol regime, earnings window, macro calendar | Elevated vol, earnings ±7d, stacked macro |
| **L2** Session flow | Session VWAP, opening 30m RS vs benchmark | Intraday source quality, bar count |
| **L3** Volume profile | POC / VAH / VAL (70% value area from POC) | Session bar depth |
| **L5** Trend | RS vs SPY (1d–120d, calendar-aligned), MA structure | Daily history length |
| **L6** Options overlay | PCR, max pain (yfinance chain, 7–45 DTE) | Contract count |

### Multi-horizon synthesis (L7)

Every run produces **three independent verdicts**:

- **Short** — session VWAP, volume profile location, opening segment RS.
- **Mid** — 20d RS, MA20/50, earnings/macro risks, optional options context.
- **Long** — 120d RS / 200 MA trend, sample-depth grade.

Each verdict includes `bias`, `confidence`, `grade` (A/B/C), `drivers`, and `risks`. The synthesis layer adds:

- **`alignment`** — short/mid/long agree, mixed, or conflict.
- **`weakest_link`** — the limiting layer (e.g. execution risk, delayed intraday, missing options).

Module-level bullish/neutral/bearish chips (`liquidity`, `context`, `vwap_flow`, etc.) mirror the Python rules in `layer_signals.py` for UI consistency.

### API surface

`GET /api/equity/analyze?ticker=AAPL&refresh=0|1`

---

## Why loads can feel slow

The terminal prioritizes **correct, auditable snapshots** over sub-second first paint. Latency is usually dominated by **external data**, not React rendering.

### Index 0DTE (`/api/snapshot`) — latency budget

| Stage | Before (typical) | After optimization |
|-------|------------------|-------------------|
| Main symbol chain (`full`) | 1× quotes + **2× OI** + trades + full-day quotes for flow | 1× OI history + quotes + flow (single OI pull) |
| Previous session (RoC) | **Full** chain serial | **`gex` lite** chain, **parallel** with main |
| Trinity SPY/QQQ | Up to **4 extra full chains** serial | **`gex` lite**, parallel; skipped until Trinity view |
| First load (single view) | ~4–6 ThetaData builds serial | ~**2–4 parallel** builds (1 full + rest lite) |
| Live cache hit | <1 s | unchanged (~30 s TTL) |

**Default fast path:** `include_trinity=0` (single heatmap). Switching to Trinity view (`3` or toggle) refetches with `include_trinity=1`.

**Remaining cost:** the primary `^SPX` chain still runs in `full` mode (needs flow for effective OI). That one ThetaData build is irreducible without dropping flow quality.

### Equity (`/api/equity/analyze`)

First fetch pulls **daily (5y) + intraday 5m + benchmark + optional option chain** via yfinance/ThetaData. Expect **5–20 s** depending on ticker and cache. Use `refresh=1` only when bypassing cache intentionally.

---

## What works today

- Underlying + option chain ingest (yfinance / ThetaData) → Parquet on disk
- Data quality checks before research use (`quality/`)
- **Quantlab Terminal** — 0DTE dashboard + equity multi-horizon research UI
- **Cloud deploy** (Railway) — live intraday via ThetaData + configurable history window (`TERMINAL_HISTORY_DAYS`, default 14)
- Positioning factor library: GEX/VEX, flip, walls, King, pin score, trinity, expected move (see `factors/gex.py`, `factors/positioning.py`)

## What is intentionally not production-ready

- No automated execution (Phase 5+).
- yfinance 0DTE IV is filtered/untrusted; intraday greeks rely on BS76 recompute where needed.
- Cloud instance has **no** bundled 18y Philipp Dubach parquet — import locally for Phase 0/1 research.
- Equity L4 signed flow / Stock Standard tape — not configured; L6 options overlay is best-effort.

---

## Quick start (local)

```powershell
# From repo root (e.g. E:\quant_lab)
.\scripts\setup_env.ps1

# Build terminal UI (first time)
.\.venv\Scripts\python.exe scripts\build_terminal_ui.py --install

# Optional: local historical factors for SPY/SPX EoD browsing
.\.venv\Scripts\python.exe scripts\build_terminal_history.py --symbol SPY

# Run terminal
.\.venv\Scripts\python.exe scripts\run_terminal.py --open-browser
```

Open http://127.0.0.1:8765

Copy `.env.example` → `.env` and set ThetaData credentials for live SPX intraday.

**Large local datasets** (Philipp Dubach SPY parquet, etc.) live under `data/external/` and are **not** in git.

---

## Cloud deploy

See **[`docs/DEPLOY.md`](./docs/DEPLOY.md)** for Railway / Render setup.

| Variable | Purpose |
|----------|---------|
| `THETADATA_EMAIL` / `THETADATA_PASSWORD` | ThetaData API |
| `TERMINAL_AUTH_USER` / `TERMINAL_AUTH_PASSWORD` | Protect public URL |
| `TERMINAL_HISTORY_DAYS` | Default `14` — recent sessions via ThetaData |
| `TERMINAL_LIVE_REFRESH_SECONDS` | Live poll interval (default 30, minimum 15) |

---

## Architecture & module boundaries

```
Research flow:
  data/ (ingest, storage, ThetaData client)
    → quality/ (read-only validation)
    → factors/ (positioning + equity factors — pure functions)
    → terminal/ (FastAPI snapshot assembly + React UI)
    → backtest/ (Phase 2+, not required for terminal)
    → strategies/ · broker/ (later phases)
```

| Module | Responsibility | Must not |
|--------|----------------|----------|
| `data/` | Fetch + persist | Factor logic |
| `factors/` | Clean data → tensors/scalars | Network I/O |
| `quality/` | Validate | Mutate data |
| `terminal/` | API + UI payload assembly | Ad-hoc factor math |
| `backtest/` | PnL / metrics | Change data sources |

Design principles:

1. **Swappable sources** — `DataSource` protocol; yfinance default, ThetaData for intraday.
2. **Local-first research** — Parquet on disk; reproducible snapshots.
3. **Auditable** — timestamps, `data_mode`, dealer sign, and raw fields preserved.
4. **Phase gates** — no Phase N+1 until exit criteria pass ([`ROADMAP.md`](./ROADMAP.md)).
5. **No premature optimization** — pandas + CPU until profiling proves otherwise.

---

## Repository layout

```
quant_lab/
├── config/              # settings.yaml, calibration refs
├── data/                # gitignored — raw + processed Parquet
├── docs/                # DEPLOY, terminal, equity plans
├── scripts/             # CLI, build, deploy entrypoints
├── src/quant_lab/
│   ├── data/            # ingest + storage + ThetaData
│   ├── factors/         # GEX, positioning, equity, trinity
│   ├── quality/         # read-only checks
│   ├── terminal/        # FastAPI + React UI
│   └── backtest/        # Phase 2+
├── Dockerfile
├── railway.toml
└── tests/
```

---

## Data ingest (Phase 0 CLI)

```powershell
.\.venv\Scripts\python.exe scripts\fetch_underlying.py --symbol ^SPX
.\.venv\Scripts\python.exe scripts\fetch_option_chain.py --symbol ^SPX --max-expiries 12
.\.venv\Scripts\python.exe scripts\check_quality.py --symbol ^SPX
```

Philipp Dubach SPY history (18y EoD with precomputed Greeks):

```powershell
.\.venv\Scripts\python.exe scripts\import_philippdubach_history.py
```

---

## Roadmap (summary)

```
Phase 0  Data foundation          ← current
Phase 1  Positioning factors (GEX) — terminal implements L2–L3 preview
Phase 2  Backtest + baselines
Phase 3  EoD 0DTE simulation     (decision gate)
Phase 4  Paid intraday + live backtest
Phase 5  Paper trading
Phase 6  Live (small size)
```

Full criteria: [`ROADMAP.md`](./ROADMAP.md) · Agent conventions: [`AGENTS.md`](./AGENTS.md)

---

## License

Private — all rights reserved unless otherwise noted for third-party datasets (e.g. Philipp Dubach SPY options, MIT).
