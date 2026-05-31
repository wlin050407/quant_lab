# Quantlab Terminal — cloud deploy

Deploy as a **single persistent Python service** (Railway or Render). No GitHub Pages, no bundled historical parquet — live and recent sessions are pulled from ThetaData at request time.

## What runs in the cloud

| Mode | Source |
|------|--------|
| Today (live) | ThetaData, 60s poll + server cache |
| Last ~2 weeks | ThetaData on demand (no local parquet) |
| Older history | Not exposed (`TERMINAL_HISTORY_DAYS=14`) |

Local dev is unchanged: full parquet history when `TERMINAL_HISTORY_DAYS` is unset.

## Required secrets

Set in the platform dashboard (never commit):

| Variable | Purpose |
|----------|---------|
| `THETADATA_EMAIL` | ThetaData account |
| `THETADATA_PASSWORD` | ThetaData password |
| `TERMINAL_AUTH_USER` | Basic auth username (strongly recommended) |
| `TERMINAL_AUTH_PASSWORD` | Basic auth password |

Optional:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TERMINAL_HISTORY_DAYS` | `14` | Calendar days of history in date picker |
| `PORT` | `8765` | Set automatically on Railway/Render |

## Railway (recommended)

### One command (after login)

```powershell
cd E:\quant_lab
railway login          # browser once
.\scripts\deploy_railway.ps1
```

The script reads your local ThetaData creds (`.env` / creds file), creates `quantlab-terminal` on Railway, sets env vars, deploys via Dockerfile, and writes basic-auth credentials to `.railway-deploy.local` (gitignored).

### Manual dashboard

1. Push this repo to GitHub.
2. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo** → `wlin050407/quant_lab`.
3. **Variables** → add the four secrets below.
4. Deploy. Open the generated URL; browser prompts for basic auth.

### CI / headless (optional)

Create a token at [railway.app/account/tokens](https://railway.app/account/tokens), then:

```powershell
$env:RAILWAY_TOKEN = "your-token"
.\scripts\deploy_railway.ps1
```

Health check: `GET /api/health` (no auth).

## Render

1. **New** → **Blueprint** → connect repo (`render.yaml` included).
2. Fill secret env vars in the dashboard.
3. Deploy.

Or: **New Web Service** → Docker → point at `Dockerfile`.

## Local Docker smoke test

```bash
docker build -t quantlab-terminal .
docker run --rm -p 8765:8765 \
  -e THETADATA_EMAIL=you@example.com \
  -e THETADATA_PASSWORD=secret \
  -e TERMINAL_AUTH_USER=admin \
  -e TERMINAL_AUTH_PASSWORD=changeme \
  -e TERMINAL_HISTORY_DAYS=14 \
  quantlab-terminal
```

Open http://127.0.0.1:8765

## Architecture notes

- **Not serverless** — snapshot builds can take several seconds; needs a always-on container.
- **No WebSocket** — frontend already polls `/api/snapshot` every 60s in live mode.
- **Credentials** stay server-side; the browser only talks to your FastAPI app.
- **Data directory** is empty in the image; recent history is fetched from ThetaData, not shipped as parquet.

## Updating the UI

The Docker image bakes `static/dist` at build time. Push to GitHub to trigger a rebuild, or locally:

```bash
python scripts/build_terminal_ui.py --install
docker build -t quantlab-terminal .
```
