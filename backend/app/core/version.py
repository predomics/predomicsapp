"""Single source for the application version reported by the API.

Order: ``PREDOMICS_VERSION`` (set at image build from the git tag), then the
``version`` field of ``backend/pyproject.toml``, then a development placeholder.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _from_pyproject() -> str | None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE)
        return m.group(1) if m else None
    except OSError:
        return None


__version__ = os.environ.get("PREDOMICS_VERSION") or _from_pyproject() or "0.0.0-dev"

# Engine source revisions baked into the image (empty outside an image build).
ENGINE_REF = os.environ.get("PREDOMICS_ENGINE_REF", "")
ENGINEPY_REF = os.environ.get("PREDOMICS_ENGINEPY_REF", "")
