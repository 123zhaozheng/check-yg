# -*- coding: utf-8 -*-
"""Customer list management router."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import CustomerList, CustomerListItem, User

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


class CustomerListCreateRequest(BaseModel):
    name: str
    items: List[str] = []


def _clean_customer_names(items: List[str]) -> List[str]:
    """Normalize pasted/imported customer names and dedupe in input order."""
    seen = set()
    names = []
    for item in items:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


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
    if not await check_admin_permission(db, current_user):
        query = query.where(CustomerList.owner_id == current_user.id)

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


@router.post("/lists", response_model=CustomerListResponse, status_code=201)
async def create_customer_list(
    request: CustomerListCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a customer list with pasted/imported customer names."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Customer list name cannot be empty")

    customer_names = _clean_customer_names(request.items)
    if not customer_names:
        raise HTTPException(status_code=422, detail="At least one customer name is required")

    customer_list = CustomerList(
        name=name,
        owner_id=current_user.id,
        row_count=len(customer_names),
    )
    customer_list.items.extend(
        CustomerListItem(name=customer_name) for customer_name in customer_names
    )
    db.add(customer_list)
    await db.commit()
    await db.refresh(customer_list)

    return CustomerListResponse(
        id=customer_list.id,
        name=customer_list.name,
        owner_id=customer_list.owner_id,
        row_count=customer_list.row_count,
        created_at=customer_list.created_at,
    )
