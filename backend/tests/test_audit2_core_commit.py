"""Work is committed before the response is sent, and insights accept stored configurations.

Both were found by driving the application from a real browser: a request sent
right after a successful one could not see what the first had created, and the
insights endpoint failed on any job launched from the interface.
"""

from __future__ import annotations

import json

import pytest
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text

from app.core.database import CommitBeforeResponseMiddleware, get_db, sync_engine
from app.main import app
from app.models.db_models import User
from app.models.schemas import RunConfig
from app.services import insights

from tests.test_api import (  # noqa: F401 - fixtures and helpers
    db_session, client, auth_client, clean_data, _create_project_with_datasets, _run_mock_analysis,
)


def _committed_users() -> int:
    """Rows visible to another connection, i.e. really committed."""
    with sync_engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM users")).scalar()


async def _asgi_call(asgi_app, method: str, path: str, body: dict | None = None):
    """Call an ASGI app directly; returns (status, visible user rows when the response started)."""
    payload = json.dumps(body).encode() if body is not None else b""
    path, _, query = path.partition("?")
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
        "headers": [(b"host", b"test"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode())],
        "client": ("127.0.0.1", 12345), "server": ("test", 80),
    }
    sent = False
    seen = {}

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
            seen["users_at_start"] = _committed_users()

    await asgi_app(scope, receive, send)
    return seen["status"], seen["users_at_start"]


def _mini_app(with_middleware: bool) -> FastAPI:
    mini = FastAPI()
    if with_middleware:
        mini.add_middleware(CommitBeforeResponseMiddleware)

    @mini.post("/users/{uid}")
    async def create(uid: str, fail: bool = False, db=Depends(get_db)):
        db.add(User(id=uid, email=f"{uid}@example.com", hashed_password="x"))
        await db.flush()
        if fail:
            raise HTTPException(status_code=409, detail="nope")
        return {"id": uid}

    return mini


class TestCommitBeforeResponse:
    @pytest.mark.asyncio
    async def test_without_the_middleware_the_row_is_not_committed_when_the_response_starts(self, db_session):
        """The behaviour being fixed (documents why the middleware exists)."""
        status, visible = await _asgi_call(_mini_app(False), "POST", "/users/u00000000001")
        assert status == 200 and visible == 0
        assert _committed_users() == 1            # committed only afterwards

    @pytest.mark.asyncio
    async def test_with_the_middleware_the_row_is_committed_before_the_response(self, db_session):
        status, visible = await _asgi_call(_mini_app(True), "POST", "/users/u00000000002")
        assert status == 200 and visible == 1

    @pytest.mark.asyncio
    async def test_failed_requests_are_still_rolled_back(self, db_session):
        status, visible = await _asgi_call(_mini_app(True), "POST", "/users/u00000000003?fail=true")
        assert status == 409 and visible == 0
        assert _committed_users() == 0

    @pytest.mark.asyncio
    async def test_real_application_registers_before_answering(self, db_session):
        """Register then log in immediately used to answer 401 now and then."""
        app.dependency_overrides.clear()          # the real get_db, not the test session
        status, visible = await _asgi_call(app, "POST", "/api/auth/register", {
            "email": "quick@example.com", "password": "a-long-password", "full_name": "Q",
        })
        assert status == 201 and visible == 1

    def test_middleware_is_the_innermost_one(self):
        """It must wrap the router directly: outer function middlewares run in another task."""
        assert app.user_middleware[-1].cls is CommitBeforeResponseMiddleware


# ---------------------------------------------------------------------------
# Insights on configurations as the API stores them (every unset parameter = None)
# ---------------------------------------------------------------------------

def _results():
    population = [
        {"rank": i, "features": {"0": 1, "1": -1}, "named_features": {"msp_0001": 1, "msp_0002": -1},
         "metrics": {"auc": 0.9 - i * 0.01, "fit": 0.9 - i * 0.01, "k": 2, "accuracy": 0.8, "sensitivity": 0.8,
                     "specificity": 0.8, "language": "Binary", "data_type": "Raw", "epoch": 3}}
        for i in range(5)
    ]
    return {
        "feature_names": ["msp_0001", "msp_0002", "msp_0003"], "sample_names": ["s1", "s2"],
        "best_individual": {"auc": 0.9, "fit": 0.9, "k": 2, "accuracy": 0.8, "sensitivity": 0.8,
                            "specificity": 0.8, "threshold": 0.5, "language": "Binary", "data_type": "Raw",
                            "epoch": 3, "features": {"0": 1, "1": -1}},
        "population": population, "population_size": 5, "generation_count": 3, "fold_count": 0,
        "generation_tracking": [{"generation": g, "best_auc": 0.8 + g * 0.03, "best_auc_test": 0.6,
                                 "best_fit": 0.8, "best_k": 2, "population_size": 5} for g in range(3)],
    }


class TestInsightsWithStoredConfig:
    def test_config_with_unset_parameters_as_none(self):
        stored = RunConfig().model_dump(mode="json")          # what POST /run saves on the job
        assert any(v is None for section in stored.values() if isinstance(section, dict)
                   for v in section.values()), "the stored configuration is expected to contain None values"
        out = insights.compute_insights(results=_results(), annotations={}, enrichment_results=None,
                                        job_config=stored)
        assert set(out) == {"insights", "scores", "summary"}
        json.dumps(out, allow_nan=False)

    @pytest.mark.parametrize("config", [
        None, {}, {"general": None, "cv": None, "ga": None, "data": None},
        {"general": {"cv": None, "threshold_ci_n_bootstrap": None, "threshold_ci_penalty": None},
         "cv": {"overfit_penalty": None, "inner_folds": None, "outer_folds": None, "fit_on_valid": None},
         "ga": {"random_sampling_pct": None, "random_sampling_epochs": None},
         "data": {"holdout_ratio": None}},
    ])
    def test_degenerate_configs(self, config):
        out = insights.compute_insights(results=_results(), annotations={}, enrichment_results=None,
                                        job_config=config)
        assert "insights" in out

    @pytest.mark.asyncio
    async def test_endpoint_on_a_job_launched_through_the_api(self, auth_client, monkeypatch):
        from app.services import msp_annotations
        def must_not_block(names):
            raise AssertionError("insights must not wait for the annotation service")

        monkeypatch.setattr(msp_annotations, "get_annotations", must_not_block)
        monkeypatch.setattr(msp_annotations, "cached_annotations", lambda names: ({}, True))  # no network in tests
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        resp = await auth_client.get(f"/api/data-explore/{pid}/insights/{job_id}")
        assert resp.status_code == 200, resp.text
        assert set(resp.json()) >= {"insights", "scores", "summary"}
        assert resp.json()["annotations_pending"] is True
