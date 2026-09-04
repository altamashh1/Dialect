# Deploying

**One Render service serves both the API and the React app.** The FastAPI
process mounts `frontend/dist` when it exists, so there is a single origin, a
single URL, and no CORS between frontend and backend at all.

Everything in the repo is ready. What remains needs your accounts, so it is
written as steps to run rather than something the code can do for you.

## Render service settings

| Field | Value |
|---|---|
| Language | **Python 3** (not Docker) |
| Branch | `main` |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt && cd ../frontend && npm ci && npm run build` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |

Python is pinned to 3.12 by `.python-version`. Render otherwise picks the
newest release, and `pydantic-core` has no wheel for it -- pip then tries to
compile it from Rust source and dies on Render's read-only cargo cache.

Do **not** set `VITE_API_BASE_URL`. Leaving it unset makes the frontend issue
relative requests, which is what single-origin serving needs.

## What you need

| Thing | Why | Free? |
|---|---|---|
| Render account | API container + Postgres | yes |
| Gemini API key | you already have one in `backend/.env` | yes |

## No ordering problem

Serving the frontend from the API removes the usual chicken-and-egg between
`CORS_ORIGINS` and the frontend URL: there is only one URL. Set `CORS_ORIGINS`
to your Render URL anyway -- `check_production_readiness()` rejects the
`localhost` default in production.

## Step 0 — build the image once, locally

```bash
cd backend
docker build -t cwyd-api .
docker run --rm -p 8000:8000 --env-file .env cwyd-api
curl localhost:8000/api/health   # {"status":"ok"}
```

## Step 1 — storage

Nothing to do. The Blueprint sets `STORAGE_BACKEND=db`, so uploaded files are
stored in the Postgres it creates -- no bucket, no object store, no persistent
disk. Render wipes the container filesystem on every restart, which is why
`local` is rejected in production.

Move to object storage when uploads outgrow a table: set `STORAGE_BACKEND=s3`
plus `S3_BUCKET`, `S3_ENDPOINT_URL` (Supabase/MinIO only), `S3_REGION` and AWS
credentials. Nothing else changes -- both sit behind the same interface in
`services/storage.py`.

## Step 2 — API and database on Render

`render.yaml` is a Blueprint, so Render creates both services from it.

1. Render → **New → Blueprint** → point at this repo.
2. It creates `cwyd-api` (Docker) and `cwyd-db` (Postgres). `DATABASE_URL` is
   wired between them automatically, and `JWT_SECRET` is generated.
3. Fill in the values marked `sync: false`, which are deliberately not in the
   repo: `GEMINI_API_KEY`, `S3_BUCKET`, `S3_ENDPOINT_URL`,
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
4. Leave `CORS_ORIGINS` empty for now.

The service will not boot if configuration is unsafe —
`check_production_readiness()` fails fast with the exact list, rather than
serving traffic on a forgeable JWT secret. If deploy logs show
`Refusing to start in production`, read the bullet list; it names every problem.

Note your API URL: `https://cwyd-api-XXXX.onrender.com`.

## Step 3 — frontend on Vercel

1. Vercel → **New Project** → this repo → set **Root Directory** to `frontend`.
2. Add an environment variable:
   `VITE_API_BASE_URL = https://cwyd-api-XXXX.onrender.com` — no trailing slash.
3. Deploy. Note the URL: `https://your-app.vercel.app`.

Vite inlines `VITE_*` variables **at build time**, so changing this later needs
a redeploy, not just a restart.

## Step 4 — close the loop

Back on Render, set `CORS_ORIGINS` to your exact Vercel URL (scheme included, no
trailing slash) and let it redeploy. If you use a custom domain or want preview
deploys to work, list them comma-separated:

```
CORS_ORIGINS=https://your-app.vercel.app,https://www.yourdomain.com
```

## Step 5 — the demo account and the admin user

**Demo account.** Set `DEMO_MODE=true` in the Render environment. On every boot
the API seeds a shared `demo` account holding `sample_sales.csv`, and the login
screen shows a **"Try the demo — no signup"** button. This is re-seeded on each
start on purpose: free instances wipe their disk, so an account created once by
hand would vanish on the first redeploy.

Note that the demo account is *shared* — anything one visitor uploads is visible
to the next. Delete `DEMO_MODE` to turn it off.

**Admin account.** `seed_admin.py` reads `ADMIN_PASSWORD` from the environment
and refuses to run without one, so no admin password lives in this public repo.
Set `ADMIN_PASSWORD` in the Render environment, then open the service **Shell**:

```bash
python seed_admin.py
```

## Verifying

1. `curl https://cwyd-api-XXXX.onrender.com/api/health` → `{"status":"ok"}`
2. Open the Vercel URL, sign up, upload `sample_sales.csv`, ask a question.
3. Redeploy the API, then reload a dataset — it must still be there. If it is
   gone, `STORAGE_BACKEND` is not `s3` and files are landing on the ephemeral
   container disk.

## Known rough edges on the free tier

- **Cold starts.** Render free instances spin down after ~15 minutes; the next
  request takes ~50s while the container wakes. The first question after idle
  may look like a hang. A paid instance or an external pinger fixes it.
- **Postgres expires.** Render's free database is deleted after 30 days. Export
  first, or move to a paid plan before then.
- **Memory.** Free instances have 512MB total, so `render.yaml` sets
  `SANDBOX_MEMORY_MB=384`. Raising it above the instance size means the
  container is OOM-killed instead of the sandbox returning a clean error.
- **No migrations.** `init_db()` calls `create_all()`, which creates missing
  tables but never alters existing ones. Adding a column to `models.py` will
  need Alembic, or a manual `ALTER TABLE`.

## Hardening the sandbox in production

`backend/Dockerfile` runs as a non-root user, which closes gap 3 in
[SECURITY.md](SECURITY.md). The remaining gaps — no network isolation, no CPU
limit — need the analysis subprocess to run in its own container with
`--network none` and `--pids-limit`, rather than as a child of the API process.
That is a follow-up, and SECURITY.md has the exact flags.
