# Pin Center Fusion — MM Structure × Local Physical (Optimal Pin Play)

**Branch:** `feature/pin-center-fusion`  
**Status:** F4 backtest hook shipped · V1 full replay gate pending (n≥200 GEXBot hist sessions)  
**Parent design:** [VENDOR_RESONANCE_V2.md](./VENDOR_RESONANCE_V2.md) · [PIN_PLAY_SPEC.md](../PIN_PLAY_SPEC.md)  
**Reference algorithm:** `SPX_MM_STRUCTURE_ALGORITHM.md` (external rule engine)

## 1. Problem statement

Pin Play @ King requires **four decisions** every session:

| ID | Decision | Current quant_lab | Gap |
|----|----------|-----------------|-----|
| **D1** | Fly center **K** (where spot may pin) | `king_dte1` only | No multi-source strike; no primary/secondary |
| **D2** | Trade today? (regime) | `long_gamma` from local net GEX | OK; add MM `unstable_near_flip` overlay |
| **D3** | Size (conviction) | `pin_score` + Playbook multipliers | OK; fuse structure conflict into size |
| **D4** | Enter now or wait? | Time window + gate | No momentum / structure-tape conflict |

**Goal:** Keep **auditable local chain** for pin_score and GEX heatmap; add **MM-style structure layer** for attraction targets and intraday dynamics; **fuse** into `pin_center` for Playbook fly body.

## 2. Design principles (non-negotiable)

1. **Dual truth — never blend heatmaps**
   - **Physical lane:** UW chain → `factors/gex.py` / `positioning.py` (audit, pin_score, King_bs).
   - **Structure lane:** GEXBot classic + orderflow (+ future state hubs) → `mm_structure.py`.
   - UI shows **both**; fusion affects **Playbook K** and **size**, not raw GEX bars.

2. **pin_score stays the sizing engine**
   - Do not replace pin_score with MM `confidence` (different semantics, FlashAlpha alignment, Phase 3e evidence).

3. **pin_center is the only Playbook fly K**
   - King_bs remains a **candidate**, not the default center.

4. **Module boundary**
   - `factors/` — pure, no network.
   - `terminal/mm_structure.py` — vendor structure rules (may read stream state).
   - `terminal/pin_center.py` — fusion of Physical + Structure snapshots.
   - `terminal/pin_playbook.py` — execution summary only.

5. **Walk-forward validation before parameter lock**
   - Fusion weights start as documented defaults; promotion requires offline V1/V2 gates (§8).

## 3. Layer architecture

```text
L0 Ingest
  UW option-contracts ──► chain snapshot
  GEXBot WS classic + orderflow ──► VendorStreamState
  structure_history ring buffer (1m samples, 30m window)

L1 PhysicalSnapshot  (from chain + factors/)
  king_bs, flip_bs, walls_bs, max_pain, pin_score, regime_local,
  pct_gex_dte1, expected_move, heatmap rows

L2 StructureSnapshot  (mm_structure.py)
  regime_mm, primary_mm_target, secondary_mm_target,
  call_wall_of, put_wall_of, gamma_flip_vendor,
  momentum_state, momentum_score, execution_state,
  attraction_profile[], structure_bias

L3 PinCenterDecision  (pin_center.py)
  pin_center, center_source, center_confidence,
  center_alts[], size_multiplier_overlay, entry_blocked_reason

L4 PinPlaybook  (pin_playbook.py)
  K = pin_center, size = pin×regime×gate×center_overlay,
  entry_allowed respects execution_state + D4
```

## 4. Data contracts

### 4.1 PhysicalSnapshot (input to fusion)

```python
@dataclass
class PhysicalSnapshot:
    spot: float
    king_bs: float | None
    flip_bs: float | None
    call_wall_bs: float | None
    put_wall_bs: float | None
    max_pain: float | None
    pin_score: float | None
    regime_local: str  # long_gamma | short_gamma | undetermined
    pct_gex_dte1: float | None
    expected_move_1sd: float | None
    magnet_strike: float | None  # from pin_score_from_chain
```

### 4.2 StructureSnapshot (MM-aligned, §15 JSON)

```python
@dataclass
class StructureTarget:
    level: float
    score: float
    distance_pts: float
    sources: list[str]

@dataclass
class AttractionRow:
    level: float
    score: float
    visual_strength: float  # 0–100, display only
    side: str  # up | down | pin
    sources: list[str]

@dataclass
class StructureSnapshot:
    regime: str  # positive_gamma | negative_gamma | unstable_near_zero_gamma | transition
    trend_state: str  # bullish | bearish | neutral
    momentum_state: str  # up_momentum | down_momentum | mixed_momentum | flat_momentum
    momentum_score: float
    primary_mm_target: StructureTarget | None
    secondary_mm_target: StructureTarget | None
    call_wall: float | None  # orderflow zero_major_call_gamma
    put_wall: float | None   # orderflow zero_major_put_gamma
    gamma_flip: float | None  # classic zero_gamma
    execution_state: str
    attraction_profile: list[AttractionRow]
    structure_bias: float  # -1..1
```

### 4.3 PinCenterDecision (output)

```python
@dataclass
class PinCenterDecision:
    pin_center: float
    center_source: str  # fused | king_bs | primary_mm | max_priors | max_pain | close_pin
    center_confidence: str  # high | medium | low
    candidates: dict[str, float]  # labeled strikes
    size_overlay: float  # multiply Playbook size (0..1)
    entry_blocked: bool
    entry_blocked_reason: str | None
    narrative: str
```

## 5. MM structure engine (phased)

### P0 — classic + orderflow (this branch)

**Inputs:** decoded `classic` gex_zero, decoded `orderflow`, `structure_history` trends.

**Candidates (5pt grid):**
- classic: `zero_gamma`, `major_pos_vol`, `major_pos_oi`, `major_neg_vol`, `major_neg_oi`
- classic: each `max_priors` strike (weight from prior value)
- classic: `strikes[]` with |value_1| or |value_2| above threshold
- orderflow: `zero_major_call_gamma`, `zero_major_put_gamma`, long/short gamma majors

**Scoring:** Port MM doc §6 with **Pin Play family weights** (not raw MM defaults):

```text
source_strength = γ + vex×(w_vex/w_γ) + iv×(w_iv/w_γ) + other   # vanna scaled down vs MM additive sum
family_mix      = w_gamma*γ_norm + w_vex*vex_norm + w_iv*iv_norm
confidence      = clamp(34 + 30*source_norm + 20*distance_shape + 18*family_mix + …)
```

| Profile | w_γ | w_vex | w_iv | Use |
|---------|-----|-------|------|-----|
| MM reference | 0.45 | 0.30 | 0.25 | External MM app §6 |
| **Pin Play P0** | **0.72** | **0.12** | **0.16** | Fly center / D1 (default) |

**Why downweight vanna:** 0DTE pin center is a **gamma/OI magnet** question (D1). Vanna/VEX drives vol–spot hedge flow (D2/D4, sizing context) — matching MM's 30% vex in `family_mix` over-rotates primary target toward vol-sensitive strikes. Env: `MM_FAMILY_GAMMA_W`, `MM_FAMILY_VEX_W`, `MM_FAMILY_IV_W`.

P0: `vex_strength` and `iv_strength` = 0 until state hubs + IV surface (P1).

**Regime:** MM §3.1 using `zero_gamma`, `sum_gex_vol`, spot, `zero_gamma_band=5`.

**Momentum P0:** Simplified flow_bias from `dex_orderflow`, `gex_orderflow`, `zero_net_total_dex`; gex_delta from history `sum_gex_vol` 5m/15m % change.

**Execution states P0:**
- `dynamic_conflict_pin_wait` — |momentum_score|≥0.22 and sign disagrees with structure_bias
- `at_mm_target_pin_or_take_profit` — |spot - primary| ≤ 5pt
- `macro_target_watch` — default when primary exists
- `transition` — insufficient data

### P1 — state hubs + IV surface

- WS groups (opt-in `TERMINAL_GEXBOT_WS_STATE=1`): `SPX_state_gamma_zero`, `SPX_state_vanna_zero`, `SPX_state_charm_zero`, `SPX_state_delta_zero`
- State GEX messages use same `gex.proto` decode; routed to `VendorStreamState.state_hubs` (do not overwrite classic)
- Hub ingest weights (relative): gamma 0.50, **vanna 0.22**, charm 0.18, delta 0.12 — still subordinate to Pin Play family_mix
- `iv_surface.py`: quadratic smile fit → `iv_floor_strike` candidate on local chain
- `structure_version: p1` when any state hub present

### P2 — tuned parameters + offline replay

- Grid search on GEXBot hist (2026+ sessions) for fusion weights
- Compare King vs primary vs fused pin_center @ 13:00 → close distance

## 6. Pin center fusion rules (default)

Parameters (env-overridable):

| Param | Default | Meaning |
|-------|---------|---------|
| `PIN_CENTER_STRIKE_TOL` | 5.0 | SPX points — "same strike" |
| `PIN_CENTER_DIVERGE_TOL` | 10.0 | local vs primary → low confidence |
| `PIN_CENTER_CONFLICT_SIZE` | 0.5 | size overlay when diverged |
| `PIN_CENTER_CLOSE_PIN_MINUTES` | 90 | MM close_pin_factor window |
| `MM_FAMILY_GAMMA_W` | 0.72 | structure family_mix gamma weight |
| `MM_FAMILY_VEX_W` | 0.12 | structure family_mix vanna weight (below MM 0.30) |
| `MM_FAMILY_IV_W` | 0.16 | structure family_mix IV weight |

**Algorithm:**

```text
1. Collect candidates:
   C_king   = king_bs
   C_pri    = primary_mm_target.level
   C_sec    = secondary_mm_target.level
   C_prior  = argmax(max_priors weight)
   C_pain   = max_pain
   C_close  = round_to_5(spot) if minutes_to_close <= 90 else None

2. Consensus:
   IF all finite(C_king, C_pri, C_prior)
      AND |C_king - C_pri| <= STRIKE_TOL
      AND |C_king - C_prior| <= STRIKE_TOL
      → pin_center = round_to_5(mean(C_king, C_pri))
      → confidence = HIGH, source = fused

   ELIF |C_king - C_pri| > DIVERGE_TOL
      IF pin_score >= 70 AND momentum NOT conflicting AND execution allows
         → pin_center = C_pri, confidence = MEDIUM, source = primary_mm
      ELSE
         → pin_center = C_king, confidence = LOW, source = king_bs
         → size_overlay *= CONFLICT_SIZE

   ELSE
      → pin_center = C_king or C_pri or C_pain (first finite)
      → confidence = MEDIUM

3. Close pin boost (visual + center tie-break only):
   IF C_close within STRIKE_TOL of pin_center → note close_pin in narrative
   IF minutes_to_close <= 90 AND pin_score >= 60 AND |C_close - C_king| > STRIKE_TOL
      → prefer C_close IF execution_state is pin-friendly

4. Entry block (D4):
   IF execution_state in {dynamic_conflict_pin_wait, macro_micro_conflict_wait}
      → entry_blocked = true
   IF center_confidence == LOW AND pin_score < 75
      → entry_blocked = true (extends low_resonance philosophy)
```

## 7. Playbook integration

- `_build_structure(center=pin_center, center_source=...)`
- `size_multiplier *= pin_center_decision.size_overlay`
- `actionable = actionable AND NOT pin_center_decision.entry_blocked`
- New PlaybookCheck: **Structure alignment** (primary vs king, execution state)

**API meta extensions:**

```json
{
  "meta": {
    "structure": { "...StructureSnapshot..." },
    "pin_center": { "...PinCenterDecision..." }
  }
}
```

## 8. Validation gates

### V1 — Strike accuracy (offline, no PnL)

Script: `scripts/validate_pin_center_offline.py`

- Sessions: SPY proxy 2010–2025 + GEXBot hist 2026 when available
- Clock: 13:00 ET information set
- Metrics: median |close - K| for K ∈ {king_bs, primary_mm, pin_center_fused}
- **Pass:** fused median ≤ min(king, primary) on pin≥70 + long_γ cohort; n ≥ 200

### V2 — Structure target hit rate

- GEXBot hist replay, 1m sample
- Same metrics as MM doc §11 (30m/1h/2h success)
- **Pass:** primary_mm_target 30m success ≥ 55% (sanity, not production guarantee)

### V3 — Pin Play PnL proxy

- Extend Phase 3f: fly@pin_center vs fly@king vs fly@spot
- **Pass:** pin_center equal-weight PnL ≥ fly@king (SPY EoD proxy until Phase 4)

### V4 — Live Terminal acceptance (P0 ship)

- [ ] `/api/snapshot` returns `meta.structure` + `meta.pin_center`
- [ ] Playbook fly center uses `pin_center`, shows source + confidence
- [ ] Unit tests: mm_structure scoring, pin_center fusion paths, playbook blocked entry
- [ ] pytest + ruff green

## 9. Implementation sprints

| Sprint | Deliverables | Gate |
|--------|--------------|------|
| **F0** (now) | spec, branch, `structure_history`, `mm_structure` P0, `pin_center`, snapshot/playbook wire, tests | V4 |
| **F1** | extend orderflow decode, attraction UI panel, history trends in API | visual review — **attraction panel + fused center in Playbook shipped** |
| **F2** | state hub WS groups, IV surface module | V2 on 2026 hist |
| **F3** | `pin_center_replay.py`, validate `--replay`, Playbook structure check, trends | V1/V2 when hist cached |
| **F4** | Phase 4 intraday + EoD backtest `center_mode=fused` via `pin_center_backtest.py` | ROADMAP Phase 4 — **shipped** |

## 10. Files (F0)

| Path | Role |
|------|------|
| `src/quant_lab/terminal/structure_history.py` | Ring buffer for classic/orderflow samples |
| `src/quant_lab/terminal/mm_structure.py` | StructureSnapshot builder |
| `src/quant_lab/terminal/pin_center.py` | Fusion decision |
| `src/quant_lab/data/gexbot_ws_decode.py` | Extended orderflow fields |
| `src/quant_lab/data/gexbot_stream.py` | Append history on WS tick |
| `src/quant_lab/terminal/snapshot.py` | Wire L1–L3 into dashboard |
| `src/quant_lab/terminal/pin_playbook.py` | Use pin_center |
| `src/quant_lab/terminal/pin_center_backtest.py` | EoD/intraday fused center for backtests |
| `scripts/run_zdte_pin_fly_eod_backtest.py` | Compare king / spot / fused |
| `scripts/run_zdte_pin_fly_intraday_backtest.py` | `--center king|fused|compare` |
| `tests/test_pin_center.py` | Fusion rules |
| `scripts/validate_pin_center_offline.py` | V1 stub |

## 11. Risks

- GEXBot field semantics may differ from MM reference repo — calibrate with side-by-side JSON capture.
- P0 without IV/state hubs: primary_mm may diverge from full MM app — document as `structure_version: p0`.
- Ring buffer empty on cold start → momentum flat, execution conservative (wait-friendly).
