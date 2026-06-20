# ML-P7.7 Label Target Governance Decision (Proposal)

**Phase:** ML-P7.7  
**Status:** Awaiting owner sign-off — **not implemented**  
**Full analysis:** [`label_target_governance_report.md`](label_target_governance_report.md)

---

## Decision Summary

| Question | Decision |
|----------|----------|
| Zone label as sole primary target? | **No** — retain as strict secondary |
| First baseline target? | **Yes** — pin-distance family (proposal) |
| Modify formal `label_spec.md` now? | **No** — addendum v1.1 after sign-off |
| Modify Pin Zone contract? | **No** (Option D forbidden) |
| Pin-centered fallback zone? | **No** (Option C deferred) |
| ML-P8B now? | **Forbidden** |

---

## Evidence Snapshot (P7.6.7)

```text
screened_dates:              19
dates_with_any_zone:         4
dates_with_meaningful_zone:  2  (included >= 10)
included_total:              89
valid_zone_ratio (anchor):   6.4%
negative_dates:              15
P8B included gap:            211 (to 300)
```

**Positive dates:** 2024-01-19 (48), 2024-10-04 (39), 2025-05-02 (1), 2025-01-03 (1)

---

## Approved Recommendations (Proposal)

### R1 — Zone label role

Keep `close_location_vs_current_zone` as **strict / secondary / Terminal-parity target**. Do not drop zone track.

### R2 — First baseline target (governance addendum)

| Priority | Field | Role |
|----------|-------|------|
| P0 | `close_distance_to_primary_pin_em` | Primary regression baseline |
| P1 | `close_near_primary_pin` | Binary classification |
| P2 | `close_above_below_primary_pin` | Ternary proposal (new) |

**Proposed baseline inclusion:**

```text
included when primary_pin_t != null AND official_close != null
```

Zone inclusion rule **unchanged**.

### R3 — Next phase order

1. Label spec addendum draft (v1.1 proposal)  
2. ML-P7.8 baseline coverage screening  
3. ML-P8B only after governance signed + baseline included ≥ 300  

### R4 — Data expansion

Continue raw lake + screening for **zone enrichment only**. Not sole P8B prerequisite. No blind top8 build.

---

## Option Matrix

| Option | Verdict |
|--------|---------|
| A — Expand dates, keep zone primary | Parallel enrichment only |
| B — Add pin-distance baseline | **Recommended primary path** |
| C — Fallback zone | Deferred / not recommended |
| D — Change zone thresholds | **Forbidden** without owner |

---

## Sign-off Checklist

- [ ] Owner accepts R1–R4
- [ ] Baseline tolerance config chosen (`fixed_5pt` vs EM-based)
- [ ] `label_spec` addendum v1.1 drafted
- [ ] ML-P7.8 scope approved
- [ ] ML-P8B remains blocked until baseline coverage gate passes

---

## Sparse Zone Root Cause (One Line)

Frozen contract gates (`short_gamma_regime` ~50%, `pin_distance_too_wide` ~37%) — not data gap.
