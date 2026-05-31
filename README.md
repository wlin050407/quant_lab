# quant_lab

Private quant research workspace focused on **SPX 0DTE positioning** — building a positive-expectancy, executable, risk-controlled strategy.

**Current focus**: Ultimate Terminal (local + cloud deploy) on top of Phase 0 data foundation.  
Roadmap: [`ROADMAP.md`](./ROADMAP.md) · Terminal design: [`docs/ULTIMATE_TERMINAL.md`](./docs/ULTIMATE_TERMINAL.md)

> **Private repo recommended.** Do not commit `.env`, `creds.txt`, or anything under `data/`. ThetaData credentials belong in environment variables only.

## What works today

- Underlying + option chain ingest (yfinance / ThetaData) → Parquet on disk
- Data quality checks before research use
- **Quantlab Terminal** — SPX 0DTE dashboard (GEX/VEX heatmap, gamma profile, pin magnets, playbook)
- **Cloud deploy** (Railway / Render) — live + ~2 weeks history via ThetaData, no bundled parquet

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

**Large local datasets** (Philipp Dubach SPY parquet, etc.) live under `data/external/` and are **not** in git. Import locally when needed for Phase 0 SPY history research.

## Cloud deploy

See **[`docs/DEPLOY.md`](./docs/DEPLOY.md)** for Railway / Render setup.

Required secrets (platform dashboard only — never in git):

| Variable | Purpose |
|----------|---------|
| `THETADATA_EMAIL` / `THETADATA_PASSWORD` | ThetaData API |
| `TERMINAL_AUTH_USER` / `TERMINAL_AUTH_PASSWORD` | Protect public URL |
| `TERMINAL_HISTORY_DAYS` | Default `14` (live + this/last week) |

## Design principles

1. **Swappable data sources** — `DataSource` protocol; yfinance is the free default, ThetaData for intraday.
2. **Local-first research** — Parquet on disk; factors and backtests read locally.
3. **Auditable** — snapshot timestamps and raw fields preserved for replay.
4. **Phase gates** — no Phase N+1 work until Phase N exit criteria pass ([`ROADMAP.md`](./ROADMAP.md)).
5. **No premature optimization** — pandas + CPU until profiling says otherwise.

## Repository layout

```
quant_lab/
├── config/              # settings.yaml, calibration refs
├── data/                # gitignored — raw + processed Parquet
├── docs/                # DEPLOY.md, terminal notes
├── scripts/             # CLI + build + deploy entrypoints
├── src/quant_lab/
│   ├── data/            # ingest + storage
│   ├── factors/         # GEX, positioning, regime
│   ├── quality/         # read-only checks
│   ├── terminal/        # FastAPI + React UI
│   └── backtest/        # Phase 2+
├── Dockerfile           # production image
├── railway.toml
├── render.yaml
└── tests/
```

## Data ingest (Phase 0)

```powershell
.\.venv\Scripts\python.exe scripts\fetch_underlying.py --symbol ^SPX
.\.venv\Scripts\python.exe scripts\fetch_option_chain.py --symbol ^SPX --max-expiries 12
.\.venv\Scripts\python.exe scripts\check_quality.py --symbol ^SPX
```

## Roadmap (summary)

```
Phase 0  Data foundation          ← current
Phase 1  Positioning factors (GEX)
Phase 2  Backtest + baselines
Phase 3  EoD 0DTE simulation     (decision gate)
Phase 4  Paid intraday + live backtest
Phase 5  Paper trading
Phase 6  Live (small size)
```

Full criteria: [`ROADMAP.md`](./ROADMAP.md) · Agent conventions: [`AGENTS.md`](./AGENTS.md)

## License

Private — all rights reserved unless otherwise noted for third-party datasets (e.g. Philipp Dubach SPY options, MIT).
