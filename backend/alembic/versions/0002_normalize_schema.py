"""Email verification columns, link-table uniqueness, and schema normalisation.

1. ``users``: ``email_verified`` becomes NOT NULL DEFAULT TRUE and every existing
   account is marked verified (the old column, added by legacy migration v12
   with DEFAULT FALSE, was never read); adds ``email_verify_token_hash`` and
   ``email_verify_expires_at``.
2. ``project_datasets`` (project, dataset) and ``project_shares`` (project, user)
   become unique, after removing duplicate rows.
3. ``datasets.description`` widens to TEXT and ``jobs.disk_size_bytes`` to BIGINT.
4. Normalisation. Databases upgraded by the pre-Alembic migrations drifted from
   the models: columns added with ALTER TABLE are nullable where the model says
   NOT NULL, a foreign key or an index may be missing. Everything is compared
   with the frozen schema of this revision and the safe differences are applied
   (missing columns, indexes, constraints, NOT NULL after back-filling NULLs with
   the model's default). Nothing is ever dropped. A difference that cannot be
   applied without losing data (NULLs in a key column, orphan rows, duplicates)
   is left in place and logged as a warning.

Revision ID: 0002_normalize_schema
Revises: 0001_baseline
Create Date: 2026-11-26
"""
import importlib.util
import logging
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0002_normalize_schema"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_log = logging.getLogger("alembic.runtime.migration")

# Values used to fill NULLs before a column becomes NOT NULL, where the generic
# per-type value (false / '' / 0 / now) would be wrong.
_BACKFILL = {
    ("users", "is_active"): "TRUE",
    ("users", "email_verified"): "TRUE",
    ("api_keys", "is_active"): "TRUE",
    ("webhooks", "is_active"): "TRUE",
    ("public_shares", "is_active"): "TRUE",
    ("project_shares", "role"): "'viewer'",
    ("jobs", "status"): "'failed'",
}


def _frozen():
    path = Path(__file__).resolve().parents[1] / "frozen_schema.py"
    spec = importlib.util.spec_from_file_location("predomics_frozen_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(bind, table):
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _dedupe(bind, table, partition, order):
    """Delete all but the first row (by ``order``) of each ``partition`` group."""
    result = bind.execute(sa.text(
        f"DELETE FROM {table} WHERE id IN ("
        f"SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY {partition} ORDER BY {order}) AS rn "
        f"FROM {table}) ranked WHERE rn > 1)"
    ))
    if result.rowcount and result.rowcount > 0:
        _log.warning("Removed %d duplicate row(s) from %s", result.rowcount, table)


def _generic_fill(column):
    t = column.type
    if isinstance(t, sa.Boolean):
        return "FALSE"
    if isinstance(t, sa.DateTime):
        return "CURRENT_TIMESTAMP"
    if isinstance(t, (sa.Integer, sa.Float)):
        return "0"
    if isinstance(t, sa.String):  # includes Text
        return "''"
    return None


def _set_not_null(bind, table, column):
    """Back-fill NULLs then set NOT NULL. Returns False (and warns) if NULLs must stay."""
    fill = _BACKFILL.get((table, column.name))
    if fill is None and not column.foreign_keys and not column.primary_key:
        fill = _generic_fill(column)
    if fill is not None:
        bind.execute(sa.text(f"UPDATE {table} SET {column.name} = {fill} WHERE {column.name} IS NULL"))
    remaining = bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {column.name} IS NULL")).scalar()
    if remaining:
        _log.warning(
            "%s.%s has %d NULL value(s) that cannot be filled in safely; the column stays nullable. "
            "Fix or remove those rows, then set NOT NULL by hand.", table, column.name, remaining,
        )
        return False
    op.alter_column(table, column.name, nullable=False)
    return True


def _normalize_postgresql(bind, target):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    ctx = MigrationContext.configure(bind, opts={"compare_type": True})
    flat = []
    chatter = [logging.getLogger("alembic.autogenerate"), logging.getLogger("alembic.ddl")]
    levels = [logger.level for logger in chatter]
    for logger in chatter:
        logger.setLevel(logging.WARNING)
    try:
        differences = compare_metadata(ctx, target)
    finally:
        for logger, level in zip(chatter, levels):
            logger.setLevel(level)
    for diff in differences:
        flat.extend(diff if isinstance(diff, list) else [diff])
    order = {"add_table": 0, "add_column": 1, "modify_type": 2, "modify_nullable": 3,
             "add_index": 4, "add_constraint": 5, "add_fk": 6}

    for diff in sorted(flat, key=lambda d: order.get(d[0], 99)):
        kind = diff[0]
        if kind == "add_table":
            bind.execute(sa.schema.CreateTable(diff[1]))

        elif kind == "add_column":
            _, _, table, column = diff
            new = column._copy()
            needs_fill = not new.nullable and new.server_default is None
            if needs_fill:
                new.nullable = True
            op.add_column(table, new)
            if needs_fill:
                _set_not_null(bind, table, target.tables[table].c[column.name])

        elif kind == "modify_type":
            _, _, table, column, _, old_type, new_type = diff
            if type(new_type) in (sa.Text, sa.BigInteger):  # widening only
                op.alter_column(table, column, type_=new_type)
            else:
                _log.warning("%s.%s is %s, expected %s; left as is", table, column, old_type, new_type)

        elif kind == "modify_nullable":
            _, _, table, column, _, _, new_nullable = diff
            if new_nullable:
                op.alter_column(table, column, nullable=True)
            else:
                _set_not_null(bind, table, target.tables[table].c[column])

        elif kind == "add_index":
            index = diff[1]
            op.create_index(index.name, index.table.name, [c.name for c in index.columns],
                            unique=index.unique, if_not_exists=True)

        elif kind == "add_constraint":
            constraint = diff[1]
            table = constraint.table.name
            cols = [c.name for c in constraint.columns]
            duplicated = bind.execute(sa.text(
                f"SELECT 1 FROM {table} GROUP BY {', '.join(cols)} HAVING count(*) > 1 LIMIT 1"
            )).first()
            if duplicated:
                _log.warning("%s has duplicate (%s) values; unique constraint not created",
                             table, ", ".join(cols))
            else:
                op.create_unique_constraint(constraint.name or f"uq_{table}_{'_'.join(cols)}", table, cols)

        elif kind == "add_fk":
            fk = diff[1]
            table = fk.table.name
            element = fk.elements[0]
            column = element.parent.name
            ref_table, ref_column = element.target_fullname.split(".")
            orphans = bind.execute(sa.text(
                f"SELECT count(*) FROM {table} t WHERE t.{column} IS NOT NULL AND NOT EXISTS "
                f"(SELECT 1 FROM {ref_table} r WHERE r.{ref_column} = t.{column})"
            )).scalar()
            if orphans:
                _log.warning("%s.%s has %d value(s) with no matching %s row; foreign key not created",
                             table, column, orphans, ref_table)
            else:
                op.create_foreign_key(f"{table}_{column}_fkey", table, ref_table, [column], [ref_column],
                                      ondelete=fk.ondelete)
        else:
            # remove_* and anything else: extra objects in the database are never dropped.
            _log.info("Schema difference left as is: %s", diff[0])


def _upgrade_sqlite(bind, target):
    """SQLite (development databases): rebuild the changed tables to the new shape."""
    users = target.tables["users"]
    have = _columns(bind, "users")
    for name in ("email_verified", "email_verify_token_hash", "email_verify_expires_at"):
        if name not in have:
            column = users.c[name]._copy()
            op.add_column("users", column)
    bind.execute(sa.text("UPDATE users SET email_verified = 1"))
    for table in ("users", "datasets", "jobs", "project_datasets", "project_shares"):
        for index in sa.inspect(bind).get_indexes(table):
            op.drop_index(index["name"], table_name=table)
        with op.batch_alter_table(table, copy_from=target.tables[table], recreate="always"):
            pass


def upgrade() -> None:
    bind = op.get_bind()
    target = _frozen().build(2)

    _dedupe(bind, "project_datasets", "project_id, dataset_id", "id")
    # Keep the most permissive share when a user was shared the same project twice.
    _dedupe(bind, "project_shares", "project_id, user_id",
            "CASE WHEN role = 'editor' THEN 0 ELSE 1 END, id")

    if bind.dialect.name == "sqlite":
        _upgrade_sqlite(bind, target)
        return

    if "email_verified" in _columns(bind, "users"):
        bind.execute(sa.text("UPDATE users SET email_verified = TRUE WHERE email_verified IS NOT TRUE"))
        op.alter_column("users", "email_verified", server_default=sa.true())
    _normalize_postgresql(bind, target)


def downgrade() -> None:
    """Remove what this revision added. Type widenings and NOT NULL fixes stay."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        previous = _frozen().build(1)
        for table in ("users", "project_datasets", "project_shares"):
            for index in sa.inspect(bind).get_indexes(table):
                op.drop_index(index["name"], table_name=table)
            with op.batch_alter_table(table, copy_from=previous.tables[table], recreate="always"):
                pass
        return
    op.drop_constraint("uq_project_shares_project_user", "project_shares", type_="unique")
    op.drop_constraint("uq_project_datasets_project_dataset", "project_datasets", type_="unique")
    op.drop_index("ix_users_email_verify_token_hash", table_name="users", if_exists=True)
    op.drop_column("users", "email_verify_expires_at")
    op.drop_column("users", "email_verify_token_hash")
    op.alter_column("users", "email_verified", nullable=True, server_default=sa.false())
