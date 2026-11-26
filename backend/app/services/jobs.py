"""Local job runner — bounded, fair, cancellable, restart-safe execution of analysis jobs.

How it works
------------
Submitted jobs go to an in-memory FIFO queue with status ``pending``. A
dispatcher starts the oldest eligible job whenever a slot is free:

* at most ``PREDOMICS_MAX_CONCURRENT_JOBS`` jobs run at once;
* at most ``PREDOMICS_MAX_JOBS_PER_USER`` of them belong to the same user
  (0 = no per-user limit), so one user's batch cannot starve everybody else —
  a job that is skipped for this reason keeps its place in the queue.

Each running job is one thread that starts the engine in a subprocess (its own
process group), streams its output to ``console.log`` and records the outcome in
the database. Whatever happens — an exception, a cancellation, a timeout, a
deleted job — the job never stays ``running``.

Restarts
--------
The queue itself is memory, but everything needed to rebuild it is durable: the
``jobs`` row (status ``pending``) and the job's ``param.yaml`` on the data
volume. At startup :func:`reconcile_orphaned_jobs` therefore

* re-queues every ``pending`` local job, oldest first;
* marks jobs that were ``running`` as failed ("interrupted by a restart"), since
  their worker process died with the old server — or re-queues them too when
  ``PREDOMICS_REQUEUE_INTERRUPTED`` is on (the run starts again from scratch);
* re-attaches the poller of jobs dispatched to scitq.

Why this stays in-process (single replica)
------------------------------------------
The application is deployed as one container with one uvicorn worker, next to
the data volume the engine reads and writes. An in-process runner needs no extra
service (no Redis, no broker, no second image) and cancellation is a signal to a
child process. The price: slots, the queue and the process table live in this
process, so **exactly one application process may run**. Two processes would
each run ``max_concurrent_jobs`` jobs, and each would treat the other's jobs as
orphans at startup.

To run several replicas this module would have to change as follows: claim jobs
in the database instead of in memory (``SELECT … FOR UPDATE SKIP LOCKED`` on
``pending`` rows, with a ``claimed_by``/heartbeat column); enforce the limits by
counting ``running`` rows inside that same transaction; replace startup
reconciliation by a heartbeat timeout; deliver cancellation through the database
(a ``cancel_requested`` flag polled by the owning process) because the worker
PID is only meaningful on the host that started it; and put the data directory
on storage shared by all replicas.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ..core.config import settings
from ..core.database import sync_session_factory
from ..models.db_models import Job, Webhook
from . import engine, results_io, scitq_client
from .sklearn_runner import is_sklearn_algo
from .webhooks import send_webhook_sync

logger = logging.getLogger(__name__)

CANCELLED_MESSAGE = "Cancelled by user."
INTERRUPTED_MESSAGE = (
    "Interrupted by a server restart before it finished. Re-run the job to get results."
)
NO_ENGINE_MESSAGE = (
    "The gpredomics engine (gpredomicspy) is not installed on this server, so the "
    "analysis could not run. Ask the administrator to check the installation."
)

_lock = threading.RLock()
_active: set[str] = set()                    # queued, running or polled in this process
_procs: dict[str, subprocess.Popen] = {}     # running worker processes
_cancelled: set[str] = set()                 # cancellation requested
_timed_out: set[str] = set()
_queue: list["_Queued"] = []                 # waiting local jobs, oldest first
_running: dict[str, str] = {}                # job id -> user id, for jobs holding a slot
_stopped_by_shutdown: set[str] = set()       # workers killed because the server is stopping


class JobCancelled(Exception):
    pass


class _Queued:
    __slots__ = ("job_id", "project_id", "param_path", "user_id")

    def __init__(self, job_id: str, project_id: str, param_path: str, user_id: str):
        self.job_id, self.project_id, self.param_path, self.user_id = job_id, project_id, param_path, user_id


def _setting(name: str, default, cast=int):
    """A setting from ``core.config`` or, until it is declared there, from the environment."""
    value = getattr(settings, name, None)
    if value is None:
        value = os.environ.get(f"PREDOMICS_{name.upper()}")
    if value is None or value == "":
        return default
    try:
        if cast is bool:
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        return cast(value)
    except (TypeError, ValueError):
        return default


def max_concurrent() -> int:
    return max(1, _setting("max_concurrent_jobs", 2))


def max_per_user() -> int:
    """Jobs one user may run at the same time (0 = no per-user limit)."""
    return max(0, _setting("max_jobs_per_user", 0))


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _inline() -> bool:
    """Tests run jobs inside the request's background tasks (deterministic)."""
    return os.environ.get("PREDOMICS_JOBS_INLINE") == "1"


def effective_threads(requested) -> int:
    """Threads a job may use: the request, capped by the server limit / CPU count."""
    cap = int(settings.max_threads_per_job) or (os.cpu_count() or 1)
    try:
        requested = int(requested)
    except (TypeError, ValueError):
        requested = 1
    return max(1, min(requested, cap))


def _dispatch() -> None:
    """Start queued jobs while slots are free. Safe to call from any thread."""
    to_start: list[_Queued] = []
    with _lock:
        limit, per_user = max_concurrent(), max_per_user()
        i = 0
        while i < len(_queue) and len(_running) < limit:
            item = _queue[i]
            if per_user and item.user_id:
                mine = sum(1 for uid in _running.values() if uid == item.user_id)
                if mine >= per_user:
                    i += 1          # stays queued, keeps its place; try the next one
                    continue
            _queue.pop(i)
            _running[item.job_id] = item.user_id
            to_start.append(item)
    for item in to_start:
        threading.Thread(
            target=_run_slot, args=(item,), name=f"predomics-job-{item.job_id}", daemon=True,
        ).start()


def _run_slot(item: _Queued) -> None:
    try:
        run_local_job(item.job_id, item.project_id, item.param_path, item.user_id)
    finally:
        with _lock:
            _running.pop(item.job_id, None)
        _dispatch()


def submit_local(job_id: str, project_id: str, param_path: str, user_id: str = "",
                 background_tasks=None) -> None:
    """Queue a job for local execution. Returns immediately."""
    with _lock:
        _active.add(job_id)
        if _inline() and background_tasks is not None:
            inline = True
        else:
            inline = False
            _queue.append(_Queued(job_id, project_id, param_path, user_id or ""))
    if inline:
        background_tasks.add_task(run_local_job, job_id, project_id, param_path, user_id)
    else:
        _dispatch()


def submit_scitq_poller(job_id: str, project_id: str, scitq_task_id: int, user_id: str = "",
                        background_tasks=None) -> None:
    """Follow a job dispatched to scitq (a light polling thread, not a job slot)."""
    with _lock:
        _active.add(job_id)
    if _inline() and background_tasks is not None:
        background_tasks.add_task(poll_scitq_job, job_id, project_id, scitq_task_id, user_id)
    else:
        threading.Thread(
            target=poll_scitq_job, args=(job_id, project_id, scitq_task_id, user_id),
            name=f"predomics-scitq-{job_id}", daemon=True,
        ).start()


def is_tracked(job_id: str) -> bool:
    """True if this process is queueing, running or polling the job."""
    with _lock:
        return job_id in _active


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return job_id in _cancelled


def stats() -> dict:
    """Runner state for metrics and health: counts only, cheap, thread-safe."""
    with _lock:
        running, queued = len(_running), len(_queue)
        users_waiting = len({q.user_id for q in _queue})
        return {
            "running": running,
            "queued": queued,
            "tracked": len(_active),            # includes scitq pollers
            "max_concurrent": max_concurrent(),
            "max_per_user": max_per_user(),
            "free_slots": max(0, max_concurrent() - running),
            "users_waiting": users_waiting,
        }


def wait_idle(timeout: float = 30.0) -> bool:
    """Block until nothing is queued or running (used by tests and shutdown)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lock:
            if not _queue and not _running:
                return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------------------
# Database helpers (sync sessions: this code runs in worker threads)
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update_job(job_id: str, **cols) -> bool:
    """Set columns on a job. Returns False if the job no longer exists."""
    with sync_session_factory() as db:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            return False
        for k, v in cols.items():
            setattr(job, k, v)
        db.commit()
        return True


def _append_log(log_path: Path, text: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as lf:
            lf.write(text)
    except OSError:
        pass


def fire_webhooks(user_id: str, event: str, payload: dict) -> None:
    """Fire matching webhooks for a user (sync, called from worker threads)."""
    if not user_id:
        return
    try:
        with sync_session_factory() as db:
            result = db.execute(
                select(Webhook).where(
                    Webhook.user_id == user_id,
                    Webhook.is_active.is_(True),
                )
            )
            webhooks = result.scalars().all()
            for wh in webhooks:
                if event in (wh.events or []):
                    send_webhook_sync(wh.url, payload, wh.secret, retries=2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook delivery error: %s", exc)


def _fail(job_id: str, project_id: str, user_id: str, message: str) -> None:
    job_dir = results_io.job_dir(project_id, job_id)
    _append_log(job_dir / "console.log", f"\n[error] {message}\n")
    try:
        exists = _update_job(
            job_id, status="failed", error_message=message, completed_at=_now(), pid=None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not record failure of job %s", job_id)
        return
    if exists:
        logger.error("Job %s failed: %s", job_id, message)
        fire_webhooks(user_id, "job.failed", {
            "event": "job.failed", "job_id": job_id, "project_id": project_id,
            "error": message,
        })


def job_disk_size(project_id: str, job_id: str) -> int | None:
    """Total size of a job directory on disk (bytes)."""
    job_dir = results_io.job_dir(project_id, job_id)
    if not job_dir.is_dir():
        return None
    total = 0
    for f in job_dir.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def _complete(job_id: str, project_id: str, user_id: str) -> None:
    summary = results_io.load_summary(project_id, job_id) or {}
    best_auc = summary.get("best_fit") if summary.get("regression") else summary.get("best_auc")
    _update_job(
        job_id,
        status="completed",
        results_path=str(results_io.results_path(project_id, job_id)),
        completed_at=_now(),
        disk_size_bytes=job_disk_size(project_id, job_id),
        best_auc=best_auc,
        best_k=summary.get("best_k"),
        pid=None,
    )
    logger.info("Job %s completed", job_id)
    fire_webhooks(user_id, "job.completed", {
        "event": "job.completed", "job_id": job_id, "project_id": project_id,
    })


# ---------------------------------------------------------------------------
# Local execution
# ---------------------------------------------------------------------------

def _worker_command(param_path: str, results_path: Path) -> tuple[list[str], str]:
    """Command line and working directory that start the worker module."""
    package = __package__ or "app.services"          # "backend.app.services" or "app.services"
    here = Path(__file__).resolve()
    cwd = here.parents[3] if package.startswith("backend.") else here.parents[2]
    return [sys.executable, "-u", "-m", f"{package}.worker", param_path, str(results_path)], str(cwd)


def _kill(proc: subprocess.Popen, grace: float = 10.0) -> None:
    """Terminate the worker's whole process group; force-kill after ``grace`` seconds."""
    def _signal(sig):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.send_signal(sig)
            except Exception:  # noqa: BLE001
                pass

    if proc.poll() is not None:
        return
    _signal(signal.SIGTERM)

    def _force():
        if proc.poll() is None:
            _signal(signal.SIGKILL)

    t = threading.Timer(grace, _force)
    t.daemon = True
    t.start()


def _tail(path: Path, n: int = 500) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 4 * n))
            return fh.read().decode("utf-8", errors="replace")[-n:]
    except OSError:
        return "Unknown error"


def _planned_generations(param_path: str) -> int:
    """Planned generation count of a genetic-algorithm job (0 when unknown or not GA)."""
    import yaml

    try:
        with open(param_path) as fh:
            params = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return 0
    if str((params.get("general") or {}).get("algo", "ga")).lower() != "ga":
        return 0
    try:
        return max(0, int((params.get("ga") or {}).get("max_epochs") or 0))
    except (TypeError, ValueError):
        return 0


def run_local_job(job_id: str, project_id: str, param_path: str, user_id: str = "") -> None:
    """Run one job to a terminal state. Never raises; never leaves it ``running``."""
    try:
        _run_local_job(job_id, project_id, param_path, user_id)
    except JobCancelled:
        with _lock:
            stopping = job_id in _stopped_by_shutdown
        if stopping:
            # Not a user decision: leave the row ``running`` so that the next start
            # reports it as interrupted (or re-queues it, if configured).
            logger.warning("Job %s stopped by server shutdown", job_id)
        else:
            _fail(job_id, project_id, user_id, CANCELLED_MESSAGE)
    except BaseException as e:  # noqa: BLE001 - includes worker crashes and DB errors
        _fail(job_id, project_id, user_id, str(e) or e.__class__.__name__)
        if not isinstance(e, Exception):
            raise
    finally:
        with _lock:
            _active.discard(job_id)
            _procs.pop(job_id, None)
            _cancelled.discard(job_id)
            _timed_out.discard(job_id)
            _stopped_by_shutdown.discard(job_id)


def _run_local_job(job_id: str, project_id: str, param_path: str, user_id: str) -> None:
    job_dir = results_io.job_dir(project_id, job_id)
    log_path = job_dir / "console.log"
    results_path = job_dir / "results.json"

    # The job may have been cancelled or deleted while it waited in the queue.
    with sync_session_factory() as db:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None or job.status != "pending":
            return
        if is_cancelled(job_id):
            raise JobCancelled()
        algo = ((job.config or {}).get("general") or {}).get("algo", "ga")
        job.status = "running"
        job.started_at = _now()
        db.commit()

    job_dir.mkdir(parents=True, exist_ok=True)

    if not engine.HAS_ENGINE and not is_sklearn_algo(str(algo)):
        if not (settings.allow_mock_engine or settings.debug):
            raise RuntimeError(NO_ENGINE_MESSAGE)
        # Mock mode (tests / development only) — labelled as such in the results.
        mock_results = engine._mock_results()
        results_io.write_json_atomic(results_path, mock_results)
        results_io.write_summary(project_id, job_id, mock_results)
        with open(log_path, "w") as lf:
            lf.write("[mock] Engine not available — these are MOCK results, not a real analysis.\n")
        _complete(job_id, project_id, user_id)
        return

    cmd, cwd = _worker_command(param_path, results_path)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, env=env,
        start_new_session=True,  # own process group, so cancel kills the engine threads too
    )
    with _lock:
        _procs[job_id] = proc
    _update_job(job_id, pid=proc.pid)

    timer = None
    if settings.job_timeout_minutes and settings.job_timeout_minutes > 0:
        def _on_timeout():
            with _lock:
                _timed_out.add(job_id)
            _kill(proc)
        timer = threading.Timer(settings.job_timeout_minutes * 60, _on_timeout)
        timer.daemon = True
        timer.start()
    if is_cancelled(job_id):  # cancelled between the status check and the start
        _kill(proc)

    progress_path = job_dir / "progress.json"
    gen_re = re.compile(r"#(\d+)\s+\|\s+best:\s+(\S+)")
    k_re = re.compile(r"\[k=(\d+)")
    epoch_re = re.compile(r"max_epochs[:\s]+(\d+)", re.IGNORECASE)
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    progress_points = []
    # The engine prints its parameters only at the end, so the planned number
    # of generations comes from the job's own parameter file.
    max_gen = _planned_generations(param_path)
    t0 = time.monotonic()

    def _write_progress():
        try:
            results_io.write_json_atomic(progress_path, {"max_gen": max_gen, "points": progress_points})
        except OSError:
            pass

    try:
        with open(log_path, "w") as lf:
            for line in proc.stdout:
                text = line.decode("utf-8", errors="replace")
                lf.write(text)
                lf.flush()

                clean = ansi_re.sub("", text)
                if not max_gen:
                    em = epoch_re.search(clean)
                    if em:
                        max_gen = int(em.group(1))
                gm = gen_re.search(clean)
                if gm:
                    gen = int(gm.group(1))
                    km = k_re.search(clean)
                    progress_points.append({
                        "generation": gen,
                        "k": int(km.group(1)) if km else 0,
                        "language": gm.group(2),
                        "elapsed": round(time.monotonic() - t0, 1),
                    })
                    # Write progress every 5 generations to avoid excessive I/O
                    if gen % 5 == 0 or gen == max_gen:
                        _write_progress()
        if progress_points:
            _write_progress()
        proc.wait()
    finally:
        if timer is not None:
            timer.cancel()
        if proc.poll() is None:  # reader failed: do not leave the engine running
            _kill(proc, grace=2.0)
            proc.wait()

    if is_cancelled(job_id):
        raise JobCancelled()
    with _lock:
        timed_out = job_id in _timed_out
    if timed_out:
        raise RuntimeError(
            f"The job exceeded the time limit of {settings.job_timeout_minutes} minutes and was stopped."
        )
    if proc.returncode != 0:
        raise RuntimeError(f"Worker exited with code {proc.returncode}: {_tail(log_path)}")
    if not results_path.exists():
        raise RuntimeError("The worker finished without writing results.")

    _complete(job_id, project_id, user_id)


# ---------------------------------------------------------------------------
# Cancellation and recovery
# ---------------------------------------------------------------------------

def cancel(job_id: str) -> bool:
    """Request cancellation of a job handled by this process.

    A running worker is terminated (process group) and its thread records the
    final state. A job still waiting in the queue is removed from it, never
    starts, and is marked failed ("Cancelled by user."). Returns True if the job
    was tracked here (queued, running or polled).
    """
    with _lock:
        tracked = job_id in _active
        queued = next((q for q in _queue if q.job_id == job_id), None)
        if queued is not None:
            _queue.remove(queued)
            _active.discard(job_id)
        elif tracked:
            _cancelled.add(job_id)
        proc = _procs.get(job_id)
    if queued is not None:
        # Record the outcome off the caller's thread (it may be an event loop;
        # webhooks are network calls).
        threading.Thread(
            target=_fail, args=(queued.job_id, queued.project_id, queued.user_id, CANCELLED_MESSAGE),
            name=f"predomics-cancel-{job_id}", daemon=True,
        ).start()
    if proc is not None:
        _kill(proc)
    return tracked


def cancel_project_jobs(project_id: str) -> int:
    """Stop every active job of a project (call before deleting the project)."""
    with sync_session_factory() as db:
        ids = db.execute(
            select(Job.id).where(Job.project_id == project_id, Job.status.in_(("pending", "running")))
        ).scalars().all()
    for jid in ids:
        cancel(jid)
    return len(ids)


MISSING_PARAMS_MESSAGE = (
    "The server restarted while this job was queued and its parameter file could not be "
    "found, so it could not be resumed. Re-run the job."
)

# What the last startup recovery did (for the log line and for tests).
last_recovery: dict = {"failed": 0, "requeued": 0, "scitq": 0}


def reconcile_orphaned_jobs() -> int:
    """Recover the jobs a previous process left ``pending`` or ``running``.

    Call once at startup, before accepting requests.

    * ``pending`` local jobs are put back in the queue, oldest first (their
      ``param.yaml`` is on the data volume). If that file is gone the job fails.
    * ``running`` local jobs are marked failed with an explanation: their worker
      died with the old process. With ``PREDOMICS_REQUEUE_INTERRUPTED`` they are
      set back to ``pending`` and queued again instead.
    * jobs dispatched to scitq get their poller re-attached.

    Returns the number of jobs marked failed.
    """
    requeue_interrupted = _setting("requeue_interrupted", False, bool)
    failed = 0
    to_poll: list[tuple] = []
    to_queue: list[_Queued] = []

    def _close(job: Job, message: str) -> None:
        job.status = "failed"
        job.error_message = message
        job.completed_at = _now()
        job.pid = None
        _append_log(results_io.job_dir(job.project_id, job.id) / "console.log", f"\n[error] {message}\n")

    with sync_session_factory() as db:
        jobs = db.execute(
            select(Job).where(Job.status.in_(("pending", "running"))).order_by(Job.created_at, Job.id)
        ).scalars().all()
        for job in jobs:
            if is_tracked(job.id):
                continue
            if job.scitq_task_id is not None and scitq_client.is_enabled():
                to_poll.append((job.id, job.project_id, job.scitq_task_id, job.user_id or ""))
                continue
            if job.status == "running" and not requeue_interrupted:
                _close(job, INTERRUPTED_MESSAGE)
                failed += 1
                continue
            param_path = results_io.job_dir(job.project_id, job.id) / "param.yaml"
            if not param_path.is_file():
                _close(job, MISSING_PARAMS_MESSAGE if job.status == "pending" else INTERRUPTED_MESSAGE)
                failed += 1
                continue
            if job.status == "running":
                job.status = "pending"
                job.started_at = None
                job.pid = None
                _append_log(param_path.parent / "console.log",
                            "\n[info] Interrupted by a server restart; queued to run again.\n")
            to_queue.append(_Queued(job.id, job.project_id, str(param_path), job.user_id or ""))
        db.commit()

    with _lock:
        for item in to_queue:
            _active.add(item.job_id)
            _queue.append(item)
    for args in to_poll:
        submit_scitq_poller(*args)
    last_recovery.update(failed=failed, requeued=len(to_queue), scitq=len(to_poll))
    if failed or to_queue or to_poll:
        logger.warning(
            "Startup recovery: %d queued job(s) resumed, %d interrupted job(s) marked failed, "
            "%d scitq job(s) re-attached", len(to_queue), failed, len(to_poll),
        )
    _dispatch()
    return failed


def shutdown() -> None:
    """Stop running workers (call on application shutdown).

    Queued jobs stay ``pending`` and stopped ones stay ``running`` in the database,
    so the next start resumes the former and reports (or re-queues) the latter.
    """
    with _lock:
        _queue.clear()
        procs = list(_procs.items())
        for jid, _ in procs:
            _cancelled.add(jid)
            _stopped_by_shutdown.add(jid)
    for _, proc in procs:
        _kill(proc, grace=3.0)


# ---------------------------------------------------------------------------
# scitq (remote execution)
# ---------------------------------------------------------------------------

def poll_scitq_job(job_id: str, project_id: str, scitq_task_id: int, user_id: str = "") -> None:
    """Poll scitq for task status and stream output to console.log until terminal."""
    job_dir = results_io.job_dir(project_id, job_id)
    log_path = job_dir / "console.log"
    last_output_len = 0
    try:
        while True:
            if is_cancelled(job_id):
                raise JobCancelled()
            status = scitq_client.get_task_status(scitq_task_id)

            with sync_session_factory() as db:
                job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
                if job is None or job.status in ("completed", "failed"):
                    return  # deleted, cancelled or closed elsewhere
                if job.status != status and status == "running":
                    job.status = "running"
                    if job.started_at is None:
                        job.started_at = _now()
                    db.commit()

            output = scitq_client.get_task_output(scitq_task_id)
            if output and len(output) > last_output_len:
                job_dir.mkdir(parents=True, exist_ok=True)
                with open(log_path, "w") as lf:
                    lf.write(output)
                last_output_len = len(output)

            if status == "completed":
                if not results_io.results_path(project_id, job_id).exists():
                    raise RuntimeError(
                        f"scitq task {scitq_task_id} completed but no results file was found "
                        "(the data directory must be shared with the workers)."
                    )
                _complete(job_id, project_id, user_id)
                logger.info("Job %s completed via scitq (task %s)", job_id, scitq_task_id)
                return

            if status == "failed":
                msg = f"scitq task {scitq_task_id} failed"
                if output:
                    msg += f": {output[-500:]}"
                raise RuntimeError(msg)

            time.sleep(5)
    except JobCancelled:
        _fail(job_id, project_id, user_id, CANCELLED_MESSAGE)
    except Exception as e:  # noqa: BLE001
        _fail(job_id, project_id, user_id, f"scitq: {e}")
    finally:
        with _lock:
            _active.discard(job_id)
            _cancelled.discard(job_id)
