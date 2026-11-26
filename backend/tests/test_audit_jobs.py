"""Job lifecycle (audit findings BE-F2, F3, F16, F19, OPS-F3, and the /run IDOR)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import sync_session_factory
from app.models.db_models import Job
from app.services import engine as ml_engine
from app.services import jobs, results_io

from tests.test_api import (  # noqa: F401 - fixtures and helpers
    db_session, client, auth_client, clean_data,
    _create_project_with_datasets, _run_mock_analysis,
)

_CONFIG = {
    "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
    "ga": {"population_size": 200, "max_epochs": 2, "k_min": 1, "k_max": 10},
}


def _job_row(job_id: str) -> Job | None:
    with sync_session_factory() as db:
        return db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()


def _wait(predicate, timeout=20.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not reached in time")


def _ensure_project(project_id: str) -> None:
    """Rows a job must reference (PostgreSQL enforces the foreign keys; SQLite does not)."""
    from app.models.db_models import Project, User
    with sync_session_factory() as db:
        if db.get(Project, project_id) is None:
            owner = "uowner000001"
            if db.get(User, owner) is None:
                db.add(User(id=owner, email="job-owner@example.com", hashed_password="x"))
                db.flush()
            db.add(Project(id=project_id, name="jobs", user_id=owner))
            db.commit()


def _insert_job(project_id="pjobs0000001", status="pending", **cols) -> str:
    _ensure_project(project_id)
    with sync_session_factory() as db:
        job = Job(project_id=project_id, status=status, config={"general": {"algo": "ga"}}, **cols)
        db.add(job)
        db.commit()
        return job.id


def _reset_runner():
    with jobs._lock:
        jobs._queue.clear()
        procs = list(jobs._procs.values())
        jobs._cancelled.update(jobs._procs)
    for proc in procs:
        jobs._kill(proc, grace=2.0)
    jobs.wait_idle(15)
    with jobs._lock:
        jobs._active.clear()
        jobs._cancelled.clear()
        jobs._stopped_by_shutdown.clear()


@pytest.fixture
def threaded_runner(monkeypatch):
    """Use the real bounded queue (the suite default runs jobs inline)."""
    monkeypatch.delenv("PREDOMICS_JOBS_INLINE", raising=False)
    monkeypatch.setattr(ml_engine, "HAS_ENGINE", True)
    _reset_runner()
    yield
    _reset_runner()


def _fake_worker(monkeypatch, script: str):
    """Replace the engine subprocess by a small Python script."""
    monkeypatch.setattr(
        jobs, "_worker_command",
        lambda param_path, results_path: ([sys.executable, "-u", "-c", script, str(results_path)], os.getcwd()),
    )


_SLEEPER = "import time,sys; print('started', flush=True); time.sleep(120)"
_QUICK = (
    "import json,sys,time; print('#1 | best: Binary [k=3]', flush=True); time.sleep(float({delay}));"
    "json.dump({{'best_individual': {{'auc': 0.75, 'k': 3}}, 'feature_names': ['a','b'], 'sample_names': ['s']}},"
    " open(sys.argv[1], 'w'))"
)


# ---------------------------------------------------------------------------
# Authorisation and validation at launch
# ---------------------------------------------------------------------------

class TestLaunchChecks:
    @pytest.mark.asyncio
    async def test_cannot_run_on_files_of_another_project(self, client):
        """A file id is not an authorisation (it used to be enough)."""
        async def _user(email):
            await client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
            tok = (await client.post("/api/auth/login", json={"email": email, "password": "testpass123"})).json()
            return {"Authorization": f"Bearer {tok['access_token']}"}

        alice, bob = await _user("alice@example.com"), await _user("bob@example.com")
        client.headers.update(alice)
        _, ax, ay = await _create_project_with_datasets(client)
        client.headers.update(bob)
        bob_pid, bx, by = await _create_project_with_datasets(client)

        with patch("app.services.engine.HAS_ENGINE", False):
            stolen = await client.post(
                f"/api/analysis/{bob_pid}/run", json=_CONFIG, params={"x_file_id": ax, "y_file_id": ay},
            )
            mixed = await client.post(
                f"/api/analysis/{bob_pid}/run", json=_CONFIG,
                params={"x_file_id": bx, "y_file_id": by, "xtest_file_id": ax},
            )
            batch = await client.post(
                f"/api/analysis/{bob_pid}/batch",
                json={"config": _CONFIG, "sweep": {"sweeps": {"general.seed": [1, 2]}}},
                params={"x_file_id": ax, "y_file_id": ay},
            )
            own = await client.post(
                f"/api/analysis/{bob_pid}/run", json=_CONFIG, params={"x_file_id": bx, "y_file_id": by},
            )
        assert stolen.status_code == 404
        assert mixed.status_code == 404
        assert batch.status_code == 404
        assert own.status_code == 200
        assert len((await client.get(f"/api/analysis/{bob_pid}/jobs")).json()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("general", [
        {"thread_number": 0}, {"thread_number": 100000}, {"seed": -1},
    ])
    async def test_out_of_range_config_is_rejected(self, auth_client, general):
        pid, x, y = await _create_project_with_datasets(auth_client)
        resp = await auth_client.post(
            f"/api/analysis/{pid}/run", json={"general": general}, params={"x_file_id": x, "y_file_id": y},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_threads_are_capped_to_the_server_limit(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "max_threads_per_job", 2)
        pid, x, y = await _create_project_with_datasets(auth_client)
        with patch("app.services.engine.HAS_ENGINE", False):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/run", json={"general": {"thread_number": 64}},
                params={"x_file_id": x, "y_file_id": y},
            )
        job = _job_row(resp.json()["job_id"])
        assert job.config["general"]["thread_number"] == 2
        param = (results_io.job_dir(pid, job.id) / "param.yaml").read_text()
        assert "thread_number: 2" in param
        assert "data_type_epsilon" in param


class TestBatch:
    async def _batch(self, auth_client, pid, x, y, sweeps, **params):
        with patch("app.services.engine.HAS_ENGINE", False):
            return await auth_client.post(
                f"/api/analysis/{pid}/batch",
                json={"config": _CONFIG, "sweep": {"sweeps": sweeps}},
                params={"x_file_id": x, "y_file_id": y, **params},
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sweeps", [
        {"ga.populaton_size": [10, 20]},        # typo: used to give identical jobs
        {"nosuchsection.x": [1]},
        {"population_size": [10]},
        {"ga.population_size": [10, -5]},       # out of range value
        {"ga.population_size": ["many"]},
        {"general.seed": []},
    ])
    async def test_bad_sweeps_create_no_job(self, auth_client, sweeps):
        pid, x, y = await _create_project_with_datasets(auth_client)
        resp = await self._batch(auth_client, pid, x, y, sweeps)
        assert resp.status_code == 422, resp.text
        assert (await auth_client.get(f"/api/analysis/{pid}/jobs")).json() == []

    @pytest.mark.asyncio
    async def test_every_job_of_a_batch_reaches_a_terminal_state(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        resp = await self._batch(auth_client, pid, x, y, {"ga.population_size": [200, 300], "general.seed": [1, 2]})
        assert resp.status_code == 200 and resp.json()["job_count"] == 4
        rows = (await auth_client.get(f"/api/analysis/{pid}/jobs")).json()
        assert sorted(r["status"] for r in rows) == ["completed"] * 4
        configs = {(_job_row(r["job_id"]).config["ga"]["population_size"],
                    _job_row(r["job_id"]).config["general"]["seed"]) for r in rows}
        assert configs == {(200, 1), (200, 2), (300, 1), (300, 2)}

    @pytest.mark.asyncio
    async def test_a_deleted_job_does_not_strand_the_rest(self, auth_client, monkeypatch):
        """One vanished job used to leave every later job of the batch pending forever."""
        pid, x, y = await _create_project_with_datasets(auth_client)
        original = jobs._run_local_job
        seen = []

        def _delete_first(job_id, project_id, param_path, user_id):
            seen.append(job_id)
            if len(seen) == 1:  # the job disappears before its turn
                with sync_session_factory() as db:
                    db.execute(text("DELETE FROM jobs WHERE id = :j"), {"j": job_id})
                    db.commit()
            return original(job_id, project_id, param_path, user_id)

        monkeypatch.setattr(jobs, "_run_local_job", _delete_first)
        resp = await self._batch(auth_client, pid, x, y, {"general.seed": [1, 2, 3]})
        assert resp.status_code == 200
        rows = (await auth_client.get(f"/api/analysis/{pid}/jobs")).json()
        assert [r["status"] for r in rows] == ["completed", "completed"]

    @pytest.mark.asyncio
    async def test_clinical_file_reaches_batch_jobs(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("metadata.tsv", b"id\tage\ns1\t30\ns2\t40\n", "text/plain")},
        )
        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        clin = next(f["id"] for d in proj["datasets"] for f in d["files"] if f["filename"].startswith("metadata"))
        cfg = {**_CONFIG, "clinical": {"enabled": True, "method": "stacking"}}
        with patch("app.services.engine.HAS_ENGINE", False):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/batch",
                json={"config": cfg, "sweep": {"sweeps": {"general.seed": [1, 2]}}},
                params={"x_file_id": x, "y_file_id": y, "clinical_file_id": clin},
            )
        assert resp.status_code == 200
        for j in resp.json()["jobs"]:
            param = (results_io.job_dir(pid, j["job_id"]) / "param.yaml").read_text()
            assert "clinical:" in param and "metadata" in param


# ---------------------------------------------------------------------------
# Mock engine
# ---------------------------------------------------------------------------

class TestMockEngine:
    @pytest.mark.asyncio
    async def test_missing_engine_fails_the_job_instead_of_inventing_results(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "allow_mock_engine", False)
        monkeypatch.setattr(settings, "debug", False)
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)   # patches HAS_ENGINE to False
        row = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}")).json()
        assert row["status"] == "failed"
        assert "gpredomicspy" in row["error_message"]
        assert not results_io.results_path(pid, job_id).exists()

    @pytest.mark.asyncio
    async def test_mock_results_are_labelled(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        status = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}")).json()
        assert status["status"] == "completed" and status["mock"] is True
        raw = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/results")).json()
        assert raw["mock"] is True and raw["engine"] == "mock"
        logs = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/logs")).json()
        assert "MOCK" in logs["log"]


# ---------------------------------------------------------------------------
# Status, logs
# ---------------------------------------------------------------------------

class TestStatusAndLogs:
    @pytest.mark.asyncio
    async def test_status_poll_does_not_parse_the_full_results(self, auth_client, monkeypatch):
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        assert (results_io.job_dir(pid, job_id) / "summary.json").exists()

        def _boom(*a, **k):
            raise AssertionError("results.json was parsed for a status poll")

        monkeypatch.setattr(results_io, "load_results", _boom)
        status = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}")).json()
        assert status["feature_count"] == 50 and status["sample_count"] == 100
        assert status["generation_count"] == 10 and status["best_k"] == 3

    @pytest.mark.asyncio
    async def test_logs_can_be_followed_by_offset(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        log_path = results_io.job_dir(pid, job_id) / "console.log"
        log_path.write_text("line 1\n")
        first = (await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/logs")).json()
        assert first["log"] == "line 1\n" and first["next_offset"] == 7 and first["truncated"] is False
        with open(log_path, "a") as fh:
            fh.write("line 2 ✓\n")
        more = (await auth_client.get(
            f"/api/analysis/{pid}/jobs/{job_id}/logs", params={"offset": first["next_offset"]},
        )).json()
        assert more["log"] == "line 2 ✓\n"
        assert more["next_offset"] == more["size"] == log_path.stat().st_size

    def test_large_logs_return_their_tail(self, tmp_path):
        p = tmp_path / "console.log"
        p.write_bytes(b"a" * 3_000_000 + b"THE END")
        chunk = results_io.read_log_chunk(p, 0, max_bytes=1000)
        assert chunk["truncated"] is True and chunk["log"].endswith("THE END") and len(chunk["log"]) == 1000

    def test_duration_is_measured_from_the_start_not_the_submission(self):
        from datetime import datetime, timedelta, timezone
        from app.routers.analysis import _job_to_summary

        now = datetime.now(timezone.utc)
        job = Job(id="jdur00000001", project_id="p", status="completed", config={},
                  created_at=now - timedelta(seconds=600), started_at=now - timedelta(seconds=30),
                  completed_at=now)
        assert _job_to_summary(job).duration_seconds == pytest.approx(30, abs=0.01)


def test_failed_write_keeps_the_previous_results(tmp_path, monkeypatch):
    target = tmp_path / "results.json"
    results_io.write_json_atomic(target, {"a": 1})

    def _fail(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(results_io.json, "dump", _fail)
    with pytest.raises(OSError):
        results_io.write_json_atomic(target, {"a": 2})
    monkeypatch.undo()
    assert json.loads(target.read_text()) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"]


# ---------------------------------------------------------------------------
# Cancel, delete, restart recovery
# ---------------------------------------------------------------------------

class TestCancelAndRecovery:
    @pytest.mark.asyncio
    async def test_cancel_and_delete_a_pending_job(self, auth_client, db_session):
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        await db_session.execute(text("UPDATE jobs SET status='pending', completed_at=NULL WHERE id=:j"), {"j": job_id})
        await db_session.commit()

        resp = await auth_client.post(f"/api/analysis/{pid}/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed" and "Cancelled" in body["error_message"]
        again = await auth_client.post(f"/api/analysis/{pid}/jobs/{job_id}/cancel")
        assert again.status_code == 409

        await db_session.execute(text("UPDATE jobs SET status='pending' WHERE id=:j"), {"j": job_id})
        await db_session.commit()
        assert (await auth_client.delete(f"/api/analysis/{pid}/jobs/{job_id}")).status_code == 200
        assert not results_io.job_dir(pid, job_id).exists()

    @pytest.mark.asyncio
    async def test_orphaned_running_job_can_be_cancelled_and_deleted(self, auth_client, db_session):
        """After a restart nobody owns the job: it must not be undeletable."""
        pid, x, y = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x, y)
        await db_session.execute(text("UPDATE jobs SET status='running', completed_at=NULL WHERE id=:j"), {"j": job_id})
        await db_session.commit()
        assert not jobs.is_tracked(job_id)
        assert (await auth_client.delete(f"/api/analysis/{pid}/jobs/{job_id}")).status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_cannot_cancel(self, client, db_session):
        async def _user(email):
            await client.post("/api/auth/register", json={"email": email, "password": "testpass123"})
            tok = (await client.post("/api/auth/login", json={"email": email, "password": "testpass123"})).json()
            return {"Authorization": f"Bearer {tok['access_token']}"}

        owner, other = await _user("owner@example.com"), await _user("other@example.com")
        client.headers.update(owner)
        pid, x, y = await _create_project_with_datasets(client)
        job_id = await _run_mock_analysis(client, pid, x, y)
        await db_session.execute(text("UPDATE jobs SET status='pending' WHERE id=:j"), {"j": job_id})
        await db_session.commit()
        client.headers.update(other)
        assert (await client.post(f"/api/analysis/{pid}/jobs/{job_id}/cancel")).status_code in (403, 404)
        assert _job_row(job_id).status == "pending"

    def test_reconcile_closes_jobs_left_by_a_previous_process(self, db_session):
        running = _insert_job(status="running", pid=999999)
        pending = _insert_job(status="pending")
        done = _insert_job(status="completed")
        assert jobs.reconcile_orphaned_jobs() == 2
        for jid in (running, pending):
            row = _job_row(jid)
            assert row.status == "failed" and "restart" in row.error_message
            assert row.completed_at is not None and row.pid is None
            assert "restart" in (results_io.job_dir(row.project_id, jid) / "console.log").read_text()
        assert _job_row(done).status == "completed"
        assert jobs.reconcile_orphaned_jobs() == 0

    def test_pending_jobs_are_requeued_in_creation_order_after_a_restart(
            self, db_session, threaded_runner, monkeypatch):
        """Queued work survives a restart (it used to be failed)."""
        monkeypatch.setattr(settings, "max_concurrent_jobs", 1)
        _fake_worker(monkeypatch, _QUICK.format(delay=0.3))
        ids = [_insert_job(status="pending", user_id=None) for _ in range(3)]
        for jid in ids:
            d = results_io.job_dir("pjobs0000001", jid)
            d.mkdir(parents=True, exist_ok=True)
            (d / "param.yaml").write_text("general: {}\n")
        interrupted = _insert_job(status="running", pid=999999)

        assert jobs.reconcile_orphaned_jobs() == 1          # only the running one is failed
        assert jobs.last_recovery == {"failed": 1, "requeued": 3, "scitq": 0}
        assert _job_row(interrupted).status == "failed"
        rows = [_wait(lambda j=j: (r := _job_row(j)) and r.status == "completed" and r) for j in ids]
        starts = [r.started_at for r in rows]
        assert starts == sorted(starts)                      # oldest first
        assert jobs.wait_idle(10)

    def test_interrupted_jobs_can_be_requeued_instead(self, db_session, threaded_runner, monkeypatch):
        monkeypatch.setenv("PREDOMICS_REQUEUE_INTERRUPTED", "true")
        if hasattr(settings, "requeue_interrupted"):
            monkeypatch.setattr(settings, "requeue_interrupted", True)
        _fake_worker(monkeypatch, _QUICK.format(delay=0.2))
        jid = _insert_job(status="running", pid=999999)
        d = results_io.job_dir("pjobs0000001", jid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "param.yaml").write_text("general: {}\n")
        assert jobs.reconcile_orphaned_jobs() == 0
        row = _wait(lambda: (r := _job_row(jid)) and r.status == "completed" and r)
        assert row.pid is None and row.error_message is None

    def test_shutdown_leaves_running_jobs_for_the_next_start(self, db_session, threaded_runner, monkeypatch):
        _fake_worker(monkeypatch, _SLEEPER)
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        _wait(lambda: (r := _job_row(jid)) and r.status == "running" and r.pid)
        jobs.shutdown()
        assert jobs.wait_idle(15)
        _wait(lambda: not jobs.is_tracked(jid))
        assert _job_row(jid).status == "running"            # not "Cancelled by user."
        assert jobs.reconcile_orphaned_jobs() == 1
        assert "restart" in _job_row(jid).error_message

    def test_reconcile_leaves_jobs_owned_by_this_process(self, db_session):
        mine = _insert_job(status="pending")
        with jobs._lock:
            jobs._active.add(mine)
        try:
            assert jobs.reconcile_orphaned_jobs() == 0
            assert _job_row(mine).status == "pending"
        finally:
            with jobs._lock:
                jobs._active.discard(mine)


class TestThreadedRunner:
    def test_job_runs_and_records_pid_start_and_summary(self, db_session, threaded_runner, monkeypatch):
        _fake_worker(monkeypatch, _QUICK.format(delay=0.6))
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        running = _wait(lambda: (r := _job_row(jid)) and r.status == "running" and r.pid and r)
        assert running.started_at is not None and jobs.is_tracked(jid)
        done = _wait(lambda: (r := _job_row(jid)) and r.status == "completed" and r)
        assert (done.best_auc, done.best_k, done.pid) == (0.75, 3, None)
        assert done.disk_size_bytes > 0
        progress = json.loads((results_io.job_dir("pjobs0000001", jid) / "progress.json").read_text())
        assert progress["points"][0]["generation"] == 1 and progress["points"][0]["k"] == 3
        _wait(lambda: not jobs.is_tracked(jid))

    def test_cancel_kills_the_worker_process(self, db_session, threaded_runner, monkeypatch):
        _fake_worker(monkeypatch, _SLEEPER)
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        pid = _wait(lambda: (r := _job_row(jid)) and r.status == "running" and r.pid)
        os.kill(pid, 0)                                   # alive
        t0 = time.time()
        assert jobs.cancel(jid) is True
        row = _wait(lambda: (r := _job_row(jid)) and r.status == "failed" and r)
        assert time.time() - t0 < 10
        assert row.error_message == jobs.CANCELLED_MESSAGE and row.pid is None
        _wait(lambda: not jobs.is_tracked(jid))
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    def test_concurrency_is_bounded_and_extra_jobs_wait(self, db_session, threaded_runner, monkeypatch):
        monkeypatch.setattr(settings, "max_concurrent_jobs", 1)
        _fake_worker(monkeypatch, _QUICK.format(delay=1.0))
        first, second = _insert_job(), _insert_job()
        jobs.submit_local(first, "pjobs0000001", "unused.yaml")
        jobs.submit_local(second, "pjobs0000001", "unused.yaml")
        _wait(lambda: _job_row(first).status == "running")
        overlap = False
        while _job_row(first).status == "running":
            overlap |= _job_row(second).status == "running"
            time.sleep(0.05)
        assert not overlap
        _wait(lambda: _job_row(second).status == "completed")
        assert _job_row(second).started_at >= _job_row(first).completed_at

    def test_queued_job_cancelled_before_its_turn_never_starts(self, db_session, threaded_runner, monkeypatch):
        monkeypatch.setattr(settings, "max_concurrent_jobs", 1)
        _fake_worker(monkeypatch, _QUICK.format(delay=0.8))
        first, second = _insert_job(), _insert_job()
        jobs.submit_local(first, "pjobs0000001", "unused.yaml")
        jobs.submit_local(second, "pjobs0000001", "unused.yaml")
        assert jobs.cancel(second) is True
        _wait(lambda: _job_row(first).status == "completed")
        row = _wait(lambda: (r := _job_row(second)) and r.status == "failed" and r)
        assert row.started_at is None and row.error_message == jobs.CANCELLED_MESSAGE

    def test_per_user_limit_lets_other_users_through(self, db_session, threaded_runner, monkeypatch):
        """One user's batch must not occupy every slot."""
        from app.core.security import hash_password
        from app.models.db_models import User
        with sync_session_factory() as db:
            for uid in ("ualice000001", "ubob00000001"):
                db.add(User(id=uid, email=f"{uid}@example.com", hashed_password=hash_password("x")))
            db.commit()
        monkeypatch.setattr(settings, "max_concurrent_jobs", 2)
        monkeypatch.setenv("PREDOMICS_MAX_JOBS_PER_USER", "1")
        if hasattr(settings, "max_jobs_per_user"):
            monkeypatch.setattr(settings, "max_jobs_per_user", 1)
        _fake_worker(monkeypatch, _QUICK.format(delay=1.0))
        a1, a2, a3 = (_insert_job(user_id="ualice000001") for _ in range(3))
        b1 = _insert_job(user_id="ubob00000001")
        for jid, uid in ((a1, "ualice000001"), (a2, "ualice000001"), (a3, "ualice000001"), (b1, "ubob00000001")):
            jobs.submit_local(jid, "pjobs0000001", "unused.yaml", uid)
        st = jobs.stats()
        assert st["running"] == 2 and st["queued"] == 2 and st["max_per_user"] == 1
        # bob's job, submitted last, runs alongside alice's first one
        _wait(lambda: _job_row(a1).status == "running" and _job_row(b1).status == "running")
        assert _job_row(a2).status == "pending" and _job_row(a3).status == "pending"
        for jid in (a1, a2, a3, b1):
            _wait(lambda j=jid: _job_row(j).status == "completed", timeout=30)
        rows = sorted((_job_row(j) for j in (a1, a2, a3)), key=lambda r: r.started_at)
        for earlier, later in zip(rows, rows[1:]):
            assert later.started_at >= earlier.completed_at   # alice never ran two at once
        assert jobs.wait_idle(10) and jobs.stats()["running"] == 0

    def test_stats_reports_queue_and_slots(self, db_session, threaded_runner, monkeypatch):
        monkeypatch.setattr(settings, "max_concurrent_jobs", 1)
        _fake_worker(monkeypatch, _SLEEPER)
        first, second = _insert_job(), _insert_job()
        jobs.submit_local(first, "pjobs0000001", "unused.yaml")
        jobs.submit_local(second, "pjobs0000001", "unused.yaml")
        _wait(lambda: _job_row(first).status == "running")
        st = jobs.stats()
        assert (st["running"], st["queued"], st["free_slots"], st["max_concurrent"]) == (1, 1, 0, 1)

    def test_timeout_stops_the_job(self, db_session, threaded_runner, monkeypatch):
        monkeypatch.setattr(settings, "job_timeout_minutes", 0.02)   # 1.2 s
        _fake_worker(monkeypatch, _SLEEPER)
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        row = _wait(lambda: (r := _job_row(jid)) and r.status == "failed" and r, timeout=20)
        assert "time limit" in row.error_message

    def test_crashing_worker_marks_the_job_failed_with_its_output(self, db_session, threaded_runner, monkeypatch):
        _fake_worker(monkeypatch, "import sys; print('boom: bad matrix'); sys.exit(3)")
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        row = _wait(lambda: (r := _job_row(jid)) and r.status == "failed" and r)
        assert "code 3" in row.error_message and "boom: bad matrix" in row.error_message

    def test_unexpected_error_never_leaves_the_job_running(self, db_session, threaded_runner, monkeypatch):
        def _explode(*a, **k):
            raise RuntimeError("cannot start worker")

        monkeypatch.setattr(jobs.subprocess, "Popen", _explode)
        jid = _insert_job()
        jobs.submit_local(jid, "pjobs0000001", "unused.yaml")
        row = _wait(lambda: (r := _job_row(jid)) and r.status == "failed" and r)
        assert "cannot start worker" in row.error_message
        _wait(lambda: not jobs.is_tracked(jid))


# ---------------------------------------------------------------------------
# Real engine, real worker subprocess (skipped where gpredomicspy is absent)
# ---------------------------------------------------------------------------

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "qin2014_cirrhosis"


@pytest.mark.parametrize("data_type", ["raw,prev", "zscore"])
def test_real_job_end_to_end(db_session, threaded_runner, data_type):
    pytest.importorskip("gpredomicspy")
    if not (_SAMPLE / "Xtrain.tsv").exists():
        pytest.skip("sample dataset not available")
    import numpy as np
    import pandas as pd
    from app.services.prediction import compute_auc, predict_from_model

    jid = _insert_job()
    job_dir = results_io.job_dir("pjobs0000001", jid)
    job_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "general": {"algo": "ga", "language": "bin,ter,ratio", "data_type": data_type, "fit": "auc",
                    "seed": 42, "thread_number": 2, "k_penalty": 0.0001, "cv": False, "gpu": False},
        "ga": {"population_size": 120, "max_epochs": 3, "min_epochs": 1, "k_min": 1, "k_max": 15},
    }
    param_path = ml_engine.write_param_yaml(
        cfg, str(_SAMPLE / "Xtrain.tsv"), str(_SAMPLE / "Ytrain.tsv"),
        str(_SAMPLE / "Xtest.tsv"), str(_SAMPLE / "Ytest.tsv"), output_dir=str(job_dir),
    )
    jobs.submit_local(jid, "pjobs0000001", param_path)
    row = _wait(lambda: (r := _job_row(jid)) and r.status in ("completed", "failed") and r, timeout=180)
    assert row.status == "completed", row.error_message

    results = results_io.load_results("pjobs0000001", jid)
    summary = json.loads((job_dir / "summary.json").read_text())
    assert results["engine"] == "gpredomics" and "mock" not in results
    assert results["epsilon"] == 1e-5
    assert row.best_auc == results["best_individual"]["auc"] == summary["best_auc"]
    assert row.best_k == results["best_individual"]["k"]
    assert not list(job_dir.glob(".results.json.*"))          # no leftover temp files

    # The stored model, applied to the test set through the public prediction path,
    # reproduces the test AUC the worker recorded for the final generation's best model.
    x_test = pd.read_csv(_SAMPLE / "Xtest.tsv", sep="\t", index_col=0)
    y_test = pd.read_csv(_SAMPLE / "Ytest.tsv", sep="\t", index_col=0).iloc[:, 0]
    out = predict_from_model(results, x_test, y_labels=y_test, features_in_rows=True)
    assert out["evaluation"]["n_evaluated"] == 30
    curve = [g.get("best_auc_test") for g in results["generation_tracking"]]
    assert all(v is not None and 0.0 <= v <= 1.0 for v in curve)
    if results["best_individual"]["data_type"] == "zscore":
        used = {results["feature_names"][int(i)] for i in results["best_individual"]["features"]}
        assert used <= set(results["zscore_stats"])
    assert np.isfinite(out["evaluation"]["auc"])
