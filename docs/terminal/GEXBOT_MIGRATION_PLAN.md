# Terminal Data Migration: GEXBot + Unusual Whales

**Branch:** `feature/gexbot-terminal-migration`  
**Status:** In progress  
**Goal:** Replace expired ThetaData as the **primary** Terminal intraday feed while preserving
deterministic GEX / Pin Play semantics wherever the new sources allow — and improve historical
replay latency via local GEXBot hist cache.

## Design principles

1. **Keep `factors/` pure** — network I/O stays in `data/`; Terminal orchestrates.
2. **Do not silently change GEX definitions** — vendor GEX is used for spot/levels cross-check
   and fast heatmaps; primary pin/GEX path remains **local BS76 from UW option chain** when
   contracts are available.
3. **ThetaData remains optional** — `TERMINAL_CHAIN_PROVIDER=thetadata` for rollback.
4. **Performance upgrade, not downgrade** — GEXBot 1Hz hist cached as Parquet; live pulls
   parallelize GEXBot + UW; retain 30s in-memory stale-while-error cache.

## Provider matrix

| Capability | ThetaData (legacy) | Vendor (GEXBot + UW) |
|------------|-------------------|----------------------|
| SPX spot @ time | index quote | GEXBot `classic/gex_zero` |
| 0DTE chain bid/ask/OI/IV | quotes + OI history | UW `option-contracts` |
| 09:30 reference OI | OI history @ 09:30 | Session cache (first poll) + GEXBot hist @ 09:30 |
| Session signed flow | trade tape | UW `flow-per-strike-intraday` cumulative |
| Historical intraday @ clock | remote pull | GEXBot `/hist/` Parquet cache (1s grid) |
| GEX heatmap | local compute | local from chain (+ vendor overlay in meta) |
| pin_score / pin_zone | local | local from UW chain |
| Trinity SPY/QQQ | ThetaData | UW contracts + GEXBot majors |
| ML raw lake | ThetaData | **Out of scope** (research track unchanged) |

## Architecture

```text
terminal/snapshot.py
    └── chain_provider.resolve_terminal_chain_provider()
            ├── thetadata → live_chain.fetch_intraday_chain_from_thetadata()
            └── vendor    → live_chain.fetch_intraday_chain_from_vendors()
                                  ├── data/vendor_chain.build_0dte_chain_from_vendors()
                                  │     ├── gexbot_client (spot, majors, orderflow)
                                  │     └── unusualwhales_client (contracts, flow)
                                  └── gexbot_history_cache (historical replay)
```

## Environment variables

| Variable | Required (vendor mode) | Purpose |
|----------|------------------------|---------|
| `GEXBOT_API_KEY` | Yes | Bearer token (`gexbot_custom_…`) |
| `UNUSUAL_WHALES_API_KEY` | Strongly recommended | Option chain + flow |
| `TERMINAL_CHAIN_PROVIDER` | No | `auto` (default), `vendor`, `thetadata` |
| `GEXBOT_HIST_CACHE_DIR` | No | Default `data/processed/gexbot_hist` |
| `THETADATA_*` | Only if provider=thetadata | Legacy |

## Phases (this branch)

### Phase A — Foundation (this PR)

- [x] Migration plan (this doc)
- [x] `gexbot_client.py`, `unusualwhales_client.py`
- [x] `vendor_chain.py` — UW contracts → `OptionChainSnapshot`
- [x] `gexbot_history_cache.py` — download + Parquet + `snapshot_at()`
- [x] `chain_provider.py`, `session_oi_cache.py`
- [x] `live_chain.py` vendor path + provider routing
- [x] `snapshot.py` remote load uses provider
- [x] `start_terminal_prod.py` accepts GEXBot OR ThetaData
- [x] Mock tests, `.env.example`, `config/settings.yaml`

### Phase B — Polish (complete)

- [x] Startup hist pre-warm (`terminal/startup_tasks.py`)
- [x] RTH background vendor live poller (REST keep-warm; WebSocket deferred)
- [x] `meta.vendor_levels` GEXBot cross-check overlay
- [x] `scripts/calibrate_vendor_gex.py`
- [x] `render.yaml` vendor env template; **Render-first** `docs/DEPLOY.md`
- [x] GEXBot WebSocket structure stream — see `docs/terminal/VENDOR_RESONANCE_V2.md`

## Known semantic gaps (documented in API meta)
|-----|------------|
| UW `prev_oi` is prior session, not 09:30 | Session OI cache after first live poll; GEXBot hist @ 09:30 for replay |
| UW contracts may be EoD snapshot on historical `date=` | Pair with GEXBot hist spot; label `oi_semantics` in meta |
| No OPRA tick tape | UW flow-per-strike intraday for `full` mode |
| Vendor GEX units vs local bn/$ | Heatmap from local chain; vendor majors in `meta.vendor_levels` |

## Acceptance gates

1. `pytest tests/test_vendor_chain.py tests/test_gexbot_history_cache.py tests/test_terminal_live_chain.py` pass
2. `ruff check` on new modules
3. With `TERMINAL_CHAIN_PROVIDER=vendor` + keys in `.env`, `build_dashboard` returns 200 for today live
4. Historical date within 90d resolves via hist cache without ThetaData
5. ThetaData path still works when `TERMINAL_CHAIN_PROVIDER=thetadata`
