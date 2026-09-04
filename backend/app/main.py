import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import check_production_readiness, settings
from app.db import init_db
from app.routers import auth, datasets, stats


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
    yield


app = FastAPI(title="Chat with your data", lifespan=lifespan)

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
    return {"status": "ok"}
