"""Response models for the account, dataset, project, sharing and admin routers.

They exist so the OpenAPI schema describes what each endpoint returns. Models
marked ``extra="allow"`` describe the stable fields of payloads that also carry
free-form or evolving keys (backup manifests, scan metadata): extra keys pass
through untouched instead of being dropped.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


# ── generic ──────────────────────────────────────────────────────────────────

class StatusOut(BaseModel):
    status: str


class DetailOut(BaseModel):
    detail: str


# ── datasets ─────────────────────────────────────────────────────────────────

class TagSuggestions(BaseModel):
    suggestions: list[str]


class ClassNamesOut(BaseModel):
    class_names: dict[str, str]


class DatasetScanResult(_Open):
    """Metadata computed from a dataset's X/y files (sample and feature counts, classes, …)."""
    class_names: Optional[dict[str, str]] = None


class FilePreview(_Open):
    filename: str
    role: Optional[str] = None
    total_rows: int
    total_cols: int
    columns: list[Any]
    rows: list[list[Any]]
    stats: dict[str, Any]
    delimiter: str
    file_size_bytes: int


class MetadataColumn(_Open):
    name: str
    type: str                      # "numeric" or "categorical"
    n_values: Optional[int] = None
    n_missing: Optional[int] = None


class MetadataColumns(BaseModel):
    columns: list[MetadataColumn]


class FileRefOut(BaseModel):
    id: str
    filename: str
    role: Optional[str] = None


class YFromMetadataResult(BaseModel):
    file: FileRefOut
    matched_samples: int
    missing_samples: int
    total_x_samples: int


class DatasetVersionOut(BaseModel):
    id: str
    version_number: int
    files_snapshot: list[FileRefOut]
    note: Optional[str] = None
    created_at: str


class RestoreVersionOut(BaseModel):
    status: str
    version_number: int
    files_restored: int


# ── samples / templates ──────────────────────────────────────────────────────

class SampleInfo(BaseModel):
    id: str
    name: str
    description: str
    available: bool
    files: list[str]


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "general"
    params: dict[str, Any]


# ── comments / sharing ───────────────────────────────────────────────────────

class CommentOut(BaseModel):
    id: str
    project_id: str
    user_id: Optional[str] = None
    user_name: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CommentUpdated(BaseModel):
    id: str
    content: str
    updated_at: str


class ShareUpdated(BaseModel):
    status: str
    role: str


class SharedProjectOut(BaseModel):
    project_id: str
    name: str
    created_at: str
    role: str
    owner_email: str
    owner_name: str


# ── admin ────────────────────────────────────────────────────────────────────

class UserActionResult(BaseModel):
    status: str
    email: str


class BackupInfo(_Open):
    backup_id: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None
    description: Optional[str] = None
    table_counts: Optional[dict[str, int]] = None


class BackupDeleted(BaseModel):
    status: str
    backup_id: str


class RestoreResult(_Open):
    status: str
    mode: Optional[str] = None
    manifest: Optional[dict[str, Any]] = None
    restored_counts: Optional[dict[str, int]] = None
    preserved_counts: Optional[dict[str, int]] = None


class AuditEntry(BaseModel):
    id: int
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Any] = None
    ip_address: Optional[str] = None
    created_at: str


class AuditLogPage(BaseModel):
    total: int
    page: int
    per_page: int
    entries: list[AuditEntry]


class ScitqView(BaseModel):
    server: str
    token: str = ""        # always empty: the token never leaves the server
    token_set: bool
    container: str
    enabled: bool
    package_installed: bool


class ScitqTestResult(_Open):
    ok: bool
    error: Optional[str] = None
    version: Optional[Any] = None


class RetentionJob(BaseModel):
    job_id: str
    project_id: str
    name: Optional[str] = None
    ended_at: Optional[str] = None
    bytes: int


class RetentionBackup(BaseModel):
    file: str
    bytes: int


class RetentionReport(BaseModel):
    dry_run: bool
    job_retention_days: int
    backup_retention_count: int
    jobs: list[RetentionJob]
    backups: list[RetentionBackup]
    bytes_freed: int
