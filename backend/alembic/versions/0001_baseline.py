"""Baseline: the schema of the pre-Alembic application ("v24").

On an empty database this creates every table. A database that already holds
the application's tables was created before Alembic and must first be brought
to this exact state by the frozen legacy migrations; that is what
``python -m backend.app.migrate`` (and application startup) does before
stamping this revision. Running plain ``alembic upgrade`` on such a database is
refused, because it would skip that step.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-26
"""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Rows the legacy migrations recorded; written on fresh databases too, so that
# ``schema_versions`` reads the same everywhere.
_LEGACY_VERSIONS = [
    "v2_dataset_library", "v3_composite_datasets", "v4_admin_flag", "v5_job_name",
    "v6_job_user_id", "v7_job_config_hash", "v8_job_disk_size", "v9_dataset_tags",
    "v10_job_batch_id", "v11_audit_log", "v12_password_reset", "v13_api_keys",
    "v14_webhooks", "v15_dataset_versions", "v16_job_best_auc", "v17_project_comments",
    "v18_public_shares", "v19_project_class_names", "v20_dataset_archived",
    "v21_dataset_data_meta", "v22_scitq_task_id", "v23_project_archived",
    "v24_job_runtime_indexes",
]


def _frozen():
    path = Path(__file__).resolve().parents[1] / "frozen_schema.py"
    spec = importlib.util.spec_from_file_location("predomics_frozen_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    bind = op.get_bind()
    schema = _frozen().build(1)
    existing = set(sa.inspect(bind).get_table_names()) & set(schema.tables)
    adopting = bool(context.config.attributes.get("adopting_legacy"))

    if existing and not adopting:
        raise RuntimeError(
            "This database already contains PredomicsApp tables but is not under Alembic "
            "control: it was created by an earlier version. Run "
            "`python -m backend.app.migrate` (or start the application), which upgrades "
            "it and stamps the baseline, instead of `alembic upgrade`."
        )

    # checkfirst: when adopting an old database only the tables it lacks are created.
    schema.create_all(bind, checkfirst=True)

    if not adopting:
        now = datetime.now(timezone.utc)
        bind.execute(
            schema.tables["schema_versions"].insert(),
            [{"version": v, "applied_at": now} for v in _LEGACY_VERSIONS],
        )


def downgrade() -> None:
    raise RuntimeError(
        "There is nothing before the baseline. To go back, restore a database backup."
    )
