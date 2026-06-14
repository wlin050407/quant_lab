# ML-P7.6.2 Label Spec Governance Options (Proposal Only)

**Phase:** ML-P7.6.2 — Long-Gamma Candidate Discovery  
**Status:** Proposal — **not implemented** (requires owner sign-off)  
**Formal label spec (`docs/ml/label_spec.md`) unchanged this phase.**

## Context

ML-P7.6.1 confirmed:

- Adapter bug fixed (regime + pin_reliability passed to `detect_pin_cluster`)
- Frozen Pin Zone contract gates block zone on short-γ sessions and weak secondary pins
- Stage A three dates: **valid_zone_ratio = 0%**

ML-P7.6.2 scans hourly anchors across up to 19 candidate dates to find long-γ sessions with valid zones.

## Trigger for Governance

If Stage A+ (long-gamma-aware sample) still shows:

```text
valid_zone_ratio < 20%
included_rows < 100
inside/below/above categories < 2
```

then zone-based primary label is **too sparse for ML-P8B baseline** without contract or target changes.

## Options

### Option A — Keep Zone Label; Expand Sampling (Recommended First)

- Retain `close_location_vs_current_zone` as primary supervised target
- Expand date sample biased toward long-γ / range / pinning-style sessions
- Re-evaluate coverage after 20+ long-γ-aware dates ingested
- **No formula or label spec change**

### Option B — Add `primary_pin_distance` Baseline Target

- First baseline model predicts distance from close to `primary_pin_t`
- Zone label remains secondary / evaluation-only
- Requires label spec addendum (new column, inclusion rules)
- **Does not change Pin Zone formula**

### Option C — Pin-Centered Fallback Zone Label

- When frozen contract produces no cluster, define fallback zone from primary pin ± buffer
- **Changes label semantics** — distinct from Terminal Pin Zone contract
- Must be documented as ML-only fallback, not Terminal parity

### Option D — Modify Pin Zone Thresholds

- Change `CLUSTER_MIN_STRENGTH_RATIO`, `CLUSTER_MAX_DIST_PCT`, or short-γ gate in `pin_cluster.py`
- **Changes deterministic contract** — forbidden without explicit owner sign-off
- Would affect Terminal, replay, and ML simultaneously

## Recommendation

1. Complete long-γ candidate ingest + Stage A+ rebuild (Option A path)
2. If coverage remains < 20%, pursue **Option B** for first baseline while keeping zone label for Phase 2 evaluation
3. **Do not** pursue Option D without governance review

## ML-P8B Gate

Do **not** enter ML-P8B until:

- `valid_zone_ratio >= 20%`, OR
- Governance approves Option B/C with updated label spec
