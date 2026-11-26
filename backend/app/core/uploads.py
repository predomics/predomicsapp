"""Bounded reading of uploaded files."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from .config import settings

_CHUNK = 1024 * 1024


async def read_upload(file: UploadFile, max_mb: int | None = None) -> bytes:
    """Read an upload fully, refusing anything larger than the limit with a 413.

    The limit defaults to PREDOMICS_MAX_UPLOAD_MB. Reading in chunks means an
    oversized body is rejected as soon as it crosses the limit instead of being
    loaded whole into memory first.
    """
    limit = (max_mb if max_mb is not None else settings.max_upload_mb) * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large (limit {limit // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


VALID_FILE_ROLES = ("xtrain", "ytrain", "xtest", "ytest", "metadata")


def check_role(role: str | None) -> str | None:
    """Validate a dataset file role given by a client; None/"" means "infer it"."""
    if role in (None, ""):
        return None
    if role not in VALID_FILE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown file role '{role}'. Use one of: {', '.join(VALID_FILE_ROLES)}",
        )
    return role
