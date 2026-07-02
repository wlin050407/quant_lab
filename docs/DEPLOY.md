# Quantlab Terminal — cloud deploy

Deploy as a **single persistent Docker web service**. No GitHub Pages, no bundled historical parquet — live and recent sessions use your configured intraday provider.

**Recommended host:** [Render](https://render.com) **Starter** ($7/mo, always-on).  
**Default data provider:** GEXBot + Unusual Whales (`TERMINAL_CHAIN_PROVIDER=auto`).  
See [`docs/terminal/GEXBOT_MIGRATION_PLAN.md`](terminal/GEXBOT_MIGRATION_PLAN.md).

## Render vs Railway (honest comparison)

| | **Render Starter** | **Render Free** | **Railway Hobby** |
|---|-------------------|-----------------|-------------------|
| Idle behavior | **Always on** | **Spins down** after ~15 min no HTTP traffic | Usually always-on while credits last |
| Cold start | None | **30–90s** first request after sleep | Rare; credit exhaustion can pause service |
| Fit for live 0DTE Terminal | **Yes** | Poor (first open each morning is slow) | OK if stable; some users see disconnects |
| Health check | `/api/health` | Same | Same |

**结论：** 不是「Render 休眠后比 Railway 更不死」—— **Render 免费版反而更容易整服务睡死**。你要盘中稳定 live，应上 **Render Starter（或同类 always-on）**，不是靠免费 tier。Railway 断连多半是 credits/网络/进程重启；换 Render Free 通常更差。

Phase B 已加 **启动时 GEXBot hist 预缓存** + **盘中后台 REST poller**，减轻冷启动后第一次 snapshot 的延迟，但 **无法替代 always-on**。

## What runs in the cloud

| Mode | Vendor (GEXBot + UW) |
|------|----------------------|
| Today (live) | GEXBot + UW parallel pull; 30s UI poll + optional background poller |
| Last ~14 days | GEXBot `/hist/` → Parquet on disk (1Hz); **pre-warmed on startup** |
| Older | Hidden (`TERMINAL_HISTORY_DAYS=14`) |

## Required secrets (Render dashboard)

| Variable | Purpose |
|----------|---------|
| `GEXBOT_API_KEY` | GEXBot Quant Bearer |
| `UNUSUAL_WHALES_API_KEY` | Option chain + flow |
| `TERMINAL_AUTH_USER` | Basic auth (strongly recommended) |
| `TERMINAL_AUTH_PASSWORD` | Basic auth |

## Optional tuning

| Variable | Default | Purpose |
|----------|---------|---------|
| `TERMINAL_CHAIN_PROVIDER` | `auto` | `auto` / `vendor` / `thetadata` |
| `TERMINAL_HISTORY_DAYS` | `14` | Date picker window |
| `TERMINAL_PREWARM_HIST` | `1` | Background download GEXBot hist on startup |
| `TERMINAL_VENDOR_LIVE_POLLER` | `1` | RTH background cache refresh (no UI visit needed) |
| `TERMINAL_LIVE_REFRESH_SECONDS` | `30` | Live poll interval |
| `GEXBOT_HIST_CACHE_DIR` | `data/processed/gexbot_hist` | Hist Parquet cache |

Health check (no auth): `GET /api/health` — includes `chain_provider`, cache file count.

## Render (recommended)

### Blueprint

1. Push repo to GitHub.
2. Render → **New** → **Blueprint** → connect repo (`render.yaml` included).
3. Set secrets: `GEXBOT_API_KEY`, `UNUSUAL_WHALES_API_KEY`, `TERMINAL_AUTH_*`.
4. Confirm **plan: starter** in blueprint (not free).
5. Deploy → open URL → basic auth prompt.

### Manual web service

1. **New Web Service** → Docker → `Dockerfile` at repo root.
2. Health check path: `/api/health`
3. Add env vars above.
4. **Instance type:** Starter or higher.

### Keep-alive on free tier (not recommended for trading hours)

If you must use Render Free, use an external cron (e.g. [cron-job.org](https://cron-job.org)) to `GET https://your-app.onrender.com/api/health` every **10 minutes** during RTH only. Still expect occasional cold starts.

## Railway (legacy / optional)

Still supported via `railway.toml` + `scripts/deploy_railway.ps1` (ThetaData-oriented). For vendor mode, set `GEXBOT_API_KEY` / `UNUSUAL_WHALES_API_KEY` in Railway variables manually instead of the deploy script defaults.

## Local Docker smoke test

```bash
docker build -t quantlab-terminal .
docker run --rm -p 8765:8765 \
  -e GEXBOT_API_KEY=your-gexbot-key \
  -e UNUSUAL_WHALES_API_KEY=your-uw-key \
  -e TERMINAL_AUTH_USER=admin \
  -e TERMINAL_AUTH_PASSWORD=changeme \
  -e TERMINAL_CHAIN_PROVIDER=vendor \
  -e TERMINAL_HISTORY_DAYS=14 \
  quantlab-terminal
```

Open http://127.0.0.1:8765

## Architecture notes

- **Not serverless** — snapshot builds take seconds; needs a running container during market hours.
- **Frontend polls** `/api/snapshot` (~30s live); background poller keeps vendor cache warm when enabled.
- **Hist cache** persists in container disk (`data/processed/gexbot_hist`); redeploy clears it — prewarm repopulates on boot.
- **Credentials** stay server-side only.

## Calibration

Compare local flip vs GEXBot `zero_gamma`:

```bash
python scripts/calibrate_vendor_gex.py --symbol ^SPX --time 13:00:00
```

## Updating the UI

Push to GitHub to trigger rebuild, or locally:

```bash
python scripts/build_terminal_ui.py --install
docker build -t quantlab-terminal .
```
