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
    for d in ["projects", "uploads"]:
        p = os.path.join(data_dir, d)
        if os.path.exists(p):
            shutil.rmtree(p)
            os.makedirs(p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project_with_datasets(auth_client):
    """Create a project with X and y datasets, return (project_id, x_id, y_id)."""
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
    x_id = datasets[0]["id"]
    y_id = datasets[1]["id"]
    return pid, x_id, y_id


async def _run_mock_analysis(auth_client, pid, x_id, y_id):
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
            params={"x_dataset_id": x_id, "y_dataset_id": y_id},
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
        assert datasets[0]["filename"] == "X.tsv"

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
            params={"x_dataset_id": "nonexistent", "y_dataset_id": "nonexistent"},
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
            params={"x_dataset_id": "abc", "y_dataset_id": "def"},
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
            params={"x_dataset_id": "abc", "y_dataset_id": "def"},
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
                params={"x_dataset_id": x_id, "y_dataset_id": y_id},
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
                params={"x_dataset_id": x_id, "y_dataset_id": y_id},
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
                params={"x_dataset_id": x_id, "y_dataset_id": y_id},
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
        assert len(data["datasets"]) == 4

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
