"""Pytest conftest — set env overrides before any test module imports `app`.

This file is collected before any sibling `test_*.py`, so env vars set here
are guaranteed to be in place when `Settings()` is first instantiated (which
happens the first time `app.core.config` is imported — from either test_api.py
or test_services_unit.py).

Putting the same env setup at the top of test_api.py is not reliable: pytest
may collect test_services_unit.py first, which imports `app.services.*` and
therefore `app.core.config.settings`, baking in the default paths before
test_api.py's module-level code ever runs.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="predomics-test-")
os.environ["PREDOMICS_DATA_DIR"] = _tmp
os.environ["PREDOMICS_PROJECT_DIR"] = os.path.join(_tmp, "projects")
os.environ["PREDOMICS_UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["PREDOMICS_SAMPLES_DIR"] = os.path.join(_tmp, "samples")
os.environ["PREDOMICS_SAMPLE_DIR"] = os.path.join(_tmp, "samples")  # legacy compat
os.environ["PREDOMICS_DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["PREDOMICS_SECRET_KEY"] = "test-secret-key"
os.environ["PREDOMICS_RATE_LIMIT_ENABLED"] = "false"

# Expose the tmpdir for tests that want to write fixture files under it.
os.environ["PREDOMICS_TEST_TMPDIR"] = _tmp
