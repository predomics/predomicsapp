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
        yield db_session

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
