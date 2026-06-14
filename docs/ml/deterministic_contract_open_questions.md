# Deterministic Contract — Open Questions (ML-P5)

Items discovered during contract freeze. **No formula changes made.**

## OQ-1: Pin score always recomputes gamma

`pin_score_from_chain()` calls `compute_gex_profile()` → `add_bs_gamma_column()`, even when the input chain already carries lake **Black-76** gamma.

**Impact:** Replay bundle GEX can use precomputed gamma (`use_precomputed_gamma=True`), but **pin score** on replay path still uses recomputed gamma unless pin path is extended.

**Action:** ML-P6 label builder must declare which gamma source labels reference.

## OQ-2: Live vs replay GEX when Black-76 ≠ recomputed

Synthetic parity passes when both paths use **recomputed** gamma (`use_precomputed_gamma=False` ≡ Terminal `_row_from_chain`).

Pilot replay with lake Black-76 may differ from live recomputation on the same timestamps if IV/T inputs diverge.

**Action:** ML-P6+ backtests should log `gamma_source` in label metadata.

## OQ-3: VEX on replay

Replay bundle computes VEX via `add_bs_vanna_column` (recomputed). Lake has no native vanna partition in ML-P3.

**Action:** Accept recomputed VEX for replay until optional vanna lake family exists.

## OQ-4: Effective OI on replay pilot

Pilot uses settled OI. Live intraday may use `oi_mode='effective'` when flow deltas exist.

**Action:** Document `oi_mode` in label provenance; do not assume parity when effective OI enabled live.

## OQ-5: Gamma flip NaN on sparse synthetic chains

Symmetric small chains may yield NaN flip (no zero crossing). Tests treat NaN ≡ NaN as pass.

**Action:** None — expected behavior.
