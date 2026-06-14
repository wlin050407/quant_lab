# Raw Event Lake Schema (ML-P3)

Immutable ThetaData raw event lake for 0DTE ML. **Not** the production EoD path (`data/raw/options/`).

## Root paths

| Path | Purpose |
|------|---------|
| `data/raw/thetadata/` | Production lake root (gitignored via `data/raw/`) |
| `artifacts/raw_lake_pilot/` | ML-P3 pilot writes (never commit) |

## Partition layout

Hive-style directories:

```text
data/raw/thetadata/
  dataset=<dataset>/
    root=<SPXW>/                          # option families
      trade_date=YYYY-MM-DD/
        expiration=YYYY-MM-DD/
          part-000.parquet
          _manifest.json

  dataset=<index_dataset>/
    symbol=SPX/
      trade_date=YYYY-MM-DD/
        part-000.parquet
        _manifest.json

  dataset=session_metadata/
    root=SPXW/
      trade_date=YYYY-MM-DD/
        part-000.parquet
        _manifest.json
```

## Manifest

- Version: `raw-lake-v1` (`MANIFEST_VERSION`)
- One `_manifest.json` per partition
- Fields: `dataset`, `dataset_schema_version`, `source`, `trade_date`, `root_or_symbol`, `expiration`, `row_count`, `contract_count`, timestamps, `files[]` with `sha256`, `source_requests[]`, `code_commit`, `ingestion_status`, `known_warnings`, `secret_redaction_checked`

## Schema versions

| Constant | Value |
|----------|-------|
| `SOURCE_SCHEMA_VERSION` | `thetadata-v3-grpc-1.0` |
| Per-dataset `dataset_schema_version` | `1.0.0` (all families in ML-P3) |

## Data families

| Dataset | Type | Notes |
|---------|------|-------|
| `option_quote_tick` | Source | NBBO quote event — **not** Level 2 order book |
| `option_quote_1s` | Source | NBBO 1s sampled quotes |
| `option_trade_tick` | Source | Trade prints; no synthetic bid/ask |
| `option_greeks_1m_first_order` | Source | ThetaData first-order greeks (no native gamma) |
| `derived_gamma_black76_1m` | **Derived** | Local Black-76 gamma + full input parameters |
| `option_open_interest` | Source | OI semantics **unconfirmed** by default |
| `index_price_tick` | Source | SPX index tick — not tradable ES future |
| `index_price_1s` | Source | SPX index 1s bars |
| `session_metadata` | Source | Pilot/session bounds metadata |
| `source_manifests` | Source | Upstream capability/audit manifests |

## Common columns (all datasets)

`source`, `source_client`, `source_endpoint`, `source_request_id`, `source_schema_version`, `dataset`, `dataset_schema_version`, `ingested_at`, `trade_date`, `event_timestamp`, `event_timezone`, `root_or_symbol`

## Option contract columns

`root`, `expiration`, `strike`, `right`, `contract_identifier`, `settlement_type`, `settlement_type_source`, `settlement_type_confidence`

When ThetaData does not return settlement type: `settlement_type=unknown`, `settlement_type_source=not_in_thetadata_response`, `settlement_type_confidence=unknown`.

## Dataset-specific columns

### option_quote_tick / option_quote_1s

`bid`, `ask`, `bid_size`, `ask_size`, `bid_exchange`, `ask_exchange`, `bid_condition`, `ask_condition`, `sequence`, `quote_timestamp_raw` (nullable where absent)

### option_trade_tick

`price`, `size`, `exchange`, `condition`, `sequence`

### option_greeks_1m_first_order

`implied_vol`, `delta`, `theta`, `vega`, `rho`, `epsilon`, `lambda`, `underlying_price`, `underlying_timestamp`, `bid`, `ask`

### derived_gamma_black76_1m

`gamma`, `gamma_method=black76`, `gamma_method_version`, `spot`, `strike`, `implied_vol`, `rate`, `dividend_yield_or_forward_assumption`, `time_to_expiry_years`, `expiry_timestamp`, `settlement_timestamp`, `input_source_hash`

### option_open_interest

`open_interest`, `oi_event_timestamp`, `oi_requested_date`, `oi_semantics_status=unconfirmed`, `oi_publication_time_confirmed=false`

### index_price_tick / index_price_1s

`symbol`, `price`, `open`, `high`, `low`, `close`, `volume_or_null`

### session_metadata

`session_rth_start`, `session_rth_end`, `strike_range`, `quote_interval`, `trade_window_start`, `trade_window_end`, `pilot_label`

## Code

- Schema constants: `src/quant_lab/data/intraday_schema.py`
- Manifest: `src/quant_lab/data/intraday_manifest.py`
- Ingest: `src/quant_lab/data/intraday_lake.py`
