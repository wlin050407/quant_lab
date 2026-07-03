# Terminal Vendor 2.0 — Structure Stream + Chain Facts + Resonance Gate

**Branch:** `feature/vendor-resonance-v2`  
**Status:** In progress  
**Goal:** Maximize GEXBot Quant + UW value while keeping `factors/` auditable. WebSocket
is the **primary** structure path; resonance is **confidence**, not a blended score.

## Design principles

1. **Local chain + local GEX/pin remain the display truth** — UW `option-contracts` +
   `factors/gex.py` / `positioning.py`.
2. **GEXBot WebSocket is the primary structure feed** — spot, flip, majors, max_priors,
   orderflow. REST `classic` is fallback only when WS is stale/down.
3. **Resonance gates confidence** — never average vendor and local into one heatmap or pin.
4. **ThetaData rollback unchanged** — `TERMINAL_CHAIN_PROVIDER=thetadata`.

## Architecture

```text
GEXBot WS (classic gex_zero + orderflow)
        │
        ▼
 VendorStreamState (in-memory, per ticker)
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
 UW REST (contracts + optional flow)   local factors/
        │                              GEX + pin_score
        └──────────► resonance.py ◄──────────┘
                        │
                        ▼
              build_dashboard meta + gate overlay
```

## Lanes

| Lane | Source | Refresh | Role |
|------|--------|---------|------|
| Structure | GEXBot WS | ~1s | spot, flip, majors, max_priors, orderflow |
| Chain facts | UW REST | 30–45s | OI, NBBO, IV → heatmap + pin |
| Compute | `factors/` | on demand | auditable GEX / pin |
| Resonance | `terminal/resonance.py` | per snapshot | confidence tier + gate |
| History | GEXBot `/hist/` | cached | replay @ clock |

## Resonance axes (0–1 each)

| Axis | Definition |
|------|------------|
| `flip_align` | \|local_flip − zero_gamma\| vs tolerance (default 15pt) |
| `magnet_align` | \|king − major_pos_oi\| in strikes |
| `pin_triangulate` | pin≥60 and max_priors peak near king |
| `wall_cage` | spot between major_neg_oi and major_pos_oi |
| `flow_regime` | long_γ + gex_orderflow≥0 or short_γ + gex_orderflow≤0 |

**Tier:** high ≥0.75 · medium 0.45–0.75 · low <0.45

**Gate overlay:** if base `should_trade` ok but tier=low and pin<75 → `low_resonance`.

## GEXBot WebSocket

- `POST /v2/negotiate` with groups e.g. `SPX_classic_gex_zero`, `SPX_orderflow_orderflow`
- Azure Web PubSub; messages zstd + protobuf (see `quant-python-sockets`)
- **1 active connection per hub** (Quant limit)
- Fallback: REST `classic` when silent >15s; poller when down >60s

Default groups (env `TERMINAL_GEXBOT_WS_GROUPS`):

```text
SPX_classic_gex_zero,SPX_orderflow_orderflow
```

Trinity extension: `SPY_classic_gex_zero`, `QQQ_classic_gex_zero`.

## UW usage

| Endpoint | Live | Notes |
|----------|------|-------|
| `option-contracts` | ✅ | Required for chain |
| `flow-per-strike-intraday` | ✅ `chain_mode=full` | signed flow |
| `greek-exposure/*` | offline only | calibration scripts |

## API meta extensions

```json
{
  "meta": {
    "vendor_stream": { "source": "gexbot_ws", "last_update_ms": 0, "hubs": [] },
    "vendor_levels": { "zero_gamma": 0, "major_pos_oi": 0 },
    "vendor_pin_ladder": [{ "strike": 7135, "weight": 1.0 }],
    "resonance": { "tier": "high", "score": 0.8, "axes": {}, "divergences": [], "narrative": "" }
  },
  "gate": {
    "should_trade": true,
    "reason": "ok",
    "base_should_trade": true,
    "base_reason": "ok"
  }
}
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TERMINAL_GEXBOT_WS` | `1` | Enable WebSocket structure stream |
| `TERMINAL_GEXBOT_WS_GROUPS` | see above | Comma-separated negotiate groups |
| `TERMINAL_RESONANCE_FLIP_TOL` | `15` | Flip alignment tolerance (points) |
| `TERMINAL_RESONANCE_MAGNET_TOL` | `1` | Magnet alignment (strikes) |
| `TERMINAL_GEXBOT_WS_STALE_SEC` | `15` | REST backfill after WS silence |
| `TERMINAL_VENDOR_LIVE_POLLER` | `0` when WS=1 | Avoid duplicate GEXBot REST |

## Implementation sprints

### C1 — Resonance core ✅

- [x] `terminal/resonance.py` + unit tests
- [x] `vendor_pin_ladder_from_classic` / stream payload helpers
- [x] `meta.resonance` + gate overlay in `snapshot.py`
- [x] `should_trade_with_resonance` in `factors/regime.py`

### C2 — GEXBot WebSocket ✅

- [x] `gexbot_proto/` + `gexbot_ws_decode.py`
- [x] `gexbot_stream.py` + `startup_tasks` integration
- [x] `_fetch_vendor_overlay` reads stream; REST fallback
- [x] `vendor_chain` uses stream classic when live
- [x] health / cache_status WS fields

### C3 — UI ✅

- [x] Resonance badge on instrument strip (compact + tooltip)
- [x] Vendor alignment card in Pin panel (compare + axes + max_priors)
- [x] GEXBot dashed guides on GEX heatmap + legend
- [x] Gate tooltip when blocked by `low_resonance`

### C4 — maxchange + calibration

- [ ] maxchange REST 60s
- [ ] daily flip calibration JSONL

## Acceptance gates

1. `pytest tests/test_resonance.py tests/test_gexbot_stream.py tests/test_vendor_chain.py`
2. `ruff check` on new modules
3. Vendor mode dashboard returns `meta.resonance` and `gate.base_should_trade`
4. WS disabled (`TERMINAL_GEXBOT_WS=0`) still works via REST fallback
5. ThetaData provider unaffected

## Related

- `docs/terminal/GEXBOT_MIGRATION_PLAN.md`
- `docs/PIN_PRO_UPGRADE_PLAN.md`
- [gexbot-openapi websocket.md](https://github.com/nfa-llc/gexbot-openapi/blob/master/docs/websocket.md)
- [quant-python-sockets](https://github.com/nfa-llc/quant-python-sockets)
