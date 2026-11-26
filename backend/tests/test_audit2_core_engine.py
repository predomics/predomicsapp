"""Engine guards added after the audit: GA parent selection and capability probe."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.database import sync_session_factory
from app.models.db_models import Job
from app.services import engine as ml_engine
from app.services import jobs, results_io

from tests.test_api import (  # noqa: F401 - fixtures and helpers
    db_session, client, auth_client, clean_data, _create_project_with_datasets,
)

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "qin2014_cirrhosis"


def _cfg(population, language="bin,ter", data_type="raw,prev", **ga):
    return {
        "general": {"algo": "ga", "language": language, "data_type": data_type, "fit": "auc",
                    "seed": 42, "thread_number": 1, "cv": False, "gpu": False},
        "ga": {"population_size": population, "max_epochs": 3, "min_epochs": 1, "k_min": 1, "k_max": 10, **ga},
    }


class TestGuaranteedParents:
    def test_formula_matches_the_engine_truncation(self):
        f = ml_engine.ga_guaranteed_parents
        assert f(100, 2.0, 0.0, 2.0, 4) == 2      # 2 elite + 4 * floor(0.5) random
        assert f(99, 2.0, 0.0, 2.0, 4) == 1       # one duplicate removed -> a single parent
        assert f(200, 2.0, 0.0, 2.0, 4) == 8      # 4 elite + 4 * 1
        assert f(100, 0.0, 10.0, 0.0, 3) == 9     # niche split over 3 types, truncated to 3 each
        assert f(5000, 2.0, 0.0, 2.0, 9) == 199   # defaults: 100 elite + 9 * 11

    @pytest.mark.parametrize("population,ok", [(50, False), (100, False), (124, False), (125, True), (5000, True)])
    def test_default_percentages(self, population, ok):
        if ok:
            ml_engine.check_ga_selection(_cfg(population))
        else:
            with pytest.raises(ValueError) as err:
                ml_engine.check_ga_selection(_cfg(population))
            assert "population_size to at least 125" in str(err.value)
            assert "select_elite_pct to at least" in str(err.value)

    def test_suggested_values_are_accepted(self):
        with pytest.raises(ValueError) as err:
            ml_engine.check_ga_selection(_cfg(60))
        message = str(err.value)
        elite = float(message.rsplit("select_elite_pct to at least ", 1)[1].rstrip("."))
        ml_engine.check_ga_selection(_cfg(60, select_elite_pct=elite))
        population = int(message.split("population_size to at least ", 1)[1].split()[0])
        ml_engine.check_ga_selection(_cfg(population))
        with pytest.raises(ValueError):
            ml_engine.check_ga_selection(_cfg(population - 1))

    def test_other_algorithms_and_switch(self, monkeypatch):
        cfg = _cfg(10)
        cfg["general"]["algo"] = "beam"
        ml_engine.check_ga_selection(cfg)
        monkeypatch.setenv("PREDOMICS_GA_PARENT_GUARD", "false")
        if hasattr(settings, "ga_parent_guard"):
            monkeypatch.setattr(settings, "ga_parent_guard", False)
        ml_engine.check_ga_selection(_cfg(10))

    def test_admin_defaults_count(self, tmp_path, monkeypatch):
        """Percentages left empty by the user come from the admin defaults."""
        path = tmp_path / "admin_defaults.json"
        path.write_text(json.dumps({"ga.select_elite_pct": 10.0}))
        monkeypatch.setattr(ml_engine, "ADMIN_DEFAULTS_PATH", path)
        ml_engine.check_ga_selection(_cfg(60))          # 10 % of 48 = 4 parents


class TestLaunchValidation:
    @pytest.mark.asyncio
    async def test_run_rejects_a_population_that_cannot_breed(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        resp = await auth_client.post(f"/api/analysis/{pid}/run", json=_cfg(100),
                                      params={"x_file_id": x, "y_file_id": y})
        assert resp.status_code == 422
        message = resp.json()["error"]["message"]
        assert "at least 2 parents" in message and "population_size to at least 125" in message
        assert (await auth_client.get(f"/api/analysis/{pid}/jobs")).json() == []

    @pytest.mark.asyncio
    async def test_batch_names_the_offending_combination(self, auth_client):
        pid, x, y = await _create_project_with_datasets(auth_client)
        resp = await auth_client.post(
            f"/api/analysis/{pid}/batch",
            json={"config": _cfg(300), "sweep": {"sweeps": {"ga.population_size": [300, 80]}}},
            params={"x_file_id": x, "y_file_id": y},
        )
        assert resp.status_code == 422
        assert "80" in resp.json()["error"]["message"]
        assert (await auth_client.get(f"/api/analysis/{pid}/jobs")).json() == []


def _wait(predicate, timeout=180.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("condition not reached in time")


def test_smallest_accepted_configuration_really_runs(db_session, monkeypatch):
    """The guard's lower bound is not theoretical: that exact configuration completes."""
    pytest.importorskip("gpredomicspy")
    if not (_SAMPLE / "Xtrain.tsv").exists():
        pytest.skip("sample dataset not available")
    monkeypatch.delenv("PREDOMICS_JOBS_INLINE", raising=False)
    monkeypatch.setattr(ml_engine, "HAS_ENGINE", True)

    cfg = _cfg(125)                                   # smallest accepted with the default percentages
    ml_engine.check_ga_selection(cfg)
    with pytest.raises(ValueError):
        ml_engine.check_ga_selection(_cfg(124))
    cfg["ga"].update(max_epochs=12, min_epochs=10)    # enough generations to hit selection repeatedly

    from tests.test_audit_jobs import _ensure_project
    _ensure_project("pguard000001")
    for seed in (1, 42, 7):
        cfg["general"]["seed"] = seed
        with sync_session_factory() as db:
            job = Job(project_id="pguard000001", status="pending", config=cfg)
            db.add(job)
            db.commit()
            jid = job.id
        job_dir = results_io.job_dir("pguard000001", jid)
        job_dir.mkdir(parents=True, exist_ok=True)
        param_path = ml_engine.write_param_yaml(
            cfg, str(_SAMPLE / "Xtrain.tsv"), str(_SAMPLE / "Ytrain.tsv"),
            str(_SAMPLE / "Xtest.tsv"), str(_SAMPLE / "Ytest.tsv"), output_dir=str(job_dir),
        )
        jobs.submit_local(jid, "pguard000001", param_path)

        def _row():
            with sync_session_factory() as db:
                r = db.execute(select(Job).where(Job.id == jid)).scalar_one()
                return r if r.status in ("completed", "failed") else None

        row = _wait(_row)
        assert row.status == "completed", f"seed {seed}: {row.error_message}"
    assert jobs.wait_idle(10)


class TestCapabilities:
    def test_shape_before_probing(self, monkeypatch):
        monkeypatch.setattr(ml_engine, "_capabilities", None)
        caps = ml_engine.capabilities()
        assert set(caps) >= {"available", "version", "probed", "data_types", "languages", "missing", "ok"}
        assert caps["probed"] is False and caps["missing"] == []

    def test_missing_default_is_reported(self, monkeypatch, caplog):
        """An engine without zscore: the default data types need it -> named, logged, not ok."""
        monkeypatch.setattr(ml_engine, "HAS_ENGINE", True)
        monkeypatch.setattr(ml_engine, "_load_admin_defaults", lambda: {})
        fake = {"available": True, "version": "0.1.0", "ref": None, "bindings_ref": None, "probed": True,
                "data_types": ["raw", "prev", "log"], "languages": ["bin", "ter", "ratio", "pow2"], "errors": {}}

        def _probe(force=False):
            monkeypatch.setattr(ml_engine, "_capabilities", fake)
            return ml_engine.capabilities()

        monkeypatch.setattr(ml_engine, "probe_capabilities", _probe)
        with caplog.at_level("ERROR"):
            caps = ml_engine.check_startup_compatibility()
        assert caps["missing"] == ["data_type:zscore"] and caps["ok"] is False
        assert any("zscore" in r.getMessage() and "not supported" in r.getMessage() for r in caplog.records)

        # an admin default that avoids it makes the server consistent again
        monkeypatch.setattr(ml_engine, "_load_admin_defaults", lambda: {"general.data_type": "raw,prev"})
        assert ml_engine.capabilities()["ok"] is True

    def test_real_probe_finds_what_the_installed_engine_supports(self, tmp_path, monkeypatch):
        pytest.importorskip("gpredomicspy")
        monkeypatch.setattr(ml_engine, "HAS_ENGINE", True)
        monkeypatch.setattr(ml_engine, "_capabilities", None)
        monkeypatch.setattr(ml_engine, "_caps_cache_path", lambda: tmp_path / "caps.json")
        caps = ml_engine.probe_capabilities(force=True)
        assert caps["probed"] is True
        assert {"raw", "prev"} <= set(caps["data_types"]) and {"bin", "ter"} <= set(caps["languages"])
        cached = json.loads((tmp_path / "caps.json").read_text())
        assert cached["data_types"] == caps["data_types"]
        # second call answers from the cache without running any fit
        monkeypatch.setattr(ml_engine, "_probe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("probed again")))
        assert ml_engine.probe_capabilities()["data_types"] == caps["data_types"]

    def test_unknown_data_type_fails_the_probe(self):
        pytest.importorskip("gpredomicspy")
        ok, _ = ml_engine._probe(["bin"], ["no_such_type"])
        assert ok is False
