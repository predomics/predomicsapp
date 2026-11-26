"""Frozen copies of the database schema, one per Alembic revision.

Revisions must not import the live ORM models: the models keep changing, and a
revision has to mean the same thing forever. ``build(n)`` returns the schema as
it is *after* revision ``n``:

* ``build(1)`` — the baseline: what the pre-Alembic application ("v24") created
  on a fresh database.
* ``build(2)`` — after ``0002``: email-verification columns, wider types for
  ``datasets.description`` and ``jobs.disk_size_bytes``, and the unique
  constraints on the two link tables.

When a new revision changes the schema, add an ``rN`` switch here rather than
editing what an earlier number returns.

Loaded by path from the revision files (this directory is not a package).
"""

import sqlalchemy as sa


def _when(condition, *items):
    return items if condition else ()


def build(revision: int) -> sa.MetaData:
    r2 = revision >= 2
    md = sa.MetaData()
    sa.Table(
        "schema_versions", md,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("version"),
    )
    sa.Table(
        "users", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *(
            [sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true())]
            if r2 else
            # v12 added it as "BOOLEAN DEFAULT FALSE"; nothing read it before revision 0002.
            [sa.Column("email_verified", sa.Boolean(), nullable=True, server_default=sa.false())]
        ),
        *_when(r2, sa.Column("email_verify_token_hash", sa.String(64), nullable=True)),
        *_when(r2, sa.Column("email_verify_expires_at", sa.DateTime(timezone=True), nullable=True)),
    )
    sa.Index("ix_users_email", md.tables['users'].c.email, unique=True)
    if r2:
        sa.Index("ix_users_email_verify_token_hash", md.tables['users'].c.email_verify_token_hash)
    sa.Table(
        "api_keys", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_api_keys_user_id", md.tables['api_keys'].c.user_id)
    sa.Table(
        "audit_logs", md,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=True),
        sa.Column("resource_id", sa.String(12), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_audit_logs_action", md.tables['audit_logs'].c.action)
    sa.Index("ix_audit_logs_created_at", md.tables['audit_logs'].c.created_at)
    sa.Index("ix_audit_logs_user_id", md.tables['audit_logs'].c.user_id)
    sa.Table(
        "datasets", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text() if r2 else sa.String(500), nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("data_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_datasets_user_id", md.tables['datasets'].c.user_id)
    sa.Table(
        "password_reset_tokens", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    sa.Index("ix_password_reset_tokens_user_id", md.tables['password_reset_tokens'].c.user_id)
    sa.Table(
        "projects", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("class_names", sa.JSON(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Index("ix_projects_user_id", md.tables['projects'].c.user_id)
    sa.Table(
        "webhooks", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("events", sa.JSON(), nullable=True),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_webhooks_user_id", md.tables['webhooks'].c.user_id)
    sa.Table(
        "dataset_files", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("dataset_id", sa.String(12), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("disk_path", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_dataset_files_dataset_id", md.tables['dataset_files'].c.dataset_id)
    sa.Table(
        "dataset_versions", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("dataset_id", sa.String(12), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("files_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(12), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_dataset_versions_dataset_id", md.tables['dataset_versions'].c.dataset_id)
    sa.Table(
        "jobs", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(12), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("results_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_hash", sa.String(32), nullable=True),
        sa.Column("disk_size_bytes", sa.BigInteger() if r2 else sa.Integer(), nullable=True),
        sa.Column("batch_id", sa.String(12), nullable=True),
        sa.Column("best_auc", sa.Float(), nullable=True),
        sa.Column("best_k", sa.Integer(), nullable=True),
        sa.Column("scitq_task_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
    )
    sa.Index("ix_jobs_batch_id", md.tables['jobs'].c.batch_id)
    sa.Index("ix_jobs_config_hash", md.tables['jobs'].c.config_hash)
    sa.Index("ix_jobs_project_id", md.tables['jobs'].c.project_id)
    sa.Index("ix_jobs_status", md.tables['jobs'].c.status)
    sa.Index("ix_jobs_user_id", md.tables['jobs'].c.user_id)
    sa.Table(
        "project_comments", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(12), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    sa.Index("ix_project_comments_project_id", md.tables['project_comments'].c.project_id)
    sa.Index("ix_project_comments_user_id", md.tables['project_comments'].c.user_id)
    sa.Table(
        "project_datasets", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(12), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.String(12), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        *_when(r2, sa.UniqueConstraint("project_id", "dataset_id", name="uq_project_datasets_project_dataset")),
    )
    sa.Index("ix_project_datasets_dataset_id", md.tables['project_datasets'].c.dataset_id)
    sa.Index("ix_project_datasets_project_id", md.tables['project_datasets'].c.project_id)
    sa.Table(
        "project_shares", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(12), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shared_by", sa.String(12), nullable=True),
        *_when(r2, sa.UniqueConstraint("project_id", "user_id", name="uq_project_shares_project_user")),
    )
    sa.Index("ix_project_shares_project_id", md.tables['project_shares'].c.project_id)
    sa.Index("ix_project_shares_user_id", md.tables['project_shares'].c.user_id)
    sa.Table(
        "public_shares", md,
        sa.Column("id", sa.String(12), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(12), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(12), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Index("ix_public_shares_created_by", md.tables['public_shares'].c.created_by)
    sa.Index("ix_public_shares_project_id", md.tables['public_shares'].c.project_id)
    sa.Index("ix_public_shares_token", md.tables['public_shares'].c.token, unique=True)
    return md
