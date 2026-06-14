# Raw Event Lake Pilot Report (ML-P3)

**Date:** 2026-06-11  
**Pilot version:** `ml-p3-pilot-1.0`  
**Status:** SUCCESS (bounded live write)

## Scope

| Parameter | Value |
|-----------|-------|
| Trade date | 2026-06-10 |
| Root | SPXW (0DTE, same-day expiration) |
| Index symbol | SPX |
| Strike range | ±2 around ATM |
| Time window | 13:00:00–13:02:00 ET |
| Output root | `artifacts/raw_lake_pilot/` (gitignored) |
| API calls (estimated) | 7 |

## Datasets written

| Dataset | Rows | Duplicate ratio | Out-of-order ratio | Manifest + SHA-256 |
|---------|------|-----------------|--------------------|--------------------|
| option_quote_1s | 968 | 0.0 | 0.007 | yes |
| option_quote_tick | 118,119 | 0.413 | 0.00008 | yes |
| option_trade_tick | 598 | 0.0 | 0.012 | yes |
| option_greeks_1m_first_order | 24 | 0.0 | 0.304 | yes |
| derived_gamma_black76_1m | 24 | 0.0 | 0.304 | yes |
| option_open_interest | 8 | 0.0 | 0.714 | yes |
| index_price_1s | 121 | 0.0 | 0.0 | yes |
| index_price_tick | 120 | 0.0 | 0.0 | yes |
| session_metadata | 1 | 0.0 | 0.0 | yes |

**Total rows:** 119,983  
**Parquet partitions:** 9  
**On-disk total (parquet + manifests):** ~1.00 MB (993 KB parquet + 10 KB manifests; 2-minute window)

## Notes

- `option_quote_tick` duplicate ratio ~41% reflects NBBO event semantics (multiple fields per logical quote update); rows retained, warning recorded in manifest.
- OI rows default to `oi_semantics_status=unconfirmed`, `oi_publication_time_confirmed=false`.
- `derived_gamma_black76_1m` stores full Black-76 inputs; separate from ThetaData first-order greeks.
- NBBO datasets labeled as quote tick/1s — **not** Level 2 order book.
- Idempotent rerun verified via unit tests; live re-run with default flags skips complete partitions.

## Git / secrets

- No parquet or real manifests committed.
- Summary JSON at `artifacts/manifests/raw_lake_pilot_summary.json` (gitignored under `artifacts/`).
- No credentials, email, or tokens in committed docs.

## ML-P4 gate

Pilot confirms lake layout, manifest checksums, and bounded ingest path. **Ready to design ML-P4 point-in-time replay** on top of this layer (replay itself not started in ML-P3).
