"""Backup/restore must cover every table and be safe to fail (audit finding BE-F6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import Base
from app.models.db_models import (
    ApiKey, AuditLog, Dataset, DatasetFile, DatasetVersion, Job, PasswordResetToken,
    Project, ProjectComment, ProjectDataset, ProjectShare, PublicShare, User, Webhook,
)
from app.services import backup

from tests.test_api import db_session, clean_data  # noqa: F401 - fixtures


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def _populate(db):
    now = datetime.now(timezone.utc)
    owner = User(id="u00000000001", email="owner@example.com", hashed_password="h1", is_admin=True)
    guest = User(id="u00000000002", email="guest@example.com", hashed_password="h2")
    db.add_all([owner, guest])
    await db.flush()
    project = Project(id="p00000000001", name="proj", user_id=owner.id)
    dataset = Dataset(id="d00000000001", name="ds", user_id=owner.id)
    db.add_all([project, dataset])
    await db.flush()

    ds_dir = Path(settings.data_dir) / "datasets" / owner.id
    ds_dir.mkdir(parents=True, exist_ok=True)
    x_file = ds_dir / "f00000000001_X.tsv"
    x_file.write_text("id\ts1\nf1\t1\n")
    job_dir = Path(settings.project_dir) / project.id / "jobs" / "j00000000001"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "results.json").write_text('{"best_individual": {"auc": 0.9}}')
    (Path(settings.data_dir) / "signature_zoo.json").write_text('[{"id": "sig1"}]')

    db.add_all([
        DatasetFile(id="f00000000001", dataset_id=dataset.id, filename="X.tsv", role="xtrain",
                    disk_path=str(x_file)),
        ProjectDataset(id="l00000000001", project_id=project.id, dataset_id=dataset.id),
        Job(id="j00000000001", project_id=project.id, user_id=owner.id, status="completed",
            results_path=str(job_dir / "results.json"), best_auc=0.9, completed_at=now),
        ProjectShare(id="s00000000001", project_id=project.id, user_id=guest.id, role="viewer"),
        ApiKey(id="k00000000001", user_id=owner.id, name="ci", key_hash="hash", prefix="abcd1234"),
        Webhook(id="w00000000001", user_id=owner.id, name="hook", url="https://example.org/h", secret="s"),
        ProjectComment(id="c00000000001", project_id=project.id, user_id=guest.id, content="looks good"),
        PublicShare(id="q00000000001", project_id=project.id, token="tok" * 10, created_by=owner.id),
        DatasetVersion(id="v00000000001", dataset_id=dataset.id, version_number=1, files_snapshot={"files": []}),
        PasswordResetToken(id="r00000000001", user_id=guest.id, token_hash="opaque",
                           expires_at=now + timedelta(hours=1)),
        AuditLog(user_id=owner.id, action="job.launch", resource_type="job", resource_id="j00000000001"),
    ])
    await db.commit()
    return x_file, job_dir


_EXTRA_TABLES = [ApiKey, Webhook, ProjectComment, PublicShare, DatasetVersion, PasswordResetToken, AuditLog]


class TestBackupRoundTrip:
    def test_every_table_is_exported(self):
        exported = {name for name, _ in backup.TABLE_EXPORT_ORDER}
        assert exported == set(Base.metadata.tables)
        for model in _EXTRA_TABLES:
            assert model.__tablename__ in exported

    @pytest.mark.asyncio
    async def test_replace_restore_keeps_everything(self, db_session):
        """API keys, comments, public shares, audit logs... used to be wiped by a restore."""
        x_file, job_dir = await _populate(db_session)
        meta = await backup.create_backup(db_session, "round trip")
        archive = backup.get_backup_path(meta["backup_id"])
        assert archive.exists()
        for model in _EXTRA_TABLES:
            assert meta["table_counts"][model.__tablename__] == 1
        assert backup.list_backups()[0]["backup_id"] == meta["backup_id"]

        # Lose data after the backup: rows of every kind, and the files
        for model in _EXTRA_TABLES + [ProjectShare, Job]:
            for row in (await db_session.execute(select(model))).scalars().all():
                await db_session.delete(row)
        db_session.add(User(id="u00000000003", email="later@example.com", hashed_password="h3"))
        await db_session.commit()
        x_file.unlink()
        (job_dir / "results.json").write_text("corrupted")
        (Path(settings.data_dir) / "signature_zoo.json").write_text("[]")

        out = await backup.restore_backup(archive, db_session, mode="replace")
        assert out["status"] == "restored"

        db_session.expire_all()
        for model in _EXTRA_TABLES + [ProjectShare, Job, Project, Dataset, DatasetFile, ProjectDataset]:
            assert await _count(db_session, model) == 1, model.__tablename__
        assert await _count(db_session, User) == 2          # the later user is gone: "replace"
        key = (await db_session.execute(select(ApiKey))).scalar_one()
        assert (key.name, key.prefix, key.key_hash) == ("ci", "abcd1234", "hash")
        comment = (await db_session.execute(select(ProjectComment))).scalar_one()
        assert comment.content == "looks good" and comment.user_id == "u00000000002"
        share = (await db_session.execute(select(PublicShare))).scalar_one()
        assert share.token == "tok" * 10 and share.is_active is True
        log = (await db_session.execute(select(AuditLog))).scalar_one()
        assert log.action == "job.launch" and isinstance(log.created_at, datetime)
        token = (await db_session.execute(select(PasswordResetToken))).scalar_one()
        assert token.token_hash == "opaque"

        assert x_file.read_text() == "id\ts1\nf1\t1\n"
        assert '"auc": 0.9' in (job_dir / "results.json").read_text()
        assert (Path(settings.data_dir) / "signature_zoo.json").read_text() == '[{"id": "sig1"}]'
        assert not list(Path(settings.data_dir).glob(".restore-*"))

    @pytest.mark.asyncio
    async def test_merge_restore_adds_without_overwriting(self, db_session):
        await _populate(db_session)
        meta = await backup.create_backup(db_session)
        archive = backup.get_backup_path(meta["backup_id"])
        key = (await db_session.execute(select(ApiKey))).scalar_one()
        await db_session.delete(key)
        comment = (await db_session.execute(select(ProjectComment))).scalar_one()
        comment.content = "edited after the backup"
        await db_session.commit()

        out = await backup.restore_backup(archive, db_session, mode="merge")
        assert out["restored_counts"]["api_keys"] == 1
        assert out["restored_counts"]["project_comments"] == 0
        db_session.expire_all()
        assert await _count(db_session, ApiKey) == 1
        assert (await db_session.execute(select(ProjectComment))).scalar_one().content == "edited after the backup"

    @pytest.mark.asyncio
    async def test_bad_archive_changes_nothing(self, db_session, tmp_path):
        x_file, _ = await _populate(db_session)
        bogus = tmp_path / "bogus.tar.gz"
        import tarfile
        (tmp_path / "junk.txt").write_text("x")
        with tarfile.open(bogus, "w:gz") as tar:
            tar.add(str(tmp_path / "junk.txt"), arcname="not-a-backup/junk.txt")
        with pytest.raises(ValueError):
            await backup.restore_backup(bogus, db_session, mode="replace")
        db_session.expire_all()
        assert await _count(db_session, ApiKey) == 1
        assert x_file.exists()
        assert not list(Path(settings.data_dir).glob(".restore-*"))

    @pytest.mark.asyncio
    async def test_old_archives_do_not_wipe_tables_they_lack(self, db_session, tmp_path):
        """Archives made before this fix hold 8 tables; the other 7 must survive a replace."""
        import json
        import tarfile

        await _populate(db_session)
        meta = await backup.create_backup(db_session)
        full = backup.get_backup_path(meta["backup_id"])
        work = tmp_path / "x"
        with tarfile.open(full, "r:gz") as tar:
            tar.extractall(work, filter="data")
        for model in _EXTRA_TABLES:
            (work / "backup" / "database" / f"{model.__tablename__}.json").unlink()
        manifest = json.loads((work / "backup" / "manifest.json").read_text())
        manifest["format"] = 1
        (work / "backup" / "manifest.json").write_text(json.dumps(manifest))
        old = tmp_path / "old.tar.gz"
        with tarfile.open(old, "w:gz") as tar:
            tar.add(str(work / "backup"), arcname="backup")

        out = await backup.restore_backup(old, db_session, mode="replace")
        db_session.expire_all()
        for model in _EXTRA_TABLES:
            assert await _count(db_session, model) == 1, model.__tablename__
            assert out["preserved_counts"][model.__tablename__] == 1

    @pytest.mark.asyncio
    async def test_paths_are_remapped_when_the_data_dir_differs(self, db_session, tmp_path):
        import json
        import tarfile

        x_file, job_dir = await _populate(db_session)
        meta = await backup.create_backup(db_session)
        full = backup.get_backup_path(meta["backup_id"])
        work = tmp_path / "x"
        with tarfile.open(full, "r:gz") as tar:
            tar.extractall(work, filter="data")
        here_data = str(Path(settings.data_dir).resolve())
        here_proj = str(Path(settings.project_dir).resolve())
        for name in ("dataset_files", "jobs"):
            f = work / "backup" / "database" / f"{name}.json"
            f.write_text(f.read_text().replace(here_proj, "/srv/old/projects").replace(here_data, "/srv/old"))
        mf = work / "backup" / "manifest.json"
        manifest = json.loads(mf.read_text())
        manifest.update(data_dir="/srv/old", project_dir="/srv/old/projects")
        mf.write_text(json.dumps(manifest))
        moved = tmp_path / "moved.tar.gz"
        with tarfile.open(moved, "w:gz") as tar:
            tar.add(str(work / "backup"), arcname="backup")

        await backup.restore_backup(moved, db_session, mode="replace")
        db_session.expire_all()
        f = (await db_session.execute(select(DatasetFile))).scalar_one()
        assert Path(f.disk_path).resolve() == x_file.resolve() and Path(f.disk_path).exists()
        j = (await db_session.execute(select(Job))).scalar_one()
        assert Path(j.results_path).resolve() == (job_dir / "results.json").resolve()
