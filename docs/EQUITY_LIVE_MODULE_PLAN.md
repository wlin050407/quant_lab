# Single Equity Live Research Module — Implementation Plan

**Status:** Draft — data inventory verified 2026-05-31 (no OPRA; no LongPort env yet)  
**Route:** `#/stock?t=AAPL`  
**Product stance:** On-demand research terminal — **no per-ticker Parquet archive**.  
**Scope:** US single names (and ETFs as benchmarks). **Not** an 0DTE product; horizons are **short / mid / long** in parallel.

---

## 1. What this module is (and is not)

| | Index 0DTE Terminal (`#/index`) | Equity Live Module (`#/stock`) |
|---|---|---|
| Primary question | Dealer gamma / pin / regime today | Multi-horizon structure + flow + liquidity for **any ticker** |
| Data model | Local history + ThetaData intraday | **Ephemeral fetch → compute → JSON** (optional in-memory TTL cache) |
| Time focus | 0DTE, session slots | **Intraday + days + months** |
| Verdict | Regime / pin / playbook | **Three horizon judgments** + weakest-link disclosure |

Index terminal keeps its Phase 0–1 positioning mission. Equity module shares **UI shell + factor discipline** but not storage layout or 0DTE centrality.

---

## 2. Multi-horizon verdict (core requirement)

Every analysis run produces **three independent judgments**, not one blended “buy/sell”:

| Horizon | Calendar span | Academic anchor | Example output |
|---------|---------------|-----------------|----------------|
| **Short** | Session + 1–5 trading days | Heston–Korajczyk–Sadka intraday periodicity; Jegadeesh short reversal; session VWAP | “Intraday: above VWAP, opening segment strong vs SPY; micro-reversal risk into close (B).” |
| **Mid** | 1 week – ~3 months | Jegadeesh–Titman momentum (compressed); RS vs SPY; event windows | “Mid: RS_20d positive, 20>50 MA; earnings in 4 days caps confidence (B).” |
| **Long** | ~3–12+ months | JT momentum; trend / 200 MA; Amihud liquidity premium context | “Long: above 200 MA, 6m RS top quartile vs SPY (A on daily bars).” |

**Synthesis layer** (`Layer 7`) reports:

- `short` / `mid` / `long`: each `{ bias: bullish|neutral|bearish, confidence: 0–1, evidence_grade: A|B|C, drivers[], risks[] }`
- `alignment`: aligned | mixed | conflicting (e.g. long bullish + short bearish)
- `weakest_link`: which layer/horizon/data source limits trust
- **No** trade instructions — research language only

Horizons **must not** reuse 0DTE-only fields (`dte≤1`, pin score, gamma flip) unless an optional **Options overlay** is enabled for liquid names.

---

## 3. Data sources — verified inventory & routing

> **2026-05-31 audit** (ran `verify_thetadata.py` + live probes on `AAPL`):
> - `.env` has **ThetaData only** — no `LONGPORT_*`, no `FLASHALPHA_API_KEY`.
> - ThetaData tiers: **Options Standard**, **Indices Standard**, **Stock Value** (not Stock Standard).
> - User has **no OPRA** (LongPort or otherwise) — options overlay uses **yfinance chain in memory**.

### 3.1 What we already have — capability matrix

| Capability | **ThetaData (configured)** | **yfinance (always)** | **In-repo free extras** |
|------------|---------------------------|----------------------|---------------------------|
| US stock **daily** bars (mid/long) | ✅ `stock_history_eod` — **≤365 calendar days per request** (chunk for 2–5y) | ✅ `period=5y interval=1d` — **preferred for long** | — |
| US stock **intraday** bars (short) | ✅ `stock_history_ohlc` **5m/1m** for a session (Stock Value) | ✅ 5m ~5d, 1h ~1mo — fallback | — |
| US stock **NBBO** snapshot | ✅ `stock_at_time` | ✅ last close / delayed quote | — |
| US stock **tape / signed stock flow** | ❌ needs **Stock Standard** (`stock_history_trade`) | ❌ | — |
| US **option chain** (any ticker) | ✅ `option_history_quote` works (tested AAPL); existing code is 0DTE-centric | ✅ full chain + expiries | — |
| **Signed option flow** | ✅ Lee-Ready via `fetch_0dte_signed_flow_at_time` (Options Standard); tested AAPL 76 rows | ❌ | reuse `factors/trade_flow.py` |
| Index SPX intraday | ✅ Indices Standard | partial | — |
| Earnings / div calendar | — | ✅ `Ticker.calendar` | — |
| FOMC / CPI gate | — | — | ✅ `data/macro_calendar.py` embedded |
| FlashAlpha GEX | code exists | — | ❌ not configured |

**LongPort (长桥):** not in `.env` today. Without OPRA, it still helps **US stock quote + kline** if added later — **optional adapter**, not Phase A blocker.

### 3.2 Recommended routing (build with what we have)

```
User ticker "AAPL"
        │
        ▼
┌───────────────────────────────────────┐
│  EquityLiveFetcher                     │
│  ephemeral only · TTL cache 60–120s    │
└───────────────────────────────────────┘
        │
        ├─ LONG horizon (3–12mo+) — daily bars
        │     PRIMARY:  yfinance  get_underlying(period=2y|5y, interval=1d)
        │     ENRICH:    ThetaData stock_history_eod (last 365d) when TD up — cross-check / fresher EOD
        │
        ├─ MID horizon (1w–3mo) — daily + 20/60d RS
        │     Same daily series as above
        │
        ├─ SHORT horizon (session + 1–5d) — intraday
        │     PRIMARY:  ThetaData stock_history_ohlc 5m (last session or today)
        │     FALLBACK: yfinance 5m/1h if TD fails or market closed without TD bar
        │     Spot:     ThetaData stock_at_time @ last pin time, else yfinance
        │
        ├─ Benchmark SPY — same split (TD 5m short / yfinance daily long)
        │
        ├─ Events (L1)
        │     yfinance calendar (earnings, ex-div)
        │     macro_calendar.py (FOMC/CPI on session date)
        │     OPTIONAL Phase B: SEC `data.sec.gov` submissions API (free, no key) for 8-K 2.02 history
        │
        ├─ Macro context (L1 optional)
        │     FRED free API key: VIXCLS, DGS10, T10Y2Y (rate/vol regime) — **new thin client**
        │
        └─ Options overlay L6 (mid context, NOT 0DTE-centric)
              PRIMARY:  yfinance get_option_chain → filter **7 ≤ dte ≤ 45**
              Metrics:   PCR volume/OI, OI concentration, max pain (reuse positioning.py in-memory)
              Flow add-on (short, B-grade): ThetaData signed flow on **nearest liquid expiry**
                         OR same-day option flow if user wants — label horizon explicitly
              IV/Greeks: only if dte>1; never yfinance 0DTE IV
```

### 3.3 Layer × source mapping (what we can ship without new paid feeds)

| Layer | Short | Mid | Long | Primary source |
|-------|-------|-----|------|----------------|
| L0 Eligibility | ✅ | ✅ | ✅ | yfinance avg volume + Amihud from daily bars |
| L1 Context | ✅ | ✅ | ✅ | macro_calendar + yfinance earnings + optional FRED |
| L2 Session / VWAP | ✅ | — | — | ThetaData 5m → fallback yfinance 5m |
| L3 Volume profile | ✅ | — | — | same intraday bars |
| L4 Flow | ✅ (B) | ✅ (B) | — | yfinance PCR + optional TD signed **option** flow; **no stock tape** |
| L5 Drift / RS / MA | ✅ | ✅ | ✅ | daily bars — RS 1d/5d/20d/60d/120d vs SPY |
| L6 Options | — | ✅ (B) | — | yfinance chain dte 7–45 |
| L7 Verdict | ✅ | ✅ | ✅ | synthesize per horizon |

### 3.4 Free authoritative supplements (recommended adds)

| Source | URL / access | Use in module | Cost |
|--------|--------------|---------------|------|
| **SEC EDGAR** | [data.sec.gov](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) — no API key | Ticker→CIK, recent 8-K Item 2.02 (earnings filed) as **hard event** backup when yfinance calendar empty | Free |
| **FRED** | [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/api_key.html) — free key | `VIXCLS`, `DGS10`, `T10Y2Y` for vol/rates context on mid/long horizon | Free |
| **Stooq** | CSV download only, no official API | **Skip for v1** — adds scraping fragility; yfinance + TD EOD sufficient | Free but brittle |

**Not recommended:** scraping LongPort web, Apify Stooq wrappers, sec-api.io (paid) unless SEC direct proves insufficient.

### 3.5 LongPort without OPRA (future optional)

If user adds `LONGPORT_*` later (still no OPRA):

- Use for **real-time US quote + minute kline** (short horizon upgrade over yfinance).
- **Do not** depend on LongPort for options — keep yfinance chain overlay.
- Monthly symbol quota → cache + warn in UI.

### 3.6 Symbol normalization

| User input | ThetaData | yfinance |
|------------|-----------|----------|
| `AAPL` | `AAPL` | `AAPL` |
| `SPY` | `SPY` | `SPY` (benchmark) |
| `^SPX` | index path (benchmark context only) | `^GSPC` or `^SPX` |

---

## 4. Signal stack (modular, horizon-tagged)

Layers are **pluggable**; each output includes `horizon_tags: short[] | mid[] | long[]`.

| Layer | ID | Horizons | Inputs | Evidence (typical) |
|-------|-----|----------|--------|-------------------|
| Eligibility | L0 | all | ADV, Amihud, spread proxy | A |
| Context | L1 | mid, long | Earnings ±N d, macro, vol regime | A/B |
| Session | L2 | **short** | VWAP, open/mid/close segment returns vs SPY | B |
| Auction / Profile | L3 | **short**, mid | Volume profile POC/VA, opening range | B |
| Flow | L4 | **short** | Signed imbalance (tape or options); degrade without tick | A/B/C |
| Drift | L5 | **mid**, **long** | RS vs SPY (1d/5d/20d/60d/120d), MA structure 20/50/200 | A/B |
| Overnight split | L5b | mid, long | Intraday vs overnight return decomposition | B |
| Options overlay | L6 | mid (optional) | Put/call volume, OI skew — **nearest monthly+, not 0DTE** | B/C |
| Synthesis | L7 | all | Weakest-link weighted verdict per horizon | — |

**Explicitly excluded or C-grade only**

- VPIN headline (Andersen–Bondarenko critique) — use simple volume imbalance instead.
- FVG / ICT / harmonic patterns — annotation only, no verdict weight.
- Multiple MA crossover grids — max 20/50/200 structure.
- yfinance 0DTE IV/Greeks.

---

## 5. Architecture (AGENTS.md boundaries)

```
terminal/web/          StockTerminalPage, horizon tabs, ticker input
terminal/api.py        GET /api/equity/analyze?ticker=&refresh=
terminal/equity_live.py Orchestrator: fetch → factors → payload (no disk)
data/equity_fetch.py    NEW — ThetaData + yfinance routing + cache
data/thetadata_equity.py NEW — thin wrappers: stock EOD, 5m OHLC, at_time
data/yfinance_source.py Reuse get_underlying + get_option_chain
data/sec_edgar.py       NEW (Phase B) — optional ticker→CIK, 8-K 2.02
data/fred_client.py     NEW (Phase B) — optional VIX / yields
factors/equity/         NEW — vwap, volume_profile, rs, session_segments,
                          drift, liquidity, events, synthesize_verdict
data/longport_source.py OPTIONAL later — only if LONGPORT_* added (no OPRA)
```

**Storage:** none for equity path. Optional:

```python
# in-memory only, not Parquet
@lru_cache / TTL dict keyed by (ticker, bar_end_ts, provider)
```

**Tests (required before merge)**

- Mock LongPort + yfinance responses → deterministic snapshot JSON.
- Hand-calculated VWAP + RS examples (1–2 per factor).
- Verdict regression: fixed input bars → known short/mid/long bias enums.

---

## 6. API contract (sketch)

`GET /api/equity/analyze?ticker=AAPL&refresh=0`

```json
{
  "ticker": "AAPL",
  "asof": "2026-05-24T15:32:00-04:00",
  "provenance": {
    "daily_bars": "yfinance",
    "intraday_bars": "thetadata",
    "options": "yfinance",
    "events": "yfinance+calendar",
    "cache_hit": false
  },
  "spot": 195.2,
  "layers": { "L0": {...}, "L2": {...}, "L5": {...} },
  "horizons": {
    "short": { "bias": "bullish", "confidence": 0.62, "grade": "B", "summary": "...", "drivers": [], "risks": [] },
    "mid":   { "bias": "neutral", "confidence": 0.55, "grade": "B", "summary": "...", "drivers": [], "risks": [] },
    "long":  { "bias": "bullish", "confidence": 0.71, "grade": "A", "summary": "...", "drivers": [], "risks": [] }
  },
  "alignment": "mixed",
  "weakest_link": { "layer": "L4", "reason": "no tick data; flow omitted" },
  "chart": { "interval": "5m", "bars": [...], "overlays": { "vwap": [...], "poc": 194.5 } }
}
```

---

## 7. UI (`#/stock`)

Reuse Index **TopBar / InstrumentStrip / panel tokens** — full cockpit, not homepage minimalism.

```
[Ticker input + Analyze]  [Short | Mid | Long tab for detail focus]
Instrument strip: spot · alignment · data badge · weakest link
Main: candle chart (interval auto: 5m short view / 1d mid+long toggle)
Right: collapsible layers L0–L7 filtered by selected horizon tab
Footer: provenance + latency + “delayed fallback” warning if yfinance
```

Default chart: **5m today + 1d 6mo mini** — short and long visible without 0DTE heatmap.

---

## 8. Implementation phases

### Phase A — Foundation (MVP, shippable)

- [ ] `data/thetadata_equity.py` + `data/equity_fetch.py` (TD 5m + yfinance daily/intraday fallback)
- [ ] `factors/equity/`: vwap, volume_profile, relative_strength, ma_structure, amihud, vol_regime
- [ ] `terminal/equity_live.py` + `/api/equity/analyze`
- [ ] `StockTerminalPage` (ticker → analyze → short/mid/long horizons)
- [ ] Tests with mocks only (no network)

**MVP data:** ThetaData intraday (short) + yfinance daily (mid/long) + yfinance option chain (L6, dte≥7).

### Phase B — Context + synthesis + free authorities

- [ ] Events: yfinance calendar + `macro_calendar` + optional `sec_edgar.py`
- [ ] Macro: optional `fred_client.py` (VIX / 10Y / curve)
- [ ] Session segments (open/mid/close vs SPY)
- [ ] `synthesize_verdict` with short/mid/long + alignment + weakest link
- [ ] In-memory TTL cache + rate limit

### Phase C — Flow enrichment (no OPRA)

- [ ] yfinance PCR + OI skew on monthly-ish expiry (7–45 DTE)
- [ ] Optional ThetaData signed **option** flow (same-day or nearest expiry) — B-grade, labeled
- [ ] Reuse `positioning.py` max_pain / oi_concentration in-memory on yfinance chain

### Phase D — Optional upgrades

- [ ] LongPort adapter (quotes/kline only, no OPRA)
- [ ] HK symbols
- [ ] Compare-two-tickers RS spread

---

## 9. Environment variables

```bash
# Existing — ThetaData (equity intraday + optional option flow)
# THETADATA_CREDENTIALS_FILE=...

# Phase B optional — FRED macro context (free key)
# FRED_API_KEY=

# Phase D optional — LongPort stock quotes only (no OPRA required)
# LONGPORT_APP_KEY=
# LONGPORT_APP_SECRET=
# LONGPORT_ACCESS_TOKEN=

# Equity module tuning
EQUITY_CACHE_TTL_SECONDS=120
EQUITY_DEFAULT_BENCHMARK=SPY
```

---

## 10. Dependencies

Phase A adds **no new packages** (reuse `thetadata`, `yfinance`, `requests`).

Phase B optional: document `FRED_API_KEY` only — implement with `requests`, no new lib.

Phase D optional: `longport>=3.0` if LongPort adapter is added.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| LongPort monthly symbol quota | N/A until adapter added |
| No OPRA / no option vendor | L6 from yfinance volume/OI only (B-grade) |
| Stock tape unavailable (TD Stock Value) | L4 uses option flow + PCR, not stock Lee-Ready |
| yfinance delay misleads short horizon | Force `grade=C` on L2 when fallback; TD 5m = B |
| User expects 0DTE heatmap on stock page | Copy + UI: “Multi-horizon research — not 0DTE pin deck” |
| Verdict overconfidence | Weakest-link cap; earnings gate; eligibility fail → neutral only |

---

## 12. Success criteria (exit gate for Phase A+B)

1. User enters any US ticker → analysis returns in < 8s (cold) / < 2s (cached) without writing disk.
2. Response always includes **short / mid / long** horizon objects with grades.
3. `provenance.intraday_bars == "thetadata"` when TD session available; `"yfinance"` on fallback.
4. yfinance-only mode still returns all three horizons with honest grades.
5. pytest: factor hand examples + API mock test green.

---

## 13. Out of scope (this plan)

- Per-ticker Parquet / watchlist database
- 0DTE pin / GEX heatmap as default stock view
- ML scoring / auto-trading / LongPort order placement
- WebSocket streaming (REST + short TTL sufficient for v1)
- Crypto / multi-asset expansion

---

*Next step after approval: implement **Phase A** with ThetaData 5m + yfinance daily (no LongPort, no OPRA).*
