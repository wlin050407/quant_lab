# ML-P7.8.2 — Baseline Label Builder Implementation Report

**Phase:** ML-P7.8.2 — Additive Baseline Label Builder Implementation  
**Branch:** `research/zdte-fusion-model`  
**Approval:** [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md)  
**Plan:** [`baseline_label_builder_implementation_plan.md`](baseline_label_builder_implementation_plan.md)  
**Module:** `src/quant_lab/ml/labels.py`  
**Schema:** `src/quant_lab/ml/schemas.py`

## Status

```text
ML-P7.8.2 implementation complete — dataset rebuild deferred to P7.8.3
ML-P8B: BLOCKED
Training: NOT performed
Full dataset rebuild: NOT performed
Formal label_spec.md: UNCHANGED (v1.0.0)
```

## Implemented Fields

| Field | Type | Description |
|-------|------|-------------|
| `labels.close_distance_to_primary_pin_points` | float \| null | `official_close - primary_pin_t` (baseline-gated) |
| `labels.close_distance_to_primary_pin_em` | float \| null | P0 regression target |
| `labels.close_near_primary_pin_025` | bool \| null | P1 @ 0.25 EM |
| `labels.close_near_primary_pin_050` | bool \| null | P1 @ 0.50 EM |
| `labels.close_above_below_primary_pin_025` | enum \| null | P2 @ 0.25 EM |
| `labels.close_above_below_primary_pin_050` | enum \| null | P2 @ 0.50 EM |
| `labels.baseline_target_eligible` | bool | Baseline inclusion flag |
| `labels.baseline_target_exclusion_reasons` | list[str] | Empty when eligible |
| `labels.baseline_label_schema_version` | string | Always `1.1.0-draft` on computed rows |

**Entry point:** `compute_baseline_primary_pin_labels()` in `labels.py`, integrated via `compute_all_labels()`.

## Eligibility Rules

Baseline targets are non-null only when **all** hold:

```text
primary_pin_t is non-null
remaining_expected_move_t is finite and > 0
official_close exists
label_source_timestamp > as_of_timestamp (valid datetime)
```

Otherwise:

```text
baseline_target_eligible = false
baseline P0/P1/P2 targets = null
baseline_target_exclusion_reasons populated
```

Invalid rows do **not** crash the builder.

## Exclusion Reasons

| Code | Condition |
|------|-----------|
| `missing_primary_pin` | `primary_pin_t` null or NaN |
| `remaining_em_invalid` | EM missing, NaN, or ≤ 0 |
| `missing_official_close` | No official close |
| `label_source_not_after_as_of` | Missing/invalid timestamp or `<= as_of` |

## Thresholds

Both fixed EM thresholds implemented:

| Threshold | P1 field | P2 field |
|-----------|----------|----------|
| 0.25 EM | `close_near_primary_pin_025` | `close_above_below_primary_pin_025` |
| 0.50 EM | `close_near_primary_pin_050` | `close_above_below_primary_pin_050` |

**Preferred first binary evaluation candidate:** 0.50 EM (per owner approval).  
**0.25 EM retained** for sensitivity analysis. No final production threshold selected.

## Schema Version

| Constant | Value | Location |
|----------|-------|----------|
| `LABEL_SCHEMA_VERSION` | `1.0.0` | Row manifest top-level (unchanged) |
| `BASELINE_LABEL_SCHEMA_VERSION` | `1.1.0-draft` | Per-row `labels.baseline_label_schema_version` |

v1.0 rows without baseline fields remain readable. New fields are nullable optional extensions.

## Zone Labels — Unchanged

Verified unchanged logic for:

```text
close_location_vs_current_zone
close_inside_current_zone
first_zone_exit_direction
valid_upside_exit_15m / 30m
valid_downside_exit_15m / 30m
no_valid_zone_at_as_of
Pin Zone thresholds / pin_cluster rules
```

Legacy `close_near_primary_pin` (`fixed_5pt`) unchanged and separate from EM-threshold P1 fields.

## Baseline vs Legacy Distance Fields

`close_distance_to_primary_pin_points/em` are now **baseline-gated** in `compute_all_labels()`: set from `compute_baseline_primary_pin_labels()` and null when ineligible. Secondary/zone distance labels still use prior `compute_close_distance_labels()` path.

## Leakage Controls

```text
primary_pin_t from as-of deterministic bundle
official_close from outcome provider (label-only future)
label_source_timestamp > as_of_timestamp enforced in eligibility
features not used in baseline label computation
session-grouped split unaffected (no split logic in label layer)
```

Screening module (`baseline_target_screening.py`) refactored to import canonical functions from `labels.py`.

## Tests

```text
tests/test_baseline_label_builder.py — 19 tests (new)
tests/test_baseline_target_screening.py — 21 tests (reason codes aligned)
tests/test_ml_labels.py — pass
full pytest — pass
```

Coverage includes: P0 formulas, sign convention, all exclusion paths, P1/P2 thresholds, schema version, zone label regression, v1.0 row_dict compatibility, leakage guard in `compute_all_labels`.

## Ruff

```text
ruff check labels.py schemas.py baseline_target_screening.py test_baseline_label_builder.py — pass
```

## Not Performed

- ML-P8B training
- Full historical dataset rebuild (P7.8.3)
- Full feature build
- Formal `label_spec.md` v1.1.0 merge
- Artifacts committed

## P7.8.2 Acceptance Gate

| Gate | Result |
|------|--------|
| Baseline labels additive | **PASS** |
| Zone labels unchanged | **PASS** |
| P0/P1/P2 implemented | **PASS** |
| Eligibility / exclusion reasons | **PASS** |
| Schema version recorded | **PASS** |
| Leakage guards | **PASS** |
| Unit tests | **PASS** |
| Full pytest | **PASS** |
| Ruff | **PASS** |
| No full build / training | **PASS** |
| label_spec.md unchanged | **PASS** |

**P7.8.2 overall: PASS**

## Next Stage

```text
ML-P7.8.3 — Dataset Rebuild and Coverage Validation
```

Rebuild dataset with v1.1 draft labels on raw lake complete dates; verify coverage vs P7.8 screening (1390 eligible rows reference).

**ML-P8B remains BLOCKED.**
