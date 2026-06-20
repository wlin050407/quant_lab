# Label Target Owner Approval Record

**Phase:** ML-P7.7.2 — Owner Approval Record for P7.8 Coverage Screening  
**Branch:** `research/zdte-fusion-model`  
**Prior proposal:** ML-P7.7.1  
**Related documents:**

- [`label_spec_addendum_v1_1_proposal.md`](label_spec_addendum_v1_1_proposal.md)
- [`label_target_owner_review_packet.md`](label_target_owner_review_packet.md)
- [`label_target_governance_decision.md`](label_target_governance_decision.md)

---

## Status

```text
Status: Approved for ML-P7.8 screening only
```

This approval **does not** constitute:

- Formal adoption of addendum v1.1 into `docs/ml/label_spec.md`
- Production label builder implementation
- ML-P8B model training
- Replacement of zone targets as strict secondary targets

---

## Owner Sign-off

```text
Owner:     Weitong Lin
Date:      2026-06-20
Decision:  Approved for ML-P7.8 screening only
Notes:     Limited scope — coverage measurement and governance gates only.
           No training, no formal spec merge, no Pin Zone contract change.
```

---

## Approved Scope

The following are **approved** for ML-P7.8:

```text
Approved:
- Proceed to ML-P7.8 Baseline Target Coverage Screening.
- Screen proposed additive primary-pin targets.
- Measure coverage, class balance, eligibility, leakage safety, and session-grouped split readiness.
- Keep existing zone labels as strict / secondary targets.
- Do not train models in P7.8.
- Do not modify official docs/ml/label_spec.md in P7.8.
- Do not implement production label builder in P7.8 unless only screening-only code is required.
```

### Owner decisions (recorded)

| ID | Decision | Recorded response |
|----|----------|-------------------|
| D1 | Additive primary-pin targets | **Approved for screening only** |
| D2 | P0 regression target (`close_distance_to_primary_pin_em`) | **Approved for screening only** |
| D3 | P1 binary target (`close_near_primary_pin`) | **Approved for screening only** |
| D4 | Near threshold | **Choose later**; screen candidate thresholds **0.25 EM** and **0.50 EM** |
| D5 | P2 directional target (`close_above_below_primary_pin`) | **Screen only, optional** |
| D6 | Zone labels remain strict secondary | **Approved** |
| D7 | ML-P7.8 coverage screening | **Approved** |
| D8 | Baseline / zone dual-track inclusion | **Approved for analysis only** |

---

## Not Approved (Explicit)

The following remain **not approved**:

```text
Not approved yet:
- ML-P8B training.
- Formal replacement of zone target.
- Modification of Pin Zone thresholds.
- Modification of deterministic financial formulas.
- Production use of new targets.
- Merge of addendum v1.1 into docs/ml/label_spec.md.
- Full feature build / joined dataset build for training (unless screening-only subset).
- Ingest of new trade dates (unless separately authorized in P7.8 scope).
```

---

## P7.8 Entry Conditions (from this approval)

ML-P7.8 may proceed with:

1. **Baseline target coverage screening** on existing raw lake complete dates (reuse / extend P7.6.7 screening pattern).
2. Measurement of:
   - `baseline_eligible_rows` (proposed inclusion rule from addendum proposal)
   - `close_distance_to_primary_pin_em` non-null rate
   - `close_near_primary_pin` at **0.25 EM** and **0.50 EM** candidate thresholds
   - Optional P2 ternary distribution (if screened)
   - Zone track metrics unchanged (strict secondary)
   - Leakage safety checks
   - Session-grouped split readiness
3. **Screening-only code** if required — no production label builder unless strictly necessary for measurement.

---

## P7.8 Exit Gates (proposal — unchanged from P7.7.1)

Before any ML-P8B discussion:

| Gate | Target |
|------|--------|
| `baseline_eligible_rows` | ≥ 300 |
| Binary target | both classes present |
| Leakage validation | PASS |
| Session-grouped split | mechanism verified |
| Owner re-approval | required for training / spec merge |

Failure of P7.8 gates → remain blocked on ML-P8B; revisit governance or data expansion.

---

## Rollback

If P7.8 screening reveals unacceptable leakage risk or coverage failure:

1. Halt progression to label builder / spec merge.
2. Zone-only track continues unchanged.
3. This approval record remains valid for **re-screening** after fixes; does not auto-approve P8B.

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-20 | Initial approval for ML-P7.8 screening only |

---

**End of approval record.**
