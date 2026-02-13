"""Comprehensive API tests for PredomicsApp backend."""

import os
import shutil
import tempfile

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Override settings before importing app
os.environ["PREDOMICS_DATA_DIR"] = tempfile.mkdtemp()
os.environ["PREDOMICS_PROJECT_DIR"] = os.path.join(os.environ["PREDOMICS_DATA_DIR"], "projects")
os.environ["PREDOMICS_UPLOAD_DIR"] = os.path.join(os.environ["PREDOMICS_DATA_DIR"], "uploads")

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clean_data():
    """Clean up test data between tests."""
    yield
    data_dir = os.environ["PREDOMICS_DATA_DIR"]
    for sub in ["projects", "uploads"]:
        p = os.path.join(data_dir, sub)
        if os.path.exists(p):
            shutil.rmtree(p)
        os.makedirs(p, exist_ok=True)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert isinstance(data["gpredomicspy_available"], bool)

    @pytest.mark.asyncio
    async def test_health_has_correct_fields(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert set(data.keys()) == {"status", "version", "gpredomicspy_available"}


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

class TestProjects:
    @pytest.mark.asyncio
    async def test_create_project(self, client):
        resp = await client.post("/api/projects/", params={"name": "my_study"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my_study"
        assert "project_id" in data
        assert len(data["project_id"]) == 12
        assert data["datasets"] == []
        assert data["jobs"] == []

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client):
        resp = await client.get("/api/projects/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_projects_after_create(self, client):
        await client.post("/api/projects/", params={"name": "proj1"})
        await client.post("/api/projects/", params={"name": "proj2"})
        resp = await client.get("/api/projects/")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) == 2
        names = {p["name"] for p in projects}
        assert names == {"proj1", "proj2"}

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "test"})
        pid = create_resp.json()["project_id"]

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test"
        assert resp.json()["project_id"] == pid

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(self, client):
        resp = await client.get("/api/projects/nonexistent123")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "to_delete"})
        pid = create_resp.json()["project_id"]

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        # Verify it's gone
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project_returns_404(self, client):
        resp = await client.delete("/api/projects/nonexistent123")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_has_created_at_timestamp(self, client):
        resp = await client.post("/api/projects/", params={"name": "timestamped"})
        data = resp.json()
        assert "created_at" in data
        assert "T" in data["created_at"]  # ISO format


# ---------------------------------------------------------------------------
# Dataset upload
# ---------------------------------------------------------------------------

class TestDatasets:
    @pytest.mark.asyncio
    async def test_upload_tsv_dataset(self, client):
        # Create project first
        create_resp = await client.post("/api/projects/", params={"name": "data_test"})
        pid = create_resp.json()["project_id"]

        # Create a small TSV file
        tsv_content = "id\tsample1\tsample2\tsample3\nfeature1\t0.5\t0.3\t0.8\nfeature2\t0.1\t0.9\t0.2\n"

        resp = await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("test_X.tsv", tsv_content.encode(), "text/tab-separated-values")},
            params={"features_in_rows": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test_X.tsv"
        assert data["n_features"] == 2
        assert data["n_samples"] == 3

    @pytest.mark.asyncio
    async def test_upload_csv_dataset(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "csv_test"})
        pid = create_resp.json()["project_id"]

        csv_content = "id,s1,s2\nf1,0.1,0.2\nf2,0.3,0.4\nf3,0.5,0.6\n"

        resp = await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("data.csv", csv_content.encode(), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["n_features"] == 3
        assert resp.json()["n_samples"] == 2

    @pytest.mark.asyncio
    async def test_upload_to_nonexistent_project_returns_404(self, client):
        resp = await client.post(
            "/api/projects/nonexistent123/datasets",
            files={"file": ("x.tsv", b"a\tb\n1\t2\n", "text/plain")},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_updates_project_metadata(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "meta_test"})
        pid = create_resp.json()["project_id"]

        await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )

        resp = await client.get(f"/api/projects/{pid}")
        data = resp.json()
        assert len(data["datasets"]) == 1


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------

class TestAnalysis:
    @pytest.mark.asyncio
    async def test_run_analysis_returns_job_id(self, client):
        # Create project and upload data
        create_resp = await client.post("/api/projects/", params={"name": "run_test"})
        pid = create_resp.json()["project_id"]

        await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\ts2\nf1\t0.1\t0.2\n", "text/plain")},
        )
        await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("y.tsv", b"id\tclass\ns1\t0\ns2\t1\n", "text/plain")},
        )

        # Get dataset IDs from project metadata
        proj = (await client.get(f"/api/projects/{pid}")).json()
        datasets = proj["datasets"]
        x_id = datasets[0]["id"] if isinstance(datasets[0], dict) else datasets[0][:8]
        y_id = datasets[1]["id"] if isinstance(datasets[1], dict) else datasets[1][:8]

        config = {
            "general": {"algo": "ga", "language": "bin", "data_type": "raw", "fit": "auc",
                        "seed": 42, "thread_number": 1, "k_penalty": 0.0001, "cv": False, "gpu": False},
            "ga": {"population_size": 50, "max_epochs": 2, "k_min": 1, "k_max": 10},
        }

        resp = await client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_dataset_id": x_id, "y_dataset_id": y_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] in ["pending", "running"]

    @pytest.mark.asyncio
    async def test_get_job_status_nonexistent_returns_404(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "status_test"})
        pid = create_resp.json()["project_id"]

        resp = await client.get(f"/api/analysis/{pid}/jobs/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "jobs_test"})
        pid = create_resp.json()["project_id"]

        resp = await client.get(f"/api/analysis/{pid}/jobs")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    @pytest.mark.asyncio
    async def test_run_with_invalid_algo_returns_422(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "val_test"})
        pid = create_resp.json()["project_id"]

        config = {"general": {"algo": "invalid_algo"}}
        resp = await client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_dataset_id": "abc", "y_dataset_id": "def"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_run_with_invalid_fit_returns_422(self, client):
        create_resp = await client.post("/api/projects/", params={"name": "fit_test"})
        pid = create_resp.json()["project_id"]

        config = {"general": {"fit": "invalid_fit"}}
        resp = await client.post(
            f"/api/analysis/{pid}/run",
            json=config,
            params={"x_dataset_id": "abc", "y_dataset_id": "def"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_run_with_defaults_accepts_empty_config(self, client):
        """RunConfig should have sensible defaults for all fields."""
        create_resp = await client.post("/api/projects/", params={"name": "default_test"})
        pid = create_resp.json()["project_id"]

        # Upload dummy data
        await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("X.tsv", b"id\ts1\nf1\t0.1\n", "text/plain")},
        )
        await client.post(
            f"/api/projects/{pid}/datasets",
            files={"file": ("y.tsv", b"id\tc\ns1\t0\n", "text/plain")},
        )

        proj = (await client.get(f"/api/projects/{pid}")).json()
        ds = proj["datasets"]
        x_id = ds[0]["id"] if isinstance(ds[0], dict) else ds[0][:8]
        y_id = ds[1]["id"] if isinstance(ds[1], dict) else ds[1][:8]

        # Empty config body → all defaults
        resp = await client.post(
            f"/api/analysis/{pid}/run",
            json={},
            params={"x_dataset_id": x_id, "y_dataset_id": y_id},
        )
        assert resp.status_code == 200
