# Label Specification (ML-P6)

Supervised labels for 0DTE SPXW point-in-time dataset builder. **Labels may use future outcomes; features may not.**

## Versioning

| Constant | Value |
|----------|-------|
| `label_schema_version` | `1.0.0` |
| `deterministic_contract_version` | `ml-p5-v1` |

## Time rules

- **Features:** all context fields use data with `event_timestamp <= as_of_timestamp`.
- **Labels:** computed from outcomes with `label_source_timestamp > as_of_timestamp`.
- **Zone for labels:** must be the pinning zone from the **as-of deterministic bundle**, never recomputed after close.

## Primary multiclass label

### `close_location_vs_current_zone`

```python
if official_close < zone_low_t:
    label = "below"
elif official_close <= zone_high_t:
    label = "inside"
else:
    label = "above"
```

- Boundaries are **inclusive** on `zone_high_t`.
- `zone_low_t` / `zone_high_t` from as-of `detect_pin_cluster` on magnet rankings.
- If no valid zone at as-of: `null` + `exclusion_reason = no_valid_zone_at_as_of`.
- `official_close_source` recorded on each row.

## Binary zone label

### `close_inside_current_zone`

```python
zone_low_t <= official_close <= zone_high_t
```

Nullable when no valid zone.

## Normalized close move

### `normalized_close_move`

```python
(official_close - spot_t) / remaining_expected_move_t
```

- `spot_t`: replay index at as-of.
- `remaining_expected_move_t`: scales frozen `expected_move_1sd` by remaining session fraction (sqrt time).
- Null when expected move missing, NaN, or `<= 0`.
- **Must not** use post-close IV to compute remaining EM.

## Close distance labels

Signed distances (points and EM-normalized):

- `close_distance_to_zone_center_points` / `_em`
- `close_distance_to_primary_pin_points` / `_em`
- `close_distance_to_secondary_pin_points` / `_em`

Nullable when reference pin/zone missing.

## Strike pin proximity labels

Boolean labels with configurable tolerance (`PinToleranceConfig`):

| Config key | Tolerance |
|------------|-----------|
| `fixed_2.5pt` | 2.5 points |
| `fixed_5pt` | 5.0 points |
| `spot_0.05pct` | 0.05% of spot |
| `spot_0.10pct` | 0.10% of spot |
| `em_0.05` | 5% of remaining EM |
| `em_0.10` | 10% of remaining EM |

Labels:

- `close_near_primary_pin`
- `close_near_secondary_pin`
- `close_near_nearest_strike`

Default builder uses `fixed_5pt`; training may sweep configs in ML-P7+.

## Exit labels

Based on **future index path** vs **zone frozen at as-of**. Exit buffer uses ML-P5 frozen `zone_break` levels.

| Label | Description |
|-------|-------------|
| `first_zone_exit_direction` | `up` / `down` on first cross of zone bounds |
| `first_zone_exit_timestamp` | Timestamp of first exit |
| `minutes_to_first_exit` | Minutes from as-of to first exit |
| `exit_before_close` | Exit occurred before session close |
| `return_to_zone_after_exit` | Price re-entered zone after exit |
| `return_to_zone_within_5m/15m/30m` | Return within window after exit |
| `valid_upside_exit_15m/30m` | Path reaches `zone_break_up` within horizon |
| `valid_downside_exit_15m/30m` | Path reaches `zone_break_down` within horizon |

**Already outside zone at as-of** (`above_break` / `below_break`): exit labels null, `exclusion_reason = already_outside_zone_at_as_of`.

**No valid zone:** all exit labels null.

## Forward realized volatility

- `realized_vol_5m_forward`
- `realized_vol_15m_forward`
- `realized_vol_30m_forward`

Computed from future index returns; null when horizon coverage `< 90%` of requested minutes.

## Maximum excursion labels

Path extrema from as-of to close (no strategy direction assumed):

- `max_upside_before_close_points`
- `max_downside_before_close_points`
- `max_favorable_excursion_to_close` (close above spot)
- `max_adverse_excursion_to_close` (close below spot)

## Outcome source contract

Supported outcome fields:

- `official_close`
- `future_index_path` (columns: `event_timestamp`, `price`)
- `session_close_timestamp`
- `early_close_timestamp` (future: from session metadata)

Pilot builds use `PilotIndexOutcomeProvider` reading `index_price_1s` from `artifacts/raw_lake_pilot/`. Tests use `SyntheticOutcomeProvider`.

## Implementation

| Module | Role |
|--------|------|
| `quant_lab.ml.labels` | Label functions |
| `quant_lab.ml.schemas` | `LabelRow`, `AsOfContext`, `OutcomeContext` |
| `quant_lab.ml.datasets.point_in_time` | Builder + outcome providers |
