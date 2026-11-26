"""Webhook management endpoints."""

import asyncio
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.db_models import User, Webhook
from ..services.webhooks import send_webhook_sync, validate_webhook_url, UnsafeWebhookURL
from typing import List
from ..models.schemas import (
    StatusResponse, WebhookInfo,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


_ALLOWED_EVENTS = {"job.completed", "job.failed"}
_MAX_WEBHOOKS_PER_USER = 10


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2000)
    events: list[str] = ["job.completed", "job.failed"]


@router.post("/", response_model=WebhookInfo, response_model_exclude_unset=True)
async def create_webhook(
    body: WebhookCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a webhook called when your jobs finish. The secret is shown only once."""
    unknown = sorted(set(body.events) - _ALLOWED_EVENTS)
    if unknown or not body.events:
        raise HTTPException(status_code=422, detail=f"Unknown events: {', '.join(unknown) or 'none given'}")
    try:
        await asyncio.to_thread(validate_webhook_url, body.url)
    except UnsafeWebhookURL as e:
        raise HTTPException(status_code=422, detail=str(e))
    count = await db.execute(select(func.count()).select_from(Webhook).where(Webhook.user_id == user.id))
    if (count.scalar() or 0) >= _MAX_WEBHOOKS_PER_USER:
        raise HTTPException(status_code=400, detail="Webhook limit reached; delete an unused webhook first")

    secret = secrets.token_hex(32)
    wh = Webhook(
        user_id=user.id,
        name=body.name,
        url=body.url,
        events=body.events,
        secret=secret,
    )
    db.add(wh)
    await db.flush()
    return {
        "id": wh.id,
        "name": wh.name,
        "url": wh.url,
        "events": wh.events,
        "secret": secret,
        "created_at": wh.created_at.isoformat(),
    }


@router.get("/", response_model=List[WebhookInfo], response_model_exclude_unset=True)
async def list_webhooks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List your webhooks (secrets are never returned again)."""
    result = await db.execute(
        select(Webhook)
        .where(Webhook.user_id == user.id)
        .order_by(Webhook.created_at.desc())
    )
    return [
        {
            "id": w.id,
            "name": w.name,
            "url": w.url,
            "events": w.events,
            "is_active": w.is_active,
            "created_at": w.created_at.isoformat(),
        }
        for w in result.scalars().all()
    ]


@router.delete("/{webhook_id}", response_model=StatusResponse, response_model_exclude_unset=True)
async def delete_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one of your webhooks."""
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    return {"status": "deleted"}


@router.post("/{webhook_id}/test", response_model=StatusResponse, response_model_exclude_unset=True)
async def test_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Send a signed test event to the webhook URL.
    payload = {"event": "test", "message": "This is a test webhook from PredomicsApp"}
    success = await asyncio.to_thread(send_webhook_sync, wh.url, payload, wh.secret, 1)
    return {"status": "delivered" if success else "failed"}
