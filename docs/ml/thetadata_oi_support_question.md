# ThetaData Open Interest — Support Question (Draft)

**Status:** Draft for owner to send to ThetaData support.  
**Context:** ML-P2 OI semantics validation for SPXW 0DTE historical backtest (QuantLab research track).

---

## Subject

Clarification of `option_history_open_interest` timestamp semantics for SPXW 0DTE backtesting

---

## Body

Hello ThetaData Support,

We are building a **point-in-time historical replay** pipeline for **SPXW same-day (0DTE) options** using the Python v3 `ThetaClient` (`option_history_open_interest`) under an **Options Standard** subscription.

During bounded capability testing we consistently observe OI rows with timestamps clustered around **06:30–07:01 America/New_York** on the requested session date `D`, for contracts with `expiration = D`.

Could you please clarify the following?

1. **What does the `timestamp` field represent** in `option_history_open_interest` when values appear near **06:30 ET** on date `D`?
   - Is this the moment the OI value became available to subscribers?
   - Is it the official opening OI for session `D`?
   - Is it still the **previous session (D−1) closing OI** being published on the morning of `D`?

2. When requesting **`date = D`**, what is the **earliest wall-clock time on D** a live subscriber could rely on that OI value for pre-market / at-the-open modeling?

3. For **0DTE contracts** (`expiration = D`), does the OI returned on `date = D` represent:
   - opening OI known before the RTH open,
   - intraday-updated OI,
   - or post-close / next-morning publication?

4. For **historical backtests**, what is the recommended rule to **avoid next-day / lookahead bias** when aligning OI with intraday quotes/trades at times such as 09:30, 10:00, or 13:00 ET?

5. How are **weekends, holidays, and corrections** handled if we request OI for `date = D` when `D` is a non-session day, or if OI is revised after initial publication?

6. If we request the **same contract on the same `date = D` multiple times during the trading day**, should we expect identical OI values and timestamps?

Our empirical samples (redacted) show stable OI values with morning timestamps only; we do **not** assume same-day intraday OI updates unless you confirm them.

Thank you,

[Owner name / account email on file with ThetaData]

---

## Internal note (do not send)

Until official confirmation is received, all ML documentation must state:

```text
OI semantics empirically constrained but not officially confirmed
```

Do **not** describe ThetaData OI as real-time intraday open interest.
