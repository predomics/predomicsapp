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
    created_at: datetime

    model_config = {"from_attributes": True}


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
    project_count: int = 0
    dataset_count: int = 0


class AdminUserUpdate(BaseModel):
    """Fields an admin can toggle on a user."""
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
