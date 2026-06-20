# Label Schema v1.1 Migration Plan

**Phase:** ML-P7.8.1 — Migration plan; **P7.8.2 label builder implemented**  
**Status:** v1.1 draft fields implemented in code — **formal `label_spec.md` remains v1.0.0**  
**P7.8.2 report:** [`baseline_label_builder_implementation_report.md`](baseline_label_builder_implementation_report.md)  
**Approval:** [`baseline_target_implementation_approval.md`](baseline_target_implementation_approval.md)  
**Implementation:** [`baseline_label_builder_implementation_plan.md`](baseline_label_builder_implementation_plan.md)

---

## 1. Principles

```text
v1.1 is additive.
Existing zone labels are unchanged.
Old v1.0 datasets remain readable.
Training must not mix v1.0 and v1.1 rows without explicit schema handling.
```

No breaking changes to v1.0.0 row schema. New fields are optional extensions under `labels.*` and manifest metadata.

---

## 2. Current Schema v1.0.0 Summary

From `docs/ml/label_spec.md`:

| Constant | Value |
|----------|-------|
| `label_schema_version` | `1.0.0` |
| `deterministic_contract_version` | `ml-p5-v1` |

### v1.0.0 primary labels

| Field | Role |
|-------|------|
| `close_location_vs_current_zone` | Multiclass zone (below / inside / above) |
| `close_inside_current_zone` | Binary zone membership |

### v1.0.0 related labels (unchanged in v1.1)

- `normalized_close_move`
- `close_distance_to_zone_center_*`, `close_distance_to_primary_pin_*`, `close_distance_to_secondary_pin_*`
- `close_near_primary_pin` (legacy `fixed_5pt` tolerance)
- Exit labels, forward vol, excursion labels

### v1.0.0 inclusion model

Zone-centric: rows without valid zone at as-of are excluded from zone track (`no_valid_zone_at_as_of`).

---

## 3. Additive v1.1 Fields

Proposed draft schema version: **`1.1.0-draft`** (manifest + per-row stamp).

| Field | Type | New in v1.1 |
|-------|------|-------------|
| `labels.close_distance_to_primary_pin_points` | float \| null | Explicit baseline role + eligibility (may exist in v1.0 output; semantics clarified) |
| `labels.close_distance_to_primary_pin_em` | float \| null | P0 baseline regression target |
| `labels.close_near_primary_pin_025` | bool \| null | **New** — EM threshold 0.25 |
| `labels.close_near_primary_pin_050` | bool \| null | **New** — EM threshold 0.50 |
| `labels.close_above_below_primary_pin_025` | enum \| null | **New** — optional P2 |
| `labels.close_above_below_primary_pin_050` | enum \| null | **New** — optional P2 |
| `labels.baseline_target_eligible` | bool | **New** |
| `labels.baseline_target_exclusion_reasons` | list[str] | **New** |
| `labels.baseline_label_schema_version` | string | **New** |

**Unchanged zone fields:** `close_location_vs_current_zone`, `close_inside_current_zone`, and all exit / vol labels.

---

## 4. Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| Read v1.0.0 parquet | All existing columns valid; new v1.1 columns absent → treat as pre-baseline-track dataset |
| Read v1.1.0-draft parquet | v1.0 zone columns present and semantically identical to v1.0.0 builder |
| Mixed-schema training | **Forbidden** without explicit filter on `label_schema_version` / `baseline_label_schema_version` |
| Legacy `close_near_primary_pin` | Remains `fixed_5pt`; **not** replaced by `_025` / `_050` columns |
| Downgrade v1.1 → v1.0 consumer | Zone labels still usable; baseline-specific columns ignored |

### Consumer guidance

```python
# Pseudocode — training entry guard
if manifest["label_schema_version"] not in ("1.1.0-draft", "1.1.0-approved"):
    raise SchemaError("Baseline track requires v1.1+ dataset")
```

---

## 5. Dataset Rebuild Requirements (P7.8.3)

P7.8.3 performs **label-only rebuild** on existing raw lake complete dates (same 19 dates as P7.8 screening; skip `2026-06-10`).

| Requirement | Detail |
|-------------|--------|
| Input | `artifacts/raw_lake_sample/` complete partitions |
| Pipeline | anchors → replay → deterministic bundle → **v1.1 label builder** → parquet + manifest |
| Feature build | **Not required** for P7.8.3 coverage validation |
| Joined build | **Not required** |
| Output location | New dataset version path (e.g. `artifacts/datasets/pit_v1_1_draft/`) — **gitignore** |
| Manifest | Must include §7 fields from implementation plan |
| Zone columns | Must be present and match v1.0 semantics on same anchors |

Rebuild validation compares P7.8.3 metrics to P7.8 screening summary:

```text
baseline_eligible_rows ≈ 1390 (± tolerance for builder integration)
leakage PASS
zone_included_total = 89 (unchanged)
```

---

## 6. Manifest Versioning

| Stage | `label_schema_version` | Notes |
|-------|------------------------|-------|
| v1.0 datasets (existing) | `1.0.0` | Unchanged |
| P7.8.2 unit tests / pilot rows | `1.1.0-draft` | Synthetic or single-day only |
| P7.8.3 coverage rebuild | `1.1.0-draft` | Full lake validation |
| Post-owner formal spec merge | `1.1.0-approved` | Requires `label_spec.md` update — **not P7.8.x** |

Required manifest keys (v1.1 draft):

```text
label_schema_version
baseline_target_thresholds
baseline_target_approval_record
baseline_target_addendum (source addendum doc)
baseline_implementation_commit (code commit)
baseline_leakage_validation
baseline_preferred_binary_threshold_em
zone_target_track
baseline_target_track
```

---

## 7. Test Requirements

### P7.8.2 (implementation)

| Test area | Requirement |
|-----------|-------------|
| P0 formula | Hand-computed fixture vs builder |
| Eligibility | Each exclusion reason triggers null labels |
| `remaining_em <= 0` | Excluded, no crash |
| Missing `primary_pin_t` | Excluded |
| `label_source_timestamp <= as_of` | Excluded + leakage fail |
| P1 @ 0.25 / 0.50 | Threshold boundary cases |
| P2 directional | below / near / above classification |
| Zone regression | Zone labels identical pre/post baseline addition |
| Screening parity | Builder matches `baseline_target_screening.py` on shared fixture |

### P7.8.3 (rebuild validation)

| Test area | Requirement |
|-----------|-------------|
| Coverage report | Automated comparison to P7.8 screening gates |
| Leakage module | Full leakage suite PASS on rebuilt sample |
| Manifest | All v1.1 manifest keys present |
| Zone preservation | `zone_included_total` unchanged vs P7.6.7 / P7.8 |

---

## 8. Rollback Plan

| Trigger | Action |
|---------|--------|
| Builder breaks zone labels | Revert P7.8.2 commit; continue v1.0 datasets only |
| Leakage failure in P7.8.3 | Halt rebuild; zone track unaffected; fix builder before retry |
| Coverage regression (eligible << 1390) | Investigate builder vs screening divergence; do not proceed to training |
| Owner withdraws approval | Stop v1.1 rebuild; archive draft artifacts locally; no spec merge |

Rollback does **not** delete v1.0 datasets or modify raw lake.

---

## 9. Acceptance Gate — P7.8.2

Implementation phase passes when:

```text
baseline targets implemented as additive labels
existing zone labels unchanged
label_spec.md either unchanged or updated only after explicit approval
unit tests for formula, eligibility, thresholds, leakage
no full feature build
no training
no artifacts committed
full pytest pass
ruff pass
```

**Status: PASS** — see [`baseline_label_builder_implementation_report.md`](baseline_label_builder_implementation_report.md).

Exclusion reason codes in builder (canonical):

```text
missing_primary_pin
remaining_em_invalid
missing_official_close
label_source_not_after_as_of
```

**Exit artifact:** P7.8.2 completion report + implementation commit.

---

## 10. Acceptance Gate — P7.8.3

Coverage validation phase passes when:

```text
dataset rebuilt with v1.1 draft labels
baseline_eligible_rows >= 300
eligible_sessions >= 10
P1 0.50 has both classes
leakage PASS
session-grouped split readiness PASS
zone labels still present
no training
no artifacts committed
```

**Status: PASS** — see [`baseline_dataset_rebuild_validation_report.md`](baseline_dataset_rebuild_validation_report.md).

Observed rebuild metrics (2026-06-20):

```text
row_count = 1391
baseline_eligible_rows = 1390
P1 0.50 near = 319 (screening ref 317, tolerance ±3)
zone_included_total = 89
screening_consistency_pass = true
leakage_pass = true
p783_pass = true
```

Dataset-only rebuild path: `build.dataset_only: true` in config + `--dataset-only` CLI flag.

---

## 11. Path to Formal v1.1.0 Spec

After P7.8.3 PASS:

1. ~~Owner review of rebuild coverage report~~ → **Done (P7.8.4)** — see [`baseline_dataset_gate_review.md`](baseline_dataset_gate_review.md)
2. Separate phase: merge addendum into `docs/ml/label_spec.md` as **1.1.0-approved**
3. Update manifest stamp from `1.1.0-draft` → `1.1.0-approved`
4. ML-P8B discussion **still requires separate training approval** — not automatic

---

## 11.1 Acceptance Gate — P7.8.4

Owner gate review phase passes when:

```text
baseline dataset gate review documented
P8A entry approval recorded (planning/harness only)
P7.8.3 dataset gate confirmed PASS
ML-P8B remains blocked
formal label_spec.md unchanged
no training performed
```

**Status: PASS** — see [`baseline_dataset_gate_review.md`](baseline_dataset_gate_review.md) and [`p8a_entry_approval_record.md`](p8a_entry_approval_record.md).

**Next authorized phase:** ML-P8A — Baseline Modeling Harness Plan（planning only, no training）

---

## 12. ML-P8B Remains Blocked

Even after P7.8.2 + P7.8.3 PASS:

```text
ML-P8B requires separate owner approval for training.
v1.1 draft labels do not authorize production use.
Zone track remains strict secondary; baseline track does not replace zone semantics.
```

---

**End of migration plan.**
