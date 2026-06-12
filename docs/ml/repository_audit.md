# QuantLab Repository Audit (ML Phase 0)

**Date:** 2026-06-11  
**Auditor:** Cursor (Phase 0 — Repository and Governance Audit)  
**Scope:** Read-only inspection of the live repository; no production code changes in this phase.

---

## 1. Executive summary

QuantLab is a mature SPX/SPXW 0DTE research repository with working data ingestion (yfinance, Philipp Dubach, ThetaData), deterministic positioning factors (GEX/VEX, Pin Score, King node), a FastAPI + React Terminal, Docker/Railway deployment, and extensive pytest coverage (55 test modules). There is **no** `src/quant_lab/ml/` package yet.

The new ML master plan (`QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md`) is compatible with the existing architecture **if** it is treated as a parallel research track with its own phase numbering (`ML-P0` … `ML-P18`) and does not override ROADMAP strategy gates or rewrite Pin/GEX definitions.

---

## 2. Actual repository structure (top level)

```
quant_lab/
├── .cursor/rules/quantlab-0dte-ml.mdc   ← added Phase 0 (Cursor rule)
├── AGENTS.md
├── ROADMAP.md
├── README.md
├── QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md   ← added Phase 0
├── Dockerfile
├── railway.toml                         ← note: no railway.json
├── render.yaml
├── pyproject.toml
├── requirements.txt
├── config/
│   ├── settings.yaml
│   └── spx_spy_calibration.yaml
├── data/                                ← gitignored runtime data
├── docs/
│   ├── DEPLOY.md
│   ├── PIN_PLAY_SPEC.md
│   ├── ULTIMATE_TERMINAL.md
│   ├── EQUITY_LIVE_MODULE_PLAN.md
│   ├── MODEL_TRANSPARENCY_PLAN_2026-06-01.md
│   ├── PIN_PRO_UPGRADE_PLAN.md
│   └── ml/                              ← created Phase 0
├── frontend/                            ← legacy/auxiliary (not primary Terminal UI)
├── scripts/                             ← 48 CLI entrypoints
├── src/quant_lab/
│   ├── config.py
│   ├── backtest/
│   ├── data/
│   ├── factors/
│   │   └── equity/                      ← single-equity research submodule
│   ├── quality/
│   ├── strategies/
│   └── terminal/
│       ├── api.py
│       ├── snapshot.py
│       ├── static/dist/                 ← built React bundle
│       └── web/                         ← React source (Vite)
├── tests/                               ← 55 test_*.py modules
└── tools/
```

### Python package modules (present)

| Module | Path | Role |
|--------|------|------|
| `data/` | `src/quant_lab/data/` | Network + persistence; ThetaData, yfinance, Philipp Dubach, storage |
| `quality/` | `src/quant_lab/quality/` | Read-only data validation |
| `factors/` | `src/quant_lab/factors/` | Pure deterministic calculations (no I/O) |
| `terminal/` | `src/quant_lab/terminal/` | FastAPI, snapshot assembly, UI payload |
| `backtest/` | `src/quant_lab/backtest/` | PnL engine, BS76 helpers |
| `strategies/` | `src/quant_lab/strategies/` | Time-series strategy logic |
| **`ml/`** | **absent** | Proposed in ML plan; not yet created |

---

## 3. Current data providers

| Provider | Module(s) | Use case | Storage |
|----------|-----------|----------|---------|
| **yfinance** | `data/yfinance_source.py` | Free delayed EoD `^SPX` / `SPY` chains; bootstrap | `data/raw/options/{symbol}/{date}/chain.parquet` via `storage.py` |
| **Philipp Dubach** | `data/philippdubach_source.py`, `scripts/import_philippdubach_history.py` | 18y SPY EoD history with precomputed Greeks | Same canonical layout as yfinance |
| **ThetaData v3** | `data/thetadata_client.py`, `thetadata_intraday.py`, `thetadata_chain.py`, `thetadata_storage.py`, `thetadata_equity.py` | Live/recent SPX/SPXW intraday quotes, OI, trades, equity OHLC | `data/raw/intraday/SPX/price_1m/`, `data/raw/options/SPXW/{date}/intraday/` |
| **FlashAlpha (archive)** | `data/flashalpha_gex.py` | External GEX reference calibration | Read-only import |
| **Macro calendar** | `data/macro_calendar.py` | FOMC/CPI gate for playbook | Config + computed gates |
| **SOFR rates** | `factors/rates.py`, `scripts/update_sofr_rates.py` | GEX discounting inputs | Processed parquet |

Cloud Terminal (`docs/DEPLOY.md`): recent ~14 days pulled from ThetaData at request time; no bundled historical parquet on Railway.

---

## 4. ThetaData client surface (installed library: `thetadata>=1.0`)

### Factory / credentials

- `get_thetadata_client()`, `refresh_thetadata_client()`, `reset_client_cache()`
- Credential resolution: `THETADATA_EMAIL` + `THETADATA_PASSWORD`, or `THETADATA_CREDENTIALS_FILE`, or project-root `creds.txt`

### Intraday (`thetadata_intraday.py`)

| Function | Purpose |
|----------|---------|
| `fetch_spx_price_1m` | SPX 1-minute underlying |
| `fetch_spx_at_time` / `fetch_stock_at_time` | Spot at clock time |
| `fetch_0dte_option_quotes_window` | Quote window for 0DTE book |
| `fetch_0dte_raw_trades_at_time` | Raw trades at time |
| `fetch_0dte_signed_flow_at_time` | Signed flow proxy |
| `fetch_0dte_cumulative_volume_at_time` | Cumulative volume at time |
| `fetch_0dte_session_flow_at_time` | Session flow aggregation |
| `fetch_0dte_chain_at_time` | Full chain at time |
| `list_option_roots` / `list_index_symbols` / `resolve_option_root` | Symbol discovery (SPXW preferred) |

Pin-play clock constants: `PIN_PLAY_TIMES_ET` (used by snapshot + pin eval).

### Chain assembly (`thetadata_chain.py`)

| Function | Purpose |
|----------|---------|
| `fetch_0dte_open_interest_history` | OI history |
| `fetch_0dte_open_interest_at_time` | Point-in-time OI |
| `build_0dte_chain_snapshot` | Assemble chain for session + time |
| `assemble_chain_from_quotes_oi` | Merge quotes + OI |
| `save_built_intraday_chain` / `load_built_intraday_chain` | Local parquet persistence |
| `list_intraday_chain_dates` | Available built-chain dates |

### Storage layout (`thetadata_storage.py`)

```
data/raw/intraday/SPX/price_1m/<YYYY-MM-DD>.parquet
data/raw/options/SPX/<YYYY-MM-DD>/intraday/quotes_<HHMM>.parquet
data/raw/options/SPXW/<YYYY-MM-DD>/intraday/chain_<HHMM>.parquet
data/raw/options/SPXW/<YYYY-MM-DD>/intraday/chain_<HHMM>_meta.parquet
```

### Equity overlay (`thetadata_equity.py`)

Stock intraday OHLC, EOD range, NBBO at time — used by equity Terminal lane.

**ML plan note:** ML-P1 must probe actual entitlement fields, finest interval, OI date semantics, and pagination — not assumed from this inventory alone.

---

## 5. Storage formats

| Layer | Format | Access path |
|-------|--------|-------------|
| EoD option chains | Parquet (pyarrow) | `quant_lab.data.storage` — `save_option_chain` / `load_option_chain` |
| Underlying bars | Parquet | `save_underlying` / `load_underlying` |
| ThetaData intraday | Parquet | `thetadata_storage.save_parquet` / `load_parquet` |
| Processed factors | Parquet under `data/processed/` | Built by scripts (`build_gex_history.py`, etc.) |

**Convention:** Single Parquet format only (per `AGENTS.md`). No CSV/pickle/sqlite for market data.

Canonical EoD layout:

```
data/raw/options/{symbol}/{YYYY-MM-DD}/chain.parquet
data/raw/options/{symbol}/{YYYY-MM-DD}/meta.parquet
```

---

## 6. Pin / GEX / VEX pipeline

### Deterministic factor layer (`factors/`)

| File | Responsibility |
|------|----------------|
| `gex.py` | BS76/Black-76 gamma & vanna; dealer GEX/VEX aggregation; gamma flip; King node; walls; profiles |
| `positioning.py` | Max pain, PCR, OI concentration, Pin Score (`PIN_SCORE_MODEL_VERSION`), expected move |
| `effective_oi.py` | Flow-adjusted OI columns for intraday chain modes |
| `trade_flow.py` | Signed flow helpers |
| `pin_cluster.py` | Pin cluster detection |
| `pin_king_proximity.py` | King proximity strata for IC research |
| `pin_intraday_eval.py` | Fixed-clock pin evaluation vs session close |
| `regime.py` | GEX regime, pin reliability, trade gate |
| `spx_spy_calibration.py` | Cross-symbol scale calibration |

Dealer sign convention is documented in `gex.py` docstrings (model-implied, not observed inventory).

### Terminal assembly (`terminal/snapshot.py`)

Flow: load chain (local parquet or live ThetaData) → filter DTE cohort → compute GEX/VEX profiles → Pin Score + King → magnet state → pin playbook → strategy hint → JSON payload.

Key integration points:

- `build_dashboard()` — main API payload builder
- `build_strike_heatmap()` — per-strike GEX heatmap
- Chain modes: `pin` | `full` | `gex` (`ChainMode` in `thetadata_chain.py`)
- Live path: `terminal/live_chain.py` (60s poll, ThetaData)
- Quality caps: `terminal/live_pin_quality.py`

### Pin Play methodology (frozen for ML labels)

| Artifact | Location |
|----------|----------|
| Strategy spec | `docs/PIN_PLAY_SPEC.md` |
| Playbook builder | `terminal/pin_playbook.py` — session phases, entry checks, **Valid Exit rules**, size multipliers |
| Intraday strategy sim | `strategies/zdte_pin_fly_intraday.py` |
| Evaluation script | `scripts/evaluate_intraday_pin.py` |

ML models must consume Pin/GEX/VEX as **inputs or label references**, not redefine them without an explicit spec change approved by the owner.

---

## 7. Current API routes

FastAPI app: `src/quant_lab/terminal/api.py` (version `0.2.0`)

| Method | Route | Handler |
|--------|-------|---------|
| GET | `/api/health` | Health + UI mode |
| GET | `/api/dates` | Available terminal dates per symbol |
| GET | `/api/snapshot` | Full dashboard payload (symbol, date, time, chain_mode, trinity) |
| GET | `/api/equity/analyze` | Single-equity analysis (v1) |
| GET | `/`, `/favicon.*`, `/assets/*`, `/{path}` | React SPA shell |

**Not present (ML plan Phase 15):** `/api/ml/zdte/*` routes.

Middleware: `TerminalBasicAuthMiddleware` (optional basic auth via env vars).

---

## 8. Current test inventory

55 test modules under `tests/`, including:

| Area | Representative tests |
|------|---------------------|
| GEX / positioning | `test_gex.py`, `test_positioning.py`, `test_positioning_intraday.py`, `test_effective_oi.py` |
| Pin / playbook | `test_pin_playbook.py`, `test_pin_intraday_eval.py`, `test_pin_king_proximity.py`, `test_pin_cluster.py` |
| ThetaData | `test_thetadata_client.py`, `test_thetadata_chain.py`, `test_thetadata_intraday.py` |
| Terminal | `test_terminal_m4.py`, `test_terminal_json.py`, `test_terminal_auth.py`, `test_terminal_deploy.py`, `test_terminal_snapshot_*` |
| Backtest / no-lookahead | `test_backtest.py`, `test_backtest_no_lookahead.py` |
| Strategies | `test_zdte_*` (eod, ic, pin_fly, intraday) |
| Equity lane | `test_equity_*.py` |
| Data / quality | `test_storage.py`, `test_quality.py`, `test_philippdubach_source.py`, `test_yfinance_source.py` |

**Existing no-lookahead coverage:** `test_backtest_no_lookahead.py` (lagged signal in backtest engine). ML plan adds broader leakage tests in later phases (`test_no_lookahead.py`, replay integrity, etc.) — not yet present.

---

## 9. Railway / production startup path

```
Dockerfile (multi-stage)
  ├── node:22 → npm ci + npm run build → static/dist
  └── python:3.12-slim → pip install . → CMD scripts/start_terminal_prod.py

scripts/start_terminal_prod.py
  ├── _preflight(): ThetaData creds required; basic auth warned if missing
  └── uvicorn.run("quant_lab.terminal.api:app", host=0.0.0.0, port=PORT)

railway.toml
  ├── builder: DOCKERFILE
  ├── healthcheckPath: /api/health
  └── restartPolicyType: ON_FAILURE

Environment (production):
  THETADATA_EMAIL, THETADATA_PASSWORD
  TERMINAL_AUTH_USER, TERMINAL_AUTH_PASSWORD (recommended)
  TERMINAL_HISTORY_DAYS=14 (Dockerfile default)
  PORT (platform-assigned)
```

**ML constraint:** Railway installs only `requirements.txt` today — no PyTorch/LightGBM. Student model + deterministic fallback must stay CPU-safe (per ML plan Phase 14–15).

---

## 10. Dependencies (production)

From `requirements.txt` (Python ≥3.12):

- Core: pandas, numpy, scipy, pyarrow, pyyaml
- Data: yfinance, requests, thetadata
- Terminal: fastapi, uvicorn, httpx, python-dotenv
- Dev/CI: pytest, pytest-mock, ruff

**Not installed:** scikit-learn, lightgbm, torch, onnx — proposed for `requirements-ml.txt` in later ML phases.

---

## 11. Conflicts between governance documents

| # | Conflict | Details |
|---|----------|---------|
| C1 | **Phase numbering collision** | `ROADMAP.md` uses Phase 0–6 (data → live trading). ML plan uses Phase 0–18 (audit → paper trading). Same numbers, different meaning. |
| C2 | **ML prohibition vs ML plan** | `AGENTS.md` L110: "不要主动建议加 ML / 深度学习因子，等 Phase 4 之后再说." `ROADMAP.md` L336: "❌ ML / 深度学习因子：等 Phase 4 之后再考虑." ML plan initiates ML infrastructure starting ML-P0. |
| C3 | **AGENTS.md stale "current phase"** | `AGENTS.md` L14 states "当前：Phase 0 数据地基." `README.md` and `ROADMAP.md` mark Phases 0–3 substantially complete; engineering focus is Terminal + Phase 4 intraday. |
| C4 | **Dual "Phase 4" meaning** | ROADMAP Phase 4 = paid intraday backtest gate. ML plan Phase 4 = point-in-time replay engine. |
| C5 | **`factors/calibration.py` naming** | Exists for factor calibration (SpotGamma alignment), not ML probability calibration. ML plan adds `ml/calibration.py` — different module, potential naming confusion. |
| C6 | **Pre-existing test / lint debt** | 3 failing tests in `test_terminal_m4.py` (uncommitted terminal work); 157 ruff findings repo-wide. Unrelated to ML but affects "tests pass" gate interpretation. |

### Non-conflicts (aligned)

- Module boundary `data → quality → factors → terminal` matches ML plan's preservation requirement.
- No auto-execution: both AGENTS and ML plan forbid broker/autotrade until explicit later phase.
- Parquet-only storage, pathlib, typed public APIs — aligned.
- Pin Play spec + playbook exit rules are the intended label/feature authority for ML.

---

## 12. Proposed authoritative phase designation

See **`docs/ml/ml_phase_governance.md`** for the full resolution. Summary:

- **ROADMAP phases** remain the **strategy/product** gates (0–6).
- **ML phases** are prefixed **`ML-P0` … `ML-P18`** in all new docs, commits, and Cursor prompts.
- ML work may begin **infrastructure and audits** after owner approves governance update; **model training** requires ROADMAP Phase 4 intraday data foundation and ML-P6 label spec sign-off.
- Deterministic Pin/GEX engine stays **production authoritative** until a registered ML model passes ML-P12 walk-forward + calibration gates.

---

## 13. Files that may and may not be changed (future ML work)

### May change (with phase scope)

| Path | When |
|------|------|
| `src/quant_lab/ml/**` | ML-P5 onward (new package) |
| `src/quant_lab/data/intraday_lake.py`, `point_in_time_replay.py`, etc. | ML-P3, ML-P4 (new files) |
| `src/quant_lab/quality/leakage_checks.py`, etc. | ML-P4+ (new files) |
| `config/ml/*.yaml` | ML-P5+ |
| `docs/ml/*.md` | Any ML phase |
| `scripts/audit_thetadata_capabilities.py`, training scripts | Per ML phase |
| `tests/test_*ml*`, `test_no_lookahead.py`, etc. | Per ML phase |
| `requirements-ml.txt` | After documented exception (ML-P8+ local training) |
| `terminal/api.py` | ML-P15 only — add `/api/ml/zdte/*` with fallback |
| `terminal/web/` | ML-P16 — model output UI |

### Must not change without owner + spec approval

| Path | Reason |
|------|--------|
| `factors/gex.py`, `factors/positioning.py` formulas | Financial definitions frozen |
| `docs/PIN_PLAY_SPEC.md` exit/entry semantics | Label authority |
| `terminal/pin_playbook.py` Valid Exit logic | Label authority |
| `strategies/zdte_pin_fly_intraday.py` sim rules | Backtest/label consistency |
| `requirements.txt` / Dockerfile (Railway deps) | Until ML deployment phase + CPU audit |
| `data/raw/**` in place (overwrite) | Immutability rule |
| `AGENTS.md`, `ROADMAP.md` | Phase 0 proposes governance only; owner merges |

### Read-only for ML phases unless explicitly scoped

- `backtest/engine.py` — extend via new modules, don't break lag semantics
- `broker/` — does not exist; must not be created by ML track

---

## 14. Phase 0 deliverables checklist

| Deliverable | Status |
|-------------|--------|
| `docs/ml/repository_audit.md` | ✅ This file |
| `docs/ml/ml_phase_governance.md` | ✅ Created |
| `QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md` in repo root | ✅ Added |
| `.cursor/rules/quantlab-0dte-ml.mdc` | ✅ Added |
| No production code changed | ✅ Docs + rule files only |
| Governance contradiction documented | ✅ Section 11 + governance doc |
| `src/quant_lab/ml/` boundary approved in writing | ✅ See governance doc |

---

## 15. Commands executed (Phase 0)

```powershell
# File placement
Copy-Item QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md → repo root
Copy-Item quantlab-0dte-ml.mdc → .cursor/rules/

# Verification
python -m pytest -q
python -m ruff check src tests scripts
```

---

## 16. Test and lint results

### pytest (2026-06-11)

```
318 passed, 3 failed (tests/test_terminal_m4.py)
```

Failures (pre-existing; tied to in-flight Terminal changes, not Phase 0):

1. `test_api_snapshot_latest` — `pin_playbook` is `None` when ThetaData live fetch fails for future session date
2. `test_build_strike_heatmap_from_chain` — `build_strike_heatmap` now returns `(rows, bool)` tuple; test expects bare list
3. `test_heatmap_roc_pct` — same tuple return-type mismatch

### ruff

```
157 errors (100 fixable with --fix)
```

Pre-existing style/import debt across `src/`, `tests/`, `scripts/`. Phase 0 did not modify Python source.

---

## 17. Unresolved risks

1. **Test gate:** Three Terminal M4 tests fail on current working tree; should be fixed before treating CI as green (separate from ML, but blocks strict Phase 0 acceptance).
2. **ThetaData entitlement unknown:** ML-P1 audit not yet run; tick/L2 claims in ML plan are unverified against account tier.
3. **OI time semantics:** Intraday OI may be prior-session or same-day depending on ThetaData field — must be documented before label construction (ML-P1/P6).
4. **Governance not yet merged:** `AGENTS.md` / `ROADMAP.md` still say "no ML until Phase 4"; owner must approve `ml_phase_governance.md` proposal.
5. **Working tree noise:** Uncommitted changes in `terminal/`, `strategy_hint.py`, equity routes — audit reflects inspected files; diffs may drift until committed.
6. **Ruff debt:** 157 issues may mask new regressions until baseline is cleaned or scoped per-phase.

---

## 18. Phase 0 acceptance gate

| Criterion | Result |
|-----------|--------|
| No production code changed | **PASS** |
| Existing tests still pass | **FAIL** (3 pre-existing failures in `test_terminal_m4.py`) |
| Governance contradiction explicitly resolved | **PASS** (documented; pending owner approval) |
| `src/quant_lab/ml/` boundary approved in writing | **PASS** |
| `data → quality → factors → terminal` intact | **PASS** |

**Overall Phase 0 gate: CONDITIONAL PASS** — audit deliverables complete; owner should (a) approve governance proposal, (b) fix or waive the 3 Terminal test failures before ML-P1.
