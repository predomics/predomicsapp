"""The OpenAPI document describes what every endpoint returns (audit DOC-18)."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.models import schemas

from tests.test_api import (  # noqa: F401 - fixtures and helpers
    db_session, client, auth_client, clean_data, _create_project_with_datasets, _run_mock_analysis,
)

# Endpoints that send a file, not JSON: their 200 response declares a media type instead.
FILE_DOWNLOADS = {
    "export_csv", "export_report", "export_json", "export_pdf", "export_notebook", "download_backup",
}


def _operations():
    spec = app.openapi()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        for method in route.methods:
            op = spec["paths"].get(route.path, {}).get(method.lower())
            if op is not None:
                yield route, method, op


def test_every_json_operation_documents_its_response():
    untyped = []
    for route, method, op in _operations():
        if route.endpoint.__name__ in FILE_DOWNLOADS:
            continue
        success = next((op["responses"][c] for c in ("200", "201") if c in op["responses"]), None)
        if success is None:        # 204 and the like
            continue
        schema = success.get("content", {}).get("application/json", {}).get("schema")
        if not schema:
            untyped.append(f"{method} {route.path} ({route.endpoint.__module__}.{route.endpoint.__name__})")
    assert not untyped, "Endpoints without a response model:\n  " + "\n  ".join(sorted(untyped))


def test_file_downloads_declare_a_media_type():
    seen = set()
    for route, _, op in _operations():
        name = route.endpoint.__name__
        if name in FILE_DOWNLOADS and name.startswith("export_"):
            seen.add(name)
            content = op["responses"]["200"].get("content", {})
            assert content and "application/json" not in content or name == "export_json", name
    assert seen == {n for n in FILE_DOWNLOADS if n.startswith("export_")}


def test_response_models_never_reject_or_rename_extra_keys():
    """New models are descriptive: unknown keys pass through untouched."""
    for name in ("JobResults", "NetworkResponse", "OrdinationResponse", "DashboardResponse", "BatchSummary"):
        model = getattr(schemas, name)
        assert model.model_config.get("extra") == "allow", name
    payload = {"best_individual": {"auc": 0.9, "anything": [1, {"x": None}]}, "future_field": {"a": 1}}
    dumped = schemas.JobResults.model_validate(payload).model_dump(exclude_unset=True)
    assert dumped == payload


class TestShapesUnchanged:
    """Typed endpoints return exactly what the handler built (no added nulls, no lost keys)."""

    @pytest.mark.asyncio
    async def test_results_and_progress_and_logs(self, auth_client):
        from app.services import results_io

        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)

        raw = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/results")).json()
        on_disk = results_io.load_results(pid, job_id)
        assert raw == on_disk                       # byte-for-byte the same structure

        logs = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/logs")).json()
        assert set(logs) == {"job_id", "status", "log", "size", "offset", "next_offset", "truncated"}

        progress = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/progress")).json()
        assert set(progress) == {"max_gen", "points"}

        config = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/config")).json()
        assert set(config) == {"job_id", "name", "config"} and config["config"]["general"]["algo"] == "ga"

        jobs = (await auth_client.get(f"/api/analysis/{pid}/jobs")).json()
        assert jobs[0]["job_id"] == job_id and "error_message" in jobs[0]   # nulls still listed here

        deleted = await auth_client.delete(f"/api/analysis/{pid}/jobs/{job_id}")
        assert deleted.json() == {"detail": "Job deleted"}

    @pytest.mark.asyncio
    async def test_dashboard_and_webhooks(self, auth_client, monkeypatch):
        from app.core.config import settings
        if hasattr(settings, "webhook_allow_private"):
            monkeypatch.setattr(settings, "webhook_allow_private", True)

        dash = (await auth_client.get("/api/dashboard/")).json()
        assert set(dash) == {"projects", "shared_with_me", "datasets", "running_jobs", "pending_jobs",
                             "completed_jobs", "failed_jobs", "active_jobs", "recent_completions", "activity"}

        created = (await auth_client.post("/api/webhooks/", json={"name": "w", "url": "https://8.8.8.8/hook"})).json()
        assert set(created) == {"id", "name", "url", "events", "secret", "created_at"}
        listed = (await auth_client.get("/api/webhooks/")).json()
        assert set(listed[0]) == {"id", "name", "url", "events", "is_active", "created_at"}   # no secret key at all
        assert (await auth_client.delete(f"/api/webhooks/{created['id']}")).json() == {"status": "deleted"}

    @pytest.mark.asyncio
    async def test_public_links(self, auth_client):
        pid, _, _ = await _create_project_with_datasets(auth_client)
        link = (await auth_client.post(f"/api/projects/{pid}/public", json={})).json()
        assert set(link) == {"id", "token", "expires_at", "created_at", "is_active"}
        public = (await auth_client.get(f"/api/public/{link['token']}")).json()
        assert set(public) == {"project", "jobs"} and set(public["project"]) == {"name", "description"}
        assert (await auth_client.delete(f"/api/projects/{pid}/public/{link['id']}")).json() == {"detail": "Link revoked"}
