# Deterministic Feature Contract (ML-P5)

Frozen contract for QuantLab 0DTE deterministic outputs consumed by Terminal, replay, and future ML labels.

## Governance

- **Dealer positioning** is a **model-implied / OI-based assumption**, not observed dealer inventory.
- **OI semantics remains unconfirmed** until ThetaData official confirmation.
- **Black-76 gamma is derived gamma**, not ThetaData native second-order gamma.
- **NBBO quote ticks are not Level 2** order book data.

Formula changes require owner sign-off per `docs/ml/ml_phase_governance.md` §8 — not silent edits in `factors/` or Terminal.

---

## Paths

| Path | Entry | Gamma source |
|------|-------|--------------|
| **Live / Terminal** | `terminal/snapshot.py` → `_row_from_chain()` | Recomputed via `add_bs_gamma_column` inside `compute_gex_profile` |
| **Replay** | `replay_state()` → `to_deterministic_input_frame()` → `compute_deterministic_bundle()` | Lake `derived_gamma_black76_1m` when `use_precomputed_gamma=True` |
| **Historical adapter** | Same as replay on lake partitions | Same as replay |

Parity rule: **same normalized input + same gamma source → same outputs**. Live path and replay precomputed-gamma path may differ when Black-76 lake gamma ≠ recomputed BS/Black-76 (documented open question).

---

## Normalized deterministic input schema (frozen)

Defined in `DETERMINISTIC_INPUT_COLUMNS` (`point_in_time_replay.py`):

```text
strike, right, open_interest, spot, implied_vol, gamma, gamma_method,
gamma_method_version, bid, ask, mid, expiration, time_to_expiry_years,
contract_identifier, quote_timestamp, greek_timestamp, oi_event_timestamp,
oi_semantics_status, oi_publication_time_confirmed, data_quality_flags
```

### Missing-data rules

| Field | Missing behavior |
|-------|------------------|
| `gamma` | Row **excluded** from GEX aggregation (`dropna` on gamma) — **not** treated as 0 |
| `open_interest` | Coerced to 0 in factor chain numeric path |
| `implied_vol` | NaN → ATM IV / expected move may be NaN |
| `oi_semantics_status` | Default replay: `unconfirmed` |
| `data_quality_flags` | Pipe-separated string; preserved in bundle |

---

## Outputs

### GEX / VEX

| Output | Definition | Units | OI | Gamma |
|--------|------------|-------|-----|-------|
| Net GEX | Σ gamma × OI × 100 × spot² × dealer_sign | USD per $1 spot move | Yes | Yes (BS/Black-76) |
| Gamma Flip | Spot where net GEX crosses zero | Index points | Yes | Yes |
| Call / Put Wall | Strike with max call-side / put-side signed GEX | Index points | Yes | Yes |
| King Node | Strike with max \|net GEX\| | Index points | Yes | Yes |
| Net VEX | Σ vanna × 0.01 × OI × 100 × spot × dealer_sign | USD delta hedge per 1% IV | Yes | Vanna (recomputed) |

**Dealer sign (SpotGamma convention):** calls +1, puts −1 (`DEFAULT_DEALER_SIGN` in `gex.py`).

**Gamma:** Replay uses **derived Black-76** from lake; live recomputes from IV + T via `add_bs_gamma_column` (BS76 for ^SPX).

### Effective OI

FlashAlpha-aligned proxy in `effective_oi.py` — optional `oi_mode='effective'` for pin/GEX when flow deltas exist. Replay pilot uses **settled OI** unless enriched.

### Pin Score

Composite 0–100 (`positioning.pin_score`): OI 30%, proximity 25%, time 25%, gamma 20%. Model version `PIN_SCORE_MODEL_VERSION = v2`.

### Expected Move

`expected_move_1sd`: `spot × IV × sqrt(T)` — prefer intraday `time_years`; EoD fallback `dte/365`.

### Pinning Zone (`pin_cluster.py`)

Merge when **both**:

- `abs(primary - secondary) / spot < 0.003` (0.3%)
- `secondary_strength / primary_strength >= 0.70`

Buffer: `max(tick_floor, 0.25 × zone_width)` — SPX tick floor **5 points**.

Spot zone states: `inside_zone`, `testing_upside_exit`, `testing_downside_exit`, `above_break`, `below_break`.

### Valid Exit

Zone break levels = zone high/low ± buffer. **Bar confirmation** (5m close) is live-only (Terminal Phase 4); replay exposes levels only.

### Pin Playbook

`terminal/pin_playbook.py` — session phase gates, size multipliers; not recomputed in replay bundle (Terminal-only).

---

## Data quality metadata

Replay: `ReplayQuality` + `data_quality_flags` per contract + warnings (`oi_semantics_unconfirmed`, stale quote, etc.).

Terminal: `_positioning_data_meta`, live pin reliability tiers.

---

## Frozen API (ML-P5)

```python
to_deterministic_input_frame(option_chain, spot=...) -> DataFrame
deterministic_input_to_factor_chain(input_df, spot=...) -> DataFrame
compute_deterministic_bundle(input_df, spot, *, use_precomputed_gamma=True) -> DeterministicBundle
```

---

## Change control

| Change type | Process |
|-------------|---------|
| Schema column add/remove | ML phase gate + contract doc update |
| GEX/Pin formula | Owner + ROADMAP-P1 review; **not** ML-P6 without sign-off |
| Dealer sign convention | Explicit `dealer_sign` param + doc |
| OI semantics upgrade | ThetaData confirmation + lake schema bump |
