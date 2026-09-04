# Dialect — LLM-Powered Data Analysis App

Upload a CSV / Excel / JSON dataset, ask questions in plain English, and get
answers + charts. An LLM (Google Gemini) translates each question into pandas
code, which runs in a sandboxed subprocess; errors feed back to the LLM for a
retry.

## Stack

| Layer    | Tech                                            |
|----------|-------------------------------------------------|
| Frontend | React + Vite + Tailwind CSS                     |
| Backend  | FastAPI + Uvicorn (Python 3.12)                 |
| Data     | pandas, openpyxl                                |
| LLM      | Google Gemini (`google-genai`)                  |
| Sandbox  | local restricted subprocess (timeout + limited namespace) |

## Build order (bricks)

0. Repo skeleton ................................. done
1. Upload endpoint + file parser ................. done
2. Schema profiler .............................. done
3. LLM: schema + question -> pandas code ......... done
4. Sandboxed code executor ...................... done
5. Error -> retry loop (agent loop) ............. done
5b. Answer verification (invariants + critic) ... done
6. Auto-visualization (Recharts) ............... done
7. Chat UI wiring .............................. done
8. Caching layer (TTL + LRU, in-process) ....... done
9. Auth (JWT) + per-user persistence (SQLite) .. done
10. Pluggable file storage (local | S3) ........ done
11. Observability (per-call metrics + /api/stats) done
12. Deployment (Vercel + Render/Railway)
13. QA pass on varied datasets

## Answer verification

A successful result is checked before it's returned ([app/services/verify.py](backend/app/services/verify.py)):

- **Invariant checks** (deterministic, free) — negative counts, a percentage
  outside 0–100, an empty result, nulls in the output, a count exceeding the row
  count.
- **Critic pass** (one LLM call) — a second model is shown the question, schema,
  generated code, and result, and answers PASS / FAIL. Never blocks an answer;
  failures just lower confidence.

The two fold into `confidence: high | medium | low` on the answer payload, shown
as a badge in the UI with any notes. Toggle with `VERIFY_ANSWERS` (default on).

## Observability

Every Gemini call is recorded in-process ([app/services/telemetry.py](backend/app/services/telemetry.py)):
model, latency, prompt/output token counts, an estimated USD cost, which retry
attempt it was, and success/failure. Two ways to read it:

- **`GET /api/stats`** (auth required) — totals, success rate, latency p50/p95,
  token + cost totals, per-model breakdown, recent calls, recent errors. The
  frontend "Stats" button in the header polls this live.
- **Structured logs** — one JSON line per call on stdout via the `llm.telemetry`
  logger, e.g. `{"event": "llm_call", "model": "...", "latency_ms": 995.0, "attempt": 1, "ok": true, ...}`.

Cost prices in `telemetry._PRICING` are estimates; call `set_pricing()` at
startup with your real per-token rates for production.

## Running locally (dev / debug)

Only `GEMINI_API_KEY` is required. DB is SQLite, storage is local disk, both
zero-config.

### Backend — terminal 1

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit .env: set GEMINI_API_KEY, and a JWT_SECRET
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs

### Frontend — terminal 2

```powershell
cd frontend
npm install
npm run dev
```

App at http://localhost:5173 (Vite proxies `/api` -> `:8000`).

### VS Code debugging

`.vscode/launch.json` has **"Backend: FastAPI (uvicorn)"** (breakpoints in
`app/`) and **"Backend: pytest"**. Select the `backend/.venv` interpreter first
(Ctrl+Shift+P -> Python: Select Interpreter). Run the frontend from an
integrated terminal alongside.

## Storage backends

| `STORAGE_BACKEND` | Needs | Use |
|-------------------|-------|-----|
| `local` (default) | nothing | dev, single-host deploys with a persistent disk |
| `s3` | `S3_BUCKET` (+ `S3_ENDPOINT_URL` for Supabase/MinIO), AWS creds | production / ephemeral hosts |

## Deploying

Vercel + Render + Postgres, step by step: [DEPLOY.md](DEPLOY.md).

## Security

The app executes LLM-generated Python. The sandbox design, the escapes it is
tested against, and its known gaps are documented in [SECURITY.md](SECURITY.md).
