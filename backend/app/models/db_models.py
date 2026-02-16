"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_id():
    return uuid.uuid4().hex[:12]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="projects")
    dataset_links: Mapped[list["ProjectDataset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    shares: Mapped[list["ProjectShare"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Dataset(Base):
    """A logical dataset — a named group of files (e.g. Xtrain + Ytrain + Xtest + Ytest)."""
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped["User"] = relationship(back_populates="datasets")
    files: Mapped[list["DatasetFile"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    project_links: Mapped[list["ProjectDataset"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class DatasetFile(Base):
    """A physical file within a dataset (e.g. Xtrain.tsv with role='xtrain')."""
    __tablename__ = "dataset_files"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # xtrain/ytrain/xtest/ytest
    disk_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="files")


class ProjectDataset(Base):
    """Junction table: many-to-many between projects and datasets."""
    __tablename__ = "project_datasets"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship(back_populates="dataset_links")
    dataset: Mapped["Dataset"] = relationship(back_populates="project_links")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    results_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    config_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    disk_size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, index=True)
    best_auc: Mapped[Optional[float]] = mapped_column(nullable=True)
    best_k: Mapped[Optional[int]] = mapped_column(nullable=True)

    project: Mapped["Project"] = relationship(back_populates="jobs")
    owner: Mapped[Optional["User"]] = relationship()


class ProjectShare(Base):
    """Share a project with another user (viewer or editor role)."""
    __tablename__ = "project_shares"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="viewer")  # viewer / editor
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    shared_by: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="shares")
    user: Mapped["User"] = relationship()


class SchemaVersion(Base):
    """Track applied schema migrations."""
    __tablename__ = "schema_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    """Track user actions for admin review."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(12), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    user: Mapped[Optional["User"]] = relationship()


class PasswordResetToken(Base):
    """Token for self-service password reset."""
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship()


class ApiKey(Base):
    """User API keys for programmatic access."""
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship()


class Webhook(Base):
    """User webhook for external notifications."""
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[Optional[list]] = mapped_column(JSON, default=lambda: ["job.completed", "job.failed"])
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship()


class ProjectComment(Base):
    """Threaded notes/discussion per project."""
    __tablename__ = "project_comments"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship()
    user: Mapped["User"] = relationship()


class PublicShare(Base):
    """Public read-only share link for a project."""
    __tablename__ = "public_shares"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped["Project"] = relationship()
    creator: Mapped["User"] = relationship()


class DatasetVersion(Base):
    """Snapshot of dataset files at a point in time."""
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    files_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    dataset: Mapped["Dataset"] = relationship()
