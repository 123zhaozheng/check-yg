# -*- coding: utf-8 -*-
"""Customer list API tests."""

import pytest

from app.models import CustomerList, Role, User


@pytest.mark.asyncio
async def test_create_customer_list_dedupes_items(client, db_session):
    session, user = db_session

    response = await client.post(
        "/api/customers/lists",
        json={"name": "重点客户", "items": ["张三", "李四", "张三", "  ", "王五"]},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "重点客户"
    assert data["owner_id"] == user.id
    assert data["row_count"] == 3

    list_response = await client.get("/api/customers/lists")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


@pytest.mark.asyncio
async def test_customer_lists_are_owner_scoped(client, db_session):
    session, user = db_session
    other_role = Role(name="other-role")
    other_user = User(
        username="other-customer-owner",
        email="other-customer-owner@example.com",
        hashed_password="x",
        role=other_role,
        is_active=True,
    )
    session.add_all(
        [
            other_role,
            other_user,
            CustomerList(name="当前用户名单", owner_id=user.id, row_count=0),
            CustomerList(name="其他用户名单", owner=other_user, row_count=0),
        ]
    )
    await session.commit()

    response = await client.get("/api/customers/lists")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "当前用户名单"
