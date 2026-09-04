from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import DatasetRecord, User
from app.services import datasets as store
from app.services.agent import ask
from app.services.cache import answer_cache, make_key
from app.services.llm import LLMError
from app.services.parser import ParseError

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, aborting as soon as it exceeds `max_bytes`.

    Reading the whole file and then checking its length lets a client OOM the
    API process with a single large request, whatever MAX_UPLOAD_MB says. This
    bounds resident memory at roughly max_bytes + one chunk.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                413, f"File exceeds the {settings.max_upload_mb} MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("")
async def upload_dataset(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    raw = await _read_capped(file, settings.max_upload_mb * 1024 * 1024)
    if not raw:
        raise HTTPException(400, "Empty file.")

    try:
        record = store.create_dataset(db, user.id, raw, file.filename or "upload")
    except ParseError as exc:
        raise HTTPException(422, str(exc)) from exc

    return _summary_with_columns(record)


@router.get("")
def list_datasets(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    return [_summary_with_columns(r) for r in store.list_records(db, user.id)]


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _summary_with_columns(_require(db, dataset_id, user))


@router.get("/{dataset_id}/profile")
def get_profile(
    dataset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return store.get_profile(_require(db, dataset_id, user))


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    store.delete_dataset(db, _require(db, dataset_id, user))
    return {"deleted": True}


class AskRequest(BaseModel):
    question: str
    fresh: bool = False


@router.post("/{dataset_id}/ask")
def ask_dataset(
    dataset_id: str,
    body: AskRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    record = _require(db, dataset_id, user)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Question is empty.")

    key = make_key(dataset_id, question)
    if not body.fresh:
        hit = answer_cache.get(key)
        if hit is not None:
            return {**hit, "cached": True}

    try:
        result = ask(store.load_df(record), store.get_profile(record), question)
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc

    payload = {**result.to_dict(), "cached": False}
    if result.ok:
        answer_cache.set(key, payload)
    return payload


@router.delete("/{dataset_id}/cache")
def clear_cache(
    dataset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require(db, dataset_id, user)
    answer_cache.clear()
    return {"cleared": True}


def _summary_with_columns(record: DatasetRecord) -> dict:
    """Record summary plus the column-name list the frontend header/suggestions need."""
    profile = store.get_profile(record)
    return {**record.summary(), "columns": list(profile["columns"].keys())}


def _require(db: Session, dataset_id: str, user: User) -> DatasetRecord:
    record = store.get_record(db, dataset_id, user.id)
    if record is None:
        raise HTTPException(404, "Dataset not found.")
    return record
