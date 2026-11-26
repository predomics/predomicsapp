"""Round-2 audit tests: sessions, WebSocket tickets, login throttling, email
verification, quotas, retention, the light access check, observability and
typed responses."""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core import metrics, observability, security
from app.core.config import Settings, settings, validate_settings
from app.core.deps import get_project_access, get_project_with_access
from app.core.errors import ApiError, http_error_handler
from app.main import app
from app.models.db_models import Job, Project, ProjectShare, User
from app.services import email as email_service
from app.services import lockout, quota, retention, ws_tickets

try:  # fixtures live in test_api.py unless they have been moved to conftest.py
    from .test_api import db_session, client, auth_client, clean_data  # noqa: F401
except ImportError:  # pragma: no cover
    pass

PW = "a-long-password"
X_TSV = b"id\ts1\ts2\nf1\t0.1\t0.2\nf2\t0.3\t0.4\n"


async def _register(client, email, password=PW, name="U"):
    return await client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})


async def _login(client, email, password=PW):
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def _headers(client, email, password=PW):
    await _register(client, email, password)
    r = await _login(client, email, password)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _make_admin(client, db_session, email="root@example.com"):
    await _register(client, email)
    await db_session.execute(update(User).where(User.email == email).values(is_admin=True))
    await db_session.commit()
    r = await _login(client, email)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _clean_state():
    lockout.clear()
    ws_tickets.clear()
    yield
    lockout.clear()
    ws_tickets.clear()


@pytest.fixture
def outbox(monkeypatch):
    """Capture outgoing email instead of sending it; SMTP looks configured."""
    sent = []

    async def _fake_send(to, subject, html_body):
        sent.append({"to": to, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr(email_service, "send_email", _fake_send)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    return sent


def _token_from(mail):
    return re.search(r"token=([A-Za-z0-9_-]+)", mail["html"]).group(1)


# ---------------------------------------------------------------------------
# 1. WebSocket tickets
# ---------------------------------------------------------------------------

class TestWsTicket:
    def test_ticket_is_single_use(self):
        t = ws_tickets.issue("user-1")
        assert ws_tickets.redeem(t) == "user-1"
        assert ws_tickets.redeem(t) is None
        assert ws_tickets.redeem("") is None
        assert ws_tickets.redeem("made-up") is None

    def test_ticket_expires(self, monkeypatch):
        t = ws_tickets.issue("user-1")
        real = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: real() + ws_tickets.TICKET_TTL + 1)
        assert ws_tickets.redeem(t) is None

    @pytest.mark.asyncio
    async def test_endpoint_requires_login_and_returns_ticket(self, client):
        assert (await client.post("/api/auth/ws-ticket")).status_code == 401
        h = await _headers(client, "ws@example.com")
        r = await client.post("/api/auth/ws-ticket", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["expires_in"] == ws_tickets.TICKET_TTL and len(body["ticket"]) >= 32

    @pytest.mark.asyncio
    async def test_ticket_grants_access_only_to_own_or_shared_projects(self, client, db_session):
        from app.routers.websocket import _verify_ws_access

        owner_h = await _headers(client, "owner@example.com")
        stranger_h = await _headers(client, "stranger@example.com")
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=owner_h)).json()["project_id"]

        owner_ticket = (await client.post("/api/auth/ws-ticket", headers=owner_h)).json()["ticket"]
        assert await _verify_ws_access(owner_ticket, pid) is True
        assert await _verify_ws_access(owner_ticket, pid) is False        # already used

        stranger_ticket = (await client.post("/api/auth/ws-ticket", headers=stranger_h)).json()["ticket"]
        assert await _verify_ws_access(stranger_ticket, pid) is False

        await client.post(f"/api/projects/{pid}/share", headers=owner_h,
                          json={"email": "stranger@example.com", "role": "viewer"})
        shared_ticket = (await client.post("/api/auth/ws-ticket", headers=stranger_h)).json()["ticket"]
        assert await _verify_ws_access(shared_ticket, pid) is True

    @pytest.mark.asyncio
    async def test_access_token_is_not_accepted_as_ticket(self, client):
        from app.routers.websocket import _verify_ws_access, job_log_ws
        import inspect

        h = await _headers(client, "jwt@example.com")
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=h)).json()["project_id"]
        jwt = h["Authorization"].split()[1]
        assert await _verify_ws_access(jwt, pid) is False
        assert await _verify_ws_access(None, pid) is False
        params = inspect.signature(job_log_ws).parameters
        assert "ticket" in params and "token" not in params


# ---------------------------------------------------------------------------
# 2. Sessions
# ---------------------------------------------------------------------------

class TestSessions:
    def test_default_lifetime_is_eight_hours(self):
        assert Settings.model_fields["access_token_expire_minutes"].default == 480

    @pytest.mark.asyncio
    async def test_refresh_returns_a_working_token(self, client):
        h = await _headers(client, "fresh@example.com")
        r = await client.post("/api/auth/refresh", headers=h)
        assert r.status_code == 200
        new_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert (await client.get("/api/auth/me", headers=new_h)).json()["email"] == "fresh@example.com"

    @pytest.mark.asyncio
    async def test_refresh_refuses_missing_expired_or_revoked_tokens(self, client, monkeypatch):
        assert (await client.post("/api/auth/refresh")).status_code == 401
        await _register(client, "old@example.com")
        monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
        expired = (await _login(client, "old@example.com")).json()["access_token"]
        monkeypatch.setattr(settings, "access_token_expire_minutes", 480)
        assert (await client.post("/api/auth/refresh",
                                  headers={"Authorization": f"Bearer {expired}"})).status_code == 401
        # a token issued before a password change cannot be refreshed either
        h = {"Authorization": f"Bearer {(await _login(client, 'old@example.com')).json()['access_token']}"}
        await client.put("/api/auth/me/password", headers=h,
                         json={"current_password": PW, "new_password": "another-long-password"})
        assert (await client.post("/api/auth/refresh", headers=h)).status_code == 401


# ---------------------------------------------------------------------------
# 3. Login throttling
# ---------------------------------------------------------------------------

@pytest.fixture
def throttle(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "login_throttle_enabled", True)
    monkeypatch.setattr(settings, "login_throttle_free_attempts", 3)
    monkeypatch.setattr(settings, "login_throttle_max_minutes", 15)


class TestLoginThrottle:
    @pytest.mark.asyncio
    async def test_back_off_after_repeated_failures(self, client, throttle):
        await _register(client, "target@example.com")
        for _ in range(3):
            assert (await _login(client, "target@example.com", "wrong")).status_code == 401
        r = await _login(client, "target@example.com", "wrong")
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) > 0
        assert r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
        assert "Try again in" in r.json()["error"]["message"]
        # the right password does not get through while the account is throttled
        assert (await _login(client, "target@example.com")).status_code == 429

    @pytest.mark.asyncio
    async def test_unknown_account_behaves_the_same(self, client, throttle):
        codes = [(await _login(client, "ghost@example.com", "wrong")).status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]

    @pytest.mark.asyncio
    async def test_success_resets_the_account_counter(self, client, throttle):
        await _register(client, "ok@example.com")
        for _ in range(2):
            await _login(client, "ok@example.com", "wrong")
        assert (await _login(client, "ok@example.com")).status_code == 200
        for _ in range(2):
            assert (await _login(client, "ok@example.com", "wrong")).status_code == 401
        assert (await _login(client, "ok@example.com")).status_code == 200

    def test_delay_doubles_and_is_capped(self, throttle):
        waits = []
        for _ in range(12):
            lockout.record_failure("a@example.com", None)
            waits.append(lockout.retry_after("a@example.com", None))
        assert waits[:2] == [0, 0]
        assert 25 <= waits[2] <= 30 and 55 <= waits[3] <= 60 and 115 <= waits[4] <= 120
        assert max(waits) <= 15 * 60

    def test_ip_gets_more_room_than_an_account(self, throttle):
        for i in range(5):
            lockout.record_failure(f"user{i}@example.com", "198.51.100.7")
        assert lockout.retry_after("someone-else@example.com", "198.51.100.7") == 0
        for i in range(5, 12):
            lockout.record_failure(f"user{i}@example.com", "198.51.100.7")
        assert lockout.retry_after("someone-else@example.com", "198.51.100.7") > 0
        assert lockout.retry_after("someone-else@example.com", "203.0.113.1") == 0

    @pytest.mark.asyncio
    async def test_admin_password_reset_unlocks(self, client, db_session, throttle):
        admin_h = await _make_admin(client, db_session)
        await _register(client, "locked@example.com")
        for _ in range(4):
            await _login(client, "locked@example.com", "wrong")
        assert (await _login(client, "locked@example.com")).status_code == 429
        uid = (await db_session.execute(select(User.id).where(User.email == "locked@example.com"))).scalar_one()
        r = await client.post(f"/api/admin/users/{uid}/reset-password", headers=admin_h,
                              json={"new_password": "brand-new-password"})
        assert r.status_code == 200
        assert (await _login(client, "locked@example.com", "brand-new-password")).status_code == 200

    def test_disabled_with_rate_limiting_off(self, monkeypatch):
        monkeypatch.setattr(settings, "rate_limit_enabled", False)
        for _ in range(50):
            lockout.record_failure("x@example.com", "1.2.3.4")
        assert lockout.retry_after("x@example.com", "1.2.3.4") == 0


class TestLoginTiming:
    def test_unknown_user_still_costs_a_hash(self, monkeypatch):
        calls = []
        real = security.verify_password
        monkeypatch.setattr(security, "verify_password", lambda p, h: calls.append(h) or real(p, h))
        assert security.verify_password_or_dummy("whatever", None) is False
        assert len(calls) == 1 and calls[0].startswith("$2")


# ---------------------------------------------------------------------------
# 4 + 5. Email verification and enumeration
# ---------------------------------------------------------------------------

@pytest.fixture
def verification(monkeypatch, outbox):
    monkeypatch.setattr(settings, "require_email_verification", True)
    return outbox


class TestEmailVerification:
    @pytest.mark.asyncio
    async def test_full_flow(self, client, verification):
        r = await _register(client, "new@example.com")
        assert r.status_code == 201
        body = r.json()
        assert body["verification_required"] is True and body["id"] == "" and body["email_verified"] is False
        assert len(verification) == 1 and verification[0]["to"] == "new@example.com"

        r = await _login(client, "new@example.com")
        assert r.status_code == 403 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
        # a wrong password never reveals the verification state
        assert (await _login(client, "new@example.com", "wrong")).status_code == 401

        bad = await client.post("/api/auth/verify-email", json={"token": "nope"})
        assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"

        token = _token_from(verification[0])
        assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
        assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400
        r = await _login(client, "new@example.com")
        assert r.status_code == 200
        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
        assert me.json()["email_verified"] is True

    @pytest.mark.asyncio
    async def test_token_is_stored_hashed_and_expires(self, client, db_session, verification):
        await _register(client, "exp@example.com")
        token = _token_from(verification[0])
        user = (await db_session.execute(select(User).where(User.email == "exp@example.com"))).scalar_one()
        assert user.email_verify_token_hash == security.hash_token(token) != token
        user.email_verify_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()
        assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400

    @pytest.mark.asyncio
    async def test_registration_does_not_reveal_existing_accounts(self, client, verification):
        first = await _register(client, "taken@example.com", name="Same")
        token = _token_from(verification[0])
        await client.post("/api/auth/verify-email", json={"token": token})
        verification.clear()

        again = await _register(client, "taken@example.com", password="some-other-password", name="Same")
        assert again.status_code == first.status_code == 201
        assert again.json() == first.json()
        # the real owner is told by email, and their password is untouched
        assert len(verification) == 1 and "already have" in verification[0]["subject"]
        assert (await _login(client, "taken@example.com")).status_code == 200
        assert (await _login(client, "taken@example.com", "some-other-password")).status_code == 401

    @pytest.mark.asyncio
    async def test_without_verification_duplicate_is_a_409(self, client):
        assert (await _register(client, "dup@example.com")).status_code == 201
        assert (await _register(client, "dup@example.com")).status_code == 409

    @pytest.mark.asyncio
    async def test_resend_always_answers_200(self, client, verification):
        await _register(client, "pending@example.com")
        verification.clear()
        for email in ("pending@example.com", "nobody@example.com"):
            r = await client.post("/api/auth/resend-verification", json={"email": email})
            assert r.status_code == 200 and r.json()["status"] == "ok"
        assert [m["to"] for m in verification] == ["pending@example.com"]
        # the newest link works
        assert (await client.post("/api/auth/verify-email",
                                  json={"token": _token_from(verification[0])})).status_code == 200

    @pytest.mark.asyncio
    async def test_existing_users_and_bootstrap_admin_count_as_verified(self, client, monkeypatch, outbox):
        await _register(client, "before@example.com")            # created while verification was off
        monkeypatch.setattr(settings, "require_email_verification", True)
        monkeypatch.setattr(settings, "admin_email", "boss@example.com")
        assert (await _login(client, "before@example.com")).status_code == 200
        await _register(client, "boss@example.com")
        assert (await _login(client, "boss@example.com")).status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_verify_and_create_verified_accounts(self, client, db_session, monkeypatch, outbox):
        admin_h = await _make_admin(client, db_session)
        monkeypatch.setattr(settings, "require_email_verification", True)
        await _register(client, "stuck@example.com")
        uid = (await db_session.execute(select(User.id).where(User.email == "stuck@example.com"))).scalar_one()
        r = await client.patch(f"/api/admin/users/{uid}", headers=admin_h, json={"email_verified": True})
        assert r.status_code == 200 and r.json()["email_verified"] is True
        assert (await _login(client, "stuck@example.com")).status_code == 200

        monkeypatch.setattr(settings, "registration_enabled", False)
        r = await client.post("/api/admin/users", headers=admin_h,
                              json={"email": "Made@Example.com", "password": "made-by-admin-pw", "full_name": "M"})
        assert r.status_code == 201 and r.json()["email"] == "made@example.com"
        assert (await _login(client, "made@example.com", "made-by-admin-pw")).status_code == 200
        dup = await client.post("/api/admin/users", headers=admin_h,
                                json={"email": "made@example.com", "password": "made-by-admin-pw"})
        assert dup.status_code == 409

    @pytest.mark.asyncio
    async def test_password_reset_by_email_also_verifies(self, client, db_session, verification):
        await _register(client, "reset@example.com")
        verification.clear()
        await client.post("/api/auth/forgot-password", json={"email": "reset@example.com"})
        # an unverified but active account can still ask for a reset link
        assert len(verification) == 1
        token = _token_from(verification[0])
        r = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "reset-long-password"})
        assert r.status_code == 200
        assert (await _login(client, "reset@example.com", "reset-long-password")).status_code == 200

    def test_refuses_to_start_without_smtp(self):
        with pytest.raises(RuntimeError, match="SMTP"):
            validate_settings(Settings(require_email_verification=True, smtp_host="", smtp_from="", debug=False))
        validate_settings(Settings(require_email_verification=True, smtp_host="", debug=True))
        validate_settings(Settings(require_email_verification=True, smtp_host="h", smtp_from="a@b.c"))
        with pytest.raises(RuntimeError, match="LOG_FORMAT"):
            validate_settings(Settings(log_format="xml"))


class TestErrorCodes:
    @pytest.mark.asyncio
    async def test_api_error_carries_code_and_headers(self):
        resp = await http_error_handler(None, ApiError(429, "slow down", code="TOO_MANY_ATTEMPTS",
                                                       headers={"Retry-After": "7"}))
        assert json.loads(resp.body) == {"error": {"code": "TOO_MANY_ATTEMPTS", "message": "slow down"}}
        assert resp.headers["retry-after"] == "7"

    @pytest.mark.asyncio
    async def test_plain_http_exception_keeps_default_code(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401 and r.json()["error"]["code"] == "HTTP_401"


# ---------------------------------------------------------------------------
# 6. Quotas and retention
# ---------------------------------------------------------------------------

class TestQuota:
    @pytest.mark.asyncio
    async def test_usage_endpoint(self, auth_client):
        r = await auth_client.get("/api/auth/me/usage")
        assert r.json() == {"used_bytes": 0, "quota_bytes": 0}
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        await auth_client.post(f"/api/projects/{pid}/datasets", files={"file": ("X.tsv", X_TSV, "text/plain")})
        assert (await auth_client.get("/api/auth/me/usage")).json()["used_bytes"] == len(X_TSV)

    @pytest.mark.asyncio
    async def test_upload_over_quota_is_refused(self, auth_client, monkeypatch):
        monkeypatch.setattr(settings, "user_quota_mb", 1)
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        blob = b"a" * (600 * 1024)
        ok = await auth_client.post(f"/api/projects/{pid}/datasets", files={"file": ("X.tsv", blob, "text/plain")})
        assert ok.status_code == 200
        over = await auth_client.post(f"/api/projects/{pid}/datasets", files={"file": ("y.tsv", blob, "text/plain")})
        assert over.status_code == 413
        assert over.json()["error"]["code"] == "QUOTA_EXCEEDED" and "quota" in over.json()["error"]["message"].lower()
        usage = (await auth_client.get("/api/auth/me/usage")).json()
        assert usage == {"used_bytes": len(blob), "quota_bytes": 1024 * 1024}

        # the dataset-library upload path is covered too
        ds_id = (await auth_client.get("/api/datasets/")).json()[0]["id"]
        over2 = await auth_client.post(f"/api/datasets/{ds_id}/files", files={"file": ("y.tsv", blob, "text/plain")})
        assert over2.status_code == 413

    @pytest.mark.asyncio
    async def test_job_directories_count(self, auth_client, db_session):
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        job_dir = Path(settings.project_dir) / pid / "jobs" / "abcdefabcdef"
        job_dir.mkdir(parents=True)
        (job_dir / "results.json").write_bytes(b"x" * 1000)
        assert (await auth_client.get("/api/auth/me/usage")).json()["used_bytes"] == 1000

    @pytest.mark.asyncio
    async def test_admin_user_list_shows_usage(self, client, db_session):
        admin_h = await _make_admin(client, db_session)
        user_h = await _headers(client, "data@example.com")
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=user_h)).json()["project_id"]
        await client.post(f"/api/projects/{pid}/datasets", headers=user_h, files={"file": ("X.tsv", X_TSV, "text/plain")})
        users = {u["email"]: u for u in (await client.get("/api/admin/users", headers=admin_h)).json()}
        assert users["data@example.com"]["used_bytes"] == len(X_TSV)
        assert users["root@example.com"]["used_bytes"] == 0 and users["root@example.com"]["email_verified"] is True
        lean = (await client.get("/api/admin/users", params={"include_usage": False}, headers=admin_h)).json()
        assert all(u["used_bytes"] is None for u in lean)


async def _old_job(db_session, client, headers, days_old, status="completed", jid=None):
    pid = (await client.post("/api/projects/", params={"name": f"p{days_old}{status}"}, headers=headers)).json()["project_id"]
    ended = datetime.now(timezone.utc) - timedelta(days=days_old)
    job = Job(project_id=pid, status=status, name="old", created_at=ended, completed_at=ended)
    if jid:
        job.id = jid
    db_session.add(job)
    await db_session.commit()
    job_dir = Path(settings.project_dir) / pid / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "results.json").write_bytes(b"r" * 500)
    return job.id, job_dir


class TestRetention:
    @pytest.mark.asyncio
    async def test_nothing_is_deleted_when_rules_are_off(self, auth_client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "job_retention_days", 0)
        monkeypatch.setattr(settings, "backup_retention_count", 0)
        jid, job_dir = await _old_job(db_session, auth_client, {}, 4000)
        backups = Path(settings.data_dir) / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        archive = backups / "predomics_backup_20200101_000000_aaaaaaaa.tar.gz"
        archive.write_bytes(b"z")
        try:
            report = retention.run_retention(dry_run=False)
            assert report["jobs"] == [] and report["backups"] == [] and report["bytes_freed"] == 0
            assert job_dir.exists() and archive.exists()
            assert retention.is_enabled() is False
        finally:
            archive.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_expired_finished_jobs_are_removed(self, auth_client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "job_retention_days", 30)
        old_id, old_dir = await _old_job(db_session, auth_client, {}, 45)
        recent_id, recent_dir = await _old_job(db_session, auth_client, {}, 5)
        running_id, running_dir = await _old_job(db_session, auth_client, {}, 90, status="running")

        dry = retention.run_retention(dry_run=True)
        assert [j["job_id"] for j in dry["jobs"]] == [old_id] and dry["bytes_freed"] == 500
        assert old_dir.exists()

        done = retention.run_retention(dry_run=False)
        assert [j["job_id"] for j in done["jobs"]] == [old_id]
        assert not old_dir.exists() and recent_dir.exists() and running_dir.exists()
        db_session.expire_all()
        left = {j for (j,) in (await db_session.execute(select(Job.id))).all()}
        assert left == {recent_id, running_id}

    def test_only_newest_backups_are_kept(self, monkeypatch):
        monkeypatch.setattr(settings, "backup_retention_count", 2)
        backups = Path(settings.data_dir) / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        made = []
        try:
            for i in range(4):
                f = backups / f"predomics_backup_2026010{i}_000000_{i:08d}.tar.gz"
                f.write_bytes(b"b" * 10)
                sidecar = f.with_name(f.name + ".manifest.json")
                sidecar.write_text("{}")
                os.utime(f, (1_700_000_000 + i * 100, 1_700_000_000 + i * 100))
                made += [f, sidecar]
            other = backups / "notes.txt"
            other.write_text("keep me")
            made.append(other)

            assert len(retention.run_retention(dry_run=True)["backups"]) == 2
            assert all(p.exists() for p in made)
            report = retention.run_retention(dry_run=False)
            assert sorted(b["file"] for b in report["backups"]) == [made[0].name, made[2].name]
            assert not made[0].exists() and not made[1].exists() and not made[2].exists() and not made[3].exists()
            assert made[4].exists() and made[5].exists() and made[6].exists() and made[7].exists()
            assert other.exists()
        finally:
            for p in made:
                p.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_admin_endpoint_defaults_to_dry_run(self, client, db_session, monkeypatch):
        monkeypatch.setattr(settings, "job_retention_days", 30)
        admin_h = await _make_admin(client, db_session)
        user_h = await _headers(client, "plain@example.com")
        old_id, old_dir = await _old_job(db_session, client, admin_h, 60)

        assert (await client.post("/api/admin/retention/run", headers=user_h)).status_code == 403
        dry = await client.post("/api/admin/retention/run", headers=admin_h)
        assert dry.status_code == 200 and dry.json()["dry_run"] is True
        assert [j["job_id"] for j in dry.json()["jobs"]] == [old_id] and old_dir.exists()
        real = await client.post("/api/admin/retention/run", params={"dry_run": False}, headers=admin_h)
        assert real.json()["dry_run"] is False and not old_dir.exists()


# ---------------------------------------------------------------------------
# 7. Access check
# ---------------------------------------------------------------------------

class TestProjectAccess:
    @pytest.mark.asyncio
    async def test_light_check_loads_nothing_extra_unless_asked(self, auth_client, db_session):
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        user = (await db_session.execute(select(User).where(User.email == "test@example.com"))).scalar_one()
        db_session.expunge_all()

        project, role = await get_project_access(pid, user, db_session)
        assert role == "owner"
        assert not {"jobs", "shares", "dataset_links"} & set(project.__dict__)

        db_session.expunge_all()
        project, _ = await get_project_access(pid, user, db_session, jobs=True)
        assert "jobs" in project.__dict__ and "shares" not in project.__dict__

        db_session.expunge_all()
        project, _ = await get_project_with_access(pid, user, db_session)
        assert {"jobs", "shares", "dataset_links"} <= set(project.__dict__)

    @pytest.mark.asyncio
    async def test_roles_for_shared_users(self, client, db_session):
        from fastapi import HTTPException

        owner_h = await _headers(client, "o@example.com")
        await _register(client, "v@example.com")
        await _register(client, "nobody@example.com")
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=owner_h)).json()["project_id"]
        await client.post(f"/api/projects/{pid}/share", headers=owner_h, json={"email": "V@Example.com", "role": "viewer"})
        viewer = (await db_session.execute(select(User).where(User.email == "v@example.com"))).scalar_one()
        nobody = (await db_session.execute(select(User).where(User.email == "nobody@example.com"))).scalar_one()

        _, role = await get_project_access(pid, viewer, db_session)
        assert role == "viewer"
        with pytest.raises(HTTPException) as e:
            await get_project_access(pid, viewer, db_session, require_role="editor")
        assert e.value.status_code == 403
        for user, required in ((viewer, "owner"), (nobody, "viewer")):
            with pytest.raises(HTTPException) as e:
                await get_project_access(pid, user, db_session, require_role=required)
            assert e.value.status_code == 404
        with pytest.raises(HTTPException) as e:
            await get_project_access("doesnotexist", viewer, db_session)
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_project_owner_can_delete_someone_elses_comment(self, client):
        owner_h = await _headers(client, "o@example.com")
        guest_h = await _headers(client, "g@example.com")
        third_h = await _headers(client, "t@example.com")
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=owner_h)).json()["project_id"]
        for email in ("g@example.com", "t@example.com"):
            await client.post(f"/api/projects/{pid}/share", headers=owner_h, json={"email": email, "role": "viewer"})
        cid = (await client.post(f"/api/projects/{pid}/comments", headers=guest_h, json={"content": "hi"})).json()["id"]
        assert (await client.delete(f"/api/projects/{pid}/comments/{cid}", headers=third_h)).status_code == 403
        assert (await client.delete(f"/api/projects/{pid}/comments/{cid}", headers=owner_h)).status_code == 200
        assert (await client.get(f"/api/projects/{pid}/comments", headers=owner_h)).json() == []


# ---------------------------------------------------------------------------
# 8. Observability
# ---------------------------------------------------------------------------

@pytest.fixture
def obs_app(monkeypatch):
    """A small app with the observability hooks installed, and the root logger restored afterwards."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    uvicorn_access = logging.getLogger("uvicorn.access")
    saved_disabled = uvicorn_access.disabled
    small = FastAPI()

    @small.get("/api/items/{item_id}")
    async def item(item_id: str):
        logging.getLogger("app.test").info("handling %s", item_id, extra={"item": item_id})
        return {"id": item_id}

    yield small
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    uvicorn_access.disabled = saved_disabled


class TestObservability:
    def test_json_formatter(self):
        record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
        record.request_id = "req-12345678"
        record.user_id = "u1"
        out = json.loads(observability.JsonFormatter().format(record))
        assert out["message"] == "hello world" and out["level"] == "WARNING" and out["logger"] == "app.x"
        assert out["request_id"] == "req-12345678" and out["user_id"] == "u1" and out["time"].endswith("+00:00")

    @pytest.mark.asyncio
    async def test_request_id_and_access_line(self, obs_app, monkeypatch, capsys):
        monkeypatch.setattr(settings, "log_format", "json")
        monkeypatch.setattr(settings, "log_level", "INFO")
        observability.install(obs_app)
        token = security.create_access_token("user-42")
        async with AsyncClient(transport=ASGITransport(app=obs_app), base_url="http://t") as c:
            r1 = await c.get("/api/items/7", headers={"Authorization": f"Bearer {token}"})
            r2 = await c.get("/api/items/8", headers={"X-Request-ID": "trace-abcdef123456"})
            r3 = await c.get("/api/items/9", headers={"X-Request-ID": "bad id\twith junk"})
        assert re.fullmatch(r"[0-9a-f]{16}", r1.headers["x-request-id"])
        assert r2.headers["x-request-id"] == "trace-abcdef123456"
        assert re.fullmatch(r"[0-9a-f]{16}", r3.headers["x-request-id"])

        lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
        access = [entry for entry in lines if entry["logger"] == "predomics.access"]
        assert len(access) == 3
        first = access[0]
        assert first["method"] == "GET" and first["route"] == "/api/items/{item_id}" and first["path"] == "/api/items/7"
        assert first["status"] == 200 and first["user_id"] == "user-42" and first["duration_ms"] >= 0
        assert first["request_id"] == r1.headers["x-request-id"]
        # application log lines inside the request carry the same id
        handler_line = next(entry for entry in lines if entry["logger"] == "app.test" and entry["item"] == "7")
        assert handler_line["request_id"] == r1.headers["x-request-id"]

    @pytest.mark.asyncio
    async def test_text_format_and_level(self, obs_app, monkeypatch, capsys):
        monkeypatch.setattr(settings, "log_format", "text")
        monkeypatch.setattr(settings, "log_level", "WARNING")
        observability.install(obs_app)
        async with AsyncClient(transport=ASGITransport(app=obs_app), base_url="http://t") as c:
            await c.get("/api/items/7")
        logging.getLogger("app.test").warning("careful")
        err = capsys.readouterr().err
        assert "predomics.access" not in err and "handling 7" not in err      # INFO is filtered out
        assert re.search(r"WARNING app\.test \[-\]: careful", err)

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, obs_app, monkeypatch, db_session):
        observability.install(obs_app)
        metrics.install(obs_app)
        async with AsyncClient(transport=ASGITransport(app=obs_app), base_url="http://t") as c:
            monkeypatch.setattr(settings, "metrics_token", "")
            assert (await c.get("/metrics")).status_code == 404            # disabled by default
            monkeypatch.setattr(settings, "metrics_token", "scrape-secret")
            assert (await c.get("/metrics")).status_code == 401
            assert (await c.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 401
            await c.get("/api/items/7")
            await c.get("/nope")
            r = await c.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
        if not metrics.HAS_PROMETHEUS:
            assert r.status_code == 503
            return
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
        text = r.text
        assert 'predomics_http_requests_total{method="GET",route="/api/items/{item_id}",status="200"}' in text
        assert 'route="(unmatched)",status="404"' in text
        assert "/api/items/7" not in text                                   # templates, not raw paths
        assert "predomics_http_request_duration_seconds_bucket" in text
        for status in ("pending", "running", "completed", "failed"):
            assert f'predomics_jobs{{status="{status}"}}' in text
        assert "predomics_jobs_running 0.0" in text and "predomics_jobs_queued 0.0" in text
        assert "predomics_data_disk_free_bytes" in text and "predomics_app_info{version=" in text
        assert "/metrics" not in obs_app.openapi()["paths"]

    def test_sentry_is_optional(self, monkeypatch):
        monkeypatch.setattr(settings, "sentry_dsn", "")
        assert observability._init_sentry() is False
        monkeypatch.setattr(settings, "sentry_dsn", "https://key@sentry.invalid/1")
        import builtins
        real_import = builtins.__import__

        def _no_sentry(name, *a, **k):
            if name == "sentry_sdk":
                raise ImportError(name)
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _no_sentry)
        assert observability._init_sentry() is False                          # warns, does not crash


# ---------------------------------------------------------------------------
# 9. Typed responses and public endpoints
# ---------------------------------------------------------------------------

_MY_TAGS = {"auth", "datasets", "projects", "admin", "samples", "comments", "sharing", "health"}


class TestOpenApi:
    def test_my_routers_declare_their_responses(self):
        schema = app.openapi()
        untyped = []
        for path, ops in schema["paths"].items():
            for method, op in ops.items():
                if not _MY_TAGS & set(op.get("tags", [])):
                    continue
                ok = op["responses"].get("200") or op["responses"].get("201") or {}
                content = ok.get("content", {})
                if "application/gzip" in content:
                    continue
                if content.get("application/json", {}).get("schema", {}) == {}:
                    untyped.append(f"{method.upper()} {path}")
        assert untyped == []

    def test_api_docs_switch_exists(self):
        assert Settings.model_fields["api_docs"].default is True

    @pytest.mark.asyncio
    async def test_public_catalogues_carry_no_user_data(self, client):
        samples = await client.get("/api/samples/")
        assert samples.status_code == 200
        assert all(set(s) == {"id", "name", "description", "available", "files"} for s in samples.json())
        assert (await client.get("/api/admin/templates/public")).status_code == 200
        assert (await client.get("/api/admin/templates/")).status_code == 401


class TestTypedResponsesKeepTheirFields:
    @pytest.mark.asyncio
    async def test_dataset_endpoints(self, auth_client):
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        await auth_client.post(f"/api/projects/{pid}/datasets", files={"file": ("X.tsv", X_TSV, "text/plain")})
        ds = (await auth_client.get("/api/datasets/")).json()[0]
        fid = ds["files"][0]["id"]

        preview = (await auth_client.get(f"/api/datasets/{ds['id']}/files/{fid}/preview")).json()
        assert {"filename", "role", "total_rows", "total_cols", "columns", "rows", "stats",
                "delimiter", "file_size_bytes"} <= set(preview)
        assert preview["total_rows"] == 2 and preview["file_size_bytes"] == len(X_TSV)

        added = await auth_client.post(f"/api/datasets/{ds['id']}/files",
                                       files={"file": ("y.tsv", b"id\tclass\ns1\t0\ns2\t1\n", "text/plain")})
        assert set(added.json()) == {"id", "filename", "role"} and added.json()["role"] == "ytrain"
        cols = await auth_client.get(f"/api/datasets/{ds['id']}/metadata-columns")
        assert cols.status_code in (200, 400, 404)
        if cols.status_code == 200:
            assert isinstance(cols.json()["columns"], list)
        scan = await auth_client.post(f"/api/datasets/{ds['id']}/scan")
        assert scan.status_code in (200, 400)
        if scan.status_code == 200:
            assert isinstance(scan.json(), dict) and scan.json()

        versions = (await auth_client.get(f"/api/datasets/{ds['id']}/versions")).json()
        assert set(versions[0]) == {"id", "version_number", "files_snapshot", "note", "created_at"}
        assert set(versions[0]["files_snapshot"][0]) == {"id", "filename", "role"}

        names = await auth_client.patch(f"/api/datasets/{ds['id']}/class-names",
                                        json={"class_names": {"0": "Healthy", "1": "Sick"}})
        assert names.json() == {"class_names": {"0": "Healthy", "1": "Sick"}}
        tags = (await auth_client.get("/api/datasets/tags/suggestions")).json()
        assert set(tags) == {"suggestions"} and all(isinstance(t, str) for t in tags["suggestions"])
        restored = await auth_client.post(f"/api/datasets/{ds['id']}/versions/{versions[0]['id']}/restore")
        assert set(restored.json()) == {"status", "version_number", "files_restored"}
        assert (await auth_client.delete(f"/api/datasets/{ds['id']}/assign/{pid}")).json() == {"status": "unassigned"}
        assert (await auth_client.delete(f"/api/datasets/{ds['id']}")).json() == {"status": "deleted"}

    @pytest.mark.asyncio
    async def test_comment_and_share_shapes(self, client):
        owner_h = await _headers(client, "o@example.com")
        await _register(client, "g@example.com")
        guest_h = {"Authorization": f"Bearer {(await _login(client, 'g@example.com')).json()['access_token']}"}
        pid = (await client.post("/api/projects/", params={"name": "p"}, headers=owner_h)).json()["project_id"]
        share = (await client.post(f"/api/projects/{pid}/share", headers=owner_h,
                                   json={"email": "g@example.com", "role": "viewer"})).json()
        upd = await client.put(f"/api/projects/{pid}/shares/{share['id']}", headers=owner_h,
                               json={"email": "g@example.com", "role": "editor"})
        assert upd.json() == {"status": "updated", "role": "editor"}
        mine = (await client.get("/api/projects/shared-with-me", headers=guest_h)).json()
        assert mine == [{"project_id": pid, "name": "p", "created_at": mine[0]["created_at"], "role": "editor",
                         "owner_email": "o@example.com", "owner_name": "U"}]

        c = (await client.post(f"/api/projects/{pid}/comments", headers=guest_h, json={"content": " hello "})).json()
        assert set(c) == {"id", "project_id", "user_id", "user_name", "content", "created_at", "updated_at"}
        assert c["content"] == "hello" and c["user_name"] == "U"
        edited = await client.put(f"/api/projects/{pid}/comments/{c['id']}", headers=guest_h, json={"content": "bye"})
        assert set(edited.json()) == {"id", "content", "updated_at"}
        empty = await client.put(f"/api/projects/{pid}/comments/{c['id']}", headers=guest_h, json={"content": "  "})
        assert empty.status_code == 400
        assert (await client.delete(f"/api/projects/{pid}/shares/{share['id']}", headers=owner_h)).json() == {"status": "revoked"}

    @pytest.mark.asyncio
    async def test_admin_shapes(self, client, db_session, tmp_path, monkeypatch):
        from app.routers import admin as admin_router, templates as templates_router
        monkeypatch.setattr(admin_router, "DEFAULTS_PATH", tmp_path / "admin_defaults.json")
        monkeypatch.setattr(templates_router, "TEMPLATES_PATH", tmp_path / "templates.json")
        admin_h = await _make_admin(client, db_session)

        put = await client.put("/api/admin/defaults", headers=admin_h, json={"ga.population_size": 300, "voting.vote": True})
        assert put.json() == {"ga.population_size": 300, "voting.vote": True}
        assert (await client.get("/api/admin/defaults", headers=admin_h)).json() == put.json()

        tpl = (await client.post("/api/admin/templates/", headers=admin_h,
                                 json={"name": "Quick", "params": {"ga": {"max_epochs": 5}}})).json()
        assert set(tpl) == {"id", "name", "description", "category", "params"} and tpl["params"] == {"ga": {"max_epochs": 5}}
        assert (await client.get("/api/admin/templates/public")).json() == [tpl]
        assert (await client.delete(f"/api/admin/templates/{tpl['id']}", headers=admin_h)).json() == {"status": "deleted"}

        log = (await client.get("/api/admin/audit-log", headers=admin_h)).json()
        assert set(log) == {"total", "page", "per_page", "entries"} and log["total"] >= 1
        assert {"id", "user_email", "action", "created_at"} <= set(log["entries"][0])

        keys = await client.post("/api/auth/api-keys", headers=admin_h, json={"name": "k"})
        assert set(keys.json()) == {"id", "name", "prefix", "key", "created_at"}
        listed = (await client.get("/api/auth/api-keys", headers=admin_h)).json()
        assert set(listed[0]) == {"id", "name", "prefix", "is_active", "last_used_at", "created_at"}
        assert (await client.delete(f"/api/auth/api-keys/{listed[0]['id']}", headers=admin_h)).json() == {"status": "revoked"}
