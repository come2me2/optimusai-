# Optimus AI

Optimus AI is a self-optimizing advertising agent. It watches campaign metrics, chooses a bid change the way a media buyer would, and applies that change on the next hour. This version runs against a simulated Yandex Direct market, so it needs no ad-account credentials.

Each hour the agent follows the same loop: observe the last period, diagnose CPA, CTR, and spend, choose an action, apply it, and store the result.

## Features

- Simulated Yandex Direct market with auction position, time of day, weekday demand, competition, occasional market shocks, and creative fatigue.
- Bid optimizer that combines marketing rules with Thompson Sampling over a fixed set of bid steps (−20%, −10%, hold, +5%, +10%).
- Creative A/B test that starts two variants, shifts traffic toward the better one, and pauses a clear loser.
- Command-line tools to create a campaign, run simulated hours, print KPIs, and reset state.
- Web dashboard with KPI cards, charts, a decision log, and creative cards.
- HTTP API for campaigns, agent ticks, metrics, decisions, and creatives.
- SQLite storage for metrics, decisions, creative stats, and bandit state.

## Stack

| Layer | Choice |
| --- | --- |
| Local CLI and API | Python 3.10+, FastAPI, Uvicorn, Typer, Pydantic, Rich |
| Hosted server | Node.js 22+ or Bun, Express |
| Database | SQLite (`node:sqlite` on Node 22+, `bun:sqlite` on Bun) |
| Dashboard | Static HTML and Chart.js |
| Deploy config | [`onreza.toml`](onreza.toml) for [ONREZA](https://onreza.ru) process hosting |

The Python package lives in `src/optimus`. The hosted server is `server.cjs` with the same agent behaviour in `lib/`.

## Run locally

### Python CLI and dashboard

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

optimus init --name "Test CPA" --budget 5000 --target-cpa 800
optimus run --ticks 48
optimus status
optimus serve
```

The dashboard is served at `http://127.0.0.1:8000`.

| Command | What it does |
| --- | --- |
| `optimus init` | Create a mock campaign |
| `optimus run --ticks N` | Run N simulated hours |
| `optimus status` | Print KPIs and the latest decisions |
| `optimus reset` | Clear metrics and restart the simulation |
| `optimus serve` | Start the API and dashboard |

### Node server

Requires Node.js 22 or newer (the ONREZA runtime uses Bun).

```bash
npm install
npm start
```

The server listens on port 8000. `GET /health` returns `{"status":"ok"}`.

### Tests

```bash
pytest
```

## HTTP API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Process health |
| `/campaigns` | GET, POST | List or create campaigns |
| `/campaigns/{id}` | GET | Campaign, tick, cumulative metrics, KPIs |
| `/campaigns/{id}/target-cpa` | PATCH | Update the CPA target |
| `/campaigns/{id}/reset` | POST | Reset one campaign |
| `/agent/tick` | POST | Run one hour |
| `/agent/run` | POST | Run N hours (`{"ticks": 12}`) |
| `/metrics/{id}` | GET | Metric snapshots |
| `/decisions/{id}` | GET | Decision log |
| `/creatives/{id}` | GET | Creative variants, metrics, and KPIs |

## Environment variables

Set these in the shell or in the host's environment settings. Do not commit a `.env` file.

| Name | Role |
| --- | --- |
| `PORT` | HTTP port. The servers default to 8000. |
| `HOST` | Bind address. `server.cjs` defaults to all interfaces. `optimus serve` defaults to loopback. |
| `OPTIMUS_DATA_DIR` | Directory for the SQLite file when `OPTIMUS_DB_PATH` is unset. |
| `OPTIMUS_DB_PATH` | Path to the SQLite database file. |
| `OPTIMUS_STATIC_DIR` | Directory that contains the dashboard `index.html`. |

## Deploy

ONREZA builds with `npm install` and `npm run build`. The build writes a Node app to `onreza-output/` and the process entry point is `server.cjs`. Details are in [docs/deploy-onreza.md](docs/deploy-onreza.md).

## Further reading

- [Architecture](docs/architecture.md) — agent loop, simulator, and how to add a live ad platform.
- [Deploy on ONREZA](docs/deploy-onreza.md) — build settings and health check.

`YandexDirectAdapter` in `src/optimus/adapters/base.py` is a stub for a future live API. The running agent uses `MockYandexAdapter`.
