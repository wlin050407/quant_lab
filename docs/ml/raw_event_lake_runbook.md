# Raw Event Lake Runbook (ML-P3)

Operational guide for the immutable ThetaData raw event lake. **Does not** replace EoD `data/raw/options/` ingestion.

## Prerequisites

- ThetaData Standard credentials via `THETADATA_EMAIL` + `THETADATA_PASSWORD` or `THETADATA_CREDENTIALS_FILE`
- Python env with `thetadata`, `pyarrow`, project deps installed
- **Do not** commit `artifacts/raw_lake_pilot/`, `*.parquet`, or real `_manifest.json`

## Pilot (bounded)

Dry-run first (no network):

```bash
python scripts/build_raw_event_lake_pilot.py --dry-run
```

Live pilot (1 date, SPXW 0DTE, `strike_range=2`, 13:00–13:02 ET window):

```bash
python scripts/build_raw_event_lake_pilot.py --date 2026-06-10 --strike-range 2
```

Output root: `artifacts/raw_lake_pilot/`

Summary JSON (gitignored path): `artifacts/manifests/raw_lake_pilot_summary.json`

Idempotent rerun skips complete partitions. To replace:

```bash
python scripts/build_raw_event_lake_pilot.py --overwrite
```

## Ingest semantics

1. Normalize ThetaData frames → lake schema (`intraday_lake.normalize_*`)
2. Stage under `.staging/` inside partition
3. Write `part-000.parquet`, compute SHA-256
4. Atomic `os.replace` into partition
5. Write `_manifest.json` with row counts, bounds, warnings
6. Verify checksums; mark `incomplete` on failure

## Duplicate / out-of-order

- Duplicates detected on `(contract_identifier, event_timestamp, sequence)` when available
- Ratios recorded in manifest `known_warnings`; rows are **not** silently dropped
- Out-of-order timestamps recorded; rows retained

## OI semantics

- Default `oi_semantics_status=unconfirmed`
- Do **not** label as realtime open interest in docs or UI

## Black-76 gamma

- Stored only in `derived_gamma_black76_1m`
- Never conflate with ThetaData-native gamma (Standard tier has no second-order greeks)

## Verification

```bash
python -m pytest -q tests/test_intraday_lake.py tests/test_intraday_manifest.py tests/test_intraday_schema.py
python -m ruff check src/quant_lab/data/intraday_*.py scripts/build_raw_event_lake_pilot.py tests/test_intraday_*.py
```

## Out of scope (ML-P3)

- Multi-year backfill
- Point-in-time replay (ML-P4)
- Model training
- Changes to production Pin/GEX/VEX or Terminal UI
