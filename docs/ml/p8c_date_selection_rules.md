# ML-P8C Date Selection Rules

**Date:** 2026-06-22  
**Stage:** ML-P8C.0  
**Status:** Pre-declared rules (committed before any ingest)  
**Parent plan:** [`p8c_controlled_dataset_expansion_plan.md`](p8c_controlled_dataset_expansion_plan.md)

---

## Purpose

定义 **可复现** 的 SPXW 0DTE session 日期选择规则，用于 P8C controlled dataset expansion。**禁止** 根据 P8B.3.7 或任何 learned model 表现选择日期。

```text
selection_seed = 20260621
```

所有 bucket 内 tie-break 与抽样均使用该固定 seed（deterministic sort / seeded shuffle）。

---

## 5.1 Allowed Selection Inputs

| Input category | Examples | Use |
|----------------|----------|-----|
| Calendar | `trade_date`, weekday, month, quarter, year | Stratification |
| OPEX / expiration | Third-Friday SPXW rule, week-of-month | OPEX bucket |
| Session metadata | `early_close`, session status | Quota / exclusion |
| Intraday path (non-label) | Realized range, realized vol, spot return from open | Vol / trend buckets |
| Data availability | Raw lake partition exists, ThetaData coverage | Hard exclusion filter |
| Pre-existing regime flags | `short_gamma_regime`, pin-zone gate rates from P8B.1 diagnostics | Stratification only |
| Data quality | P8B.1 / P8B.3.5 feature quality scores, missingness thresholds | Exclude corrupt sessions |
| Frozen baseline cohort | Existing 19 P8B.1 sessions | Always retained; never re-selected |

---

## 5.2 Forbidden Selection Inputs

| Forbidden input | Reason |
|-----------------|--------|
| P8B.3.7 model performance (MAE, balanced_acc, etc.) | Performance cherry-picking |
| Future learned model performance | Same |
| Validation / test split metrics | Test-set tuning |
| Hyperparameter search outcomes | P8B.4 blocked |
| PnL / trading outcome | Not research selection criterion |
| Labels as selection target (`close_near_primary_pin_050`, `official_close` outcome) | Target leakage |
| Manual cherry-picking after seeing model results | Governance violation |
| Post-hoc bucket redefinition after candidate list generated | Rules must be frozen at P8C.1 |

---

## 5.3 Candidate Selection Method

### Step 0 — Freeze baseline

Retain all **19** existing P8B.1 sessions (listed in expansion plan). New sessions must **not** duplicate these dates.

### Step 1 — Build candidate calendar pool

```text
Universe: all US equity trading sessions with SPXW 0DTE availability
Calendar window (Stage 1 backfill): 2023-01-01 through 2025-06-30
Exclude: dates already in P8B.1 baseline cohort (19 sessions)
```

### Step 2 — Hard exclusions (data quality)

Exclude a date if **any** of:

```text
Incomplete raw lake partition for SPXW chain or index path
Missing official close / settlement reference for label join
Known corrupt partition (documented in prior ingest QA)
ThetaData availability flag = unavailable (checked in P8C.1, not P8C.0)
feature_quality_score below P8B.1 minimum gate (same threshold as baseline build)
```

### Step 3 — Stratify by year / quarter

Within remaining pool, tag each session:

```text
year_bucket: {2023, 2024, 2025}
quarter_bucket: Q1–Q4 within year
```

Stage 1 new sessions: minimum **4 distinct quarters** represented among the 21 new dates.

### Step 4 — Realized intraday move bucket (vol)

Using **index path only** (no labels), compute per session:

```text
session_range_pct = (session_high - session_low) / spot_open * 100
```

Tercile thresholds computed on **candidate pool only** (not on P8B.3.7 test sessions):

| Bucket | Rule |
|--------|------|
| `low_vol` | range_pct ≤ 33rd percentile of pool |
| `medium_vol` | 33rd < range_pct ≤ 67th |
| `high_vol` | range_pct > 67th percentile |

### Step 5 — Trend bucket

```text
session_return_pct = (spot_at_last_observation - spot_open) / spot_open * 100

trend_up:   session_return_pct > +0.30%
trend_down: session_return_pct < −0.30%
range_bound: |session_return_pct| ≤ 0.15% AND low_vol or medium_vol
normal:     all other sessions
```

Thresholds **fixed** in this document; not tuned on validation/test.

### Step 6 — OPEX bucket

```text
opex_heavy: trade_date is SPX monthly expiration Friday OR T−1 trading day before it
non_opex: all other sessions
```

Calendar rule only — no label inspection.

### Step 7 — Early-close quota

```text
early_close: session metadata early_close = true
Quota: max 1 session in P8C Stage 1; max 2 cumulative through Stage 2
```

### Step 8 — Within-bucket selection (deterministic)

For each bucket quota:

```text
1. Filter candidates matching bucket tags
2. Sort by trade_date ascending
3. Apply seeded shuffle: random.Random(20260621).shuffle within bucket
4. Take first N sessions satisfying quota
5. If bucket under-filled, spill to next priority bucket per spill rules (below)
```

**Spill priority (Stage 1):** `high_vol` → `trend` → `normal/range` → `opex` → `recent`

---

## 5.4 P8C Stage 1 Target (+21 sessions → 40 total)

**Goal:** Add **21** new sessions to reach **40** total (19 existing + 21 new).

### Stage 1 quota proposal

| Bucket tag | Quota (new sessions) | Overlap allowed |
|------------|---------------------|-----------------|
| Normal / range-bound | 8 | May overlap `low_vol` + `range_bound` |
| High-vol | 5 | May overlap `high_vol` + any trend |
| Trend (up or down) | 4 | May overlap `trend_up`/`trend_down` + vol bucket |
| Monthly OPEX / expiration-heavy | 2 | May overlap vol/trend |
| Early-close | 1 | May overlap any; counts toward nearest primary bucket |
| Recent (calendar year ≥ 2025, not in baseline test set) | 1 | May overlap any |

**Quota sum:** 8 + 5 + 4 + 2 + 1 + 1 = **21**

### Overlap rules

```text
A session may satisfy multiple bucket tags simultaneously.
Each selected session is assigned ONE primary_bucket for manifest logging
  (first matching bucket in quota fill order: high_vol → trend → opex → normal/range → recent → early_close).
Primary bucket assignment is for audit only; does not affect label or feature build.
No session counted twice toward the 21-session total.
```

### Temporal constraints (Stage 1)

```text
At least 6 new sessions from calendar year 2023 (older history backfill)
At least 8 new sessions from calendar year 2024
At least 5 new sessions from calendar year 2025
At least 1 new session must be after 2025-05-02 (post baseline test window)
```

### Excluded from Stage 1 new picks

```text
Any date in existing P8B.1 19-session list
Any date with forbidden selection inputs (Section 5.2)
```

**Note:** Actual date list generation occurs in **P8C.1** — this document defines rules only.

---

## 5.5 P8C Stage 2 Target (+20 sessions → 60 total)

**Prerequisite:** P8C Stage 1 ingest/build PASS + P8C.5 Stage 1 review PASS.

**Goal:** Add **20** new sessions (40 → 60 total).

### Stage 2 quota proposal (pre-declared — not performance-adjusted)

| Bucket tag | Quota (new sessions) |
|------------|---------------------|
| Older history (year ≤ 2023) | 6 |
| Normal / range-bound | 5 |
| High-vol | 4 |
| Trend (up or down) | 3 |
| OPEX / expiration-heavy | 1 |
| Early-close (cumulative cap 2) | 1 |

**Quota sum:** 6 + 5 + 4 + 3 + 1 + 1 = **20**

### Stage 2 binding rule

```text
Stage 2 MUST NOT cherry-pick based on Stage 1 model performance.
Only pre-declared buckets and spill rules apply.
If Stage 1 P8C.5 review FAILS OOS criteria, Stage 2 is BLOCKED until owner review.
```

---

## 5.6 P8C Stage 3 Target (+40 sessions → 100 total)

**Prerequisite:** Stage 1 + Stage 2 PASS through P8C.5; owner cost approval.

Quota template (to be finalized in separate owner record before P8C.1 Stage 3 planning):

```text
20 older (≤ 2023)
10 high-vol
6 trend
4 opex
```

Exact quotas committed in a P8C.3.x addendum **before** any Stage 3 ingest — not in P8C.0.

---

## Audit Manifest Fields (P8C.1 output — future)

Each selected date must record:

```text
trade_date
primary_bucket
all_bucket_tags
year_quarter
selection_seed
selection_rule_version: p8c_date_rules_v1
excluded_reason (if candidate rejected)
data_availability_status
overlap_with_baseline_cohort: false
```

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-22 | Initial pre-declared date selection rules (`selection_seed=20260621`) |
