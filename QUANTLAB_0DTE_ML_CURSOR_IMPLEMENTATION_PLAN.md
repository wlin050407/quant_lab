# QuantLab 0DTE Machine Learning System
## Cursor Implementation Master Plan

**Version:** 1.0  
**Date:** 2026-06-10  
**Target repository:** `wlin050407/quant_lab`  
**Primary scope:** SPX/SPXW 0DTE pinning, close distribution, and zone-exit probability research  
**Execution environment:** Local RTX 5080 Laptop for research/training; Railway for the existing web application and CPU-safe inference  
**Document role:** Source of truth for Cursor implementation. Cursor must execute this document phase by phase, not as a one-shot request.

---

# 0. Executive decision

## 0.1 Can Cursor build this?

Yes. Cursor is suitable for:

- auditing the existing repository;
- adding data-ingestion and replay infrastructure;
- implementing typed schemas and tests;
- building feature pipelines;
- training baseline and deep-learning candidates;
- creating evaluation and calibration tooling;
- integrating a production-safe inference API;
- adding UI components for model output;
- writing documentation and migration scripts.

Cursor is **not** allowed to make independent decisions about:

- the financial meaning of a label;
- what counts as a valid pin or exit;
- whether a timestamp is point-in-time valid;
- whether a backtest is acceptable;
- whether a result is safe to call a trading signal;
- whether a model is “best” because one headline metric improved;
- whether a new model can replace the deterministic Pin/GEX engine.

Those decisions are frozen in specifications and acceptance gates in this document.

## 0.2 Should this whole document be pasted into Cursor once?

No.

Place this file in the repository root and tell Cursor to read it. Then issue **one phase prompt at a time**. Each phase ends with:

1. code;
2. tests;
3. a written phase report;
4. an acceptance gate;
5. a git commit.

Cursor must not continue to the next phase until the current phase passes.

## 0.3 What is the strongest realistic implementation?

The research program should preserve and exploit all available data, including raw intraday option events, but it must run a controlled model competition:

1. deterministic QuantLab engine;
2. historical statistical baselines;
3. calibrated GBDT models;
4. multi-resolution sequence models;
5. full-chain encoders;
6. event-stream encoders;
7. self-supervised pretraining;
8. fusion and ensemble models;
9. teacher-to-student distillation for Railway.

The most advanced architecture is a **candidate**, not a foregone conclusion. The final production model is whichever model has the best pre-registered walk-forward, calibration, robustness, and execution-aware results.

This avoids two opposite mistakes:

- underusing the available ThetaData and RTX 5080 resources;
- assuming that the largest neural network must be the most accurate.

---

# 1. Existing QuantLab context that must be preserved

QuantLab currently has two product lanes:

- **Index 0DTE research**, centered on SPX/SPXW positioning, GEX/VEX, gamma flip, walls, King node, expected move, Pin Score, pin playbook, and intraday pin evaluation.
- **Single-equity research**, centered on structure, liquidity, VWAP, volume profile, relative strength, risk, and options overlays.

The current repository follows an important module boundary:

```text
src/quant_lab/data/       external data access and persistence
src/quant_lab/quality/    data-quality validation
src/quant_lab/factors/    pure deterministic factor calculations
src/quant_lab/terminal/   API/payload assembly and UI-facing services
src/quant_lab/backtest/   backtest logic
src/quant_lab/strategies/ strategy definitions
scripts/                  command-line workflows
tests/                    automated tests
```

Known relevant files include:

```text
src/quant_lab/data/thetadata_client.py
src/quant_lab/data/thetadata_intraday.py
src/quant_lab/data/thetadata_chain.py
src/quant_lab/data/thetadata_storage.py

src/quant_lab/factors/gex.py
src/quant_lab/factors/positioning.py
src/quant_lab/factors/effective_oi.py
src/quant_lab/factors/trade_flow.py
src/quant_lab/factors/pin_intraday_eval.py
src/quant_lab/factors/pin_king_proximity.py

src/quant_lab/terminal/api.py
src/quant_lab/terminal/snapshot.py
src/quant_lab/terminal/pin_playbook.py
src/quant_lab/terminal/magnet_state.py

src/quant_lab/strategies/zdte_pin_fly_intraday.py
```

Cursor must inspect the real repository before relying on this list, because file contents may have changed.

---

# 2. Non-negotiable financial and research rules

## 2.1 Dealer positioning language

Open interest does not directly reveal dealer inventory. Every output derived from an assumed sign convention must remain explicitly labeled as:

```text
model-implied positioning
OI-based positioning estimate
assumed dealer-sign convention
```

Never label it as:

```text
actual dealer inventory
observed dealer position
dealers will force price to ...
```

## 2.2 Time to expiration

For 0DTE, time to expiration must be based on the actual session and contract settlement time.

The pipeline must store:

```text
minutes_to_expiry
time_to_expiry_years
time_to_expiry_mode
fallback_used
settlement_type
session_close_timestamp
```

A fallback may prevent a crash, but a fallback observation must not be treated as high-quality training data.

## 2.3 SPX and SPXW

The training set must distinguish:

- SPXW PM-settled contracts;
- standard SPX AM-settled contracts;
- expiration date;
- last trading timestamp;
- holiday and early-close sessions.

The primary modern 0DTE model should initially use only a clearly defined homogeneous contract population, normally same-day PM-settled SPXW contracts.

## 2.4 No lookahead

At prediction timestamp \(t\), a feature may use only information whose source timestamp is less than or equal to \(t\).

Forbidden examples:

- final daily option volume;
- a quote published after the snapshot timestamp;
- close-of-day Greeks;
- next-day OI;
- a pin zone recomputed using closing data;
- a macro release outcome before its release time;
- a strike universe selected using the final close;
- data revisions that were unavailable in real time unless explicitly marked as revised.

## 2.5 Whole-session grouping

All train, validation, calibration, and test splits must group by entire trading session.

Never randomly split rows where one timestamp from a day is in training and another timestamp from the same day is in validation.

## 2.6 No automatic live execution

This project is research and decision support.

The allowed progression is:

```text
offline evaluation
→ shadow live predictions
→ paper trading
→ limited manual review
```

Cursor must not add brokerage order execution or an automatic buy/sell endpoint under this plan.

---

# 3. Target product outputs

The model layer enhances the deterministic engine; it does not replace it.

At each live prediction timestamp, the final system should be able to return:

```json
{
  "timestamp": "2026-06-10T15:30:00-04:00",
  "model_version": "zdte-fusion-1.0.0",
  "data_schema_version": "zdte-point-in-time-v1",
  "feature_schema_version": "zdte-features-v1",
  "spot": 6032.4,
  "deterministic_context": {
    "primary_pin": 6030,
    "secondary_pin": 6040,
    "pin_zone_low": 6025,
    "pin_zone_high": 6040,
    "pin_score": 81.2,
    "gamma_flip": 6008,
    "call_wall": 6050,
    "put_wall": 5980,
    "positioning_label": "model_implied"
  },
  "probabilities": {
    "close_below_zone": 0.12,
    "close_inside_zone": 0.69,
    "close_above_zone": 0.19
  },
  "close_distribution": {
    "p05": 5998.0,
    "p10": 6007.0,
    "p25": 6019.0,
    "p50": 6031.0,
    "p75": 6042.0,
    "p90": 6053.0,
    "p95": 6063.0
  },
  "exit_risk": {
    "upside_exit_15m": 0.24,
    "downside_exit_15m": 0.09,
    "return_to_zone_30m": 0.43
  },
  "quality": {
    "score": 0.94,
    "quote_coverage": 0.97,
    "greeks_coverage": 0.92,
    "stale_quote_ratio": 0.03,
    "time_alignment_ok": true,
    "out_of_distribution_score": 0.11
  },
  "calibration": {
    "method": "temperature_scaling",
    "recent_bucket_hit_rate": 0.67,
    "sample_count": 184
  }
}
```

The UI must clearly distinguish:

- deterministic structural outputs;
- machine-learning probabilities;
- data quality;
- calibration;
- model version;
- the fact that probabilities are research estimates, not guarantees.

---

# 4. Target technical architecture

```text
ThetaData / underlying source
          │
          ▼
Immutable raw event lake
quotes / trades / OI / Greeks / underlying
          │
          ├──────────────► quality audit
          │
          ▼
Point-in-time replay engine
          │
          ├──────────────► deterministic Pin/GEX engine
          │
          ▼
Multi-resolution state builder
tick / 1s / 10s / 1m / 5m
          │
          ├──────────────► tabular features
          ├──────────────► full-chain tensors
          └──────────────► event sequences
          │
          ▼
Model competition
GBDT / temporal / chain / event / fusion
          │
          ▼
OOF ensemble + calibration + uncertainty
          │
          ├──────────────► local GPU teacher
          └──────────────► distilled CPU student
                                  │
                                  ▼
                            Railway API/UI
```

---

# 5. Recommended repository additions

Cursor must adapt this proposal to the repository after audit. It must not duplicate an existing abstraction.

```text
config/
  ml/
    dataset_v1.yaml
    baseline_v1.yaml
    chain_encoder_v1.yaml
    event_encoder_v1.yaml
    fusion_v1.yaml
    deployment_v1.yaml

src/quant_lab/
  ml/
    __init__.py
    schemas.py
    contracts.py
    labels.py
    splits.py
    metrics.py
    calibration.py
    registry.py
    inference.py

    datasets/
      __init__.py
      point_in_time.py
      tabular.py
      chain.py
      event.py
      multiresolution.py

    features/
      __init__.py
      deterministic.py
      chain_summary.py
      microstructure.py
      temporal.py
      quality.py
      context.py

    models/
      __init__.py
      baselines.py
      gbdt.py
      temporal_tcn.py
      chain_encoder.py
      event_encoder.py
      fusion.py
      distillation.py

    training/
      __init__.py
      seed.py
      runner.py
      objectives.py
      tuning.py
      evaluation.py
      oof.py
      ablation.py

  data/
    intraday_lake.py
    intraday_manifest.py
    point_in_time_replay.py
    multiresolution.py

  quality/
    intraday_integrity.py
    replay_integrity.py
    feature_integrity.py
    leakage_checks.py

scripts/
  audit_thetadata_capabilities.py
  estimate_intraday_storage.py
  backfill_intraday_events.py
  build_point_in_time_dataset.py
  train_zdte_baselines.py
  train_zdte_chain_model.py
  train_zdte_event_model.py
  train_zdte_fusion_model.py
  evaluate_zdte_models.py
  calibrate_zdte_model.py
  distill_zdte_student.py
  export_zdte_model.py
  run_zdte_shadow.py

tests/
  test_intraday_manifest.py
  test_point_in_time_replay.py
  test_no_lookahead.py
  test_zdte_labels.py
  test_zdte_splits.py
  test_zdte_features.py
  test_zdte_metrics.py
  test_zdte_calibration.py
  test_zdte_inference_contract.py

docs/
  ml/
    data_contract.md
    point_in_time_spec.md
    label_spec.md
    feature_catalog.md
    evaluation_protocol.md
    deployment_runbook.md
    model_card_template.md

artifacts/                 # gitignored
  models/
  reports/
  manifests/
  predictions/
```

---

# 6. Dependency strategy

Do not make Railway install a large local-training stack unless production inference actually needs it.

Recommended files:

```text
requirements.txt           existing production/runtime dependencies
requirements-ml.txt        -r requirements.txt plus local research dependencies
```

`requirements-ml.txt` may eventually include:

```text
scikit-learn
lightgbm
xgboost
catboost
optuna
torch
tensorboard
onnx
onnxruntime
joblib
```

Potential data-performance dependencies such as Polars or DuckDB must be added only after an actual benchmark shows that current pandas/pyarrow processing is a bottleneck.

The project should still use one Python environment. The separate requirements file is a dependency profile, not a separate package manager or competing environment.

Before changing dependencies, Cursor must:

1. inspect `AGENTS.md`;
2. inspect `requirements.txt`;
3. inspect `pyproject.toml`;
4. document the approved ML dependency exception;
5. confirm Railway continues to install only production dependencies.

---

# 7. Git and Cursor workflow

## 7.1 Branch

Create:

```text
research/zdte-fusion-model
```

Do not implement this on `main`.

## 7.2 Commit discipline

One commit per completed phase. Suggested format:

```text
chore(ml): freeze 0dte research contracts
feat(data): add immutable intraday event manifest
feat(replay): implement point-in-time chain replay
feat(ml): add calibrated gbdt baselines
feat(ml): add normalized option-chain encoder
```

## 7.3 Cursor operating rules

Every Cursor task must begin with:

```text
Read AGENTS.md, ROADMAP.md, and QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md.
Do not violate existing module boundaries.
Do not modify files outside the listed scope.
Do not proceed to the next phase.
```

Every task must end with:

```text
Run the relevant tests.
Run the full test suite if practical.
Run ruff.
Provide:
1. files changed;
2. assumptions;
3. commands run;
4. test results;
5. unresolved risks;
6. acceptance-gate status.
```

---

# 8. Phase-by-phase implementation plan

---

## Phase 0 — Repository and governance audit

### Goal

Resolve contradictions between the current repository, `AGENTS.md`, and the new ML roadmap before writing ML code.

The existing project rules may still state that ML is prohibited before a later phase. Cursor must not silently ignore that rule.

### Cursor scope

Read only:

```text
AGENTS.md
ROADMAP.md
README.md
requirements.txt
pyproject.toml
Dockerfile
railway.json
src/quant_lab/**
tests/**
```

### Deliverables

Create:

```text
docs/ml/repository_audit.md
docs/ml/ml_phase_governance.md
```

The audit must list:

- actual repository structure;
- current data providers;
- current ThetaData methods;
- current storage formats;
- current Pin/GEX pipeline;
- current API routes;
- current tests;
- current Railway startup path;
- conflicting project rules;
- proposed authoritative phase designation;
- files that may and may not be changed.

### Acceptance gate

- No production code changed.
- Existing tests still pass.
- Governance contradiction explicitly resolved.
- The new `src/quant_lab/ml/` boundary is approved in writing.
- Existing `data → quality → factors → terminal` boundary remains intact.

### Cursor prompt

```text
Read AGENTS.md, ROADMAP.md, README.md, and
QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md.

Perform Phase 0 only.

Audit the current repository and create:
- docs/ml/repository_audit.md
- docs/ml/ml_phase_governance.md

Do not write ML code.
Do not change financial formulas.
Do not change API behavior.
Do not update dependencies.

Explicitly identify any conflict between AGENTS.md, ROADMAP.md,
the current codebase, and this ML plan. Propose a minimal governance
update, but do not apply it unless the existing repository rules permit it.

Run the existing tests and ruff, and report results.
```

---

## Phase 1 — ThetaData and underlying-data capability audit

### Goal

Determine exactly what the current account and installed client can retrieve. Do not rely on pricing-page assumptions or memory.

### Test dates

Use a small, deliberately varied set:

- one recent ordinary session;
- one monthly expiration session;
- one early-close session if available;
- one high-volatility event day;
- one date near the earliest expected historical coverage;
- one current live or recent session.

### Required probes

For same-day SPXW contracts, determine:

- symbol discovery behavior;
- quote history availability;
- trade history availability;
- actual finest usable interval;
- whether raw event timestamps are available;
- bid/ask sizes;
- trade sizes;
- IV availability;
- Greek availability and timestamp behavior;
- OI availability and date semantics;
- cumulative volume semantics;
- SPX underlying availability;
- timestamp timezone;
- response limits;
- pagination;
- rate limits;
- entitlement errors;
- historical start date;
- missing and stale data behavior.

### Deliverables

```text
scripts/audit_thetadata_capabilities.py
docs/ml/thetadata_capability_report.md
artifacts/manifests/thetadata_capabilities.json
```

The JSON report should record the actual account response, not secrets.

### Security requirements

- Never log API keys.
- Never commit credentials.
- Redact request headers.
- Store only entitlement names and response metadata.

### Acceptance gate

- At least two dates successfully audited.
- The exact quote/trade/Greek/OI/underlying fields are documented.
- The finest reliable historical resolution is documented.
- A firm decision is made about whether a separate SPX index source is required.
- No bulk historical download has occurred.

### Cursor prompt

```text
Implement Phase 1 only.

Inspect the existing ThetaData client and intraday data modules.
Add a read-only capability-audit script that probes a small set of dates
and contracts without bulk downloading data.

Create:
- scripts/audit_thetadata_capabilities.py
- docs/ml/thetadata_capability_report.md
- a machine-readable JSON manifest under artifacts/manifests/

Requirements:
- no credentials in output;
- no changes to current live behavior;
- no assumptions about entitlements;
- record timestamps, schemas, coverage, and errors;
- test both options data and the actual source used for SPX spot;
- report whether point-in-time synchronization is feasible.

Add tests for response-schema normalization using fixtures or mocks.
Run tests and ruff.
```

---

## Phase 2 — Storage and throughput estimator

### Goal

Measure one full session before deciding how much disk, bandwidth, and preprocessing capacity are required.

### Required measurements

For at least one ordinary day and one busy day:

- raw quote event count;
- raw trade event count;
- compressed Parquet size;
- uncompressed memory footprint;
- number of contracts;
- events per second distribution;
- API retrieval time;
- normalization time;
- write time;
- replay time;
- data gaps;
- duplicate rates;
- out-of-order event rates.

Project the estimated size for:

- one month;
- one year;
- May 2022 to present.

The estimate must include a range, not one false-precision number.

### Deliverables

```text
scripts/estimate_intraday_storage.py
docs/ml/storage_and_throughput_report.md
```

### Acceptance gate

- Estimates are based on observed samples.
- Partitioning and compression decisions are justified.
- The user can decide whether local SSD capacity is sufficient before bulk backfill.
- The report identifies the minimum viable raw-data retention policy.

### Cursor prompt

```text
Implement Phase 2 only.

Using the audited data methods from Phase 1, measure one ordinary session
and one high-activity session. Do not begin a multi-year backfill.

Create:
- scripts/estimate_intraday_storage.py
- docs/ml/storage_and_throughput_report.md

Use Parquet and the repository's storage conventions.
Report event counts, compressed sizes, throughput, gaps, duplicates,
and projected storage ranges.

Do not add model code.
Do not delete or rewrite existing market data.
Add tests for size-estimation math and partition-path generation.
```

---

## Phase 3 — Immutable raw event lake

### Goal

Preserve all usable source information without letting downstream transformations overwrite it.

### Data families

```text
option_quotes
option_trades
option_greeks
daily_open_interest
underlying_events_or_bars
session_metadata
source_manifests
```

### Suggested partitioning

```text
data/raw/thetadata/
  event_type=option_quote/
    root=SPXW/
      date=YYYY-MM-DD/
        part-*.parquet
```

Do not create one tiny file per event or per contract.

### Required columns

Every record must include:

```text
source
source_schema_version
event_timestamp
ingested_at
root
expiration
strike
right
contract_identifier
event_type
```

Then event-specific fields.

### Manifest requirements

For every partition:

- row count;
- min/max event timestamp;
- contract count;
- file checksum;
- schema hash;
- retrieval timestamp;
- source request identifier without secrets;
- completeness status;
- known errors;
- retry count.

### Write requirements

- atomic temp-file then rename;
- idempotent reruns;
- no silent overwrite;
- checksum verification;
- deterministic sorting;
- duplicate handling documented, not hidden.

### Acceptance gate

- One full day can be ingested twice without corrupting or duplicating data.
- Raw records are immutable.
- Manifest and data checksums agree.
- Corrupt or incomplete partitions are detected.
- Existing current-chain storage continues to work.

### Cursor prompt

```text
Implement Phase 3 only.

Add an immutable raw intraday event-lake layer that integrates with the
existing quant_lab.data module. Preserve current chain-snapshot behavior.

Requirements:
- Parquet only;
- atomic writes;
- idempotent backfill;
- partition manifests with checksums;
- source timestamps retained;
- no network I/O in factors;
- no silent overwrite;
- no credentials in manifests.

Implement one-day ingestion and replay fixtures first.
Add unit and integration tests using a small local fixture.
Do not start the multi-year backfill.
```

---

## Phase 4 — Point-in-time replay engine

### Goal

Given a historical date and timestamp, reproduce exactly what QuantLab could have known at that time.

### Public contract

```python
replay_state(
    session_date,
    as_of_timestamp,
    contract_scope,
    data_versions,
) -> PointInTimeState
```

### `PointInTimeState` should contain

```text
as_of_timestamp
session metadata
spot and spot source
eligible same-day contracts
latest quote at or before t
latest Greek observation at or before t
OI value that was available at t
cumulative trades only through t
cumulative volume only through t
quote age
trade age
Greek age
coverage statistics
data-quality warnings
```

### Required replay properties

- deterministic;
- no event after `as_of_timestamp`;
- explicit stale-data flags;
- explicit OI publication semantics;
- exact timezone handling;
- early-close awareness;
- contract-settlement awareness.

### Hash reproducibility

The same source partition, code commit, configuration, and timestamp must produce the same replay-state hash.

### Acceptance gate

- Automated tests inject future events and verify they never enter replay.
- Replay matches hand-checked source events for several timestamps.
- Repeated replay produces identical hashes.
- Existing deterministic Pin/GEX engine can consume replayed chains without network access.

### Cursor prompt

```text
Implement Phase 4 only.

Create a deterministic point-in-time replay engine over the raw event lake.

Hard rules:
- no source event after the requested timestamp;
- no final-day volume;
- no next-day OI;
- no network calls during replay;
- preserve source and age metadata;
- handle timezones and early closes explicitly.

Add adversarial no-lookahead tests that insert future quotes, trades,
Greeks, and OI and confirm they are excluded.

Connect replay output to the existing deterministic chain/Pin/GEX
functions without modifying their financial meaning.
```

---

## Phase 5 — Freeze deterministic calculation contracts

### Goal

Ensure historical replay and live calculation use the same deterministic definitions.

### Freeze specifications for

- contract selection;
- same-day expiration;
- settlement type;
- spot source;
- IV source/recalculation;
- Greeks;
- effective OI;
- dealer-sign assumption;
- GEX units;
- VEX units;
- gamma flip search;
- walls;
- King node;
- primary and secondary Pin;
- pin-cluster rule;
- exit-state rule;
- expected move;
- data-quality score.

### Existing Pin cluster rule to preserve unless a separate spec revision is approved

```text
merge when:
abs(primary_pin - secondary_pin) < 0.3% of spot
and
secondary_strength >= 70% of primary_strength
```

### Existing exit framework to preserve as deterministic context

```text
buffer = max(5 points, 0.25 × zone_width)
```

with states such as:

```text
inside_zone
testing_upside_exit
testing_downside_exit
valid_upside_exit
valid_downside_exit
failed_upside_breakout
failed_downside_breakout
```

### Deliverables

```text
docs/ml/point_in_time_spec.md
docs/ml/deterministic_feature_contract.md
tests/test_live_replay_parity.py
```

### Acceptance gate

- For the same normalized input chain, live and replay paths produce identical deterministic outputs.
- Every core output includes assumption and quality metadata.
- No financial formula is silently changed.

### Cursor prompt

```text
Implement Phase 5 only.

Document and test parity between the live deterministic engine and
historical point-in-time replay.

Do not redesign Pin, GEX, VEX, walls, or gamma flip.
Do not tune formulas for better historical outcomes.

Create explicit schemas and parity tests.
Any inconsistency must be reported before it is fixed.
```

---

## Phase 6 — Label specification and leakage-proof dataset builder

### Goal

Define targets before training any model.

### Primary target A: close location relative to current zone

At timestamp \(t\), use the zone computed at \(t\):

```text
0 = official close below zone_low_t
1 = official close within [zone_low_t, zone_high_t]
2 = official close above zone_high_t
```

### Primary target B: normalized close move

```text
(close - spot_t) / remaining_expected_move_t
```

If remaining expected move is missing or invalid, the sample must be excluded or explicitly placed in a fallback dataset.

### Primary target C: discrete close density

Create a normalized grid such as:

```text
-3.0 remaining EM to +3.0 remaining EM
```

The exact number and width of bins must be configured and evaluated.

### Auxiliary targets

- close near primary Pin;
- close near secondary Pin;
- close near each normalized strike bucket;
- first exit direction;
- time-to-first-exit;
- return to zone within 5/15/30 minutes;
- realized volatility over 5/15/30 minutes;
- maximum favorable and adverse excursion through close.

### Sample weighting

Because many timestamps share one close:

- normalize total weight per trading day;
- optionally maintain a separate time-of-day weighting config;
- never let a high-event-count day dominate only because it has more ticks.

### Dataset manifest

Every dataset build must record:

```text
source partition hashes
code commit
configuration hash
date range
eligible session count
row count
excluded rows and reasons
feature schema version
label schema version
```

### Acceptance gate

- A human-readable label specification exists.
- Unit tests cover boundary cases.
- Dataset rebuild is deterministic.
- Leakage checks pass.
- Labels use official, homogeneous settlement/close definitions.

### Cursor prompt

```text
Implement Phase 6 only.

Create the label specification, typed label functions, and deterministic
dataset-builder manifests.

Do not train a model.

Add tests for:
- close exactly on zone boundaries;
- absent zone;
- invalid expected move;
- early close;
- missing official close;
- SPX versus SPXW settlement;
- future-event exclusion;
- per-day sample-weight normalization.
```

---

## Phase 7 — Multi-resolution state construction

### Goal

Use all available raw information without treating every tick as an independent supervised sample.

### Required resolutions

Subject to Phase 1 capability results:

```text
raw event sequences
1-second state
10-second state
1-minute state
5-minute audit state
```

### Event-driven anchors

In addition to regular anchors, create prediction anchors when:

- spot crosses a zone edge;
- primary Pin changes;
- secondary Pin changes;
- zone center moves materially;
- gamma flip crosses spot;
- call/put wall changes;
- IV shock occurs;
- volume or quote-update-rate shock occurs;
- spread quality changes sharply.

### Important rule

Raw ticks are retained for event encoding and self-supervised learning. Supervised close labels are attached to controlled anchor timestamps, not every nearly identical tick.

### Acceptance gate

- Aggregation uses only prior events.
- State at each resolution is reproducible.
- Feature values at 1m and 5m reconcile with hand checks.
- Event-anchor generation is deterministic and configurable.

### Cursor prompt

```text
Implement Phase 7 only.

Build causal multi-resolution states from raw events:
- raw event windows;
- 1-second;
- 10-second;
- 1-minute;
- 5-minute audit states;
- configured event-driven anchors.

Do not train models.
Add tests proving that an event just after an anchor cannot affect that
anchor's state.
Document aggregation semantics for every field.
```

---

## Phase 8 — Baselines and calibrated GBDT competition

### Goal

Create the strongest transparent baseline before deep models.

This is not a disposable prototype. It remains:

- a valid production candidate;
- an ensemble member;
- a CPU fallback;
- a leakage detector;
- a benchmark for every advanced model.

### Baselines

1. unconditional class frequency by time bucket;
2. current spot location;
3. nearest strike;
4. highest OI strike;
5. highest model-implied GEX strike;
6. deterministic Pin Score calibration;
7. expected-move distribution baseline;
8. multinomial logistic regression;
9. LightGBM;
10. XGBoost;
11. CatBoost.

### Features

Use only causal, documented groups:

- deterministic Pin/GEX context;
- normalized distances;
- chain concentration;
- strike-grid summaries;
- intraday quote/trade proxies;
- IV and skew changes;
- spot path;
- time;
- calendar and known event context;
- data quality.

### Validation

Use nested expanding walk-forward validation:

```text
outer folds: model evaluation
inner folds: hyperparameter and feature selection
separate calibration segment
final locked holdout
```

### Metrics

Classification:

- negative log-likelihood;
- Brier score;
- multiclass Brier score;
- expected calibration error;
- balanced accuracy;
- macro F1;
- confusion matrix;
- high-confidence error rate.

Distribution:

- pinball loss;
- CRPS if implemented correctly;
- median MAE;
- interval coverage;
- average interval width.

### Acceptance gate

- All simple baselines reported.
- No random-row split exists.
- Calibration is evaluated on untouched data.
- Best GBDT is reproducible from config and manifest.
- Feature importance is stable enough to inspect.
- Final holdout has not yet been used for repeated model selection.

### Cursor prompt

```text
Implement Phase 8 only.

Train and evaluate:
- historical statistical baselines;
- multinomial logistic regression;
- LightGBM;
- XGBoost;
- CatBoost.

Use nested expanding walk-forward splits grouped by full trading session.
Add separate probability calibration.
Do not use the final locked holdout for iterative tuning.

Create an HTML or Markdown evaluation report containing:
- every baseline;
- fold-by-fold metrics;
- calibration plots;
- time-of-day breakdown;
- regime breakdown;
- feature-group ablations;
- high-confidence failures.

Export the best transparent model and full metadata, but do not connect it
to the live API yet.
```

---

## Phase 9 — Full-chain representation

### Goal

Allow a model to learn the shape of the entire same-day option chain rather than only hand-engineered summaries.

### Input normalization

For each contract:

```text
normalized_moneyness = (strike - spot) / remaining_expected_move
```

Include:

- call/put indicator;
- mid;
- spread;
- bid/ask size if available;
- IV;
- delta;
- gamma;
- vanna/charm if available;
- OI;
- cumulative volume;
- trade-flow proxy;
- quote/Greek age;
- quality mask.

### Parallel representations

#### A. Fixed normalized strike grid

Interpolate or bucket the chain into a configured grid and use:

- 1D convolution for local strike structure;
- lightweight Transformer or attention for long-range relations.

#### B. Variable-length set

Use a set-aware encoder with masks so missing or extra strikes do not change semantics.

### Self-supervised pretraining tasks

- masked contract-feature reconstruction;
- masked-strike reconstruction;
- IV-curve reconstruction;
- Gamma-curve reconstruction;
- predict deterministic Pin/GEX summaries from raw-chain state;
- contrastive learning across nearby states of the same session.

### Acceptance gate

- Model handles variable contract counts.
- Missing-data masks are explicit.
- Interpolation cannot use future states.
- Self-supervised validation losses improve over trivial baselines.
- Frozen-encoder downstream performance is compared with GBDT.

### Cursor prompt

```text
Implement Phase 9 only.

Create a full-chain dataset and encoder with:
1. a normalized fixed strike-grid representation;
2. a variable-length masked contract-set representation.

Implement self-supervised pretraining tasks before close-label fine-tuning.

Keep the network small enough for the local RTX 5080 configuration.
Use mixed precision and configuration-driven dimensions.
Add shape, mask, determinism, and no-lookahead tests.

Produce an ablation report comparing:
- tabular features only;
- strike grid only;
- contract set only;
- both chain representations.
```

---

## Phase 10 — Event-stream and temporal encoding

### Goal

Use raw quote/trade events and intraday evolution.

### Important data limitation

ThetaData NBBO events are not automatically a full multi-level exchange order book. The event encoder must be described as an NBBO/trade microstructure encoder, not an L2 order-book model, unless Phase 1 proves deeper data is available.

### Event token fields

Depending on audited availability:

```text
contract identity embedding
relative strike
call/put
event type
time since previous event
time before prediction anchor
bid change
ask change
bid-size change
ask-size change
spread
trade price relative to bid/mid/ask
trade size
IV change
Greek change
quote age
quality mask
```

### Multi-scale windows

Example configurable windows:

- recent 30 seconds at highest resolution;
- recent 5 minutes at moderate resolution;
- recent 30–60 minutes as compressed states;
- full-session summary through the current timestamp.

### Candidate architectures

Implement in this order:

1. multi-scale TCN;
2. causal Transformer;
3. optional irregular-time model such as Neural CDE only if the first two justify it.

### Self-supervised tasks

- next-event-type prediction;
- next spread-state prediction;
- future 1s/10s quote-update intensity;
- masked event reconstruction;
- short-horizon IV-change prediction;
- contrastive state learning.

### Acceptance gate

- No future events in a causal window.
- Throughput fits the RTX 5080 training budget.
- TCN baseline is completed before a more complex Transformer.
- Advanced event model must beat sequence summaries out of sample to survive.
- Latency and memory are measured.

### Cursor prompt

```text
Implement Phase 10 only.

Build the causal event/temporal branch:
- first a multi-scale TCN;
- then a compact causal Transformer as a challenger.

Use raw NBBO/trade events only as supported by the capability audit.
Do not call the data a full order book unless proven.

Add self-supervised pretraining tasks and downstream fine-tuning.
Measure:
- throughput;
- VRAM;
- sequence truncation;
- latency;
- fold-by-fold downstream gain.

Produce an ablation report. Do not build fusion yet.
```

---

## Phase 11 — Unified multi-task fusion model

### Goal

Fuse:

- raw-event representation;
- full-chain representation;
- temporal state;
- deterministic Pin/GEX outputs;
- context;
- data quality.

### Architecture

A practical candidate:

```text
Event encoder ──────┐
Chain encoder ──────┤
Temporal encoder ───┼─► gated fusion ─► shared latent state
Pin/GEX MLP ────────┤
Context encoder ────┤
Quality encoder ────┘
```

Optional time/regime experts:

```text
open
morning
midday
power hour
final 15 minutes
high volatility
low volatility
```

Use a gating network only if it improves strict validation. Do not add Mixture of Experts for visual sophistication.

### Unified primary output

Predict one normalized close probability density.

Derive from it:

- close below/inside/above current zone;
- Pin-zone probability;
- strike-neighborhood probabilities;
- quantiles;
- expected normalized move.

### Auxiliary heads

- exit hazard by horizon;
- return-to-zone hazard;
- future realized volatility;
- data/reconstruction quality;
- deterministic-factor distillation.

### Loss

Configuration-driven weighted combination, for example:

```text
close-density negative log-likelihood
+ zone classification loss
+ quantile/pinball auxiliary loss
+ exit survival loss
+ volatility loss
+ self-supervised regularization
```

Weights must be tuned on inner validation only.

### Acceptance gate

- Derived probabilities are mathematically consistent with the predicted close density.
- The model beats the best GBDT on pre-registered primary metrics.
- Improvement is present across multiple folds, not one period.
- Calibration is not worse.
- High-confidence error rate does not rise materially.
- Each branch’s incremental value is demonstrated by ablation.
- If these conditions fail, the fusion model is rejected.

### Cursor prompt

```text
Implement Phase 11 only.

Build a configuration-driven multi-task fusion model using the completed
branches. The primary output must be one normalized close density from
which zone and strike probabilities are derived.

Add auxiliary exit and volatility heads.

Do not assume fusion is best. Run branch-removal ablations and compare
against the best calibrated GBDT and each standalone deep model.

Pre-register the primary selection metrics before evaluating the locked
holdout. Produce a model card and a rejection recommendation if the
fusion model does not earn its complexity.
```

---

## Phase 12 — Ensemble, calibration, and uncertainty

### Goal

Turn candidate scores into reliable probabilities and estimate model disagreement.

### Candidate ensemble members

- best GBDT model;
- best chain model;
- best temporal/event model;
- best fusion model;
- multiple random seeds for the strongest deep architecture.

### OOF stacking

Only out-of-fold predictions may train the meta-model.

The stacker should initially be simple:

- constrained non-negative linear blend;
- multinomial logistic regression;
- no deep meta-model unless justified.

### Calibration candidates

- temperature scaling;
- sigmoid/Platt;
- isotonic;
- classwise or multiclass calibration where appropriate.

Calibration selection must be based on separate calibration folds.

### Uncertainty signals

- ensemble disagreement;
- out-of-distribution score;
- missingness/quality score;
- recent calibration drift;
- prediction entropy;
- distance from training regimes.

### Acceptance gate

- Ensemble beats its best member on primary OOF metrics or is rejected.
- Calibrated probabilities improve Brier/NLL without unacceptable sharpness loss.
- Reliability diagrams are available by time bucket and volatility regime.
- Recent rolling calibration can be monitored.
- The final holdout is evaluated once after architecture and thresholds are frozen.

### Cursor prompt

```text
Implement Phase 12 only.

Create out-of-fold ensemble and probability calibration tooling.
Use only OOF predictions for stacking.

Compare:
- best single model;
- simple average;
- constrained blend;
- logistic stacker.

Add uncertainty outputs from disagreement, entropy, OOD score, and
data quality.

Generate reliability diagrams and breakdowns by time of day and regime.
Evaluate the locked final holdout only after all decisions are frozen.
```

---

## Phase 13 — Reproducibility and model registry

### Goal

Make every reported result reproducible.

### Model artifact metadata

Every model version must include:

```text
model name and semantic version
git commit
training configuration hash
source data-manifest hashes
dataset manifest hash
feature schema version
label schema version
training/validation/calibration/test dates
random seeds
dependency snapshot
hardware summary
metrics
calibration method
known limitations
approved status
```

### Model statuses

```text
research
candidate
shadow
paper
production
retired
rejected
```

### Acceptance gate

- A fresh checkout can reproduce one candidate from manifests.
- Inference refuses a feature-schema mismatch.
- Model loading verifies checksum.
- The registry distinguishes model selection data from final holdout.

### Cursor prompt

```text
Implement Phase 13 only.

Create a lightweight local model registry with immutable metadata,
checksums, schema compatibility checks, and model-card generation.

Do not introduce a heavy external tracking platform unless the repository
audit proves it is necessary.

Add tests for:
- checksum mismatch;
- feature-schema mismatch;
- missing metadata;
- retired model;
- deterministic inference fixture.
```

---

## Phase 14 — Teacher/student deployment design

### Goal

Use the local RTX 5080 for the highest-quality research model while keeping Railway reliable.

### Teacher

Runs on:

- local RTX 5080; or
- a future dedicated GPU service.

Inputs may include:

- raw event windows;
- full-chain tensors;
- multi-resolution sequences.

### Student

Runs on Railway CPU.

Possible student forms:

- calibrated GBDT;
- compact TCN;
- compact MLP over engineered and distilled features;
- ONNX-exported lightweight model.

### Distillation targets

The student should learn:

- teacher close density;
- teacher zone probabilities;
- teacher uncertainty;
- hard observed labels.

Use a mixture of soft-target and hard-label losses.

### Production behavior

Railway must have a deterministic fallback order:

```text
student available and schema matches
→ use student

student unavailable
→ use deterministic QuantLab output only

teacher prediction available and fresh
→ display as enhanced research output with source label
```

The application must never fail entirely because the ML model is absent.

### Local teacher communication

Preferred pattern:

```text
Railway creates or exposes a prediction job
local GPU worker pulls or receives an authenticated job
local worker computes prediction
local worker writes result back
```

Do not expose the laptop directly to the public internet without a carefully designed authentication and network layer.

### Acceptance gate

- Railway starts without GPU packages.
- Student inference meets latency and memory targets.
- Teacher outage does not break the site.
- Every prediction identifies teacher/student/fallback source.
- No secret enters the frontend.

### Cursor prompt

```text
Implement Phase 14 only.

Design and implement a teacher/student inference boundary.

Railway must remain CPU-safe and must not require the local RTX machine
to be online for the site to function.

Add:
- typed inference contract;
- student model loader;
- deterministic fallback;
- model health endpoint;
- prediction-source metadata;
- checksum and schema checks.

Implement a local worker prototype only after the CPU path passes.
Do not expose the laptop through an unauthenticated public endpoint.
```

---

## Phase 15 — Railway API integration

### Suggested routes

Adapt to the existing API style:

```text
GET  /api/ml/zdte/health
GET  /api/ml/zdte/model
POST /api/ml/zdte/predict
GET  /api/ml/zdte/latest
```

### Health output

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_version": "zdte-student-1.0.0",
  "feature_schema_version": "zdte-features-v1",
  "prediction_source": "student",
  "last_successful_inference": "...",
  "fallback_available": true
}
```

### API safeguards

- strict Pydantic schema;
- no arbitrary file paths;
- no arbitrary model names from user input;
- request-size limit;
- timeout;
- structured errors;
- input timestamp validation;
- model/version logging;
- no raw market-data redistribution beyond licensing constraints.

### Acceptance gate

- Existing routes are unchanged.
- New endpoints have tests.
- Model absence triggers fallback, not HTTP 500.
- Railway Docker image remains within practical size.
- Startup health check passes.

### Cursor prompt

```text
Implement Phase 15 only.

Add the CPU student/fallback inference API to the existing FastAPI
application using the current project conventions.

Do not alter existing response contracts.
Use strict request/response models.
Add health, model metadata, prediction, and latest-prediction endpoints.

Test:
- valid request;
- missing model;
- schema mismatch;
- stale input;
- low-quality input;
- fallback path;
- startup health.
```

---

## Phase 16 — QuantLab UI integration

### Display blocks

- model-implied Pin probability;
- below/inside/above distribution;
- close quantile band;
- strike probability map;
- exit-risk probabilities;
- 5m/30m probability change;
- model source;
- data quality;
- calibration status;
- model version;
- sample/regime warning.

### Copy rules

Good:

```text
Model-implied close-in-zone probability
Calibrated probability
Current data quality
Research estimate under stated assumptions
```

Forbidden:

```text
Guaranteed pin
AI says buy
Dealer forced move
Certain close
```

### Visual rule

Do not hide uncertainty. A 72% estimate should appear with:

- calibration context;
- timestamp;
- model version;
- quality indicator;
- distribution, not only a single number.

### Acceptance gate

- UI can render deterministic-only fallback.
- Accessibility does not rely on color alone.
- Mobile layout works.
- Loading/error/stale states exist.
- No trading execution button is introduced.

### Cursor prompt

```text
Implement Phase 16 only.

Add a model research panel to the existing Index 0DTE UI.
Preserve the current deterministic Pin/GEX displays.

The panel must show:
- below/inside/above probabilities;
- close quantiles;
- exit risk;
- data quality;
- calibration;
- model version and source;
- stale/fallback state.

Use neutral research language.
Do not add buy/sell instructions or automatic execution.
Add UI tests if the project supports them.
```

---

## Phase 17 — Shadow-mode live logging

### Goal

Capture predictions exactly as they were made, before any paper strategy is tested.

### Required prediction log

```text
prediction_timestamp
source data cutoff
feature manifest/hash
model version
raw and calibrated probabilities
deterministic context
quality
latency
teacher/student/fallback source
later realized outcomes
```

Predictions must be append-only. Do not overwrite a bad prediction after the fact.

### Monitoring

- missing feature drift;
- feature-distribution drift;
- class-probability drift;
- calibration drift;
- latency;
- failed inference;
- source-data delay;
- disagreement between teacher and student.

### Acceptance gate

- Predictions are immutable.
- Outcomes are joined later without altering original predictions.
- Dashboard can separate live shadow results from historical backtest results.
- No trade execution occurs.

### Cursor prompt

```text
Implement Phase 17 only.

Add append-only shadow prediction logging and outcome reconciliation.

The original prediction payload must never be overwritten.
Outcome labels are attached later with separate timestamps and provenance.

Add monitoring reports for data delay, drift, calibration, latency,
and teacher/student disagreement.

Do not implement paper or live trades.
```

---

## Phase 18 — Paper-trading evaluation

### Goal

Test whether calibrated predictions have decision value after realistic costs.

### Rules

The model does not invent a strategy. The strategy must be separately specified with:

- entry time;
- allowed structures;
- maximum defined loss;
- exit conditions;
- bid/ask execution assumptions;
- commission;
- slippage;
- fill uncertainty;
- no overlapping-position rule;
- event-day restrictions;
- capital allocation limits.

### Evaluation

Report:

- signal count;
- average and median outcome;
- win rate;
- expected value;
- maximum drawdown;
- tail losses;
- performance by regime;
- performance by confidence bucket;
- performance after costs;
- comparison with deterministic baseline;
- comparison with no-trade.

### Acceptance gate

- At least one meaningful shadow period is complete.
- Paper results are separate from historical fit results.
- Costs and spreads are included.
- No conclusion relies on one small confidence bucket.
- The strategy can be rejected.

### Cursor prompt

```text
Implement Phase 18 only after a separate paper-strategy specification
has been approved.

Do not let the model create entry and risk rules.
Use fixed, versioned paper-trading rules.
Include spreads, slippage, commissions, and failed fills.

Keep paper results separate from model-fit metrics.
Do not implement brokerage execution.
```

---

# 9. Model-selection protocol

The phrase “best model” means the model that wins the pre-registered evaluation, not the largest model.

## 9.1 Primary selection criteria

Choose before final holdout:

1. close-density negative log-likelihood or equivalent proper scoring rule;
2. multiclass Brier score for below/inside/above;
3. calibration error;
4. 80% and 90% interval coverage and width;
5. high-confidence failure rate;
6. stability across walk-forward folds;
7. stability by time of day;
8. stability by volatility and Gamma regime.

## 9.2 Practical-complexity criteria

A more complex model must show:

- consistent improvement, not one-fold improvement;
- a bootstrap confidence interval supporting the gain;
- acceptable latency;
- acceptable memory;
- maintainable feature pipeline;
- no serious calibration degradation;
- explainable failure modes;
- a safe fallback.

## 9.3 Final holdout

Reserve a recent contiguous period.

The final holdout must not be used to:

- choose features;
- choose architecture;
- tune hyperparameters;
- choose calibration;
- select thresholds;
- decide ensemble weights.

Evaluate it once after freezing all decisions.

---

# 10. Feature groups

The exact catalog belongs in `docs/ml/feature_catalog.md`. The groups below are the required starting taxonomy.

## 10.1 Deterministic Pin and positioning

```text
primary_pin
secondary_pin
primary_strength
secondary_strength
strength_ratio
pin_score
zone_low
zone_high
zone_center
zone_width
spot_position_in_zone
distance_to_primary_pin
distance_to_secondary_pin
distance_to_zone_center
distance_to_nearest_edge
number_of_cluster_nodes
exit_state
time_since_zone_entry
time_since_zone_exit
zone_crossing_count
```

Normalize distances by:

- points;
- spot percentage;
- remaining expected move.

## 10.2 Gamma and Greek structure

```text
net_model_implied_gex
absolute_gex
call_gex
put_gex
positive_gex_share
negative_gex_share
gex_hhi
top_1_gex_share
top_3_gex_share
gex_weighted_strike
gamma_flip_distance
call_wall_distance
put_wall_distance
king_node_distance
net_vanna
net_charm
near_spot_vanna
near_spot_charm
```

## 10.3 Chain shape

For normalized strike buckets:

```text
call_oi
put_oi
call_volume
put_volume
call_gex
put_gex
average_iv
iv_skew
spread
quote_age
coverage
```

## 10.4 Intraday event and flow proxies

```text
quote_update_intensity
trade_intensity
call_volume_since_open
put_volume_since_open
call_put_volume_ratio
volume_to_oi
near_pin_volume_share
volume_hhi
trade_at_ask_proxy
trade_at_bid_proxy
mid_trade_share
spread_change
iv_change
skew_change
```

Use `proxy` in names when buyer/seller identity is inferred.

## 10.5 Underlying and path

```text
return_from_open
return_1m
return_5m
return_15m
return_30m
distance_to_vwap
distance_to_open
distance_to_session_high
distance_to_session_low
realized_volatility
range_expansion
opening_range_position
momentum
gap
```

## 10.6 Time and calendar

```text
minutes_since_open
minutes_to_close
minutes_to_expiry
time_sin
time_cos
day_of_week
monthly_expiration
quarterly_expiration
early_close
known_macro_event
event_release_state
```

## 10.7 Data quality

```text
quote_coverage
trade_coverage
greeks_coverage
oi_coverage
stale_quote_ratio
stale_greek_ratio
wide_spread_ratio
underlying_alignment_error
active_contract_count
missingness pattern
source version
```

---

# 11. Data-quality and exclusion policy

A sample must not silently pass if:

- spot is missing;
- official close is missing;
- settlement type is ambiguous;
- time-to-expiry fallback is used;
- quote coverage is below the configured threshold;
- most nearby contracts are stale;
- Greeks are badly misaligned;
- expected move is invalid;
- source timestamps are inconsistent;
- a partition checksum fails.

Each sample receives:

```text
eligible_for_training
eligible_for_live_inference
quality_score
exclusion_reasons
warning_codes
```

Training may include lower-quality samples only through a deliberate configuration and ablation.

---

# 12. Hardware-aware training on the RTX 5080 Laptop

The training code must discover actual hardware rather than hard-code assumptions.

Record:

- GPU model;
- VRAM;
- CUDA version;
- PyTorch version;
- driver;
- CPU;
- RAM;
- storage path;
- available disk.

## 12.1 Training defaults

- mixed precision;
- gradient accumulation;
- gradient clipping;
- deterministic seed where feasible;
- gradient checkpointing for deep models;
- configurable sequence length;
- configurable chain-grid width;
- checkpoint resume;
- validation after a fixed number of optimizer steps;
- early stopping by proper scoring rule.

## 12.2 Avoid waste

Do not start a four-year deep-model run before:

- one-day pipeline test;
- one-month replay test;
- storage report;
- baseline completion;
- profiler run;
- memory benchmark;
- model-overfit test on a tiny subset.

## 12.3 Tiny-overfit test

Every neural model must first prove it can overfit a tiny dataset. Failure means an implementation or target problem, not insufficient scale.

## 12.4 Parameter budget

Start with compact candidates. Expand only after learning curves show underfitting.

The model should not be made larger solely because the GPU can hold it.

---

# 13. Testing strategy

## 13.1 Unit tests

- timestamp normalization;
- partition paths;
- manifests;
- point-in-time event filtering;
- quote age;
- OI semantics;
- label boundaries;
- sample weights;
- split grouping;
- normalization;
- masks;
- model I/O schemas;
- calibration;
- registry checks.

## 13.2 Integration tests

- one-day ingestion;
- one-day replay;
- live/replay deterministic parity;
- dataset build;
- one-epoch model run;
- model export and reload;
- Railway fallback.

## 13.3 Adversarial leakage tests

Inject:

- a future quote with an extreme bid/ask;
- a future trade with extreme size;
- a later Greek update;
- next-day OI;
- final daily volume;
- an event result before release;
- final close into a source column.

Verify none affect earlier features.

## 13.4 Golden sessions

Maintain a small set of manually inspected sessions with expected outputs.

Golden fixtures should include:

- ordinary range day;
- strong trend day;
- high-volatility event day;
- monthly expiration;
- early close;
- missing-data case;
- multiple gamma-flip crossings;
- two close Pin nodes that form a zone.

---

# 14. Documentation required before production use

```text
docs/ml/data_contract.md
docs/ml/point_in_time_spec.md
docs/ml/deterministic_feature_contract.md
docs/ml/label_spec.md
docs/ml/feature_catalog.md
docs/ml/evaluation_protocol.md
docs/ml/model_card_<version>.md
docs/ml/deployment_runbook.md
docs/ml/shadow_monitoring.md
docs/ml/paper_strategy_spec.md
```

Each model card must state:

- intended use;
- prohibited use;
- data period;
- training population;
- assumptions;
- metrics;
- calibration;
- failure regimes;
- OOD behavior;
- inference requirements;
- licensing/data restrictions;
- version and checksum.

---

# 15. What Cursor must never do

1. Change a financial formula to improve model metrics without a separate approved specification.
2. Use random row-level train/test splits.
3. Use data after the prediction timestamp.
4. Use final daily volume at an intraday timestamp.
5. Use next-day OI.
6. mix SPX AM settlement and SPXW PM settlement without an explicit model design.
7. Put network calls inside `factors/`.
8. Overwrite raw event files.
9. Store raw market data in ad hoc CSV files.
10. Commit API keys or credentials.
11. Add a second competing package manager.
12. Make Railway install the full GPU training stack.
13. Claim NBBO data is a full L2 order book unless verified.
14. Claim dealer positions are observed.
15. Treat raw classifier scores as calibrated probabilities.
16. Evaluate the final holdout repeatedly.
17. Select a model only by accuracy.
18. Ignore spreads, slippage, and fill assumptions in strategy evaluation.
19. Add automatic brokerage execution.
20. Proceed to the next phase after a failed acceptance gate.
21. Rewrite large unrelated portions of the repository.
22. create a “one-shot” implementation of all phases.
23. hide missing data with silent forward fills.
24. use synthetic labels not documented in `label_spec.md`.
25. delete a simpler model merely because a deeper model exists.

---

# 16. How to use this document with Cursor

## Step 1

Add this file to the repository root:

```text
QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md
```

Add the companion rule file to:

```text
.cursor/rules/quantlab-0dte-ml.mdc
```

## Step 2

Open the repository root in Cursor and allow indexing to complete.

## Step 3

Start with the audit prompt below. Do not ask it to code the model.

```text
Read:
- AGENTS.md
- ROADMAP.md
- README.md
- QUANTLAB_0DTE_ML_CURSOR_IMPLEMENTATION_PLAN.md
- .cursor/rules/quantlab-0dte-ml.mdc

Execute Phase 0 only.
Do not proceed to another phase.
```

## Step 4

After Cursor returns:

- inspect its audit;
- run the commands yourself;
- review the git diff;
- confirm acceptance gate;
- commit.

## Step 5

Issue the next phase prompt from this document.

## Step 6

When Cursor proposes an architectural shortcut or new dependency, require:

```text
Show the exact bottleneck or failing test that justifies this change.
Do not implement it yet.
```

---

# 17. Definition of done

The research system is complete only when:

- full raw source provenance is retained;
- historical replay is deterministic and leakage-tested;
- live and replay deterministic engines match;
- labels are frozen and versioned;
- baseline models exist;
- advanced models have ablation evidence;
- probabilities are calibrated;
- final holdout was evaluated once;
- model artifacts are reproducible;
- Railway has a CPU-safe fallback;
- shadow predictions are append-only;
- paper evaluation includes costs;
- UI shows uncertainty and assumptions;
- no automatic execution exists;
- the best model is selected by evidence, not architectural prestige.

---

# 18. Recommended immediate next action

Do not begin model training yet.

The next action is exactly:

```text
Phase 0 — repository and governance audit
```

Then:

```text
Phase 1 — live entitlement and schema audit
```

Then:

```text
Phase 2 — one-day storage and throughput measurement
```

These phases are not “small prototypes” that will be discarded. They establish the contracts that allow the full tick, full-chain, self-supervised, multi-task system to be built without contaminating it with timestamp errors or data leakage.

The design deliberately preserves the maximum future model ceiling while requiring every increase in complexity to earn its place through strict out-of-sample evidence.
