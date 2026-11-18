# Deploy on ONREZA

The hosted app is the Node server in `server.cjs`. ONREZA runs that process with Bun. Python is used for local development and tests; the build image does not need it.

Build settings are already declared in [`onreza.toml`](../onreza.toml).

## Connect the repository

1. In the ONREZA workspace, open **Settings → Git**.
2. Install the GitHub App and grant access to this repository.
3. Create a project from GitHub and set the production branch to `main`.

## Build

In **Project → Settings → Build & Deployment**:

| Setting | Value |
| --- | --- |
| Framework preset | Other |
| Install command | `npm install` |
| Build command | `npm run build` |
| Output directory | `onreza-output` |

`npm run build` copies `server.cjs`, `lib/`, and `static/` into `onreza-output/` and installs Express there.

## Process

| Setting | Value |
| --- | --- |
| Compute type | process |
| Entry point | `server.cjs` |
| Health check | HTTP `GET /health` |

## Environment

Optional variables:

| Name | Role |
| --- | --- |
| `OPTIMUS_DATA_DIR` | Writable directory for the SQLite file |
| `HOST` | Bind address; use all interfaces on the host |
| `OPTIMUS_DB_PATH` | Explicit path to the database file |
| `OPTIMUS_STATIC_DIR` | Override for the dashboard files |

The platform sets `PORT`. Keep real values in the host's environment settings, not in git.

## Release

Save the settings, then deploy from the ONREZA UI or push to `main` if auto-deploy is enabled.

After the deploy is live:

- `GET /health` returns `{"status":"ok"}`
- `/` serves the dashboard

## Check the same server locally

```bash
npm install
npm start
```

Or build the artifact the host runs:

```bash
npm install
npm run build
cd onreza-output
npm start
```

The Python entry point `server.py` runs the FastAPI app for local use after `pip install .`. Point the ONREZA install and build commands at npm, as in `onreza.toml`.
