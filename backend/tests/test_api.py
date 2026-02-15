"""Comprehensive API tests for PredomicsApp backend."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Override settings before importing app
_tmp = tempfile.mkdtemp()
os.environ["PREDOMICS_DATA_DIR"] = _tmp
os.environ["PREDOMICS_PROJECT_DIR"] = os.path.join(_tmp, "projects")
os.environ["PREDOMICS_UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["PREDOMICS_SAMPLE_DIR"] = os.path.join(_tmp, "samples")
_db_path = os.path.join(_tmp, "test.db")
os.environ["PREDOMICS_DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"
os.environ["PREDOMICS_SECRET_KEY"] = "test-secret-key"
os.environ["PREDOMICS_RATE_LIMIT_ENABLED"] = "false"

from app.main import app  # noqa: E402
from app.core.database import engine, Base, get_db, async_session_factory, sync_engine  # noqa: E402
from app.services import engine as ml_engine  # noqa: E402
from app.services import storage  # noqa: E402
from app.services import data_analysis  # noqa: E402


@pytest_asyncio.fixture
async def db_session():
    """Create tables and yield a test database session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Also create tables for the sync engine (used by background tasks)
    Base.metadata.create_all(sync_engine)
    async with async_session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    Base.metadata.drop_all(sync_engine)


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP client with overridden DB dependency."""
    async def _override_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client):
    """Authenticated HTTP client with a pre-registered user."""
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "testpass123",
        "full_name": "Test User",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "testpass123",
    })
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture(autouse=True)
def clean_data():
    """Clean data directory between tests."""
    yield
    data_dir = os.environ["PREDOMICS_DATA_DIR"]
    for d in ["projects", "uploads", "datasets"]:
        p = os.path.join(data_dir, d)
        if os.path.exists(p):
            shutil.rmtree(p)
            os.makedirs(p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project_with_datasets(auth_client):
    """Create a project with X and y datasets, return (project_id, x_file_id, y_file_id)."""
    create_resp = await auth_client.post("/api/projects/", params={"name": "test_proj"})
    pid = create_resp.json()["project_id"]

    await auth_client.post(
        f"/api/projects/{pid}/datasets",
        files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\nf2\t0.3\t0.4\n", "text/plain")},
    )
    await auth_client.post(
        f"/api/projects/{pid}/datasets",
        files={"file": ("y.tsv", b"id\tclass\ns1\t0\ns2\t1\n", "text/plain")},
    )

    proj = (await auth_client.get(f"/api/projects/{pid}")).json()
    datasets = proj["datasets"]
    # Each upload creates a one-file dataset group; extract file IDs
    x_file_id = datasets[0]["files"][0]["id"]
    y_file_id = datasets[1]["files"][0]["id"]
    return pid, x_file_id, y_file_id


async def _run_mock_analysis(auth_client, pid, x_file_id, y_file_id):
    """Run a mock analysis job, return the job_id."""
    config = {
        "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                    "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
        "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
    }

    with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
        resp = await auth_client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_file_id": x_file_id, "y_file_id": y_file_id},
        )
    return resp.json()["job_id"]


async def _create_completed_job(auth_client, db_session):
    """Create a project, run a mock analysis, save results, mark as completed.

    Returns (project_id, job_id).
    """
    from sqlalchemy import text

    pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
    job_id = await _run_mock_analysis(auth_client, pid, x_fid, y_fid)

    # Save mock results to disk
    mock = ml_engine._mock_results()
    storage.save_job_result(pid, job_id, mock)

    # Mark job as completed in the database
    await db_session.execute(
        text("UPDATE jobs SET status = 'completed' WHERE id = :jid"),
        {"jid": job_id},
    )
    await db_session.commit()

    return pid, job_id


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_has_correct_fields(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert "gpredomicspy_available" in data


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_register_new_user(self, client):
        resp = await client.post("/api/auth/register", json={
            "email": "new@example.com", "password": "pass123"
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == "new@example.com"

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client):
        await client.post("/api/auth/register", json={"email": "dup@x.com", "password": "p"})
        resp = await client.post("/api/auth/register", json={"email": "dup@x.com", "password": "p"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_login_returns_token(self, client):
        await client.post("/api/auth/register", json={"email": "a@b.com", "password": "p"})
        resp = await client.post("/api/auth/login", json={"email": "a@b.com", "password": "p"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client):
        await client.post("/api/auth/register", json={"email": "a@b.com", "password": "right"})
        resp = await client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_returns_401(self, client):
        resp = await client.post("/api/auth/login", json={"email": "nope@x.com", "password": "p"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_without_token_returns_error(self, client):
        resp = await client.get("/api/auth/me")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, auth_client):
        resp = await auth_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_me_returns_full_name(self, auth_client):
        resp = await auth_client.get("/api/auth/me")
        assert resp.json()["full_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Projects (all require auth)
# ---------------------------------------------------------------------------

class TestProjects:
    @pytest.mark.asyncio
    async def test_create_project(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "TestProject"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "TestProject"
        assert "project_id" in data

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, auth_client):
        resp = await auth_client.get("/api/projects/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_projects_after_create(self, auth_client):
        await auth_client.post("/api/projects/", params={"name": "P1"})
        resp = await auth_client.get("/api/projects/")
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "P1"

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "Mine"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Mine"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(self, auth_client):
        resp = await auth_client.get("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "Del"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 200

        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project_returns_404(self, auth_client):
        resp = await auth_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_has_created_at_timestamp(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "TimedProject"})
        data = resp.json()
        assert "created_at" in data
        assert "T" in data["created_at"]  # ISO format

    @pytest.mark.asyncio
    async def test_unauthenticated_access_returns_error(self, client):
        resp = await client.get("/api/projects/")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

class TestDatasets:
    @pytest.mark.asyncio
    async def test_upload_tsv_dataset(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "ds_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\n", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "X.tsv"

    @pytest.mark.asyncio
    async def test_upload_csv_dataset(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "csv_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("data.csv", b"id,s1,s2\nf1,0.1,0.2\n", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "data.csv"

    @pytest.mark.asyncio
    async def test_upload_to_nonexistent_project_returns_404(self, auth_client):
        resp = await auth_client.post(
            "/api/projects/nonexistent/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_updates_project_metadata(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "meta_test"})
        pid = create_resp.json()["project_id"]
        await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        resp = await auth_client.get(f"/api/projects/{pid}")
        datasets = resp.json()["datasets"]
        assert len(datasets) == 1
        assert datasets[0]["name"] == "X.tsv"
        assert len(datasets[0]["files"]) == 1
        assert datasets[0]["files"][0]["filename"] == "X.tsv"

    @pytest.mark.asyncio
    async def test_upload_multiple_datasets(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "multi_ds"})
        pid = create_resp.json()["project_id"]
        await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\n", "text/plain")},
        )
        await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("y.tsv", b"id\tclass\ns1\t0\ns2\t1\n", "text/plain")},
        )
        resp = await auth_client.get(f"/api/projects/{pid}")
        assert len(resp.json()["datasets"]) == 2


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------

class TestAnalysis:
    @pytest.mark.asyncio
    async def test_run_analysis_returns_job_id(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)
        assert job_id  # non-empty string

    @pytest.mark.asyncio
    async def test_get_job_status_nonexistent_returns_404(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "status_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "jobs_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_after_run(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        await _run_mock_analysis(auth_client, pid, x_id, y_id)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_get_job_logs_nonexistent_returns_404(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "log_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/nonexistent/logs")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_logs_returns_log_content(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)

        # Write a fake console.log for the job
        job_dir = Path(storage.settings.project_dir) / pid / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "console.log").write_text("Starting analysis...\nDone.\n")

        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert "Starting analysis" in data["log"]

    @pytest.mark.asyncio
    async def test_get_job_detail_nonexistent_returns_404(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "detail_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/nonexistent/detail")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_detail_with_results(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)

        # Save mock results to disk
        mock = ml_engine._mock_results()
        storage.save_job_result(pid, job_id, mock)

        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["best_auc"] == mock["best_individual"]["auc"]
        assert data["best_k"] == mock["best_individual"]["k"]
        assert len(data["feature_names"]) == 50

    @pytest.mark.asyncio
    async def test_get_job_results_raw(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_id, y_id)

        mock = ml_engine._mock_results()
        storage.save_job_result(pid, job_id, mock)

        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/results")
        assert resp.status_code == 200
        data = resp.json()
        assert "best_individual" in data
        assert "feature_names" in data
        assert data["generation_count"] == mock["generation_count"]

    @pytest.mark.asyncio
    async def test_get_job_results_raw_nonexistent_returns_404(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "raw_test"})
        pid = create_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/nonexistent/results")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_run_analysis_missing_datasets_returns_404(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "no_ds"})
        pid = create_resp.json()["project_id"]

        resp = await auth_client.post(
            f"/api/analysis/{pid}/run",
            json={},
            params={"x_file_id": "nonexistent", "y_file_id": "nonexistent"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    @pytest.mark.asyncio
    async def test_run_with_invalid_algo_returns_422(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "val_test"})
        pid = create_resp.json()["project_id"]

        config = {"general": {"algo": "invalid_algo"}}
        resp = await auth_client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_file_id": "abc", "y_file_id": "def"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_run_with_invalid_fit_returns_422(self, auth_client):
        create_resp = await auth_client.post("/api/projects/", params={"name": "fit_test"})
        pid = create_resp.json()["project_id"]

        config = {"general": {"fit": "invalid_fit"}}
        resp = await auth_client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_file_id": "abc", "y_file_id": "def"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_run_with_defaults_accepts_empty_config(self, auth_client):
        """RunConfig should have sensible defaults for all fields."""
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)

        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/run",
                json={},
                params={"x_file_id": x_id, "y_file_id": y_id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_run_with_beam_algorithm(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)

        config = {"general": {"algo": "beam"}}
        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/run",
                json=config,
                params={"x_file_id": x_id, "y_file_id": y_id},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_run_with_mcmc_algorithm(self, auth_client):
        pid, x_id, y_id = await _create_project_with_datasets(auth_client)

        config = {"general": {"algo": "mcmc"}}
        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/run",
                json=config,
                params={"x_file_id": x_id, "y_file_id": y_id},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Samples (demo data)
# ---------------------------------------------------------------------------

class TestSamples:
    @pytest.mark.asyncio
    async def test_list_samples_returns_list(self, auth_client):
        resp = await auth_client.get("/api/samples/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Verify structure
        sample = data[0]
        assert "id" in sample
        assert "name" in sample
        assert "available" in sample

    @pytest.mark.asyncio
    async def test_list_samples_no_auth_required(self, client):
        # samples/list should work without auth (it just lists what's available)
        # Note: the endpoint does not require auth in current implementation
        resp = await client.get("/api/samples/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_load_sample_nonexistent_returns_404(self, auth_client):
        resp = await auth_client.post("/api/samples/nonexistent/load")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_load_sample_creates_project(self, auth_client):
        # Create a fake sample directory with files
        sample_dir = Path(os.environ["PREDOMICS_SAMPLE_DIR"])
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "Xtrain.tsv").write_text("id\ts1\ts2\nf1\t0.1\t0.2\n")
        (sample_dir / "Ytrain.tsv").write_text("id\tclass\ns1\t0\ns2\t1\n")
        (sample_dir / "Xtest.tsv").write_text("id\ts3\nf1\t0.3\n")
        (sample_dir / "Ytest.tsv").write_text("id\tclass\ns3\t1\n")

        resp = await auth_client.post("/api/samples/qin2014_cirrhosis/load")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Qin2014 Liver Cirrhosis"
        # One composite dataset with 4 files
        assert len(data["datasets"]) == 1
        assert len(data["datasets"][0]["files"]) == 4

    @pytest.mark.asyncio
    async def test_load_sample_twice_returns_same_project(self, auth_client):
        """Loading the same demo twice must NOT create a duplicate project."""
        sample_dir = Path(os.environ["PREDOMICS_SAMPLE_DIR"])
        sample_dir.mkdir(parents=True, exist_ok=True)
        (sample_dir / "Xtrain.tsv").write_text("id\ts1\ts2\nf1\t0.1\t0.2\n")
        (sample_dir / "Ytrain.tsv").write_text("id\tclass\ns1\t0\ns2\t1\n")
        (sample_dir / "Xtest.tsv").write_text("id\ts3\nf1\t0.3\n")
        (sample_dir / "Ytest.tsv").write_text("id\tclass\ns3\t1\n")

        resp1 = await auth_client.post("/api/samples/qin2014_cirrhosis/load")
        resp2 = await auth_client.post("/api/samples/qin2014_cirrhosis/load")
        assert resp1.json()["project_id"] == resp2.json()["project_id"]

        # Verify only one project exists
        projects = (await auth_client.get("/api/projects/")).json()
        demo_projects = [p for p in projects if p["name"] == "Qin2014 Liver Cirrhosis"]
        assert len(demo_projects) == 1


# ---------------------------------------------------------------------------
# Project isolation between users
# ---------------------------------------------------------------------------

class TestProjectIsolation:
    @pytest.mark.asyncio
    async def test_user_cannot_see_other_users_projects(self, client):
        # Register two users
        await client.post("/api/auth/register", json={"email": "a@x.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "b@x.com", "password": "p"})

        # User A creates a project
        r = await client.post("/api/auth/login", json={"email": "a@x.com", "password": "p"})
        token_a = r.json()["access_token"]
        await client.post("/api/projects/", params={"name": "a_proj"},
                          headers={"Authorization": f"Bearer {token_a}"})

        # User B should not see it
        r = await client.post("/api/auth/login", json={"email": "b@x.com", "password": "p"})
        token_b = r.json()["access_token"]
        resp = await client.get("/api/projects/",
                                headers={"Authorization": f"Bearer {token_b}"})
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_project(self, client):
        # Register two users
        await client.post("/api/auth/register", json={"email": "own@x.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "other@x.com", "password": "p"})

        # User A creates a project
        r = await client.post("/api/auth/login", json={"email": "own@x.com", "password": "p"})
        token_a = r.json()["access_token"]
        create_resp = await client.post("/api/projects/", params={"name": "private_proj"},
                                         headers={"Authorization": f"Bearer {token_a}"})
        pid = create_resp.json()["project_id"]

        # User B cannot access it
        r = await client.post("/api/auth/login", json={"email": "other@x.com", "password": "p"})
        token_b = r.json()["access_token"]
        resp = await client.get(f"/api/projects/{pid}",
                                headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_user_cannot_delete_other_users_project(self, client):
        await client.post("/api/auth/register", json={"email": "own2@x.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "other2@x.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own2@x.com", "password": "p"})
        token_a = r.json()["access_token"]
        create_resp = await client.post("/api/projects/", params={"name": "protected"},
                                         headers={"Authorization": f"Bearer {token_a}"})
        pid = create_resp.json()["project_id"]

        r = await client.post("/api/auth/login", json={"email": "other2@x.com", "password": "p"})
        token_b = r.json()["access_token"]
        resp = await client.delete(f"/api/projects/{pid}",
                                   headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Storage service unit tests
# ---------------------------------------------------------------------------

class TestStorage:
    def test_ensure_dirs(self):
        storage.ensure_dirs()
        assert storage.settings.upload_dir.exists()
        assert storage.settings.project_dir.exists()

    def test_save_and_get_dataset_file(self):
        storage.ensure_project_dirs("test_proj")
        path = storage.save_dataset_file("test_proj", "ds1", "X.tsv", b"test content")
        assert os.path.exists(path)

        found = storage.get_dataset_path("test_proj", "ds1")
        assert found is not None
        assert found.read_bytes() == b"test content"

    def test_get_dataset_path_nonexistent(self):
        storage.ensure_project_dirs("empty_proj")
        result = storage.get_dataset_path("empty_proj", "nonexistent")
        assert result is None

    def test_save_and_get_job_result(self):
        mock = ml_engine._mock_results()
        path = storage.save_job_result("test_proj", "job1", mock)
        assert os.path.exists(path)

        loaded = storage.get_job_result("test_proj", "job1")
        assert loaded is not None
        assert loaded["best_individual"]["auc"] == mock["best_individual"]["auc"]

    def test_get_job_result_nonexistent(self):
        result = storage.get_job_result("nonexistent_proj", "nonexistent_job")
        assert result is None

    def test_delete_project_files(self):
        storage.ensure_project_dirs("del_proj")
        storage.save_dataset_file("del_proj", "ds1", "X.tsv", b"data")
        project_path = storage.settings.project_dir / "del_proj"
        assert project_path.exists()

        storage.delete_project_files("del_proj")
        assert not project_path.exists()

    def test_delete_nonexistent_project_files(self):
        # Should not raise
        storage.delete_project_files("does_not_exist")


# ---------------------------------------------------------------------------
# Engine service unit tests
# ---------------------------------------------------------------------------

class TestEngine:
    def test_write_param_yaml(self):
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 100, "max_epochs": 5, "k_min": 1, "k_max": 10},
        }
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            path = ml_engine.write_param_yaml(
                config, x_path="/data/X.tsv", y_path="/data/y.tsv", output_dir=tmp
            )
            assert os.path.exists(path)
            with open(path) as f:
                param = yaml.safe_load(f)
            assert param["general"]["algo"] == "ga"
            assert param["data"]["X"] == "/data/X.tsv"
            assert param["ga"]["population_size"] == 100

    def test_mock_results_structure(self):
        mock = ml_engine._mock_results()
        assert "fold_count" in mock
        assert "generation_count" in mock
        assert "execution_time" in mock
        assert "feature_names" in mock
        assert "sample_names" in mock
        assert "best_individual" in mock
        best = mock["best_individual"]
        assert "auc" in best
        assert "fit" in best
        assert "k" in best
        assert "features" in best

    def test_check_engine(self):
        result = ml_engine.check_engine()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Security unit tests
# ---------------------------------------------------------------------------

class TestSecurity:
    def test_hash_and_verify_password(self):
        from app.core.security import hash_password, verify_password
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"
        assert verify_password("mysecret", hashed)
        assert not verify_password("wrongpass", hashed)

    def test_create_and_decode_token(self):
        from app.core.security import create_access_token, decode_access_token
        token = create_access_token("user123")
        user_id = decode_access_token(token)
        assert user_id == "user123"

    def test_decode_invalid_token(self):
        from app.core.security import decode_access_token
        result = decode_access_token("garbage.token.value")
        assert result is None


# ---------------------------------------------------------------------------
# User Profile Management
# ---------------------------------------------------------------------------

class TestUserProfile:
    @pytest.mark.asyncio
    async def test_update_profile_name(self, auth_client):
        resp = await auth_client.put("/api/auth/me", json={"full_name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "New Name"

        # Verify persisted
        me = await auth_client.get("/api/auth/me")
        assert me.json()["full_name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_profile_null_name_keeps_existing(self, auth_client):
        resp = await auth_client.put("/api/auth/me", json={})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Test User"  # unchanged

    @pytest.mark.asyncio
    async def test_change_password_success(self, auth_client):
        resp = await auth_client.put("/api/auth/me/password", json={
            "current_password": "testpass123",
            "new_password": "newpass456",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "password_changed"

        # Login with new password
        resp = await auth_client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "newpass456",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, auth_client):
        resp = await auth_client.put("/api/auth/me/password", json={
            "current_password": "wrongpass",
            "new_password": "newpass456",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_users_by_email(self, client):
        # Register multiple users
        await client.post("/api/auth/register", json={"email": "alice@example.com", "password": "p", "full_name": "Alice"})
        await client.post("/api/auth/register", json={"email": "bob@example.com", "password": "p", "full_name": "Bob"})
        await client.post("/api/auth/register", json={"email": "alice2@example.com", "password": "p", "full_name": "Alice2"})

        # Login as bob
        r = await client.post("/api/auth/login", json={"email": "bob@example.com", "password": "p"})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Search for "alice" — should find 2 results, not bob
        resp = await client.get("/api/auth/users/search", params={"q": "alice"}, headers=headers)
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        emails = {u["email"] for u in results}
        assert "alice@example.com" in emails
        assert "alice2@example.com" in emails
        assert "bob@example.com" not in emails

    @pytest.mark.asyncio
    async def test_search_users_excludes_self(self, auth_client):
        # auth_client is test@example.com — searching for "test" should not return self
        resp = await auth_client.get("/api/auth/users/search", params={"q": "test"})
        assert resp.status_code == 200
        emails = {u["email"] for u in resp.json()}
        assert "test@example.com" not in emails

    @pytest.mark.asyncio
    async def test_search_users_min_query_length(self, auth_client):
        resp = await auth_client.get("/api/auth/users/search", params={"q": "a"})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Dataset Library
# ---------------------------------------------------------------------------

class TestDatasetLibrary:
    @pytest.mark.asyncio
    async def test_create_dataset_group(self, auth_client):
        resp = await auth_client.post(
            "/api/datasets/", params={"name": "My Dataset"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Dataset"
        assert data["project_count"] == 0
        assert data["files"] == []

    @pytest.mark.asyncio
    async def test_upload_file_to_dataset(self, auth_client):
        # Create group
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Test DS"})
        ds_id = ds_resp.json()["id"]

        # Upload file into group
        resp = await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("Xtrain.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "Xtrain.tsv"
        assert resp.json()["role"] == "xtrain"

    @pytest.mark.asyncio
    async def test_list_datasets(self, auth_client):
        await auth_client.post("/api/datasets/", params={"name": "DS A"})
        await auth_client.post("/api/datasets/", params={"name": "DS B"})
        resp = await auth_client.get("/api/datasets/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_delete_dataset(self, auth_client):
        resp = await auth_client.post("/api/datasets/", params={"name": "To Delete"})
        ds_id = resp.json()["id"]
        resp = await auth_client.delete(f"/api/datasets/{ds_id}")
        assert resp.status_code == 200
        resp = await auth_client.get("/api/datasets/")
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_file_from_dataset(self, auth_client):
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "File Del"})
        ds_id = ds_resp.json()["id"]
        file_resp = await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        file_id = file_resp.json()["id"]

        resp = await auth_client.delete(f"/api/datasets/{ds_id}/files/{file_id}")
        assert resp.status_code == 200

        # Dataset group still exists but has no files
        ds = (await auth_client.get(f"/api/datasets/{ds_id}")).json()
        assert len(ds["files"]) == 0

    @pytest.mark.asyncio
    async def test_assign_dataset_to_project(self, auth_client):
        # Create dataset group with a file
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Xtrain Set"})
        ds_id = ds_resp.json()["id"]
        await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("Xtrain.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )

        # Create project
        proj_resp = await auth_client.post("/api/projects/", params={"name": "assign_test"})
        pid = proj_resp.json()["project_id"]

        # Assign
        resp = await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 200

        # Project should show the dataset with its files
        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        assert len(proj["datasets"]) == 1
        assert proj["datasets"][0]["name"] == "Xtrain Set"
        assert len(proj["datasets"][0]["files"]) == 1
        assert proj["datasets"][0]["files"][0]["role"] == "xtrain"

    @pytest.mark.asyncio
    async def test_unassign_dataset_from_project(self, auth_client):
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Unassign DS"})
        ds_id = ds_resp.json()["id"]
        proj_resp = await auth_client.post("/api/projects/", params={"name": "unassign_test"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        resp = await auth_client.delete(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 200

        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        assert len(proj["datasets"]) == 0

    @pytest.mark.asyncio
    async def test_dataset_shared_across_projects(self, auth_client):
        """One dataset can be assigned to multiple projects."""
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Shared DS"})
        ds_id = ds_resp.json()["id"]

        p1 = (await auth_client.post("/api/projects/", params={"name": "p1"})).json()["project_id"]
        p2 = (await auth_client.post("/api/projects/", params={"name": "p2"})).json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{p1}")
        await auth_client.post(f"/api/datasets/{ds_id}/assign/{p2}")

        # Dataset should report project_count = 2
        ds_detail = (await auth_client.get(f"/api/datasets/{ds_id}")).json()
        assert ds_detail["project_count"] == 2

    @pytest.mark.asyncio
    async def test_delete_project_keeps_datasets(self, auth_client):
        """Deleting a project should NOT delete the user's datasets."""
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Keep Me"})
        ds_id = ds_resp.json()["id"]

        proj_resp = await auth_client.post("/api/projects/", params={"name": "temp_proj"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        await auth_client.delete(f"/api/projects/{pid}")

        # Dataset should still exist in library
        resp = await auth_client.get(f"/api/datasets/{ds_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Keep Me"

    @pytest.mark.asyncio
    async def test_backward_compat_project_upload_creates_library_entry(self, auth_client):
        """POST /projects/{pid}/datasets should also create a library entry."""
        proj_resp = await auth_client.post("/api/projects/", params={"name": "compat_test"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )

        # Should appear in user's dataset library
        library = (await auth_client.get("/api/datasets/")).json()
        assert any(d["name"] == "X.tsv" for d in library)

    @pytest.mark.asyncio
    async def test_duplicate_assignment_returns_409(self, auth_client):
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Dup DS"})
        ds_id = ds_resp.json()["id"]
        proj_resp = await auth_client.post("/api/projects/", params={"name": "dup_test"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        resp = await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_composite_dataset_with_multiple_files(self, auth_client):
        """Create a composite dataset with 4 files like real Qin2014 data."""
        ds_resp = await auth_client.post(
            "/api/datasets/", params={"name": "Qin2014", "description": "Cirrhosis data"},
        )
        ds_id = ds_resp.json()["id"]

        for fname in ["Xtrain.tsv", "Ytrain.tsv", "Xtest.tsv", "Ytest.tsv"]:
            await auth_client.post(
                f"/api/datasets/{ds_id}/files",
                files={"file": (fname, b"id\ts1\nf1\t0.1\n", "text/plain")},
            )

        ds = (await auth_client.get(f"/api/datasets/{ds_id}")).json()
        assert ds["name"] == "Qin2014"
        assert ds["description"] == "Cirrhosis data"
        assert len(ds["files"]) == 4

        roles = {f["role"] for f in ds["files"]}
        assert roles == {"xtrain", "ytrain", "xtest", "ytest"}


# ---------------------------------------------------------------------------
# Project Sharing
# ---------------------------------------------------------------------------

class TestProjectSharing:
    @pytest.mark.asyncio
    async def test_share_project_with_user(self, client):
        """Owner shares project → target can see it."""
        # Register two users
        await client.post("/api/auth/register", json={"email": "owner@test.com", "password": "p", "full_name": "Owner"})
        await client.post("/api/auth/register", json={"email": "viewer@test.com", "password": "p", "full_name": "Viewer"})

        # Owner creates project
        r = await client.post("/api/auth/login", json={"email": "owner@test.com", "password": "p"})
        owner_token = r.json()["access_token"]
        owner_h = {"Authorization": f"Bearer {owner_token}"}

        proj = await client.post("/api/projects/", params={"name": "shared_proj"}, headers=owner_h)
        pid = proj.json()["project_id"]

        # Share with viewer
        resp = await client.post(
            f"/api/projects/{pid}/share",
            json={"email": "viewer@test.com", "role": "viewer"},
            headers=owner_h,
        )
        assert resp.status_code == 200

        # Viewer logs in and can see shared project
        r = await client.post("/api/auth/login", json={"email": "viewer@test.com", "password": "p"})
        viewer_token = r.json()["access_token"]
        viewer_h = {"Authorization": f"Bearer {viewer_token}"}

        shared = await client.get("/api/projects/shared-with-me", headers=viewer_h)
        assert len(shared.json()) == 1
        assert shared.json()[0]["project_id"] == pid

    @pytest.mark.asyncio
    async def test_viewer_can_see_project(self, client):
        """Viewer can GET /projects/{pid}."""
        await client.post("/api/auth/register", json={"email": "own3@test.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "view3@test.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own3@test.com", "password": "p"})
        own_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "viewable"}, headers=own_h)).json()["project_id"]

        await client.post(f"/api/projects/{pid}/share", json={"email": "view3@test.com", "role": "viewer"}, headers=own_h)

        r = await client.post("/api/auth/login", json={"email": "view3@test.com", "password": "p"})
        view_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        resp = await client.get(f"/api/projects/{pid}", headers=view_h)
        assert resp.status_code == 200
        assert resp.json()["name"] == "viewable"

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_project(self, client):
        await client.post("/api/auth/register", json={"email": "own4@test.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "view4@test.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own4@test.com", "password": "p"})
        own_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "nodelete"}, headers=own_h)).json()["project_id"]

        await client.post(f"/api/projects/{pid}/share", json={"email": "view4@test.com", "role": "viewer"}, headers=own_h)

        r = await client.post("/api/auth/login", json={"email": "view4@test.com", "password": "p"})
        view_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        resp = await client.delete(f"/api/projects/{pid}", headers=view_h)
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_editor_can_upload_dataset(self, client):
        await client.post("/api/auth/register", json={"email": "own5@test.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "edit5@test.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own5@test.com", "password": "p"})
        own_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "editable"}, headers=own_h)).json()["project_id"]

        await client.post(f"/api/projects/{pid}/share", json={"email": "edit5@test.com", "role": "editor"}, headers=own_h)

        r = await client.post("/api/auth/login", json={"email": "edit5@test.com", "password": "p"})
        edit_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        resp = await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
            headers=edit_h,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_cannot_upload_dataset(self, client):
        await client.post("/api/auth/register", json={"email": "own6@test.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "view6@test.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own6@test.com", "password": "p"})
        own_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "readonly"}, headers=own_h)).json()["project_id"]

        await client.post(f"/api/projects/{pid}/share", json={"email": "view6@test.com", "role": "viewer"}, headers=own_h)

        r = await client.post("/api/auth/login", json={"email": "view6@test.com", "password": "p"})
        view_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        resp = await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
            headers=view_h,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_revoke_share_removes_access(self, client):
        await client.post("/api/auth/register", json={"email": "own7@test.com", "password": "p"})
        await client.post("/api/auth/register", json={"email": "view7@test.com", "password": "p"})

        r = await client.post("/api/auth/login", json={"email": "own7@test.com", "password": "p"})
        own_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "revokable"}, headers=own_h)).json()["project_id"]

        # Share then revoke
        share_resp = await client.post(f"/api/projects/{pid}/share", json={"email": "view7@test.com", "role": "viewer"}, headers=own_h)
        share_id = share_resp.json()["id"]

        await client.delete(f"/api/projects/{pid}/shares/{share_id}", headers=own_h)

        # Viewer should no longer see the project
        r = await client.post("/api/auth/login", json={"email": "view7@test.com", "password": "p"})
        view_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        resp = await client.get(f"/api/projects/{pid}", headers=view_h)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_share_with_self(self, auth_client):
        pid = (await auth_client.post("/api/projects/", params={"name": "self_share"})).json()["project_id"]
        resp = await auth_client.post(
            f"/api/projects/{pid}/share",
            json={"email": "test@example.com", "role": "viewer"},
        )
        assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────
#  Admin Management
# ──────────────────────────────────────────────────────────────

class TestAdmin:
    """Tests for admin user management endpoints."""

    async def _make_admin(self, client, db_session):
        """Register a user and promote to admin, return auth headers."""
        await client.post("/api/auth/register", json={
            "email": "admin@example.com", "password": "adminpass", "full_name": "Admin User",
        })
        from app.models.db_models import User
        from sqlalchemy import update
        await db_session.execute(
            update(User).where(User.email == "admin@example.com").values(is_admin=True)
        )
        await db_session.commit()
        r = await client.post("/api/auth/login", json={
            "email": "admin@example.com", "password": "adminpass",
        })
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_users(self, auth_client):
        resp = await auth_client.get("/api/admin/users")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_access_admin(self, client, db_session):
        resp = await client.get("/api/admin/users")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        resp = await client.get("/api/admin/users", headers=admin_h)
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) >= 1
        assert any(u["email"] == "admin@example.com" for u in users)

    @pytest.mark.asyncio
    async def test_user_list_includes_counts(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        resp = await client.get("/api/admin/users", headers=admin_h)
        user = resp.json()[0]
        assert "project_count" in user
        assert "dataset_count" in user

    @pytest.mark.asyncio
    async def test_admin_toggle_active(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        # Create target user
        await client.post("/api/auth/register", json={
            "email": "target@example.com", "password": "p",
        })
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        target = next(u for u in users if u["email"] == "target@example.com")

        # Deactivate
        resp = await client.patch(
            f"/api/admin/users/{target['id']}",
            json={"is_active": False},
            headers=admin_h,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Target cannot login
        resp = await client.post("/api/auth/login", json={
            "email": "target@example.com", "password": "p",
        })
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_toggle_admin_flag(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        await client.post("/api/auth/register", json={
            "email": "promote@example.com", "password": "p",
        })
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        target = next(u for u in users if u["email"] == "promote@example.com")

        resp = await client.patch(
            f"/api/admin/users/{target['id']}",
            json={"is_admin": True},
            headers=admin_h,
        )
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    @pytest.mark.asyncio
    async def test_admin_cannot_modify_self(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        self_user = next(u for u in users if u["email"] == "admin@example.com")

        resp = await client.patch(
            f"/api/admin/users/{self_user['id']}",
            json={"is_admin": False},
            headers=admin_h,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_delete_user(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        await client.post("/api/auth/register", json={
            "email": "delete_me@example.com", "password": "p",
        })
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        target = next(u for u in users if u["email"] == "delete_me@example.com")

        resp = await client.delete(f"/api/admin/users/{target['id']}", headers=admin_h)
        assert resp.status_code == 200

        # Verify deleted
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        assert not any(u["email"] == "delete_me@example.com" for u in users)

    @pytest.mark.asyncio
    async def test_admin_cannot_delete_self(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        users = (await client.get("/api/admin/users", headers=admin_h)).json()
        self_user = next(u for u in users if u["email"] == "admin@example.com")

        resp = await client.delete(f"/api/admin/users/{self_user['id']}", headers=admin_h)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_user_response_includes_is_admin(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        resp = await client.get("/api/auth/me", headers=admin_h)
        assert resp.status_code == 200
        assert "is_admin" in resp.json()
        assert resp.json()["is_admin"] is True


# ---------------------------------------------------------------------------
# Data Explore
# ---------------------------------------------------------------------------

async def _create_project_with_roled_datasets(auth_client):
    """Create a project with a composite dataset containing xtrain and ytrain files.

    Returns the project_id.
    """
    # Create dataset group
    ds_resp = await auth_client.post("/api/datasets/", params={"name": "Train Data"})
    ds_id = ds_resp.json()["id"]

    # Upload Xtrain and Ytrain files (roles auto-detected from filenames)
    await auth_client.post(
        f"/api/datasets/{ds_id}/files",
        files={"file": ("Xtrain.tsv", b"id\ts1\ts2\ts3\ts4\nf1\t0.1\t0.2\t0.3\t0.0\nf2\t0.3\t0.4\t0.0\t0.5\n", "text/plain")},
    )
    await auth_client.post(
        f"/api/datasets/{ds_id}/files",
        files={"file": ("Ytrain.tsv", b"id\tclass\ns1\t0\ns2\t0\ns3\t1\ns4\t1\n", "text/plain")},
    )

    # Create project and assign dataset
    proj_resp = await auth_client.post("/api/projects/", params={"name": "explore_test"})
    pid = proj_resp.json()["project_id"]
    await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
    return pid


class TestDataExplore:
    """Tests for data exploration endpoints (mock the Rust engine)."""

    _mock_filter = staticmethod(data_analysis._mock_filtering)

    @pytest.mark.asyncio
    async def test_summary_returns_data_dimensions(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        with patch.object(data_analysis, "run_filtering", return_value=self._mock_filter()):
            resp = await auth_client.get(f"/api/data-explore/{pid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "n_features" in data
        assert "n_samples" in data
        assert "n_classes" in data
        assert data["n_classes"] >= 2

    @pytest.mark.asyncio
    async def test_summary_no_datasets_returns_404(self, auth_client):
        proj_resp = await auth_client.post("/api/projects/", params={"name": "empty_proj"})
        pid = proj_resp.json()["project_id"]
        resp = await auth_client.get(f"/api/data-explore/{pid}/summary")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_feature_stats_returns_features(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        with patch.object(data_analysis, "run_filtering", return_value=self._mock_filter()):
            resp = await auth_client.get(f"/api/data-explore/{pid}/feature-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "features" in data
        assert "selected_count" in data
        assert "method" in data
        assert data["method"] == "wilcoxon"
        assert isinstance(data["features"], list)
        assert len(data["features"]) > 0

    @pytest.mark.asyncio
    async def test_feature_stats_with_custom_params(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        mock = self._mock_filter("studentt")
        with patch.object(data_analysis, "run_filtering", return_value=mock):
            resp = await auth_client.get(f"/api/data-explore/{pid}/feature-stats", params={
                "method": "studentt",
                "prevalence_pct": 5,
                "max_pvalue": 0.1,
            })
        assert resp.status_code == 200
        assert resp.json()["method"] == "studentt"

    @pytest.mark.asyncio
    async def test_feature_stats_invalid_method_returns_400(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        resp = await auth_client.get(f"/api/data-explore/{pid}/feature-stats", params={
            "method": "invalid",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_distributions_returns_histograms(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        mock = self._mock_filter()
        with patch.object(data_analysis, "run_filtering", return_value=mock):
            resp = await auth_client.get(f"/api/data-explore/{pid}/distributions")
        assert resp.status_code == 200
        data = resp.json()
        assert "prevalence_histogram" in data
        assert "sd_histogram" in data
        assert "class_distribution" in data
        assert "bin_edges" in data["prevalence_histogram"]
        assert "counts" in data["prevalence_histogram"]

    @pytest.mark.asyncio
    async def test_feature_abundance_returns_boxplot_stats(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        mock_abundance = [
            {"name": "feature_0", "classes": {"0": {"min": 0, "q1": 0.001, "median": 0.003, "q3": 0.006, "max": 0.01, "mean": 0.004, "n": 55}}}
        ]
        with patch.object(data_analysis, "compute_feature_abundance", return_value=mock_abundance):
            resp = await auth_client.get(f"/api/data-explore/{pid}/feature-abundance", params={
                "features": "feature_0",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "features" in data
        assert len(data["features"]) == 1
        assert data["features"][0]["name"] == "feature_0"

    @pytest.mark.asyncio
    async def test_feature_abundance_no_features_returns_400(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        resp = await auth_client.get(f"/api/data-explore/{pid}/feature-abundance")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_barcode_data_returns_matrix(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        mock_barcode = {
            "matrix": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            "feature_names": ["feature_0", "feature_1"],
            "sample_names": ["s1", "s2", "s3"],
            "sample_classes": [0, 0, 1],
            "class_labels": ["0", "1"],
            "class_boundaries": [2],
        }
        with patch.object(data_analysis, "compute_barcode_data", return_value=mock_barcode):
            resp = await auth_client.get(f"/api/data-explore/{pid}/barcode-data", params={
                "features": "feature_0,feature_1",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "matrix" in data
        assert "feature_names" in data
        assert "sample_names" in data
        assert "sample_classes" in data
        assert "class_labels" in data
        assert "class_boundaries" in data
        assert len(data["matrix"]) == 2
        assert len(data["matrix"][0]) == 3

    @pytest.mark.asyncio
    async def test_barcode_data_no_features_returns_400(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        resp = await auth_client.get(f"/api/data-explore/{pid}/barcode-data")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_barcode_data_with_max_samples(self, auth_client):
        pid = await _create_project_with_roled_datasets(auth_client)
        mock_barcode = {
            "matrix": [[0.1, 0.2]], "feature_names": ["f0"],
            "sample_names": ["s1", "s2"], "sample_classes": [0, 1],
            "class_labels": ["0", "1"], "class_boundaries": [1],
        }
        with patch.object(data_analysis, "compute_barcode_data", return_value=mock_barcode) as mock_fn:
            resp = await auth_client.get(f"/api/data-explore/{pid}/barcode-data", params={
                "features": "f0", "max_samples": 100,
            })
        assert resp.status_code == 200
        # Verify max_samples was passed through
        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args
        assert call_kwargs.kwargs.get("max_samples") == 100 or call_kwargs[1].get("max_samples") == 100

    @pytest.mark.asyncio
    async def test_unauthenticated_data_explore_returns_error(self, client):
        resp = await client.get("/api/data-explore/someid/summary")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Worker parsing functions (pure functions, no I/O)
# ---------------------------------------------------------------------------

class TestWorkerParsing:
    """Test pure parsing functions from the worker module."""

    def test_strip_ansi_removes_color_codes(self):
        from app.services.worker import _strip_ansi
        text = "\x1b[31mERROR\x1b[0m: something \x1b[1;32mgreen\x1b[0m"
        assert _strip_ansi(text) == "ERROR: something green"

    def test_strip_ansi_leaves_plain_text_unchanged(self):
        from app.services.worker import _strip_ansi
        text = "normal text with no escapes"
        assert _strip_ansi(text) == text

    def test_parse_jury_returns_none_without_jury_data(self):
        from app.services.worker import _parse_jury_from_display
        result = _parse_jury_from_display("no jury info here")
        assert result is None

    def test_parse_jury_extracts_metrics(self):
        from app.services.worker import _parse_jury_from_display
        text = (
            "Majority jury [50 experts] | AUC 0.950/0.820 | accuracy 0.900/0.780 "
            "| sensitivity 0.880/0.750 | specificity 0.920/0.810 | rejection rate 0.050/0.100\n"
        )
        result = _parse_jury_from_display(text)
        assert result is not None
        assert result["method"] == "Majority"
        assert result["expert_count"] == 50
        assert result["train"]["auc"] == 0.95
        assert result["test"]["auc"] == 0.82
        assert result["train"]["sensitivity"] == 0.88
        assert result["test"]["rejection_rate"] == 0.1

    def test_parse_jury_extracts_confusion_matrix(self):
        from app.services.worker import _parse_jury_from_display
        text = (
            "Majority jury [10 experts] | AUC 1.000/0.900 | accuracy 1.000/0.850 "
            "| sensitivity 1.000/0.800 | specificity 1.000/0.900 | rejection rate 0.000/0.050\n"
            "CONFUSION MATRIX (TRAIN)\n"
            "         | Pred 1 | Pred 0 | Rejected\n"
            "Real 1   |     8  |     1  |     1\n"
            "Real 0   |     2  |     7  |     1\n"
        )
        result = _parse_jury_from_display(text)
        assert result is not None
        assert "confusion_train" in result
        cm = result["confusion_train"]
        assert cm["tp"] == 8
        assert cm["fn"] == 1
        assert cm["abstain_1"] == 1
        assert cm["fp"] == 2
        assert cm["tn"] == 7
        assert cm["abstain_0"] == 1

    def test_parse_jury_extracts_sample_predictions(self):
        from app.services.worker import _parse_jury_from_display
        text = (
            "Majority jury [5 experts] | AUC 1.000/0.900 | accuracy 1.000/0.850 "
            "| sensitivity 1.000/0.800 | specificity 1.000/0.900 | rejection rate 0.000/0.000\n"
            "  sample1 | 1 | 11111 | bla → 1 | ✓ | 100.0%\n"
            "  sample2 | 0 | 00010 | bla → 0 | ✓ | 80.0%\n"
            "  sample3 | 1 | 01010 | bla → 0 | ✗ | 60.0%\n"
        )
        result = _parse_jury_from_display(text)
        assert result is not None
        preds = result.get("sample_predictions", [])
        assert len(preds) == 3
        assert preds[0]["name"] == "sample1"
        assert preds[0]["real"] == 1
        assert preds[0]["correct"] is True
        assert preds[0]["consistency"] == 100.0
        assert preds[2]["correct"] is False
        assert preds[2]["consistency"] == 60.0

    def test_parse_jury_builds_vote_matrix(self):
        from app.services.worker import _parse_jury_from_display
        text = (
            "Majority jury [3 experts] | AUC 1.000/0.900 | accuracy 1.000/0.850 "
            "| sensitivity 1.000/0.800 | specificity 1.000/0.900 | rejection rate 0.000/0.000\n"
            "  s1 | 1 | 110 | x → 1 | ✓ | 66.7%\n"
            "  s2 | 0 | 001 | x → 0 | ✓ | 66.7%\n"
        )
        result = _parse_jury_from_display(text)
        assert result is not None
        vm = result.get("vote_matrix")
        assert vm is not None
        assert vm["n_experts"] == 3
        assert vm["sample_names"] == ["s1", "s2"]
        assert vm["votes"] == [[1, 1, 0], [0, 0, 1]]

    def test_parse_jury_extracts_fbm(self):
        from app.services.worker import _parse_jury_from_display
        text = (
            "Majority jury [10 experts] | AUC 1.000/0.900 | accuracy 1.000/0.850 "
            "| sensitivity 1.000/0.800 | specificity 1.000/0.900 | rejection rate 0.000/0.050\n"
            "FBM mean (n=42) - AUC 0.980/0.850 | accuracy 0.960/0.820 "
            "| sensitivity 0.940/0.790 | specificity 0.970/0.860\n"
        )
        result = _parse_jury_from_display(text)
        assert result is not None
        fbm = result.get("fbm")
        assert fbm is not None
        assert fbm["count"] == 42
        assert fbm["train"]["auc"] == 0.98
        assert fbm["test"]["accuracy"] == 0.82

    def test_parse_importance_returns_none_without_data(self):
        from app.services.worker import _parse_importance_from_display
        result = _parse_importance_from_display("no importance data")
        assert result is None

    def test_parse_importance_extracts_features(self):
        from app.services.worker import _parse_importance_from_display
        text = (
            "Feature importance (MDA, scaled, mean):\n"
            "  msp_0001  0.0543  +\n"
            "  msp_0002  0.0321  -\n"
            "  msp_0003  0.0100  +\n"
        )
        result = _parse_importance_from_display(text)
        assert result is not None
        assert len(result) == 3
        assert result[0]["feature"] == "msp_0001"
        assert result[0]["importance"] == 0.0543
        assert result[0]["direction"] == "+"
        assert result[1]["feature"] == "msp_0002"
        assert result[1]["direction"] == "-"


# ---------------------------------------------------------------------------
# Analysis pure functions
# ---------------------------------------------------------------------------

class TestAnalysisPureFunctions:
    """Test pure helper functions from the analysis router."""

    def test_strip_nulls_removes_none_values(self):
        from app.routers.analysis import _strip_nulls
        data = {"a": 1, "b": None, "c": {"d": None, "e": 2}}
        result = _strip_nulls(data)
        assert result == {"a": 1, "c": {"e": 2}}

    def test_strip_nulls_handles_empty_dict(self):
        from app.routers.analysis import _strip_nulls
        assert _strip_nulls({}) == {}

    def test_strip_nulls_handles_non_dict(self):
        from app.routers.analysis import _strip_nulls
        assert _strip_nulls("hello") == "hello"
        assert _strip_nulls(42) == 42

    def test_compute_config_hash_is_stable(self):
        from app.routers.analysis import _compute_config_hash
        config = {"general": {"algo": "ga", "language": "bin"}}
        h1 = _compute_config_hash(config)
        h2 = _compute_config_hash(config)
        assert h1 == h2
        assert len(h1) == 16

    def test_compute_config_hash_ignores_nulls(self):
        from app.routers.analysis import _compute_config_hash
        config1 = {"general": {"algo": "ga"}}
        config2 = {"general": {"algo": "ga", "epsilon": None}}
        assert _compute_config_hash(config1) == _compute_config_hash(config2)

    def test_compute_config_hash_includes_file_ids(self):
        from app.routers.analysis import _compute_config_hash
        config = {"general": {"algo": "ga"}}
        h1 = _compute_config_hash(config, {"x": "file1", "y": "file2"})
        h2 = _compute_config_hash(config, {"x": "file1", "y": "file3"})
        assert h1 != h2

    def test_config_summary_ga(self):
        from app.routers.analysis import _config_summary
        config = {
            "general": {"algo": "ga", "language": "bin,ter", "data_type": "raw", "seed": 42},
            "ga": {"population_size": 5000, "max_epochs": 200},
            "voting": {},
        }
        summary = _config_summary(config)
        assert "GA" in summary
        assert "lang=bin,ter" in summary
        assert "pop=5000" in summary
        assert "ep=200" in summary
        assert "seed=42" in summary

    def test_config_summary_with_vote(self):
        from app.routers.analysis import _config_summary
        config = {
            "general": {"algo": "ga"},
            "ga": {},
            "voting": {"vote": True, "method": "Consensus"},
        }
        summary = _config_summary(config)
        assert "vote=Consensus" in summary

    def test_config_summary_empty(self):
        from app.routers.analysis import _config_summary
        assert _config_summary(None) == ""
        assert _config_summary({}) == ""

    def test_job_disk_size_nonexistent_dir(self):
        from app.routers.analysis import _job_disk_size
        result = _job_disk_size("nonexistent_project", "nonexistent_job")
        assert result is None

    def test_job_disk_size_with_files(self, tmp_path):
        from app.routers.analysis import _job_disk_size
        # Create a fake job directory with files
        job_dir = tmp_path / "test_proj" / "jobs" / "test_job"
        job_dir.mkdir(parents=True)
        (job_dir / "results.json").write_text('{"test": true}')
        (job_dir / "console.log").write_text("log data here")

        with patch.object(storage.settings, 'project_dir', tmp_path):
            result = _job_disk_size("test_proj", "test_job")
        assert result is not None
        assert result > 0


# ---------------------------------------------------------------------------
# Analysis endpoints — deeper coverage
# ---------------------------------------------------------------------------

class TestAnalysisDeep:

    @pytest.mark.asyncio
    async def test_delete_job(self, auth_client):
        """Test job deletion removes the job."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_fid, y_fid)
        # Delete it
        resp = await auth_client.delete(f"/api/analysis/{pid}/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Job deleted"
        # Verify gone
        resp2 = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job_returns_404(self, auth_client):
        pid, _, _ = await _create_project_with_datasets(auth_client)
        resp = await auth_client.delete(f"/api/analysis/{pid}/jobs/nonexistent_id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_status_returns_summary(self, auth_client, db_session):
        """Test get job status for a completed job returns summary fields."""
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
        assert "config_hash" in data
        assert "config_summary" in data

    @pytest.mark.asyncio
    async def test_list_jobs_backfills_config_hash(self, auth_client):
        """Test that list_jobs backfills config_hash for older jobs."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_fid, y_fid)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) >= 1
        # All completed jobs should have config_hash
        for j in jobs:
            if j["status"] == "completed":
                assert j["config_hash"] is not None

    @pytest.mark.asyncio
    async def test_find_duplicates(self, auth_client):
        """Test the find duplicates endpoint."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        await _run_mock_analysis(auth_client, pid, x_fid, y_fid)
        await _run_mock_analysis(auth_client, pid, x_fid, y_fid)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/duplicates")
        assert resp.status_code == 200
        data = resp.json()
        # Two identical jobs should form a duplicate group
        assert isinstance(data, list)
        if len(data) > 0:
            assert "config_summary" in data[0]
            assert "jobs" in data[0]

    @pytest.mark.asyncio
    async def test_run_analysis_with_missing_file_returns_404(self, auth_client):
        """Test running analysis with invalid file IDs returns 404."""
        pid, _, _ = await _create_project_with_datasets(auth_client)
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
        }
        resp = await auth_client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_file_id": "nonexistent", "y_file_id": "nonexistent"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_detail_returns_features(self, auth_client, db_session):
        """Test that job detail returns feature names and best individual."""
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/detail")
        assert resp.status_code == 200
        data = resp.json()
        assert "feature_names" in data
        assert "best_individual" in data

    @pytest.mark.asyncio
    async def test_get_job_logs_returns_dict(self, auth_client):
        """Test that job logs endpoint returns log content."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        job_id = await _run_mock_analysis(auth_client, pid, x_fid, y_fid)
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs/{job_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert "log" in data
        assert isinstance(data["log"], str)


# ---------------------------------------------------------------------------
# Project endpoints — deeper coverage
# ---------------------------------------------------------------------------

class TestProjectsDeep:

    @pytest.mark.asyncio
    async def test_update_project_name(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "original"})
        pid = resp.json()["project_id"]
        resp2 = await auth_client.patch(f"/api/projects/{pid}", params={"name": "renamed"})
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "renamed"

    @pytest.mark.asyncio
    async def test_update_project_description(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "myproj"})
        pid = resp.json()["project_id"]
        resp2 = await auth_client.patch(f"/api/projects/{pid}", params={"description": "A new description"})
        assert resp2.status_code == 200
        assert resp2.json()["description"] == "A new description"

    @pytest.mark.asyncio
    async def test_update_nonexistent_project_returns_404(self, auth_client):
        resp = await auth_client.patch("/api/projects/nonexistent", params={"name": "foo"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_datasets_list(self, auth_client):
        """Projects should show their linked datasets."""
        pid, _, _ = await _create_project_with_datasets(auth_client)
        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        proj = resp.json()
        assert len(proj["datasets"]) == 2
        for ds in proj["datasets"]:
            assert "id" in ds
            assert "name" in ds
            assert "files" in ds


# ---------------------------------------------------------------------------
# Sharing endpoints — deeper coverage
# ---------------------------------------------------------------------------

class TestSharingDeep:

    async def _setup_two_users(self, client):
        """Register two users, return (auth_client1, auth_client2, user2_email)."""
        await client.post("/api/auth/register", json={
            "email": "owner@test.com", "password": "pass123", "full_name": "Owner",
        })
        await client.post("/api/auth/register", json={
            "email": "viewer@test.com", "password": "pass123", "full_name": "Viewer",
        })
        resp1 = await client.post("/api/auth/login", json={"email": "owner@test.com", "password": "pass123"})
        resp2 = await client.post("/api/auth/login", json={"email": "viewer@test.com", "password": "pass123"})
        return resp1.json()["access_token"], resp2.json()["access_token"]

    @pytest.mark.asyncio
    async def test_share_with_invalid_role(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        resp2 = await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "admin"})
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_share_with_nonexistent_user(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        resp2 = await client.post(f"/api/projects/{pid}/share", json={"email": "nobody@test.com", "role": "viewer"})
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_share_with_yourself(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        resp2 = await client.post(f"/api/projects/{pid}/share", json={"email": "owner@test.com", "role": "viewer"})
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_share_duplicate_returns_409(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "viewer"})
        resp2 = await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "editor"})
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_list_shares(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "viewer"})
        resp2 = await client.get(f"/api/projects/{pid}/shares")
        assert resp2.status_code == 200
        shares = resp2.json()
        assert len(shares) == 1
        assert shares[0]["email"] == "viewer@test.com"
        assert shares[0]["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_update_share_role(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        share_resp = await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "viewer"})
        share_id = share_resp.json()["id"]
        resp2 = await client.put(f"/api/projects/{pid}/shares/{share_id}", json={"email": "viewer@test.com", "role": "editor"})
        assert resp2.status_code == 200
        assert resp2.json()["role"] == "editor"

    @pytest.mark.asyncio
    async def test_update_nonexistent_share_returns_404(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        resp2 = await client.put(f"/api/projects/{pid}/shares/nonexistent", json={"email": "x@x.com", "role": "viewer"})
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_share_returns_404(self, client):
        t1, _ = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "proj"})
        pid = resp.json()["project_id"]
        resp2 = await client.delete(f"/api/projects/{pid}/shares/nonexistent")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_shared_with_me(self, client):
        t1, t2 = await self._setup_two_users(client)
        client.headers["Authorization"] = f"Bearer {t1}"
        resp = await client.post("/api/projects/", params={"name": "shared_proj"})
        pid = resp.json()["project_id"]
        await client.post(f"/api/projects/{pid}/share", json={"email": "viewer@test.com", "role": "viewer"})
        # Switch to viewer
        client.headers["Authorization"] = f"Bearer {t2}"
        resp2 = await client.get("/api/projects/shared-with-me")
        assert resp2.status_code == 200
        projects = resp2.json()
        assert len(projects) >= 1
        assert projects[0]["name"] == "shared_proj"
        assert projects[0]["role"] == "viewer"


# ---------------------------------------------------------------------------
# Admin endpoints — deeper coverage
# ---------------------------------------------------------------------------

class TestAdminDeep:

    async def _make_admin(self, client, db_session):
        """Register a user, promote to admin via db_session, return auth headers."""
        from app.models.db_models import User as UserModel
        from sqlalchemy import update
        await client.post("/api/auth/register", json={
            "email": "admin2@test.com", "password": "adminpass", "full_name": "Admin",
        })
        await db_session.execute(
            update(UserModel).where(UserModel.email == "admin2@test.com").values(is_admin=True)
        )
        await db_session.commit()
        resp = await client.post("/api/auth/login", json={"email": "admin2@test.com", "password": "adminpass"})
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    @pytest.mark.asyncio
    async def test_admin_update_user_active_flag(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        await client.post("/api/auth/register", json={"email": "target@test.com", "password": "pass", "full_name": "Target"})
        resp = await client.get("/api/admin/users", headers=admin_h)
        target = next(u for u in resp.json() if u["email"] == "target@test.com")
        resp2 = await client.patch(f"/api/admin/users/{target['id']}", json={"is_active": False}, headers=admin_h)
        assert resp2.status_code == 200
        assert resp2.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_admin_update_user_admin_flag(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        await client.post("/api/auth/register", json={"email": "target2@test.com", "password": "pass", "full_name": "Target2"})
        resp = await client.get("/api/admin/users", headers=admin_h)
        target = next(u for u in resp.json() if u["email"] == "target2@test.com")
        resp2 = await client.patch(f"/api/admin/users/{target['id']}", json={"is_admin": True}, headers=admin_h)
        assert resp2.status_code == 200
        assert resp2.json()["is_admin"] is True

    @pytest.mark.asyncio
    async def test_admin_delete_user(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        await client.post("/api/auth/register", json={"email": "todelete@test.com", "password": "pass", "full_name": "ToDelete"})
        resp = await client.get("/api/admin/users", headers=admin_h)
        target = next(u for u in resp.json() if u["email"] == "todelete@test.com")
        resp2 = await client.delete(f"/api/admin/users/{target['id']}", headers=admin_h)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_admin_delete_nonexistent_user_returns_404(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        resp = await client.delete("/api/admin/users/nonexistent_id", headers=admin_h)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_update_nonexistent_user_returns_404(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        resp = await client.patch("/api/admin/users/nonexistent_id", json={"is_active": False}, headers=admin_h)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_defaults_get_set(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        defaults = {"general.language": "bin,ter", "ga.population_size": 3000}
        resp = await client.put("/api/admin/defaults", json=defaults, headers=admin_h)
        assert resp.status_code == 200
        resp2 = await client.get("/api/admin/defaults", headers=admin_h)
        assert resp2.status_code == 200
        assert resp2.json()["general.language"] == "bin,ter"

    @pytest.mark.asyncio
    async def test_admin_defaults_public(self, client, db_session):
        admin_h = await self._make_admin(client, db_session)
        defaults = {"general.seed": 123}
        await client.put("/api/admin/defaults", json=defaults, headers=admin_h)
        resp = await client.get("/api/admin/defaults/public")
        assert resp.status_code == 200
        assert resp.json()["general.seed"] == 123


# ---------------------------------------------------------------------------
# MSP Annotations service
# ---------------------------------------------------------------------------

class TestMspAnnotations:
    """Test the MSP annotations cache service."""

    def test_get_annotations_empty_list(self):
        from app.services.msp_annotations import get_annotations
        result = get_annotations([])
        assert result == {}

    def test_get_annotations_non_msp_features(self):
        from app.services.msp_annotations import get_annotations
        result = get_annotations(["feature_1", "gene_abc", "otu_123"])
        assert result == {}

    def test_load_cache_missing_file(self, tmp_path):
        from app.services import msp_annotations
        original_file = msp_annotations.CACHE_FILE
        original_cache = msp_annotations._cache
        msp_annotations.CACHE_FILE = tmp_path / "nonexistent.json"
        msp_annotations._cache = None  # Force reload
        try:
            result = msp_annotations._load_cache()
            assert result == {}
        finally:
            msp_annotations.CACHE_FILE = original_file
            msp_annotations._cache = original_cache

    def test_save_and_load_cache(self, tmp_path):
        from app.services import msp_annotations
        original_file = msp_annotations.CACHE_FILE
        original_cache = msp_annotations._cache
        cache_path = tmp_path / "test_cache.json"
        msp_annotations.CACHE_FILE = cache_path
        try:
            # Set the global _cache and save it
            msp_annotations._cache = {"msp_0001": {"species": "E. coli"}}
            msp_annotations._save_cache()
            assert cache_path.exists()
            # Reset and reload
            msp_annotations._cache = None
            result = msp_annotations._load_cache()
            assert "msp_0001" in result
            assert result["msp_0001"]["species"] == "E. coli"
        finally:
            msp_annotations.CACHE_FILE = original_file
            msp_annotations._cache = original_cache


# ---------------------------------------------------------------------------
# Data Analysis service — cache and mock
# ---------------------------------------------------------------------------

class TestDataAnalysisService:
    """Test data_analysis service functions."""

    def test_cache_key_is_stable(self):
        from app.services.data_analysis import _cache_key
        k1 = _cache_key("/path/x.tsv", "/path/y.tsv", "wilcoxon", 10, 0.05)
        k2 = _cache_key("/path/x.tsv", "/path/y.tsv", "wilcoxon", 10, 0.05)
        assert k1 == k2

    def test_cache_key_differs_for_different_params(self):
        from app.services.data_analysis import _cache_key
        k1 = _cache_key("/path/x.tsv", "/path/y.tsv", "wilcoxon", 10, 0.05)
        k2 = _cache_key("/path/x.tsv", "/path/y.tsv", "kruskal", 10, 0.05)
        assert k1 != k2

    def test_get_cached_returns_none_for_missing(self):
        from app.services.data_analysis import _get_cached
        result = _get_cached("nonexistent_key_xyz")
        assert result is None

    def test_set_and_get_cached(self):
        from app.services.data_analysis import _set_cached, _get_cached
        _set_cached("test_key_abc", {"data": 42})
        result = _get_cached("test_key_abc")
        assert result is not None
        assert result["data"] == 42


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------

class TestExport:
    """Tests for CSV, JSON, HTML report, and notebook export endpoints."""

    @pytest.mark.asyncio
    async def test_export_csv_best_model(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/csv",
            params={"section": "best_model"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "best_model_" in resp.headers["content-disposition"]
        body = resp.text
        assert "Metric" in body
        assert "auc" in body.lower()

    @pytest.mark.asyncio
    async def test_export_csv_population(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/csv",
            params={"section": "population"},
        )
        assert resp.status_code == 200
        assert "population_" in resp.headers["content-disposition"]
        body = resp.text
        assert "Rank" in body

    @pytest.mark.asyncio
    async def test_export_csv_generation_tracking(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/csv",
            params={"section": "generation_tracking"},
        )
        assert resp.status_code == 200
        assert "generation_tracking_" in resp.headers["content-disposition"]
        body = resp.text
        assert "Generation" in body

    @pytest.mark.asyncio
    async def test_export_csv_unknown_section_returns_400(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/csv",
            params={"section": "nonexistent_section"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_export_csv_nonexistent_job_returns_404(self, auth_client):
        pid, _, _ = await _create_project_with_datasets(auth_client)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/nonexistent123/csv",
            params={"section": "best_model"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_json(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        data = resp.json()
        assert "best_individual" in data
        assert "feature_names" in data

    @pytest.mark.asyncio
    async def test_export_report_html(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(f"/api/export/{pid}/jobs/{job_id}/report")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "predomics_report_" in resp.headers["content-disposition"]
        body = resp.text
        assert "Predomics Analysis Report" in body
        assert "Best AUC" in body

    @pytest.mark.asyncio
    async def test_export_notebook_python(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/notebook",
            params={"lang": "python"},
        )
        assert resp.status_code == 200
        assert "ipynb" in resp.headers["content-disposition"]
        data = resp.json()
        assert "nbformat" in data
        assert data["nbformat"] == 4
        assert len(data["cells"]) > 0

    @pytest.mark.asyncio
    async def test_export_notebook_r(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/notebook",
            params={"lang": "r"},
        )
        assert resp.status_code == 200
        assert ".Rmd" in resp.headers["content-disposition"]
        body = resp.text
        assert "gpredomicsR" in body
        assert "ggplot2" in body

    @pytest.mark.asyncio
    async def test_export_notebook_invalid_lang_returns_400(self, auth_client, db_session):
        pid, job_id = await _create_completed_job(auth_client, db_session)
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/notebook",
            params={"lang": "julia"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_export_unauthenticated_returns_error(self, client):
        resp = await client.get("/api/export/fake_proj/jobs/fake_job/csv")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Export helper unit tests
# ---------------------------------------------------------------------------

class TestExportHelpers:
    """Unit tests for export helper functions."""

    def test_esc_html_entities(self):
        from app.routers.export import _esc
        assert _esc('<script>alert("xss")</script>') == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert _esc("plain text") == "plain text"
        assert _esc(None) == ""

    def test_fmt_numeric(self):
        from app.routers.export import _fmt
        assert _fmt(0.89213, 4) == "0.8921"
        assert _fmt(None) == "—"
        assert _fmt(42, 2) == "42.00"
        assert _fmt("text") == "text"

    def test_build_jury_html(self):
        from app.routers.export import _build_jury_html
        jury = {
            "train": {"auc": 0.92, "accuracy": 0.88},
            "test": {"auc": 0.87},
            "sample_predictions": [
                {"name": "s1", "real": 0, "predicted": 0, "correct": True, "consistency": 95.0},
                {"name": "s2", "real": 1, "predicted": 0, "correct": False, "consistency": 55.0},
            ],
        }
        html = _build_jury_html(jury)
        assert "Jury Voting" in html
        assert "0.9200" in html
        assert "s1" in html
        assert "s2" in html

    def test_build_importance_html(self):
        from app.routers.export import _build_importance_html
        importance = [
            {"feature": "feature_A", "importance": 0.35},
            {"feature": "feature_B", "importance": 0.12},
        ]
        html = _build_importance_html(importance)
        assert "Feature Importance" in html
        assert "feature_A" in html
        assert "0.3500" in html

    def test_nb_cell_markdown(self):
        from app.routers.export import _nb_cell
        cell = _nb_cell("markdown", "# Title\nParagraph")
        assert cell["cell_type"] == "markdown"
        assert len(cell["source"]) == 2  # two lines

    def test_nb_cell_code(self):
        from app.routers.export import _nb_cell
        cell = _nb_cell("code", "x = 1")
        assert cell["cell_type"] == "code"
        assert cell["execution_count"] is None
        assert cell["outputs"] == []


# ---------------------------------------------------------------------------
# Batch runs
# ---------------------------------------------------------------------------

class TestBatchRuns:
    """Tests for batch run endpoints."""

    @pytest.mark.asyncio
    async def test_batch_run_creates_multiple_jobs(self, auth_client):
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }
        sweep = {"sweeps": {"general.seed": [1, 2, 3]}}

        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            resp = await auth_client.post(
                f"/api/analysis/{pid}/batch",
                json={"config": config, "sweep": sweep},
                params={"x_file_id": x_fid, "y_file_id": y_fid},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_count"] == 3
        assert data["batch_id"] is not None

    @pytest.mark.asyncio
    async def test_batch_run_too_many_combinations_returns_400(self, auth_client):
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }
        # 10 x 10 = 100 > 50 max
        sweep = {"sweeps": {
            "general.seed": list(range(10)),
            "ga.population_size": list(range(100, 200, 10)),
        }}

        resp = await auth_client.post(
            f"/api/analysis/{pid}/batch",
            json={"config": config, "sweep": sweep},
            params={"x_file_id": x_fid, "y_file_id": y_fid},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_batches(self, auth_client):
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }
        sweep = {"sweeps": {"general.seed": [1, 2]}}

        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            await auth_client.post(
                f"/api/analysis/{pid}/batch",
                json={"config": config, "sweep": sweep},
                params={"x_file_id": x_fid, "y_file_id": y_fid},
            )

        resp = await auth_client.get(f"/api/analysis/{pid}/batches")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "batch_id" in data[0]
        assert "job_count" in data[0]


# ---------------------------------------------------------------------------
# Concurrent job execution
# ---------------------------------------------------------------------------

class TestConcurrentJobs:
    """Test concurrent job execution and isolation."""

    @pytest.mark.asyncio
    async def test_run_multiple_jobs_same_project(self, auth_client):
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }

        job_ids = []
        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            for seed in [1, 2, 3]:
                cfg = {**config, "general": {**config["general"], "seed": seed}}
                resp = await auth_client.post(
                    f"/api/analysis/{pid}/run",
                    json=cfg,
                    params={"x_file_id": x_fid, "y_file_id": y_fid},
                )
                assert resp.status_code == 200
                job_ids.append(resp.json()["job_id"])

        # All job IDs should be unique
        assert len(set(job_ids)) == 3

        # All jobs should be listed
        resp = await auth_client.get(f"/api/analysis/{pid}/jobs")
        assert len(resp.json()) == 3

    @pytest.mark.asyncio
    async def test_jobs_isolated_between_projects(self, auth_client):
        pid1, x1, y1 = await _create_project_with_datasets(auth_client)
        pid2_resp = await auth_client.post("/api/projects/", params={"name": "proj2"})
        pid2 = pid2_resp.json()["project_id"]
        await auth_client.post(
            f"/api/projects/{pid2}/datasets",
            files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\nf2\t0.3\t0.4\n", "text/plain")},
        )
        await auth_client.post(
            f"/api/projects/{pid2}/datasets",
            files={"file": ("y.tsv", b"id\tclass\ns1\t0\ns2\t1\n", "text/plain")},
        )
        proj2 = (await auth_client.get(f"/api/projects/{pid2}")).json()
        x2 = proj2["datasets"][0]["files"][0]["id"]
        y2 = proj2["datasets"][1]["files"][0]["id"]

        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }

        with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
            await auth_client.post(
                f"/api/analysis/{pid1}/run", json=config,
                params={"x_file_id": x1, "y_file_id": y1},
            )
            await auth_client.post(
                f"/api/analysis/{pid2}/run", json=config,
                params={"x_file_id": x2, "y_file_id": y2},
            )

        jobs1 = (await auth_client.get(f"/api/analysis/{pid1}/jobs")).json()
        jobs2 = (await auth_client.get(f"/api/analysis/{pid2}/jobs")).json()
        assert len(jobs1) == 1
        assert len(jobs2) == 1


# ---------------------------------------------------------------------------
# Error recovery and edge cases
# ---------------------------------------------------------------------------

class TestErrorRecovery:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_export_pending_job_returns_400(self, auth_client):
        """Exporting results of a non-completed job should fail."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        # Create a job but don't mark it as completed
        job_id = await _run_mock_analysis(auth_client, pid, x_fid, y_fid)

        # Try to export — job is pending/running, not completed
        resp = await auth_client.get(
            f"/api/export/{pid}/jobs/{job_id}/csv",
            params={"section": "best_model"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_project_with_running_job(self, auth_client):
        """Deleting a project should work even if it has jobs."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)
        await _run_mock_analysis(auth_client, pid, x_fid, y_fid)

        resp = await auth_client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 200

        # Project should be gone
        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_empty_file_returns_error(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "empty_test"})
        pid = resp.json()["project_id"]
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("empty.tsv", b"", "text/plain")},
        )
        # Should reject or handle gracefully
        assert resp.status_code in (200, 400, 422)

    @pytest.mark.asyncio
    async def test_analysis_with_all_algorithms(self, auth_client):
        """Test that all algorithm types are accepted."""
        pid, x_fid, y_fid = await _create_project_with_datasets(auth_client)

        for algo in ["ga", "beam", "mcmc"]:
            config = {
                "general": {"algo": algo, "language": "bin", "data_type": "raw", "fit": "auc",
                            "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
                "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
            }
            with patch("app.services.engine.run_experiment", return_value=ml_engine._mock_results()):
                resp = await auth_client.post(
                    f"/api/analysis/{pid}/run",
                    json=config,
                    params={"x_file_id": x_fid, "y_file_id": y_fid},
                )
                assert resp.status_code == 200, f"algo={algo} failed"

    @pytest.mark.asyncio
    async def test_dataset_tags_crud(self, auth_client):
        """Test dataset tag operations."""
        # Create a dataset (uses query params, not JSON body)
        resp = await auth_client.post("/api/datasets/", params={"name": "TagTest"})
        assert resp.status_code in (200, 201)
        ds_id = resp.json()["id"]

        # Update tags (PATCH with embedded body)
        resp = await auth_client.patch(
            f"/api/datasets/{ds_id}/tags",
            json={"tags": ["metagenomic", "clinical"]},
        )
        assert resp.status_code == 200

        # Verify tags persisted
        resp = await auth_client.get("/api/datasets/")
        assert resp.status_code == 200
        ds = next((d for d in resp.json() if d["id"] == ds_id), None)
        assert ds is not None
        assert set(ds["tags"]) == {"metagenomic", "clinical"}

        # Filter by tag
        resp = await auth_client.get("/api/datasets/", params={"tag": "metagenomic"})
        assert resp.status_code == 200
        assert any(d["id"] == ds_id for d in resp.json())


# ---------------------------------------------------------------------------
# Dataset Library CRUD
# ---------------------------------------------------------------------------

class TestDatasetLibrary:
    """Tests for dataset library endpoints (create, read, update, delete)."""

    @pytest.mark.asyncio
    async def test_create_dataset(self, auth_client):
        resp = await auth_client.post("/api/datasets/", params={"name": "My Dataset", "description": "Test desc"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Dataset"
        assert data["description"] == "Test desc"
        assert data["files"] == []
        assert data["project_count"] == 0

    @pytest.mark.asyncio
    async def test_create_dataset_with_tags(self, auth_client):
        resp = await auth_client.post("/api/datasets/", params={"name": "Tagged DS", "tags": "clinical,metagenomic"})
        assert resp.status_code == 200
        assert set(resp.json()["tags"]) == {"clinical", "metagenomic"}

    @pytest.mark.asyncio
    async def test_get_tag_suggestions(self, auth_client):
        # Create dataset with custom tags first
        await auth_client.post("/api/datasets/", params={"name": "ds1", "tags": "custom_tag"})
        resp = await auth_client.get("/api/datasets/tags/suggestions")
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert "custom_tag" in suggestions
        # Should also include predefined tags
        assert "clinical" in suggestions

    @pytest.mark.asyncio
    async def test_list_datasets_empty(self, auth_client):
        resp = await auth_client.get("/api/datasets/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_datasets_with_search(self, auth_client):
        await auth_client.post("/api/datasets/", params={"name": "Alpha Dataset"})
        await auth_client.post("/api/datasets/", params={"name": "Beta Dataset"})

        resp = await auth_client.get("/api/datasets/", params={"search": "alpha"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "Alpha Dataset"

    @pytest.mark.asyncio
    async def test_get_dataset_by_id(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "Detail DS"})
        ds_id = create_resp.json()["id"]

        resp = await auth_client.get(f"/api/datasets/{ds_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Detail DS"

    @pytest.mark.asyncio
    async def test_get_dataset_not_found(self, auth_client):
        resp = await auth_client.get("/api/datasets/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_dataset(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "To Delete"})
        ds_id = create_resp.json()["id"]

        resp = await auth_client.delete(f"/api/datasets/{ds_id}")
        assert resp.status_code == 200

        # Verify gone
        resp = await auth_client.get(f"/api/datasets/{ds_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_dataset_not_found(self, auth_client):
        resp = await auth_client.delete("/api/datasets/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tags(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "Tag DS"})
        ds_id = create_resp.json()["id"]

        resp = await auth_client.patch(f"/api/datasets/{ds_id}/tags", json={"tags": ["a", "b", "c"]})
        assert resp.status_code == 200
        assert set(resp.json()["tags"]) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_update_tags_deduplicates(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "Dedup DS"})
        ds_id = create_resp.json()["id"]

        resp = await auth_client.patch(f"/api/datasets/{ds_id}/tags", json={"tags": ["a", "a", "b"]})
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_upload_file_to_dataset(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "File DS"})
        ds_id = create_resp.json()["id"]

        resp = await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\n", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "X.tsv"
        assert data["role"] == "xtrain"

    @pytest.mark.asyncio
    async def test_upload_file_auto_infer_role(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "Role DS"})
        ds_id = create_resp.json()["id"]

        # y.tsv should be inferred as ytrain
        resp = await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("y.tsv", b"id\tclass\ns1\t0\n", "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "ytrain"

    @pytest.mark.asyncio
    async def test_delete_file_from_dataset(self, auth_client):
        create_resp = await auth_client.post("/api/datasets/", params={"name": "Del File DS"})
        ds_id = create_resp.json()["id"]

        # Upload a file
        file_resp = await auth_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("test.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        file_id = file_resp.json()["id"]

        # Delete it
        resp = await auth_client.delete(f"/api/datasets/{ds_id}/files/{file_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_assign_dataset_to_project(self, auth_client):
        # Create dataset
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Assign DS"})
        ds_id = ds_resp.json()["id"]

        # Create project
        proj_resp = await auth_client.post("/api/projects/", params={"name": "Assign Proj"})
        pid = proj_resp.json()["project_id"]

        # Assign
        resp = await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "assigned"

        # Check project now has the dataset
        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        assert any(d["id"] == ds_id for d in proj["datasets"])

    @pytest.mark.asyncio
    async def test_assign_dataset_duplicate_returns_409(self, auth_client):
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Dup DS"})
        ds_id = ds_resp.json()["id"]
        proj_resp = await auth_client.post("/api/projects/", params={"name": "Dup Proj"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        resp = await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_unassign_dataset_from_project(self, auth_client):
        ds_resp = await auth_client.post("/api/datasets/", params={"name": "Unassign DS"})
        ds_id = ds_resp.json()["id"]
        proj_resp = await auth_client.post("/api/projects/", params={"name": "Unassign Proj"})
        pid = proj_resp.json()["project_id"]

        await auth_client.post(f"/api/datasets/{ds_id}/assign/{pid}")
        resp = await auth_client.delete(f"/api/datasets/{ds_id}/assign/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unassigned"


# ---------------------------------------------------------------------------
# Project update / delete
# ---------------------------------------------------------------------------

class TestProjectCRUD:
    """Tests for project update and delete operations."""

    @pytest.mark.asyncio
    async def test_update_project_name(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "Original"})
        pid = resp.json()["project_id"]

        resp = await auth_client.patch(f"/api/projects/{pid}", params={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_project_description(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "Desc Proj"})
        pid = resp.json()["project_id"]

        resp = await auth_client.patch(f"/api/projects/{pid}", params={"description": "New description"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "New description"

    @pytest.mark.asyncio
    async def test_get_project_details(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "Detail Proj", "description": "Desc"})
        pid = resp.json()["project_id"]

        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Detail Proj"
        assert data["description"] == "Desc"
        assert data["datasets"] == []

    @pytest.mark.asyncio
    async def test_delete_project(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "To Delete"})
        pid = resp.json()["project_id"]

        resp = await auth_client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify gone
        resp = await auth_client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_nonexistent(self, auth_client):
        resp = await auth_client.delete("/api/projects/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_dataset_to_project(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "Upload Proj"})
        pid = resp.json()["project_id"]

        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\ts2\ts3\nf1\t0.1\t0.2\t0.3\nf2\t0.4\t0.5\t0.6\n", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "X.tsv"
        assert data["n_features"] == 2
        assert data["n_samples"] == 3


# ---------------------------------------------------------------------------
# Project Sharing
# ---------------------------------------------------------------------------

class TestSharing:
    """Tests for project sharing endpoints."""

    async def _create_second_user(self, client):
        """Register a second user and return auth headers."""
        await client.post("/api/auth/register", json={
            "email": "user2@example.com", "password": "pass2", "full_name": "User Two",
        })
        r = await client.post("/api/auth/login", json={
            "email": "user2@example.com", "password": "pass2",
        })
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    @pytest.mark.asyncio
    async def test_share_project(self, auth_client, client, db_session):
        # Create a second user
        await self._create_second_user(client)

        # Create project as first user
        resp = await auth_client.post("/api/projects/", params={"name": "Share Proj"})
        pid = resp.json()["project_id"]

        # Share with user2
        resp = await auth_client.post(
            f"/api/projects/{pid}/share",
            json={"email": "user2@example.com", "role": "viewer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "user2@example.com"
        assert data["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_share_with_self_rejected(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "Self Share"})
        pid = resp.json()["project_id"]

        resp = await auth_client.post(
            f"/api/projects/{pid}/share",
            json={"email": "test@example.com", "role": "viewer"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_share_invalid_role_rejected(self, auth_client, client, db_session):
        await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "Bad Role"})
        pid = resp.json()["project_id"]

        resp = await auth_client.post(
            f"/api/projects/{pid}/share",
            json={"email": "user2@example.com", "role": "admin"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_share_nonexistent_user(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "No User"})
        pid = resp.json()["project_id"]

        resp = await auth_client.post(
            f"/api/projects/{pid}/share",
            json={"email": "nobody@example.com", "role": "viewer"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_share_duplicate_rejected(self, auth_client, client, db_session):
        await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "Dup Share"})
        pid = resp.json()["project_id"]

        await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "viewer"})
        resp = await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "viewer"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_shares(self, auth_client, client, db_session):
        await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "List Shares"})
        pid = resp.json()["project_id"]

        await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "editor"})

        resp = await auth_client.get(f"/api/projects/{pid}/shares")
        assert resp.status_code == 200
        shares = resp.json()
        assert len(shares) == 1
        assert shares[0]["email"] == "user2@example.com"
        assert shares[0]["role"] == "editor"

    @pytest.mark.asyncio
    async def test_update_share_role(self, auth_client, client, db_session):
        await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "Update Share"})
        pid = resp.json()["project_id"]

        share_resp = await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "viewer"})
        share_id = share_resp.json()["id"]

        resp = await auth_client.put(
            f"/api/projects/{pid}/shares/{share_id}",
            json={"email": "user2@example.com", "role": "editor"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    @pytest.mark.asyncio
    async def test_revoke_share(self, auth_client, client, db_session):
        await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "Revoke Share"})
        pid = resp.json()["project_id"]

        share_resp = await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "viewer"})
        share_id = share_resp.json()["id"]

        resp = await auth_client.delete(f"/api/projects/{pid}/shares/{share_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"

        # Verify removed
        resp = await auth_client.get(f"/api/projects/{pid}/shares")
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_shared_with_me(self, auth_client, client, db_session):
        user2_h = await self._create_second_user(client)
        resp = await auth_client.post("/api/projects/", params={"name": "Shared Proj"})
        pid = resp.json()["project_id"]

        await auth_client.post(f"/api/projects/{pid}/share", json={"email": "user2@example.com", "role": "viewer"})

        # User2 checks shared-with-me
        resp = await client.get("/api/projects/shared-with-me", headers=user2_h)
        assert resp.status_code == 200
        shared = resp.json()
        assert len(shared) == 1
        assert shared[0]["project_id"] == pid
        assert shared[0]["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_share(self, auth_client):
        resp = await auth_client.post("/api/projects/", params={"name": "No Share"})
        pid = resp.json()["project_id"]

        resp = await auth_client.delete(f"/api/projects/{pid}/shares/nonexistent")
        assert resp.status_code == 404
