import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import check_production_readiness, settings
from app.db import SessionLocal, init_db
from app.routers import auth, datasets, stats
from app.services.demo import seed_demo


def _configure_logging() -> None:
    """One structured line per LLM call on stdout, alongside uvicorn's logs."""
    logger = logging.getLogger("llm")
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to serve production traffic on development defaults: a forgeable
    # JWT secret or an ephemeral disk fails quietly and expensively otherwise.
    problems = check_production_readiness()
    if problems:
        detail = "\n".join(f"  - {p}" for p in problems)
        raise RuntimeError(f"Refusing to start in production:\n{detail}")
    init_db()
    # Re-seeded on every boot: free hosting wipes the disk on each restart, so a
    # demo account created once by hand would not survive the first redeploy.
    if settings.demo_mode:
        db = SessionLocal()
        try:
            seed_demo(db)
        finally:
            db.close()
    yield


app = FastAPI(title="Dialect", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(stats.router)


@app.get("/api/health")
def health() -> dict:
    """Liveness probe. `demo` tells the login screen whether to offer
    one-click access, so the button never appears where it would 404."""
    return {"status": "ok", "demo": settings.demo_mode}


# --- Single-origin frontend -------------------------------------------------
#
# When `frontend/dist` has been built, this process serves the React app as well
# as the API. One origin means no CORS preflight, no VITE_API_BASE_URL baked in
# at build time, and one URL to put on a CV -- at the cost of the API's cold
# start now gating the first page load too.
#
# Mounted only when the build exists, so a backend-only run (tests, local dev
# against the Vite dev server) behaves exactly as before.

_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_INDEX = _DIST / "index.html"


def _safe_asset(relative: str) -> Path | None:
    """Resolve a request path inside the build directory, or None.

    `relative` is attacker-controlled, so resolve it and confirm the result is
    still under _DIST -- otherwise `../../etc/passwd` reads whatever the process
    can reach.
    """
    if not relative:
        return None
    try:
        candidate = (_DIST / relative).resolve()
    except (OSError, ValueError):
        return None
    if candidate == _DIST or _DIST not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


if _INDEX.is_file():

    # HEAD as well as GET: FastAPI, unlike plain Starlette, does not add HEAD to
    # a GET route, so a platform probing `HEAD /` gets a 405 and may read the
    # service as unhealthy.
    @app.api_route(
        "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def serve_spa(full_path: str) -> FileResponse:
        # Registered last, so every route above still wins. Unmatched /api paths
        # must 404 as JSON rather than silently returning the HTML shell.
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")

        asset = _safe_asset(full_path)
        if asset is not None:
            return FileResponse(asset)
        # Client-side routing: unknown paths are the app's problem, not 404s.
        return FileResponse(_INDEX)
