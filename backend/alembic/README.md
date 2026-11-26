# Database migrations

Schema changes are Alembic revisions in `versions/`.

- `0001_baseline` is the schema the application had before Alembic ("v24").
- Databases created before Alembic are brought to that state by the frozen
  functions in `app/migrations_legacy.py`, then stamped at the baseline.
  `python -m backend.app.migrate` does this automatically; plain
  `alembic upgrade head` refuses such a database and says so.
- `frozen_schema.py` holds a frozen copy of the schema per revision. Revisions
  use it instead of importing the ORM models.

## Everyday commands (from the repository or image root)

    python -m backend.app.migrate            # upgrade to the latest revision
    python -m backend.app.migrate status     # where the database is
    python -m backend.app.migrate check      # exit 1 if the schema differs from the models

## Adding a schema change

1. Change the model in `app/models/db_models.py`.
2. `alembic -c backend/alembic.ini revision --autogenerate -m "what changed"`
   against an up-to-date PostgreSQL database, then read and edit the result.
3. Add the change to `frozen_schema.py` behind an `rN` switch.
4. Run the migration tests with `PREDOMICS_TEST_PG_URL` set (see CONTRIBUTING).

The application applies pending revisions at startup under a PostgreSQL advisory
lock unless `PREDOMICS_AUTO_MIGRATE=false`, in which case it refuses to start on
an out-of-date database. Take a backup before upgrading: downgrades are not
supported across the baseline.
