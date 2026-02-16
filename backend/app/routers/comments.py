"""Project comments — threaded notes/discussion per project."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, ProjectComment

router = APIRouter(prefix="/projects", tags=["comments"])


class CommentCreate(BaseModel):
    content: str


class CommentUpdate(BaseModel):
    content: str


@router.post("/{project_id}/comments")
async def create_comment(
    project_id: str,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a project (viewer access)."""
    await get_project_with_access(project_id, user, db, require_role="viewer")

    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    comment = ProjectComment(
        project_id=project_id,
        user_id=user.id,
        content=body.content.strip(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return {
        "id": comment.id,
        "project_id": comment.project_id,
        "user_id": comment.user_id,
        "user_name": user.full_name or user.email,
        "content": comment.content,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "updated_at": None,
    }


@router.get("/{project_id}/comments")
async def list_comments(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all comments for a project (viewer access)."""
    await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(ProjectComment)
        .options(selectinload(ProjectComment.user))
        .where(ProjectComment.project_id == project_id)
        .order_by(ProjectComment.created_at.asc())
    )
    comments = result.scalars().all()

    return [
        {
            "id": c.id,
            "project_id": c.project_id,
            "user_id": c.user_id,
            "user_name": c.user.full_name or c.user.email if c.user else "Unknown",
            "content": c.content,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in comments
    ]


@router.put("/{project_id}/comments/{comment_id}")
async def update_comment(
    project_id: str,
    comment_id: str,
    body: CommentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a comment (author only)."""
    await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(ProjectComment).where(
            ProjectComment.id == comment_id,
            ProjectComment.project_id == project_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")

    comment.content = body.content.strip()
    comment.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"id": comment.id, "content": comment.content, "updated_at": comment.updated_at.isoformat()}


@router.delete("/{project_id}/comments/{comment_id}")
async def delete_comment(
    project_id: str,
    comment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a comment (author or project owner)."""
    project = await get_project_with_access(project_id, user, db, require_role="viewer")

    result = await db.execute(
        select(ProjectComment).where(
            ProjectComment.id == comment_id,
            ProjectComment.project_id == project_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Allow deletion by comment author or project owner
    if comment.user_id != user.id and project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    await db.delete(comment)
    await db.commit()
    return {"detail": "Comment deleted"}
