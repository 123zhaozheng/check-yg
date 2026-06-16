# -*- coding: utf-8 -*-
"""Review API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.permissions import check_task_permission
from app.database import get_db
from app.models import User
from app.schemas.review import (
    ReviewMatchListResponse,
    ReviewMatchResponse,
    ReviewResponse,
    ReviewRunRequest,
)
from app.services.review_service import ReviewService
from app.websocket.notifications import notify_user

router = APIRouter(tags=["reviews"])


@router.post("/tasks/{task_id}/review", response_model=ReviewResponse)
async def run_task_review(
    task_id: int,
    request: ReviewRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create and execute a task review."""
    if not await check_task_permission(db, current_user, task_id, required_role="write"):
        raise HTTPException(status_code=403, detail="Task access denied")

    service = ReviewService()
    try:
        review = await service.run_review(
            db,
            task_id=task_id,
            customer_list_id=request.customer_list_id if request else None,
            match_config=request.match_config if request else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    _, total = await service.list_matches(db, review.id, page=1, page_size=1)
    await notify_user(
        current_user.id,
        event="review.completed",
        title="审查完成",
        message=f"任务 {task_id} 审查完成，命中 {total} 条匹配。",
        resource={"task_id": task_id, "review_id": review.id},
    )
    return _review_response(review, total)


@router.get("/reviews/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get review summary."""
    service = ReviewService()
    review = await service.get_review(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if not await check_task_permission(db, current_user, review.task_id):
        raise HTTPException(status_code=403, detail="Task access denied")

    _, total = await service.list_matches(db, review.id, page=1, page_size=1)
    return _review_response(review, total)


@router.get("/reviews/{review_id}/matches", response_model=ReviewMatchListResponse)
async def list_review_matches(
    review_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List review match details."""
    service = ReviewService()
    review = await service.get_review(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if not await check_task_permission(db, current_user, review.task_id):
        raise HTTPException(status_code=403, detail="Task access denied")

    matches, total = await service.list_matches(db, review_id, page=page, page_size=page_size)
    return ReviewMatchListResponse(
        items=[_match_response(match) for match in matches],
        total=total,
        page=page,
        page_size=page_size,
    )


def _review_response(review, total_matches: int) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        task_id=review.task_id,
        customer_list_id=review.customer_list_id,
        status=review.status,
        match_config=review.match_config,
        created_at=review.created_at,
        total_matches=total_matches,
    )


def _match_response(match) -> ReviewMatchResponse:
    return ReviewMatchResponse(
        id=match.id,
        review_id=match.review_id,
        record_id=match.record_id,
        customer_name=match.customer_name,
        match_type=match.match_type,
        score=match.score,
        counterparty_name=match.counterparty_name,
        counterparty_account=match.counterparty_account,
        source_file=match.source_file,
        transaction_time=match.transaction_time,
        amount=match.amount,
        summary=match.summary,
    )
