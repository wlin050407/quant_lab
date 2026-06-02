# Model Transparency & Data Quality Plan

**Date:** 2026-06-01  
**Scope:** Local implementation only — no GitHub push, no deploy.  
**Trigger:** External review (`quant_lab_review.md`) cross-checked against repo + industry sources.  
**Goal:** Make model-implied positioning outputs auditable (assumption + confidence + data quality), without rewriting architecture.

---

## Principles

1. **Extend** existing `snapshot.meta` / equity payloads — no second metadata system.
2. **Keep** `factors/` pure (no network I/O); transparency assembly stays in `terminal/`.
3. **Backward compatible:** `levels.flip` remains the primary flip; new fields are additive.
4. **Phase-aligned:** Fundamentals / external macro API are **out of scope** for this plan.

---

## Work packages

### WP0 — Plan & tracking (this document)

| ID | Task | Status |
|----|------|--------|
| 0.1 | Write this plan (dated) | done |
| 0.2 | Implement in order below; tick boxes as merged locally | done (local) |

---

### WP1 — P0: Index 0DTE model metadata (API)

**Files:** `factors/gex.py`, `terminal/snapshot.py`, `tests/test_gex.py`, `tests/test_terminal_snapshot_metadata.py` (new)

| ID | Task | Acceptance |
|----|------|------------|
| 1.1 | `TimeToExpiryDiagnostics` + `diagnose_cohort_time_to_expiry()` | done |
| 1.2 | `GammaFlipResult` + `compute_gamma_flip()` | done |
| 1.3 | `gamma_flip_level()` → delegates to `compute_gamma_flip().primary_flip` | done |
| 1.4 | `build_model_metadata()` in `terminal/model_metadata.py` | done |
| 1.5 | Snapshot `meta.model_metadata` + `levels.gamma_flip_detail` | done |
| 1.6 | Tests: multiple crossings, nearest primary, T fallback warning | done |

---

### WP2 — P0: Index 0DTE UI disclosure

**Files:** `terminal/web/src/types/snapshot.ts`, `components/ModelAssumptionStrip.tsx`, `InstrumentStrip.tsx`, `GammaProfileChart.tsx`, `styles/terminal.css`

| ID | Task | Acceptance |
|----|------|------------|
| 2.1 | TypeScript types for `model_metadata` | done |
| 2.2 | `ModelAssumptionStrip` under instrument strip | done |
| 2.3 | VEX label footnote when metric=vex | done (title tooltip) |
| 2.4 | Soften magnet / level labels | done |
| 2.5 | `build_terminal_ui.py` (local) | run after pull |

---

### WP3 — P1: Gamma flip API surface

| ID | Task | Acceptance |
|----|------|------------|
| 3.1 | Expose `all_flips` in snapshot | UI optional secondary list (tooltip or meta line) |
| 3.2 | `compute_gex_profile` stores flip confidence | Available in metadata |

---

### WP4 — P1: Equity trading-structure fixes

**Files:** `factors/equity/liquidity.py`, `data/yfinance_source.py` (already has adj_close), `terminal/equity_live.py`, `factors/equity/options_overlay.py`, `terminal/web` equity strings/pages

| ID | Task | Acceptance |
|----|------|------------|
| 4.1 | Amihud + ADV use `adj_close` when present | done |
| 4.2 | `OptionsOverlay` quality fields | done |
| 4.3 | Rename UI: Trading Structure | done (home + equity tagline + API `product_title`) |
| 4.4 | Soften POC copy | done |
| 4.5 | Tests: Amihud on synthetic split series | done |

---

### WP5 — P1: Macro calendar transparency (light)

**Files:** `data/macro_calendar.py`, `terminal/equity_live.py`

| ID | Task | Acceptance |
|----|------|------------|
| 5.1 | `macro_calendar_meta()` | done |
| 5.2 | Equity L1 payload includes meta | done |

---

### WP6 — Follow-up (2026-06-01 judgment)

| Item | Verdict | Status |
|------|---------|--------|
| Equity RS / MA / vol on **adj_close** | **Necessary** (same bug class as Amihud) | done (`factors/equity/prices.py`) |
| **SOFR** local update script + yaml path | **Worth it** (low cost; improves GEX r) | done (`scripts/update_sofr_rates.py`, parquet written locally) |
| Backtest **lagged-signal** regression test | **Worth it** before Phase 3 | done (`tests/test_backtest_no_lookahead.py`) |
| Equity **intraday_quality** on L2 | **Worth it** | done |
| Brent / denser flip grid | **Not now** — 41pt grid + nearest primary enough | deferred |
| External macro API | **Not now** — embedded + parquet extension OK | deferred |
| Full options-chain no-lookahead suite | **Phase 3** when intraday strategies ship | deferred |
| Fundamentals module | **Out of roadmap** | deferred |

---

## Implementation order (execution log)

1. WP1 (backend metadata + gamma flip + T diagnostics)  
2. WP2 (UI strip)  
3. WP4 (equity liquidity + overlay + naming)  
4. WP5 (macro meta)  
5. Local verification: `pytest` subset + `build_terminal_ui.py`  

---

## Verification commands (local)

```powershell
cd E:\quant_lab
.\.venv\Scripts\python.exe -m pytest tests/test_gex.py tests/test_terminal_snapshot_metadata.py tests/test_equity_liquidity.py -q
.\.venv\Scripts\python.exe scripts\build_terminal_ui.py
```

---

## References

- Review doc: `c:\Users\ROG\Downloads\quant_lab_review.md`
- Project rules: `AGENTS.md`, `ROADMAP.md`
- Prior analysis: agent session 2026-06-01
