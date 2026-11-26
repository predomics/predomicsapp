"""Logging setup: text or JSON lines, a request id on every record, an access log.

Call :func:`install` once on the FastAPI app (after the other middleware is
added). It configures the root logger from ``PREDOMICS_LOG_FORMAT`` /
``PREDOMICS_LOG_LEVEL``, tags each request with an id (taken from an incoming
``X-Request-ID`` header when it looks sane, otherwise generated, and echoed in
the response), writes one access line per request, and starts Sentry when
``PREDOMICS_SENTRY_DSN`` is set and ``sentry-sdk`` is installed.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from .config import settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_access_log = logging.getLogger("predomics.access")
_log = logging.getLogger(__name__)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS = {"/health", "/health/ready", "/metrics"}

# Attributes every LogRecord has; anything else was passed via ``extra=``.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "request_id"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, request_id, extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging() -> None:
    """(Re)configure the root logger according to the settings. Idempotent."""
    level = getattr(logging, str(settings.log_level).upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"
        ))
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)
    # Our middleware writes the access line (with user and route template);
    # uvicorn's own would duplicate it.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def _user_id_from(request) -> str | None:
    """Best-effort user id for the access log, from a valid bearer token (no DB access)."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        from .security import decode_access_token

        return decode_access_token(auth[7:])
    if request.headers.get("x-api-key"):
        return "api-key"
    return None


def route_template(request) -> str:
    """The matched route's path template ("/api/projects/{project_id}"), or a fixed label.

    Templates keep log and metric cardinality bounded; unmatched paths (404s,
    SPA assets, scanners) collapse into one label.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path and path != "/{full_path:path}":
        return path
    return "(unmatched)" if path is None else "(spa)"


def _init_sentry() -> bool:
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        _log.warning("PREDOMICS_SENTRY_DSN is set but the sentry-sdk package is not installed; error tracking is off")
        return False
    from .version import __version__

    sentry_sdk.init(dsn=settings.sentry_dsn, release=f"predomicsapp@{__version__}",
                    send_default_pii=False, traces_sample_rate=0.0)
    _log.info("Sentry error tracking enabled")
    return True


def install(app) -> None:
    """Configure logging and add the request-id / access-log middleware to ``app``."""
    configure_logging()
    _init_sentry()

    @app.middleware("http")
    async def _request_context(request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            template = route_template(request)
            from . import metrics

            metrics.observe_request(request.method, template, status, duration_ms / 1000)
            if request.url.path not in _QUIET_PATHS:
                _access_log.info(
                    "%s %s %s %.1fms", request.method, request.url.path, status, duration_ms,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "route": template,
                        "status": status,
                        "duration_ms": duration_ms,
                        "user_id": _user_id_from(request),
                        "client_ip": request.client.host if request.client else None,
                    },
                )
            request_id_var.reset(token)
