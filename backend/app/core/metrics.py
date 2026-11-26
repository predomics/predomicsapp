"""Prometheus metrics at ``GET /metrics``.

Disabled unless ``PREDOMICS_METRICS_TOKEN`` is set; scrapers authenticate with
``Authorization: Bearer <token>``. Needs the ``prometheus-client`` package; without
it the endpoint answers 503 and request observation is a no-op.

Exposed:

* ``predomics_http_requests_total{method,route,status}``
* ``predomics_http_request_duration_seconds{method,route}`` (histogram)
* ``predomics_jobs{status}`` — rows in the jobs table by status
* ``predomics_jobs_running`` / ``predomics_jobs_queued`` — this process's job runner
* ``predomics_data_disk_free_bytes`` / ``predomics_data_disk_total_bytes``
* ``predomics_app_info{version}``
"""

from __future__ import annotations

import hmac
import logging
import shutil

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select

from .config import settings

_log = logging.getLogger(__name__)

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

    HAS_PROMETHEUS = True
except ImportError:  # pragma: no cover - exercised only without the package
    HAS_PROMETHEUS = False

if HAS_PROMETHEUS:
    registry = CollectorRegistry()
    _requests = Counter(
        "predomics_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry,
    )
    _duration = Histogram(
        "predomics_http_request_duration_seconds", "HTTP request duration", ["method", "route"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120), registry=registry,
    )
    _jobs = Gauge("predomics_jobs", "Jobs in the database by status", ["status"], registry=registry)
    _jobs_running = Gauge("predomics_jobs_running", "Analysis workers running in this process", registry=registry)
    _jobs_queued = Gauge("predomics_jobs_queued", "Jobs waiting for a worker slot in this process", registry=registry)
    _disk_free = Gauge("predomics_data_disk_free_bytes", "Free bytes on the data volume", registry=registry)
    _disk_total = Gauge("predomics_data_disk_total_bytes", "Size of the data volume in bytes", registry=registry)
    _info = Gauge("predomics_app_info", "Application version", ["version"], registry=registry)

_JOB_STATUSES = ("pending", "running", "completed", "failed")


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    """Record one finished request (called by the access-log middleware)."""
    if not HAS_PROMETHEUS:
        return
    _requests.labels(method, route, str(status)).inc()
    _duration.labels(method, route).observe(seconds)


def runner_counts() -> tuple[int, int]:
    """(running, queued) for this process's job runner; (0, 0) if it cannot be read."""
    try:
        from ..services import jobs

        stats = jobs.stats()  # exact counts; excludes scitq pollers from "queued"
        return int(stats["running"]), int(stats["queued"])
    except Exception:
        return 0, 0


async def _refresh_gauges() -> None:
    from .database import async_session_factory
    from .version import __version__
    from ..models.db_models import Job

    _info.labels(__version__).set(1)
    counts = dict.fromkeys(_JOB_STATUSES, 0)
    try:
        async with async_session_factory() as db:
            rows = await db.execute(select(Job.status, func.count()).group_by(Job.status))
            for status, n in rows.all():
                counts[str(status)] = n
    except Exception as e:  # database down: still serve the process metrics
        _log.warning("metrics: could not count jobs: %s", e)
    for status, n in counts.items():
        _jobs.labels(status).set(n)
    running, queued = runner_counts()
    _jobs_running.set(running)
    _jobs_queued.set(queued)
    try:
        usage = shutil.disk_usage(settings.data_dir)
        _disk_free.set(usage.free)
        _disk_total.set(usage.total)
    except OSError:
        pass


def _authorized(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    supplied = auth[7:] if auth.startswith("Bearer ") else ""
    return bool(supplied) and hmac.compare_digest(supplied.encode(), settings.metrics_token.encode())


async def metrics_endpoint(request: Request) -> Response:
    if not settings.metrics_token:
        return PlainTextResponse("Not found", status_code=404)
    if not _authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"})
    if not HAS_PROMETHEUS:
        return PlainTextResponse("prometheus-client is not installed", status_code=503)
    await _refresh_gauges()
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


def install(app) -> None:
    """Register ``GET /metrics`` on ``app`` (hidden from the OpenAPI schema).

    Must be called before the SPA catch-all route is added, or that route wins.
    """
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    if settings.metrics_token and not HAS_PROMETHEUS:
        _log.warning("PREDOMICS_METRICS_TOKEN is set but prometheus-client is not installed; /metrics will answer 503")
