"""Password hashing and JWT token utilities."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from .config import settings

_BCRYPT_MAX_BYTES = 72  # bcrypt ignores (older versions) or rejects (>= 5.0) anything longer


def _pw_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_pw_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode("utf-8"))
    except ValueError:  # malformed stored hash
        return False


_dummy_hash: str | None = None


def verify_password_or_dummy(plain: str, hashed: str | None) -> bool:
    """Like :func:`verify_password`, but spends the same time when there is no hash.

    Used at login so that a response for an unknown email takes as long as one
    for a wrong password, and timing does not reveal which accounts exist.
    """
    global _dummy_hash
    if hashed is None:
        if _dummy_hash is None:
            _dummy_hash = hash_password("not-a-real-password")
        verify_password(plain, _dummy_hash)
        return False
    return verify_password(plain, hashed)


def hash_token(raw: str) -> str:
    """Fast, indexable hash for high-entropy random tokens (reset tokens).

    bcrypt is for low-entropy passwords; a 256-bit random token only needs SHA-256,
    which allows a direct database lookup instead of a scan.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def password_fingerprint(hashed_password: str) -> str:
    """Short keyed digest of a user's current password hash.

    Embedded in access tokens so that changing or resetting the password
    invalidates every token issued before it.
    """
    return hmac.new(
        settings.secret_key.encode("utf-8"), hashed_password.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:16]


def create_access_token(user_id: str, hashed_password: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if hashed_password:
        payload["pwd"] = password_fingerprint(hashed_password)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Return the verified token payload, or None if invalid or expired."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def decode_access_token(token: str) -> Optional[str]:
    """Returns user_id or None if invalid."""
    payload = decode_token(token)
    return payload.get("sub") if payload else None


def token_matches_user(payload: dict, hashed_password: str) -> bool:
    """False when the token was issued for a password that has since changed."""
    fp = payload.get("pwd")
    if fp is None:  # tokens issued before fingerprints existed; they expire on their own
        return True
    return hmac.compare_digest(fp, password_fingerprint(hashed_password))
