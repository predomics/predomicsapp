"""Project template endpoints — admin CRUD + public list."""

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.config import settings
from ..core.deps import get_admin_user
from ..models.api_schemas import TemplateOut, StatusOut
from ..models.db_models import User

TEMPLATES_PATH = Path(settings.data_dir) / "templates.json"

router = APIRouter(prefix="/admin/templates", tags=["admin"])


class TemplateCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    params: dict


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    params: Optional[dict] = None


def _load_templates() -> list[dict]:
    if TEMPLATES_PATH.exists():
        return json.loads(TEMPLATES_PATH.read_text())
    return []


def _save_templates(templates: list[dict]) -> None:
    """Replace the templates file atomically (temp file + rename)."""
    TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = TEMPLATES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(templates, indent=2))
    os.replace(tmp, TEMPLATES_PATH)


@router.get("/", response_model=list[TemplateOut])
async def list_templates(admin: User = Depends(get_admin_user)):
    """List parameter templates (admin view)."""
    return _load_templates()


@router.get("/public", response_model=list[TemplateOut])
async def list_templates_public():
    """List parameter templates for the Parameters form.

    Deliberately public: templates are named parameter presets written by an
    administrator for every user of the instance (algorithm, population size,
    …). They hold no user data, file paths or credentials. Editing them is
    admin-only.
    """
    return _load_templates()


@router.post("/", response_model=TemplateOut)
async def create_template(
    body: TemplateCreate,
    admin: User = Depends(get_admin_user),
):
    """Create a parameter template (admin only)."""
    templates = _load_templates()
    template = {
        "id": secrets.token_hex(6),
        "name": body.name,
        "description": body.description,
        "category": body.category,
        "params": body.params,
    }
    templates.append(template)
    _save_templates(templates)
    return template


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    admin: User = Depends(get_admin_user),
):
    """Update a parameter template (admin only)."""
    templates = _load_templates()
    for t in templates:
        if t["id"] == template_id:
            if body.name is not None:
                t["name"] = body.name
            if body.description is not None:
                t["description"] = body.description
            if body.category is not None:
                t["category"] = body.category
            if body.params is not None:
                t["params"] = body.params
            _save_templates(templates)
            return t
    raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/{template_id}", response_model=StatusOut)
async def delete_template(
    template_id: str,
    admin: User = Depends(get_admin_user),
):
    """Delete a parameter template (admin only)."""
    templates = _load_templates()
    filtered = [t for t in templates if t["id"] != template_id]
    if len(filtered) == len(templates):
        raise HTTPException(status_code=404, detail="Template not found")
    _save_templates(filtered)
    return {"status": "deleted"}
