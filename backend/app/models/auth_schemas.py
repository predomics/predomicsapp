"""Auth-related Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    is_admin: bool = False
    email_verified: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterResponse(BaseModel):
    """Result of a registration.

    With email verification on, the body is the same whether or not the address
    already had an account (``id`` is empty and ``verification_required`` is
    true), so the endpoint cannot be used to test which addresses are registered.
    """
    id: str = ""
    email: str
    full_name: str = ""
    is_active: bool = True
    is_admin: bool = False
    email_verified: bool = True
    created_at: Optional[datetime] = None
    verification_required: bool = False
    message: Optional[str] = None

    model_config = {"from_attributes": True}


class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None


class PasswordChangedResponse(BaseModel):
    status: str
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None   # debug mode only
    note: Optional[str] = None


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class UsageResponse(BaseModel):
    used_bytes: int
    quota_bytes: int   # 0 = unlimited


class ApiKeyInfo(BaseModel):
    id: str
    name: str
    prefix: str
    is_active: bool = True
    last_used_at: Optional[str] = None
    created_at: str


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    prefix: str
    key: str            # shown once
    created_at: str


class UserPublicResponse(BaseModel):
    """Minimal user info for sharing UI (no sensitive data)."""
    id: str
    email: str
    full_name: str

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AdminUserResponse(BaseModel):
    """User info as seen by admin, including counts."""
    id: str
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    email_verified: bool = True
    project_count: int = 0
    dataset_count: int = 0
    used_bytes: Optional[int] = None


class AdminUserUpdate(BaseModel):
    """Fields an admin can toggle on a user."""
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    email_verified: Optional[bool] = None
