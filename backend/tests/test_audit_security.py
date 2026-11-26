"""Regression tests for the security findings of the November 2026 audit.

Each test names the finding it guards (SEC-n in the audit document).
"""

from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.core import security
from app.core.config import settings
from app.services import storage

try:  # fixtures live in test_api.py unless they have been moved to conftest.py
    from .test_api import db_session, client, auth_client, clean_data  # noqa: F401
except ImportError:  # pragma: no cover
    pass

X_TSV = b"id\ts1\ts2\nf1\t0.1\t0.2\nf2\t0.3\t0.4\n"


async def _register(client, email, password="a-long-password", name="U"):
    return await client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": name,
    })


async def _login(client, email, password="a-long-password"):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r


async def _headers(client, email, password="a-long-password"):
    await _register(client, email, password)
    r = await _login(client, email, password)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# SEC-1: upload filename traversal
# ---------------------------------------------------------------------------

class TestUploadFilename:
    @pytest.mark.parametrize("name,expected", [
        ("x/../../../../app/backend/app/main.py", "main.py"),
        ("..\\..\\evil.py", "evil.py"),
        ("Xtrain.tsv", "Xtrain.tsv"),
        ("...", "file"),
        ("", "file"),
        (None, "file"),
        (".env", "env"),
    ])
    def test_safe_filename(self, name, expected):
        assert storage.safe_filename(name) == expected

    def test_safe_filename_is_single_component(self):
        for name in ["a/b", "/etc/passwd", "..", "../..", "a\x00b", "C:\\x\\y.tsv"]:
            out = storage.safe_filename(name)
            assert "/" not in out and "\\" not in out and out not in ("", ".", "..")

    def test_save_rejects_unsafe_ids(self):
        with pytest.raises(ValueError):
            storage.save_user_dataset_file("../other", "abc", "x.tsv", b"x")
        with pytest.raises(ValueError):
            storage.save_user_dataset_file("user", "../../abc", "x.tsv", b"x")

    @pytest.mark.asyncio
    async def test_traversal_upload_stays_in_user_directory(self, auth_client):
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        evil = "x/../../../../../../pwned_by_upload.txt"
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets", files={"file": (evil, X_TSV, "text/plain")},
        )
        assert resp.status_code == 200
        base = (Path(settings.data_dir) / "datasets").resolve()
        written = [p for p in base.rglob("*") if p.is_file()]
        assert written, "the upload should have been stored"
        assert all(p.resolve().is_relative_to(base) for p in written)
        assert not list(Path(settings.data_dir).resolve().parent.glob("pwned_by_upload.txt"))
        # the stored display name carries no path
        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        assert proj["datasets"][0]["files"][0]["filename"] == "pwned_by_upload.txt"

    @pytest.mark.asyncio
    async def test_upload_role_is_honoured(self, auth_client):
        """FE-3: a file with an arbitrary name lands in the slot the user chose."""
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets", params={"role": "xtrain"},
            files={"file": ("abundance.tsv", X_TSV, "text/plain")},
        )
        assert resp.status_code == 200
        proj = (await auth_client.get(f"/api/projects/{pid}")).json()
        assert proj["datasets"][0]["files"][0]["role"] == "xtrain"

        bad = await auth_client.post(
            f"/api/projects/{pid}/datasets", params={"role": "../x"},
            files={"file": ("abundance.tsv", X_TSV, "text/plain")},
        )
        assert bad.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_size_limit(self, auth_client, monkeypatch):
        """SEC-11: uploads over PREDOMICS_MAX_UPLOAD_MB are refused with 413."""
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        monkeypatch.setattr(settings, "max_upload_mb", 1)
        big = b"a" * (1024 * 1024 + 10)
        resp = await auth_client.post(
            f"/api/projects/{pid}/datasets", files={"file": ("X.tsv", big, "text/plain")},
        )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# SEC-2: password reset token must not be returned
# ---------------------------------------------------------------------------

class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_forgot_password_never_returns_token(self, client, monkeypatch):
        monkeypatch.setattr(settings, "debug", False)
        await _register(client, "victim@example.com")
        for email in ("victim@example.com", "nobody@example.com"):
            resp = await client.post("/api/auth/forgot-password", json={"email": email})
            assert resp.status_code == 200
            body = resp.json()
            assert "token" not in body
            assert body == {"status": "ok", "message": "If the email exists, a reset link has been sent"}

    @pytest.mark.asyncio
    async def test_reset_with_valid_token_and_single_use(self, client, db_session):
        from app.models.db_models import User, PasswordResetToken
        from datetime import datetime, timedelta, timezone

        await _register(client, "reset@example.com")
        user = (await db_session.execute(select(User).where(User.email == "reset@example.com"))).scalar_one()
        db_session.add(PasswordResetToken(
            user_id=user.id, token_hash=security.hash_token("the-raw-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        await db_session.commit()

        bad = await client.post("/api/auth/reset-password",
                                json={"token": "wrong", "new_password": "another-long-password"})
        assert bad.status_code == 400
        ok = await client.post("/api/auth/reset-password",
                               json={"token": "the-raw-token", "new_password": "another-long-password"})
        assert ok.status_code == 200
        assert (await _login(client, "reset@example.com", "another-long-password")).status_code == 200
        again = await client.post("/api/auth/reset-password",
                                  json={"token": "the-raw-token", "new_password": "third-long-password"})
        assert again.status_code == 400


# ---------------------------------------------------------------------------
# SEC-5 / SEC-12 / SEC-14: accounts and tokens
# ---------------------------------------------------------------------------

class TestAccounts:
    @pytest.mark.asyncio
    async def test_register_validates_email_and_password(self, client, monkeypatch):
        monkeypatch.setattr(settings, "password_min_length", 8)
        assert (await _register(client, "not-an-email")).status_code == 422
        assert (await _register(client, "ok@example.com", password="short")).status_code == 422
        assert (await _register(client, "ok@example.com")).status_code == 201

    @pytest.mark.asyncio
    async def test_email_is_case_insensitive(self, client):
        assert (await _register(client, "Mixed.Case@Example.com")).status_code == 201
        assert (await _register(client, "mixed.case@example.com")).status_code == 409
        assert (await _login(client, "MIXED.CASE@EXAMPLE.COM")).status_code == 200

    @pytest.mark.asyncio
    async def test_registration_can_be_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "registration_enabled", False)
        assert (await _register(client, "late@example.com")).status_code == 403

    @pytest.mark.asyncio
    async def test_admin_email_bootstrap(self, client, monkeypatch):
        monkeypatch.setattr(settings, "admin_email", "Boss@Example.com")
        h = await _headers(client, "boss@example.com")
        assert (await client.get("/api/auth/me", headers=h)).json()["is_admin"] is True
        h2 = await _headers(client, "prifti-lookalike@example.com")
        assert (await client.get("/api/auth/me", headers=h2)).json()["is_admin"] is False

    @pytest.mark.asyncio
    async def test_password_change_invalidates_old_tokens(self, client):
        h_old = await _headers(client, "rotate@example.com")
        assert (await client.get("/api/auth/me", headers=h_old)).status_code == 200
        resp = await client.put("/api/auth/me/password", headers=h_old, json={
            "current_password": "a-long-password", "new_password": "a-new-long-password",
        })
        assert resp.status_code == 200
        assert (await client.get("/api/auth/me", headers=h_old)).status_code == 401
        h_new = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        assert (await client.get("/api/auth/me", headers=h_new)).status_code == 200

    @pytest.mark.asyncio
    async def test_long_password_does_not_crash(self, client):
        pw = "x" * 200
        assert (await _register(client, "long@example.com", password=pw)).status_code == 201
        assert (await _login(client, "long@example.com", pw)).status_code == 200

    @pytest.mark.asyncio
    async def test_user_search_cannot_enumerate_with_wildcards(self, client):
        h = await _headers(client, "searcher@example.com")
        await _register(client, "alice@example.com")
        await _register(client, "bob@example.com")
        for q in ("%", "__", "%%%", "___", "%a%", "a%"):
            r = await client.get("/api/auth/users/search", params={"q": q}, headers=h)
            assert r.status_code == 200 and r.json() == [], q
        r = await client.get("/api/auth/users/search", params={"q": "ali"}, headers=h)
        assert [u["email"] for u in r.json()] == ["alice@example.com"]

    @pytest.mark.asyncio
    async def test_api_key_authenticates_and_junk_key_does_not(self, client):
        h = await _headers(client, "keys@example.com")
        key = (await client.post("/api/auth/api-keys", headers=h, json={"name": "k"})).json()["key"]
        assert (await client.get("/api/auth/me", headers={"X-API-Key": key})).status_code == 200
        assert (await client.get("/api/auth/me", headers={"X-API-Key": key[:-1] + "x"})).status_code == 401
        assert (await client.get("/api/auth/me", headers={"X-API-Key": "junk"})).status_code == 401


class TestRateLimitKey:
    """SEC-8: an arbitrary X-API-Key header must not select the rate-limit bucket."""

    def _request(self, headers):
        from starlette.requests import Request
        scope = {
            "type": "http", "method": "POST", "path": "/api/auth/login", "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("203.0.113.9", 1234),
        }
        return Request(scope)

    def test_junk_api_key_falls_back_to_ip(self):
        from app.core.rate_limit import _get_user_or_ip, get_ip
        a = _get_user_or_ip(self._request({"X-API-Key": "aaaaaaaa1"}))
        b = _get_user_or_ip(self._request({"X-API-Key": "bbbbbbbb2"}))
        assert a == b == "203.0.113.9"
        assert get_ip(self._request({"Authorization": "Bearer whatever"})) == "203.0.113.9"

    def test_valid_jwt_keys_by_user(self):
        from app.core.rate_limit import _get_user_or_ip
        token = security.create_access_token("user-1")
        assert _get_user_or_ip(self._request({"Authorization": f"Bearer {token}"})) == "user-1"


# ---------------------------------------------------------------------------
# SEC-3: secret key defaults
# ---------------------------------------------------------------------------

class TestSecretKey:
    def test_known_default_is_replaced_and_persisted(self, tmp_path):
        from app.core.config import Settings, _resolve_secret_key
        s = Settings(secret_key="change-me-in-production", data_dir=tmp_path, debug=False)
        key = _resolve_secret_key(s)
        assert key not in ("change-me-in-production", "CHANGE-ME-IN-PRODUCTION", "") and len(key) >= 32
        key_file = tmp_path / ".secret_key"
        assert key_file.read_text() == key
        assert (key_file.stat().st_mode & 0o077) == 0
        # stable across restarts
        assert _resolve_secret_key(Settings(secret_key="", data_dir=tmp_path, debug=False)) == key

    def test_explicit_secret_is_kept(self, tmp_path):
        from app.core.config import Settings, _resolve_secret_key
        explicit = "an-explicit-secret-key-that-is-long-enough-0123456789"
        s = Settings(secret_key=explicit, data_dir=tmp_path)
        assert _resolve_secret_key(s) == explicit
        assert not (tmp_path / ".secret_key").exists()


# ---------------------------------------------------------------------------
# SEC-10: webhook SSRF
# ---------------------------------------------------------------------------

class TestWebhookUrl:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:5432/", "http://localhost/", "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/hook", "http://192.168.1.1/", "http://[::1]/", "ftp://example.com/x",
        "file:///etc/passwd", "http://user:pw@8.8.8.8/", "not a url", "",
    ])
    def test_internal_or_malformed_urls_are_rejected(self, url, monkeypatch):
        from app.services.webhooks import validate_webhook_url, UnsafeWebhookURL
        monkeypatch.setattr(settings, "webhook_allow_private", False)
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url(url)

    def test_public_ip_is_accepted(self, monkeypatch):
        from app.services.webhooks import validate_webhook_url
        monkeypatch.setattr(settings, "webhook_allow_private", False)
        assert validate_webhook_url("https://8.8.8.8/hook") == "https://8.8.8.8/hook"

    @pytest.mark.asyncio
    async def test_create_webhook_rejects_internal_target(self, client, monkeypatch):
        monkeypatch.setattr(settings, "webhook_allow_private", False)
        h = await _headers(client, "hooks@example.com")
        r = await client.post("/api/webhooks/", headers=h,
                              json={"name": "x", "url": "http://127.0.0.1:8000/api/admin/users"})
        assert r.status_code == 422
        r = await client.post("/api/webhooks/", headers=h,
                              json={"name": "x", "url": "https://8.8.8.8/hook", "events": ["nope"]})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# SEC-7: signature zoo authorization
# ---------------------------------------------------------------------------

SIG = {"name": "S", "disease": "d", "features": [{"name": "f1", "coefficient": 1, "direction": "enriched"}]}


class TestSignatureZoo:
    @pytest.fixture(autouse=True)
    def _isolated_zoo(self, tmp_path, monkeypatch):
        from app.routers import signature_zoo
        monkeypatch.setattr(signature_zoo, "ZOO_PATH", tmp_path / "signature_zoo.json")
        monkeypatch.setattr(signature_zoo, "_LOCK_PATH", tmp_path / "signature_zoo.lock")

    @pytest.mark.asyncio
    async def test_only_creator_or_admin_can_update(self, client, db_session):
        from app.models.db_models import User
        owner = await _headers(client, "owner@example.com")
        other = await _headers(client, "other@example.com")
        sid = (await client.post("/api/signature-zoo/", headers=owner, json=SIG)).json()["id"]

        assert (await client.put(f"/api/signature-zoo/{sid}", headers=other,
                                 json={**SIG, "name": "hijacked"})).status_code == 403
        assert (await client.put(f"/api/signature-zoo/{sid}", headers=owner,
                                 json={**SIG, "name": "renamed"})).status_code == 200

        await db_session.execute(update(User).where(User.email == "other@example.com").values(is_admin=True))
        await db_session.commit()
        assert (await client.put(f"/api/signature-zoo/{sid}", headers=other,
                                 json={**SIG, "name": "by admin"})).status_code == 200

    @pytest.mark.asyncio
    async def test_public_listing_hides_contributor_email(self, client):
        owner = await _headers(client, "owner@example.com")
        sid = (await client.post("/api/signature-zoo/", headers=owner, json=SIG)).json()["id"]
        listed = (await client.get("/api/signature-zoo/")).json()
        one = (await client.get(f"/api/signature-zoo/{sid}")).json()
        assert "owner@example.com" not in str(listed) + str(one)

    @pytest.mark.asyncio
    async def test_import_requires_project_access_and_plain_ids(self, client, auth_client):
        pid = (await auth_client.post("/api/projects/", params={"name": "mine"})).json()["project_id"]
        stranger = await _headers(client, "stranger@example.com")
        body = {"project_id": pid, "job_id": "abcdefabcdef", "name": "x", "disease": "d"}
        r = await client.post("/api/signature-zoo/import-from-job", headers=stranger, json=body)
        assert r.status_code == 404
        for evil in ("../../..", "..", "a/b"):
            r = await client.post("/api/signature-zoo/import-from-job", headers=stranger,
                                  json={**body, "project_id": evil})
            assert r.status_code == 404

    def test_corrupt_file_is_not_treated_as_empty(self, tmp_path):
        from app.routers import signature_zoo
        signature_zoo.ZOO_PATH.write_text("{not json")
        with pytest.raises(Exception):
            signature_zoo._load_signatures()


# ---------------------------------------------------------------------------
# SEC-17 / SEC-18: information exposure
# ---------------------------------------------------------------------------

class TestExposure:
    @pytest.mark.asyncio
    async def test_health_hides_internal_addresses(self, client):
        body = (await client.get("/health")).json()
        assert body["status"] == "ok" and "version" in body
        assert "scitq_server" not in body

    @pytest.mark.asyncio
    async def test_readiness_checks_database(self, client):
        r = await client.get("/health/ready")
        assert r.status_code == 200 and r.json()["database"] == "ok"

    @pytest.mark.asyncio
    async def test_security_headers_present(self, client):
        r = await client.get("/health")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_validation_errors_use_the_error_envelope(self, client):
        r = await client.post("/api/auth/login", json={"email": "x@example.com"})
        assert r.status_code == 422
        body = r.json()
        assert body["error"]["code"] == "VALIDATION_ERROR" and "password" in body["error"]["message"]
        assert isinstance(body["detail"], list)

    @pytest.mark.asyncio
    async def test_dataset_versions_do_not_leak_server_paths(self, auth_client):
        pid = (await auth_client.post("/api/projects/", params={"name": "p"})).json()["project_id"]
        await auth_client.post(f"/api/projects/{pid}/datasets", files={"file": ("X.tsv", X_TSV, "text/plain")})
        ds_id = (await auth_client.get("/api/datasets/")).json()[0]["id"]
        await auth_client.post(f"/api/datasets/{ds_id}/files", files={"file": ("y.tsv", b"id\tc\ns1\t0\n", "text/plain")})
        versions = (await auth_client.get(f"/api/datasets/{ds_id}/versions")).json()
        assert versions and "disk_path" not in str(versions)

    @pytest.mark.asyncio
    async def test_scitq_token_is_never_returned(self, client, db_session, tmp_path, monkeypatch):
        from app.models.db_models import User
        from app.services import scitq_client
        monkeypatch.setattr(scitq_client, "_CONFIG_PATH", tmp_path / "scitq_config.json")
        h = await _headers(client, "admin2@example.com")
        await db_session.execute(update(User).where(User.email == "admin2@example.com").values(is_admin=True))
        await db_session.commit()
        r = await client.put("/api/admin/scitq", headers=h,
                             json={"server": "s:5000", "token": "super-secret-token", "container": "c"})
        assert r.status_code == 200 and r.json()["token_set"] is True
        got = (await client.get("/api/admin/scitq", headers=h)).json()
        assert "super-secret-token" not in str(got) and got["token_set"] is True
        # an empty token keeps the stored one
        await client.put("/api/admin/scitq", headers=h, json={"server": "s:5000", "token": "", "container": "c"})
        assert scitq_client.get_config()["token"] == "super-secret-token"
