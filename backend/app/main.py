import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
