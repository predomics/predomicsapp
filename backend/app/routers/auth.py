"""Authentication endpoints: register, login, me, password reset, API keys."""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.config import settings
from ..core.rate_limit import limiter, get_ip
from ..core.errors import ApiError
from ..core.security import (
    hash_password, hash_token, verify_password, verify_password_or_dummy, create_access_token,
)
from ..core.deps import get_current_user
from ..models.db_models import User, PasswordResetToken, ApiKey
from ..models.auth_schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    UserPublicResponse,
    UpdateProfileRequest,
    ChangePasswordRequest,
    RegisterResponse,
    StatusResponse,
    PasswordChangedResponse,
    ForgotPasswordResponse,
    WsTicketResponse,
    UsageResponse,
    ApiKeyInfo,
    ApiKeyCreated,
)
from ..services import audit
from ..services import email as email_service
from ..services import lockout, quota, ws_tickets

router = APIRouter(prefix="/auth", tags=["auth"])
_log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _check_new_password(password: str) -> None:
    if len(password or "") < settings.password_min_length:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {settings.password_min_length} characters long",
        )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


_VERIFY_TTL = timedelta(hours=24)
_VERIFY_MESSAGE = "Check your inbox: we sent a link to confirm your email address."


async def _send_verification(user: User) -> str:
    """Store a fresh verification token (hashed) on the user and email the link."""
    raw = secrets.token_urlsafe(32)
    user.email_verify_token_hash = hash_token(raw)
    user.email_verify_expires_at = datetime.now(timezone.utc) + _VERIFY_TTL
    await email_service.send_email_verification(user.email, raw)
    return raw


# ── Auth ─────────────────────────────────────────────────────────────────────


@router.post("/register", response_model=RegisterResponse, status_code=201)
@limiter.limit("10/minute", key_func=get_ip)
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account.

    Without email verification, an address that is already registered gets a 409:
    the form has to tell the person why nothing happened, and there is no other
    channel to do so. With PREDOMICS_REQUIRE_EMAIL_VERIFICATION on, the response
    is identical for new and existing addresses (the existing owner is told by
    email instead), so the endpoint does not reveal who has an account.
    """
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=403,
            detail="Self-registration is disabled. Ask an administrator for an account.",
        )
    email = _normalize_email(body.email)
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    _check_new_password(body.password)
    full_name = (body.full_name or "").strip()[:200]
    verify = settings.require_email_verification
    is_bootstrap_admin = bool(settings.admin_email) and email == _normalize_email(settings.admin_email)

    existing = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    if existing:
        if not verify:
            raise HTTPException(status_code=409, detail="Email already registered")
        # Same work and same answer as for a new account.
        hash_password(body.password)
        if existing.is_active:
            if existing.email_verified:
                await email_service.send_already_registered(existing.email)
            else:
                await _send_verification(existing)
        return RegisterResponse(email=email, full_name=full_name, email_verified=False,
                                verification_required=True, message=_VERIFY_MESSAGE)

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        full_name=full_name,
        email_verified=(not verify) or is_bootstrap_admin,
    )
    # Admin bootstrap: the account named by PREDOMICS_ADMIN_EMAIL is an administrator.
    if is_bootstrap_admin:
        user.is_admin = True
    db.add(user)
    await db.flush()
    await audit.log_action(db, user, audit.ACTION_REGISTER, "user", user.id, ip_address=_client_ip(request))
    if verify:
        raw = None
        if not user.email_verified:
            raw = await _send_verification(user)
        response = RegisterResponse(email=email, full_name=full_name, email_verified=False,
                                    verification_required=True, message=_VERIFY_MESSAGE)
        if raw and settings.debug and not email_service.is_email_configured():
            response.message = f"Debug mode: verification token {raw}"
        return response
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute", key_func=get_ip)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return a JWT access token.

    Repeated failures are throttled per account and per IP address (429 with a
    Retry-After header). The same checks and the same amount of password
    hashing run whether or not the account exists.
    """
    email = _normalize_email(body.email)
    ip = _client_ip(request)

    wait = lockout.retry_after(email, ip)
    if wait:
        minutes = max(1, round(wait / 60))
        raise ApiError(
            429,
            "Too many failed sign-in attempts. Try again in "
            + (f"{wait} seconds." if wait < 90 else f"about {minutes} minutes."),
            code="TOO_MANY_ATTEMPTS",
            headers={"Retry-After": str(wait)},
        )

    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalars().first()
    if not verify_password_or_dummy(body.password, user.hashed_password if user else None):
        lockout.record_failure(email, ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # From here on the caller has proven knowledge of the password.
    lockout.record_success(email, ip)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    if settings.require_email_verification and not user.email_verified:
        raise ApiError(
            403,
            "Confirm your email address first: use the link we sent you, or ask for a new one.",
            code="EMAIL_NOT_VERIFIED",
        )

    token = create_access_token(user.id, user.hashed_password)
    await audit.log_action(db, user, audit.ACTION_LOGIN, ip_address=ip)
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(user: User = Depends(get_current_user)):
    """Exchange a still-valid session for a fresh access token.

    Lets an active browser session outlive the token lifetime without keeping
    long-lived tokens around. An expired or revoked token cannot be refreshed.
    """
    return TokenResponse(access_token=create_access_token(user.id, user.hashed_password))


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def create_ws_ticket(user: User = Depends(get_current_user)):
    """Get a single-use ticket (valid 30 s) to open a job-log WebSocket.

    Connect with ``/ws/jobs/{project_id}/{job_id}?ticket=<ticket>``. The access
    token itself must not be put in a WebSocket URL.
    """
    return WsTicketResponse(ticket=ws_tickets.issue(user.id), expires_in=ws_tickets.TICKET_TTL)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/verify-email", response_model=StatusResponse)
@limiter.limit("10/minute", key_func=get_ip)
async def verify_email(request: Request, body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Confirm an email address with the token from the verification email."""
    result = await db.execute(
        select(User).where(
            User.email_verify_token_hash == hash_token(body.token or ""),
            User.email_verify_expires_at > datetime.now(timezone.utc),
        )
    )
    user = result.scalars().first()
    if not user or not body.token:
        raise ApiError(400, "This confirmation link is invalid or has expired. Ask for a new one.",
                       code="INVALID_VERIFICATION_TOKEN")
    user.email_verified = True
    user.email_verify_token_hash = None
    user.email_verify_expires_at = None
    return StatusResponse(status="verified", message="Email confirmed. You can sign in now.")


@router.post("/resend-verification", response_model=StatusResponse)
@limiter.limit("5/minute", key_func=get_ip)
async def resend_verification(
    request: Request, body: ResendVerificationRequest, db: AsyncSession = Depends(get_db),
):
    """Send a new confirmation link. Always answers 200, whatever the address."""
    response = StatusResponse(
        status="ok", message="If this address has an unconfirmed account, a new link has been sent.",
    )
    email = _normalize_email(body.email)
    user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
    if user and user.is_active and not user.email_verified:
        await _send_verification(user)
    return response


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return user


@router.put("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    if body.full_name is not None:
        user.full_name = body.full_name
    return user


@router.get("/me/usage", response_model=UsageResponse)
async def get_my_usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Storage used by the current user (datasets and job results) and their quota."""
    return UsageResponse(
        used_bytes=await quota.user_usage_bytes(db, user.id),
        quota_bytes=quota.quota_bytes(),
    )


@router.put("/me/password", response_model=PasswordChangedResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    _check_new_password(body.new_password)
    user.hashed_password = hash_password(body.new_password)
    # Every earlier token is now invalid; hand back a fresh one for this session.
    return {
        "status": "password_changed",
        "access_token": create_access_token(user.id, user.hashed_password),
        "token_type": "bearer",
    }


@router.get("/users/search", response_model=list[UserPublicResponse])
async def search_users(
    q: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search users by email prefix (for sharing UI).

    Needs at least 3 literal characters; SQL wildcards in the query are escaped
    so the endpoint cannot be used to page through every account.
    """
    q = (q or "").strip()
    if len(q) < 3:
        return []
    pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    result = await db.execute(
        select(User)
        .where(
            User.email.ilike(pattern, escape="\\"),
            User.id != user.id,
            User.is_active.is_(True),
        )
        .order_by(User.email)
        .limit(10)
    )
    return result.scalars().all()


# ── Password Reset ───────────────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password", response_model=ForgotPasswordResponse, response_model_exclude_none=True)
@limiter.limit("5/minute", key_func=get_ip)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset. Always returns the same 200 to prevent email enumeration.

    The reset token is delivered by email only. Without SMTP there is no
    self-service reset: an administrator resets the password instead. The token
    is echoed in the response only when the server runs in debug mode.
    """
    response = {"status": "ok", "message": "If the email exists, a reset link has been sent"}
    email = _normalize_email(body.email)
    result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = result.scalars().first()
    if not user or not user.is_active:
        return response

    if not email_service.is_email_configured() and not settings.debug:
        _log.warning(
            "Password reset requested for user %s but SMTP is not configured; "
            "an administrator must reset the password.", user.id,
        )
        return response

    # One live token per user: older unused ones are retired.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used.is_(False))
        .values(used=True)
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ))
    await db.flush()

    email_sent = await email_service.send_password_reset(user.email, raw_token)
    if not email_sent and settings.debug:
        # Development convenience only — never reachable with debug off.
        return {**response, "status": "token_generated", "token": raw_token,
                "note": "Debug mode: token returned directly"}
    return response


@router.post("/reset-password", response_model=StatusResponse, response_model_exclude_none=True)
@limiter.limit("5/minute", key_func=get_ip)
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid token."""
    _check_new_password(body.new_password)
    result = await db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hash_token(body.token or ""),
            PasswordResetToken.used.is_(False),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
        .options(selectinload(PasswordResetToken.user))
    )
    matched = result.scalars().first()
    if not matched or not matched.user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    matched.used = True
    matched.user.hashed_password = hash_password(body.new_password)
    # The link arrived in the account's mailbox, which also proves the address.
    matched.user.email_verified = True
    lockout.unlock_account(matched.user.email)
    return {"status": "password_reset"}


# ── API Keys ─────────────────────────────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    name: str

_MAX_API_KEYS_PER_USER = 20


@router.post("/api-keys", response_model=ApiKeyCreated)
async def create_api_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. The full key is returned ONLY in this response."""
    count = await db.execute(select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id))
    if (count.scalar() or 0) >= _MAX_API_KEYS_PER_USER:
        raise HTTPException(status_code=400, detail="API key limit reached; revoke an unused key first")
    raw_key = f"pk_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:8]
    key_hash = hash_password(raw_key)

    api_key = ApiKey(
        user_id=user.id,
        name=body.name,
        key_hash=key_hash,
        prefix=prefix,
    )
    db.add(api_key)
    await db.flush()

    return {
        "id": api_key.id,
        "name": api_key.name,
        "prefix": prefix,
        "key": raw_key,
        "created_at": api_key.created_at.isoformat(),
    }


@router.get("/api-keys", response_model=list[ApiKeyInfo])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List your API keys (the key itself is shown only when it is created)."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return [
        {
            "id": k.id,
            "name": k.name,
            "prefix": k.prefix,
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat(),
        }
        for k in result.scalars().all()
    ]


@router.delete("/api-keys/{key_id}", response_model=StatusResponse, response_model_exclude_none=True)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (delete) one of your API keys."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key)
    return {"status": "revoked"}
