# ML Phase Governance — QuantLab 0DTE Research

**Date:** 2026-06-11  
**Status:** **Applied** — merged into `AGENTS.md` and `ROADMAP.md` at ML-P0.5 (2026-06-11)  
**Authority chain:** `AGENTS.md` → `ROADMAP.md` → `QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md` → `.cursor/rules/quantlab-0dte-ml.mdc`

---

## 1. Purpose

This document resolves naming collisions and policy conflicts between the existing QuantLab roadmap (strategy phases 0–6) and the new 0DTE ML implementation plan (18 engineering phases). It defines when ML work is permitted, how module boundaries extend, and what Cursor must not do without owner sign-off.

**Phase 0 did not modify `AGENTS.md` or `ROADMAP.md`.** ML-P0.5 merged the amendments in Section 8 into those files.

---

## 2. Two parallel phase systems

### 2.1 ROADMAP phases (strategy / product) — prefix `ROADMAP-P`

| ROADMAP-P | Name | Role |
|-----------|------|------|
| ROADMAP-P0 | Data foundation | EoD history, quality |
| ROADMAP-P1 | Positioning factors | GEX, max pain, PCR |
| ROADMAP-P2 | Backtest + baselines | Engine validation |
| ROADMAP-P3 | EoD 0DTE approx + Pin pivot | IC, King adsorption, fly@King |
| ROADMAP-P4 | Paid intraday backtest | ThetaData spend gate |
| ROADMAP-P5 | Paper trading | tastytrade |
| ROADMAP-P6 | Live small size | Execution |

These gates control **capital, data spend, and live trading**.

### 2.2 ML phases (engineering) — prefix `ML-P`

All references in commits, Cursor prompts, and new docs must use **`ML-Pn`**, not bare "Phase n", when meaning the ML implementation plan.

| ML-P | Name (short) |
|------|----------------|
| ML-P0 | Repository & governance audit ✅ |
| ML-P0.5 | Research branch, governance merge, test baseline freeze ✅ |
| ML-P1 | ThetaData capability audit |
| ML-P2 | Storage & throughput estimator |
| ML-P3 | Immutable raw event lake |
| ML-P4 | Point-in-time replay engine |
| ML-P5 | Freeze deterministic feature contracts |
| ML-P6 | Labels + leakage-proof dataset builder |
| ML-P7 | Multi-resolution state |
| ML-P8 | GBDT baselines |
| ML-P9 | Full-chain encoder |
| ML-P10 | Event / temporal encoder |
| ML-P11 | Fusion model |
| ML-P12 | Ensemble + calibration |
| ML-P13 | Model registry |
| ML-P14 | Teacher/student deployment design |
| ML-P15 | Railway API integration |
| ML-P16 | UI integration |
| ML-P17 | Shadow mode |
| ML-P18 | Paper-trading evaluation |

**Rule:** Saying "Phase 4" without prefix is ambiguous. Cursor must ask or use `ROADMAP-P4` vs `ML-P4`.

---

## 3. Conflict resolution

### C1 — ML prohibition in AGENTS.md / ROADMAP.md

**Current text:**

- `AGENTS.md`: Do not proactively add ML / deep-learning factors; wait until after Phase 4.
- `ROADMAP.md` §不在路线图里的事: ❌ ML until Phase 4; focus on linear factors first.

**Resolution:**

1. **Interpretation:** The prohibition targets **uncontrolled ML factor injection into `factors/` or production Terminal** without data contracts, leakage tests, and walk-forward evidence. It does **not** forbid a governed parallel **`ml/` research track** that consumes existing deterministic outputs.

2. **Permitted now (after owner approves this doc):**
   - ML-P0 audit documentation ✅
   - ML-P1–ML-P2 read-only capability and storage estimates
   - ML-P3–ML-P4 infrastructure (immutable lake, replay) **without training**

3. **Requires ROADMAP-P4 readiness + ML-P6 sign-off before:**
   - Fitting models on intraday labels
   - Replacing or shadowing Terminal pin probabilities with ML outputs
   - Adding `requirements-ml.txt` to any production install path

4. **Always forbidden (both tracks):**
   - Automatic order execution
   - Silent changes to Pin/GEX/VEX math in `factors/`
   - Row-level random train/test splits on intraday data

### C2 — AGENTS.md "current phase = Phase 0"

**Resolution:** Treat `AGENTS.md` phase pointer as **stale**. Authoritative status lives in `ROADMAP.md` + `README.md` (Phases 0–3 complete; Terminal productization + ROADMAP-P4 intraday next). Proposed AGENTS.md patch in Section 8.

### C3 — Production authority

| Layer | Authority until ML-P12 + owner approval |
|-------|----------------------------------------|
| Pin zone, King, GEX/VEX levels | `factors/` + `terminal/snapshot.py` |
| Pin Play entry/exit rules | `docs/PIN_PLAY_SPEC.md` + `pin_playbook.py` |
| Terminal user-facing probabilities | Deterministic engine or explicit "research" badge |
| ML predictions | Research artifacts only; Railway fallback to deterministic |

---

## 4. Approved module boundary: `src/quant_lab/ml/`

### 4.1 Charter

The `ml/` package is **approved in principle** as a sibling to `backtest/` and `strategies/`:

```text
data/       → fetch, store, replay (network + I/O allowed)
quality/    → validate, leakage checks (read-only on data)
factors/    → deterministic features (NO network, NO training)
ml/         → datasets, labels, splits, training, calibration, registry, inference
terminal/   → assemble API payloads; call ml/inference when deployed
backtest/   → PnL from signals (may consume ml predictions as inputs later)
strategies/ → time-series position logic (may consume ml outputs later)
```

### 4.2 `ml/` responsibilities

| Submodule | Purpose |
|-----------|---------|
| `ml/schemas.py`, `contracts.py` | Versioned feature/label schemas |
| `ml/labels.py`, `splits.py` | Session-grouped labels; no random row splits |
| `ml/datasets/` | Point-in-time tabular, chain, event builders |
| `ml/features/` | Wrappers over `factors/` + learned featurizers |
| `ml/models/` | GBDT, encoders, fusion (candidates, not defaults) |
| `ml/training/` | Runners, OOF, walk-forward evaluation |
| `ml/calibration.py` | Probability calibration (distinct from `factors/calibration.py`) |
| `ml/registry.py`, `inference.py` | Artifact versioning; CPU student inference |

### 4.3 Hard rules for `ml/`

- **No network I/O** inside `ml/features/` or `ml/models/` — pull data via `data/` loaders only.
- **No duplicate** of `compute_gex_profile`, `pin_score_from_chain`, etc. — import from `factors/`.
- **Every artifact** carries: model version, dataset version, feature schema, label spec, git SHA, data cutoff timestamp.
- **Advanced models** must beat transparent baselines on pre-registered metrics or be rejected (ML plan §0.3).

### 4.4 Extensions to existing modules (approved targets)

New files only (no formula edits unless spec change):

```text
src/quant_lab/data/intraday_lake.py
src/quant_lab/data/intraday_manifest.py
src/quant_lab/data/point_in_time_replay.py
src/quant_lab/quality/intraday_integrity.py
src/quant_lab/quality/replay_integrity.py
src/quant_lab/quality/leakage_checks.py
config/ml/*.yaml
requirements-ml.txt          # local research profile; NOT Railway default
```

---

## 5. Data and leakage governance

### 5.1 Immutability

- Raw ThetaData/event partitions: **append-only**; never overwrite incomplete partitions silently.
- Manifests with checksums and schema version required before ML-P6 dataset builds.

### 5.2 Point-in-time

At prediction time `t`, features may use only events with `source_timestamp <= t`.

Forbidden without explicit revised-data flag:

- Final daily option volume
- Next-day OI
- Close recomputed pin zones applied to earlier timestamps
- Post-release macro values before release time

### 5.3 Splits

- Group by **complete trading session** (ML plan §2.5).
- Maintain a **locked final holdout** not used for any hyperparameter decision.
- OOF predictions for any stacking/ensemble.

### 5.4 Language

All dealer positioning outputs: **model-implied** / **OI-based estimate** — never "observed dealer inventory."

---

## 6. Dependency and deployment governance

| Environment | Dependencies | ML stack |
|-------------|--------------|----------|
| Railway / Docker prod | `requirements.txt` only | CPU student + **deterministic fallback** if model missing |
| Local RTX research | `requirements-ml.txt` (`-r requirements.txt` + sklearn/lightgbm/torch/…) | Teacher training |

**Rules:**

- Do not add PyTorch to Railway `requirements.txt` until ML-P14 proves CPU inference path and size budget.
- Do not expose local laptop as unauthenticated public endpoint.
- Every `/api/ml/*` response includes: model version, schema version, timestamp, quality flags, prediction source (`student` | `teacher` | `deterministic_fallback`).

### 6.1 Ruff baseline (ML-P0.5)

- **Known debt:** the repository currently has **157** Ruff findings repo-wide (`python -m ruff check src tests scripts`, frozen 2026-06-11). Do not mass-fix in ML phases unless explicitly scoped.
- **Rule from ML-P0 onward:** every Python file **added or modified** by an ML phase must pass Ruff in isolation before that phase is marked complete.
- Record phase-local Ruff commands and pass/fail in the phase report.

---

## 7. Git workflow

| Rule | Value |
|------|-------|
| Branch | `research/zdte-fusion-model` (feature branch, not `main`) |
| Commits | One per completed ML-P phase; prefix `chore(ml):`, `feat(ml):`, `feat(data):`, etc. |
| Cursor | One ML-P prompt at a time; stop at acceptance gate |

---

## 8. Applied amendments (ML-P0.5)

The following were merged into `AGENTS.md` and `ROADMAP.md` on 2026-06-11.

### 8.1 `AGENTS.md` — replace stale phase pointer + clarify ML

```markdown
## 项目阶段

- **ROADMAP 当前重心**：Phase 4 付费 intraday Pin Play 真回测（见 `ROADMAP.md`）。
- **ML 研究轨**：见 `QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md` 与 `docs/ml/ml_phase_governance.md`；
  使用 `ML-Pn` 编号，与 ROADMAP Phase 0–6 区分。
- 阶段路线图、出口判据、决策门见 `ROADMAP.md`。
- **没达成当前 ROADMAP 阶段出口判据**之前，**不要**提前进入该阶段的执行/花钱步骤。
```

Replace "不要主动建议加 ML" bullet with:

```markdown
- 不要在没有 `docs/ml/` 数据契约、泄漏测试和 walk-forward 证据的情况下，把 ML 因子塞进 `factors/` 或替换 Terminal 确定性引擎。
  受治理的 `src/quant_lab/ml/` 研究轨除外（见 `docs/ml/ml_phase_governance.md`）。
```

Add module row:

```markdown
| `ml/` | 数据集、训练、校准、注册、推理 | 网络 I/O、改 factors 公式、自动下单 |
```

### 8.2 `ROADMAP.md` — add ML research track note

After §不在路线图里的事, add:

```markdown
### ML 研究轨（平行，不替代上述门）

- 0DTE ML 工程计划见 `QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md`（`ML-P0`–`ML-P18`）。
- ML 基础设施（审计、replay、泄漏测试）可在 ROADMAP-P4 前启动；**模型训练与 Terminal 替换**需 ROADMAP-P4 数据基础 + ML-P6 标签规范签署。
- 详见 `docs/ml/ml_phase_governance.md`。
```

Update ML bullet:

```markdown
- ❌ 未治理的 ML / 深度学习因子：不要直接塞进 `factors/` 或 production Terminal
- ✅ 受 `ml/` 模块治理的研究轨：见 `docs/ml/ml_phase_governance.md`
```

### 8.3 `README.md` — documentation table row

```markdown
| [`QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md`](./QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md) | 0DTE ML 分阶段工程计划（`ML-P0`–`ML-P18`） |
| [`docs/ml/ml_phase_governance.md`](./docs/ml/ml_phase_governance.md) | ML 与 ROADMAP 阶段并行治理 |
```

---

## 9. Cursor operating contract (effective immediately via `.cursor/rules/`)

1. Execute **only** the ML-P phase explicitly requested.
2. Read: `AGENTS.md`, `ROADMAP.md`, `README.md`, `QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md`, this file.
3. Do not modify financial formulas, API behavior, or `requirements.txt` unless the active ML-P scope says so.
4. End every phase with: files changed, commands, test results, risks, acceptance gate status.
5. Stop after the requested phase; wait for owner review.

---

## 10. Decision log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-11 | Adopt `ML-Pn` prefix | Eliminate Phase 4 collision (ROADMAP vs ML) |
| 2026-06-11 | Approve `src/quant_lab/ml/` boundary in writing | Extends architecture without breaking `factors/` purity |
| 2026-06-11 | Keep deterministic Pin/GEX as production authority | ML is candidate until walk-forward + calibration gates pass |
| 2026-06-11 | ML-P0.5 governance merge + Ruff baseline | AGENTS/ROADMAP updated; 157 Ruff debt frozen |
| 2026-06-11 | Defer AGENTS/ROADMAP edits to owner | Phase 0 scope: propose, not apply — **superseded by ML-P0.5** |
| 2026-06-11 | ML-P0 gate conditional on 3 pre-existing test failures | Documented in `repository_audit.md` §16–18 |

---

## 11. Next step

**Owner review checklist (ML-P0.5):**

- [x] Section 8 amendments merged into `AGENTS.md` / `ROADMAP.md`
- [ ] Fix or waive `tests/test_terminal_m4.py` failures (3 tests) — see [`preexisting_test_failures.md`](./preexisting_test_failures.md)
- [ ] Authorize **ML-P1** prompt: ThetaData capability audit (read-only probes, no bulk download)

**Do not** authorize bulk historical tick download or model training until ML-P1–P6 gates pass.
