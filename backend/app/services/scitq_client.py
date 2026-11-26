"""Optional scitq integration for distributed job execution.

When PREDOMICS_SCITQ_SERVER is set (or configured via the admin panel),
jobs are dispatched to a scitq server instead of running locally via
BackgroundTasks. If scitq is not installed or not configured, all functions
gracefully degrade (is_enabled() returns False).
"""

import json
import logging
import sys
from pathlib import Path

from ..core.config import settings

_log = logging.getLogger(__name__)

# Try importing scitq — optional dependency
try:
    from scitq.lib import Server as ScitqServer
    _HAS_SCITQ = True
except ImportError:
    _HAS_SCITQ = False
    ScitqServer = None

# scitq status → PredomicsApp status mapping
_STATUS_MAP = {
    "pending": "pending",
    "waiting": "pending",
    "assigned": "pending",
    "accepted": "running",
    "running": "running",
    "succeeded": "completed",
    "failed": "failed",
}

# Runtime config file (admin-managed overrides)
_CONFIG_PATH = Path(settings.data_dir) / "scitq_config.json"


def _load_runtime_config() -> dict:
    """Load admin-managed scitq config from disk.

    Returns a dict with optional keys: server, token, container.
    Falls back to env-var-based settings for missing keys.
    """
    runtime = {}
    if _CONFIG_PATH.exists():
        try:
            runtime = json.loads(_CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            _log.warning("Could not read scitq config from %s", _CONFIG_PATH)
    return runtime


def save_runtime_config(config: dict) -> None:
    """Persist scitq config to disk (called by admin endpoint)."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_config() -> dict:
    """Get effective scitq configuration (runtime overrides > env vars)."""
    runtime = _load_runtime_config()
    return {
        "server": runtime.get("server") or settings.scitq_server,
        "token": runtime.get("token") or settings.scitq_token,
        "container": runtime.get("container") or settings.scitq_container,
    }


def is_enabled() -> bool:
    """Check if scitq integration is configured and available."""
    cfg = get_config()
    return _HAS_SCITQ and bool(cfg["server"])


def _get_server() -> "ScitqServer":
    """Get a scitq Server client instance."""
    cfg = get_config()
    return ScitqServer(cfg["server"], style="object")


def test_connection() -> dict:
    """Test connectivity to the scitq server.

    Returns {"ok": True, "version": ...} or {"ok": False, "error": ...}.
    """
    if not _HAS_SCITQ:
        return {"ok": False, "error": "scitq package not installed"}

    cfg = get_config()
    if not cfg["server"]:
        return {"ok": False, "error": "No server configured"}

    try:
        import httpx
        url = cfg["server"]
        if not url.startswith("http"):
            url = f"http://{url}"
        headers = {}
        if cfg["token"]:
            headers["Authorization"] = f"Bearer {cfg['token']}"
        resp = httpx.get(f"{url}/workers/", headers=headers, timeout=5.0)
        if resp.status_code < 400:
            return {"ok": True, "workers": len(resp.json()) if resp.headers.get("content-type", "").startswith("application/json") else 0}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def dispatch_job(
    job_id: str,
    project_id: str,
    param_path: str,
    job_dir: str,
) -> int:
    """Submit a gpredomics job to scitq.

    Returns the scitq task_id (integer).
    """
    cfg = get_config()
    results_path = str(Path(job_dir) / "results.json")

    # Build the same command that _run_job() uses via subprocess
    # Same module path as the local runner (the image's working directory is the
    # parent of `backend/`); paths are quoted because the command runs in a shell.
    import shlex
    command = (
        f"{shlex.quote(sys.executable)} -u -m backend.app.services.worker "
        f"{shlex.quote(str(param_path))} {shlex.quote(results_path)}"
    )

    server = _get_server()
    kwargs = dict(
        command=command,
        name=f"predomics-{job_id}",
        batch=f"predomics-{project_id}",
        shell=True,
    )
    if cfg["container"]:
        kwargs["container"] = cfg["container"]

    task = server.task_create(**kwargs)
    task_id = task.task_id if hasattr(task, "task_id") else task.get("task_id", task.get("id"))

    _log.info("Dispatched job %s to scitq as task %s", job_id, task_id)
    return int(task_id)


def get_task_status(scitq_task_id: int) -> str:
    """Query scitq for task status, mapped to PredomicsApp status values.

    Returns one of: 'pending', 'running', 'completed', 'failed'.
    """
    server = _get_server()
    task = server.task_get(scitq_task_id)
    raw_status = task.status if hasattr(task, "status") else task.get("status", "pending")
    return _STATUS_MAP.get(raw_status, "pending")


def get_task_output(scitq_task_id: int) -> str:
    """Get stdout/stderr output from a scitq task execution.

    Returns the output text, or empty string if not available.
    """
    try:
        server = _get_server()
        execs = server.executions(task_id=scitq_task_id)
        if not execs:
            return ""
        # Get the latest execution
        latest = execs[-1] if isinstance(execs, list) else execs
        exec_id = latest.execution_id if hasattr(latest, "execution_id") else latest.get("execution_id", latest.get("id"))
        if exec_id is None:
            return ""
        output = server.execution_output(exec_id)
        if hasattr(output, "output"):
            return output.output or ""
        if isinstance(output, dict):
            return output.get("output", "")
        return str(output) if output else ""
    except Exception as e:
        _log.debug("Could not fetch scitq task output: %s", e)
        return ""
