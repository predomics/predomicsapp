"""WebSocket endpoint for live job log streaming."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from ..core.config import settings
from ..core.database import async_session_factory
from ..models.db_models import User, Job, Project, ProjectShare
from ..services import ws_tickets

_log = logging.getLogger(__name__)
router = APIRouter()


async def _verify_ws_access(ticket: str | None, project_id: str) -> bool:
    """Redeem a single-use ticket and check that its user may see the project."""
    user_id = ws_tickets.redeem(ticket or "")
    if not user_id:
        return False
    async with async_session_factory() as db:
        result = await db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        if result.scalar_one_or_none() is None:
            return False
        # Check project ownership
        result = await db.execute(
            select(Project.user_id).where(Project.id == project_id)
        )
        owner_id = result.scalar_one_or_none()
        if owner_id is None:
            return False
        if owner_id == user_id:
            return True
        # Check shared access
        result = await db.execute(
            select(ProjectShare.id).where(
                ProjectShare.project_id == project_id,
                ProjectShare.user_id == user_id,
            )
        )
        return result.first() is not None


def _read_new_log(log_path: Path, last_size: int) -> tuple[str, int]:
    """Return (text appended since ``last_size``, new offset). Blocking."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return "", last_size
    if size < last_size:      # log was rewritten
        last_size = 0
    if size == last_size:
        return "", last_size
    with open(log_path, "rb") as f:
        f.seek(last_size)
        raw = f.read(size - last_size)
    # Do not split a multi-byte character across two messages: an incomplete
    # sequence at the very end is left for the next read.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start >= len(raw) - 3 and e.end == len(raw) and e.start > 0:
            raw = raw[:e.start]
        text = raw.decode("utf-8", errors="replace")
    return text, last_size + len(raw)


def _read_progress_if_changed(progress_path: Path, last_sig):
    """Return (progress dict or None, signature). Blocking."""
    try:
        st = progress_path.stat()
        sig = (st.st_mtime_ns, st.st_size)
        if sig == last_sig:
            return None, last_sig
        return json.loads(progress_path.read_text()), sig
    except (OSError, ValueError):
        return None, last_sig


@router.websocket("/ws/jobs/{project_id}/{job_id}")
async def job_log_ws(
    websocket: WebSocket,
    project_id: str,
    job_id: str,
    ticket: str | None = Query(None),
):
    """Stream job console.log in real-time (tail -f style).

    Browsers cannot send an Authorization header on a WebSocket, so the client
    first calls ``POST /api/auth/ws-ticket`` and passes the returned single-use
    ticket as ``?ticket=``. The access token is not accepted here: URLs end up
    in proxy and access logs.

    Messages sent to client:
    - {"type": "status", "status": "running"}
    - {"type": "log", "content": "...new lines..."}
    - {"type": "done", "status": "completed"|"failed"}
    - {"type": "error", "message": "..."}
    """
    if not await _verify_ws_access(ticket, project_id):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    job_dir = Path(settings.project_dir) / project_id / "jobs" / job_id
    log_path = job_dir / "console.log"
    progress_path = job_dir / "progress.json"
    last_size = 0
    last_status = None
    last_progress_sig = None

    try:
        while True:
            # Check job status from DB
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Job).where(Job.id == job_id, Job.project_id == project_id)
                )
                job = result.scalar_one_or_none()
                if not job:
                    await websocket.send_json({"type": "error", "message": "Job not found"})
                    break

                current_status = job.status

            # Send status change
            if current_status != last_status:
                await websocket.send_json({
                    "type": "status",
                    "status": current_status,
                })
                last_status = current_status

            # Stream new log content (byte offsets; tolerant of partial UTF-8 sequences)
            new_content, last_size = await asyncio.to_thread(_read_new_log, log_path, last_size)
            if new_content:
                await websocket.send_json({
                    "type": "log",
                    "content": new_content,
                })

            # Stream structured progress metrics
            progress_data, last_progress_sig = await asyncio.to_thread(
                _read_progress_if_changed, progress_path, last_progress_sig,
            )
            if progress_data is not None:
                await websocket.send_json({
                    "type": "progress",
                    "data": progress_data,
                })

            # Stop on terminal state
            if current_status in ("completed", "failed"):
                await websocket.send_json({
                    "type": "done",
                    "status": current_status,
                })
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        _log.debug("WebSocket client disconnected for job %s", job_id)
    except Exception as e:
        _log.error("WebSocket error for job %s: %s", job_id, e)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
