# Label Target Owner Review Packet

**Phase:** ML-P7.7.1 — Owner Review Packet and Label Spec Addendum v1.1 Draft  
**Status:** **Pending owner review**  
**Branch:** `research/zdte-fusion-model`  
**Related documents:**

- [`label_target_governance_report.md`](label_target_governance_report.md) — full analysis (ML-P7.7)
- [`label_target_governance_decision.md`](label_target_governance_decision.md) — decision summary (pending)
- [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md) — addendum draft

> **This packet is a proposal.** Nothing herein is approved or implemented until owner sign-off below.

---

## 1. Decision Summary

| Topic | Proposal |
|-------|----------|
| Zone label role | Keep as **strict / secondary** — do not remove |
| First baseline primary track | **Additive primary-pin distance targets** |
| Formal spec change now | **No** — addendum proposal only |
| Pin Zone contract | **No change** |
| ML-P8B | **Still forbidden** until P7.8 gates + implementation |

**One-line rationale:** Zone labels are Terminal-parity correct but too sparse (89 / ~1,393 anchors); baseline needs a high-coverage additive target without weakening frozen Pin Zone semantics.

---

## 2. Why Current Zone Target Is Insufficient Alone

### Evidence (P7.6.1 – P7.6.7)

| Metric | Value |
|--------|-------|
| screened_dates | 19 |
| dates_with_any_zone | 4 (21%) |
| included_total (zone) | **89** |
| P8B minimum included | **300** → gap **211** |
| anchor-level valid_zone_ratio | **6.4%** (need ≥ 20%) |
| negative dates (included = 0) | 15 / 19 |

### Root cause

Sparse zone labels reflect **frozen contract gates**, not data bugs:

```text
short_gamma_regime         ~50% of anchors
pin_distance_too_wide      ~37%
secondary_strength_too_low ~7%
```

Expanding dates alone (Option A) is insufficient without either many high-yield opex days or contract changes (Option D — forbidden).

---

## 3. Proposed Additive Targets

| Priority | Target | Type | Role |
|----------|--------|------|------|
| **P0** | `close_distance_to_primary_pin_em` | Regression | First baseline primary |
| **P1** | `close_near_primary_pin` | Binary | Pin-hit classification |
| **P2** | `close_above_below_primary_pin` | Ternary | Optional directional |

Full definitions: [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)

---

## 4. What Changes (If Approved)

| Area | Change |
|------|--------|
| Label governance | New **baseline track** parallel to zone track |
| Inclusion rules | `baseline_included` when `primary_pin_t` + valid EM + official_close |
| Sample weights | Separate per-track session weights (proposal) |
| Manifest | Record baseline threshold version + calibration metadata |
| ML-P8B entry target | Baseline track becomes primary for first model |
| Formal spec | Future v1.1.0 merge — **not in P7.7.1** |

---

## 5. What Does Not Change

```text
close_location_vs_current_zone     — unchanged
close_inside_current_zone          — unchanged
Pin Zone thresholds / pin_cluster    — unchanged
GEX / VEX / Expected Move / Valid Exit formulas — unchanged
Feature cutoff (<= as_of)            — unchanged
Zone strict / secondary role         — unchanged
deterministic_contract_version       — unchanged (ml-p5-v1)
docs/ml/label_spec.md (formal)       — unchanged this phase
Label builder / dataset builder      — not implemented this phase
```

---

## 6. Leakage Controls

| Control | Requirement |
|---------|-------------|
| As-of freeze | `primary_pin_t` from deterministic bundle at `as_of_timestamp` |
| Feature cutoff | All features `event_timestamp <= as_of_timestamp` |
| Label timing | `label_source_timestamp > as_of_timestamp` |
| Split | **Session-grouped split mandatory**; no row-level random split |
| Threshold calibration | Training sessions only; no test/holdout calibration |
| Calibration artifact | Versioned; session list recorded |
| Holdout | Locked before calibration; no refit on holdout |

Existing P7.6.x leakage validation (PASS on built dates) applies to zone track; baseline track must pass same checks in P7.8.

---

## 7. Required Owner Decisions

Please record **yes / no / deferred** for each item.

| # | Decision | Options | Owner response |
|---|----------|---------|----------------|
| D1 | Approve additive primary-pin baseline targets? | yes / no | __________ |
| D2 | Approve regression `close_distance_to_primary_pin_em` as P0? | yes / no | __________ |
| D3 | Approve binary `close_near_primary_pin` as P1? | yes / no | __________ |
| D4 | Approve initial near threshold candidate? | choose later / **0.25 EM** / **0.50 EM** / train-calibrated | __________ |
| D5 | Approve optional ternary `close_above_below_primary_pin` (P2)? | yes / no / defer | __________ |
| D6 | Approve keeping zone labels as strict secondary targets? | yes / no | __________ |
| D7 | Approve ML-P7.8 baseline target coverage screening? | yes / no | __________ |
| D8 | Approve separate baseline vs zone inclusion tracks? | yes / no | __________ |

**Minimum to proceed to P7.8:** D1=yes, D2=yes, D6=yes, D7=yes. D3/D4 required before P8B classification baseline.

---

## 8. Approval Checklist

- [ ] Owner reviewed `label_target_governance_report.md`
- [ ] Owner reviewed `label_spec_addendum_v1_1_proposal.md`
- [ ] D1–D8 recorded above
- [ ] No Pin Zone threshold change requested (Option D rejected)
- [ ] No fallback zone label requested (Option C rejected or deferred)
- [ ] ML-P8B remains blocked until P7.8 passes
- [ ] Sign-off name / date recorded below

### Sign-off (leave blank until approved)

```text
Owner:
Date:
Decision: Pending / Approved / Rejected / Approved with modifications
Notes:
```

---

## 9. Rollback Plan

If owner **rejects** additive baseline targets or approval is withdrawn:

1. **No code rollback required** — P7.7.1 is documentation-only.
2. Continue zone-only track with data expansion (Option A enrichment) — P8B still blocked at current coverage.
3. Revisit governance options: Option C (fallback zone) or Option D (threshold change) — both require separate review; Option D affects Terminal.
4. Do not merge addendum into formal `label_spec.md`.
5. Do not implement label builder changes.

If owner **approves** then later revokes before P7.8 implementation:

1. Halt P7.8 / any builder work.
2. Archive addendum proposal with revocation date.
3. Revert to v1.0.0 zone-only governance state.

---

## 10. Next Phase After Approval

### ML-P7.8 — Baseline Target Coverage Screening

**Scope:**

```text
implement screening only (extend P7.6.7 pattern)
measure coverage of primary_pin_distance targets
do not train models yet
do not enter ML-P8B until coverage and label distributions pass gates
```

**P7.8 gates (proposal):**

| Gate | Target |
|------|--------|
| `baseline_eligible_rows` | ≥ 300 |
| Session count | sufficient for session-grouped split |
| Binary target (`close_near_primary_pin`) | both classes present |
| Leakage validation | PASS |
| Session-grouped split | mechanism verified |

### ML-P8B (still blocked)

Entry requires **all**:

```text
P7.7.1 owner approval recorded
P7.8 baseline coverage gates pass
label builder implementation complete (future phase)
formal label_spec v1.1.0 merged (future phase)
no leakage violations
```

---

## 11. Document Status

```text
Status: Pending owner review
Not approved for implementation
Not a substitute for docs/ml/label_spec.md
```
