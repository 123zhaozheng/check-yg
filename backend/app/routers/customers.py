# -*- coding: utf-8 -*-
"""Customer list management router."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..database import get_db
from ..models import CustomerList, User

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerListResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    row_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerListListResponse(BaseModel):
    items: List[CustomerListResponse]
    total: int
    page: int
    page_size: int


@router.get("/lists", response_model=CustomerListListResponse)
async def list_customer_lists(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List customer lists with pagination."""
    query = select(CustomerList)

    if search:
        query = query.where(CustomerList.name.contains(search))

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(CustomerList.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    lists = result.scalars().all()

    items = [
        CustomerListResponse(
            id=cl.id,
            name=cl.name,
            owner_id=cl.owner_id,
            row_count=cl.row_count,
            created_at=cl.created_at,
        )
        for cl in lists
    ]

    return CustomerListListResponse(items=items, total=total, page=page, page_size=page_size)
