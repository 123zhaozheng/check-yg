# -*- coding: utf-8 -*-
"""审查维度 CRUD service（06-26-ai-agent）.

复刻 ``keyword_library_service`` 范式：list / create(admin) / update(admin) /
delete(admin；删 system 需 admin，删 agent 建的需 owner/admin=created_by 本人
或 admin；已被 finding 引用 → 409）。create/update 时调
``build_dimension_prompt`` 拼好 prompt 存库。

维度 = 结构化提示词；新维度沉淀零代码（``source=agent`` 来自 create_dimension
工具，``enabled=false`` 草稿；``source=system`` 5 条由 Alembic seed）。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import check_admin_permission
from app.models import AuditDimension, Finding, User
from app.models.audit_dimension import (
    DIMENSION_SEVERITIES,
    DIMENSION_SOURCES,
    SOURCE_AGENT,
    SOURCE_SYSTEM,
)
from app.services.audit.dimension_prompt import build_dimension_prompt

logger = logging.getLogger(__name__)


class DimensionService:
    """审查维度 CRUD。"""

    async def list_dimensions(self, db: AsyncSession) -> list[dict]:
        """列出所有维度。返 ``[{id, name, source, purpose, severity, enabled,
        created_by, created_at, updated_at}]``。所有登录用户可读。"""
        result = await db.execute(
            select(AuditDimension).order_by(AuditDimension.id.asc())
        )
        rows: list[dict] = []
        for d in result.scalars().all():
            rows.append(self._to_dict(d))
        return rows

    async def get_dimension(self, db: AsyncSession, dimension_id: int) -> Optional[dict]:
        """维度详情（含 steps / judgment / prompt）。"""
        result = await db.execute(
            select(AuditDimension).where(AuditDimension.id == dimension_id)
        )
        d = result.scalar_one_or_none()
        if d is None:
            return None
        out = self._to_dict(d)
        out["steps"] = d.steps
        out["judgment"] = d.judgment
        out["prompt"] = d.prompt
        return out

    async def create_dimension(
        self,
        db: AsyncSession,
        *,
        name: str,
        purpose: str,
        steps: list[dict],
        judgment: str,
        severity: str,
        created_by: Optional[int],
        source: str = SOURCE_SYSTEM,
        enabled: bool = True,
    ) -> AuditDimension:
        """新建维度（admin）。调 ``build_dimension_prompt`` 拼好 prompt 存库。"""
        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 50:
            raise ValueError("维度名不能为空且需 ≤50 字")
        if source not in DIMENSION_SOURCES:
            raise ValueError(f"source 必须是 {DIMENSION_SOURCES} 之一")
        if severity not in DIMENSION_SEVERITIES:
            raise ValueError(f"severity 必须是 {DIMENSION_SEVERITIES} 之一")
        clean_purpose = (purpose or "").strip()
        if not clean_purpose:
            raise ValueError("purpose 不能为空")
        clean_judgment = (judgment or "").strip()
        if not clean_judgment:
            raise ValueError("judgment 不能为空")
        clean_steps = self._validate_steps(steps)

        prompt = build_dimension_prompt(
            name=clean_name,
            purpose=clean_purpose,
            steps=clean_steps,
            judgment=clean_judgment,
            severity=severity,
        )
        dim = AuditDimension(
            name=clean_name,
            source=source,
            purpose=clean_purpose,
            steps=clean_steps,
            judgment=clean_judgment,
            severity=severity,
            prompt=prompt,
            enabled=enabled,
            created_by=created_by,
        )
        db.add(dim)
        await db.flush()
        logger.info("新建维度: id=%s name=%s source=%s", dim.id, clean_name, source)
        return dim

    async def update_dimension(
        self,
        db: AsyncSession,
        dimension_id: int,
        *,
        name: Optional[str] = None,
        purpose: Optional[str] = None,
        steps: Optional[list[dict]] = None,
        judgment: Optional[str] = None,
        severity: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> AuditDimension:
        """编辑维度（admin）。可改 name/purpose/steps/judgment/severity/enabled；
        任一字段变化时重拼 prompt 存库。"""
        result = await db.execute(
            select(AuditDimension).where(AuditDimension.id == dimension_id)
        )
        dim = result.scalar_one_or_none()
        if dim is None:
            raise LookupError("Dimension not found")

        need_rebuild = False
        if name is not None:
            clean_name = name.strip()
            if not clean_name or len(clean_name) > 50:
                raise ValueError("维度名不能为空且需 ≤50 字")
            if dim.name != clean_name:
                dim.name = clean_name
                need_rebuild = True
        if purpose is not None:
            clean_purpose = purpose.strip()
            if not clean_purpose:
                raise ValueError("purpose 不能为空")
            if dim.purpose != clean_purpose:
                dim.purpose = clean_purpose
                need_rebuild = True
        if judgment is not None:
            clean_judgment = judgment.strip()
            if not clean_judgment:
                raise ValueError("judgment 不能为空")
            if dim.judgment != clean_judgment:
                dim.judgment = clean_judgment
                need_rebuild = True
        if severity is not None:
            if severity not in DIMENSION_SEVERITIES:
                raise ValueError(f"severity 必须是 {DIMENSION_SEVERITIES} 之一")
            if dim.severity != severity:
                dim.severity = severity
                need_rebuild = True
        if steps is not None:
            clean_steps = self._validate_steps(steps)
            dim.steps = clean_steps
            need_rebuild = True
        if enabled is not None:
            dim.enabled = bool(enabled)

        if need_rebuild:
            dim.prompt = build_dimension_prompt(
                name=dim.name,
                purpose=dim.purpose,
                steps=dim.steps or [],
                judgment=dim.judgment,
                severity=dim.severity,
            )
        await db.flush()
        logger.info("编辑维度: id=%s", dimension_id)
        return dim

    async def delete_dimension(
        self,
        db: AsyncSession,
        dimension_id: int,
        *,
        user: User,
    ) -> None:
        """删维度（admin）。权限：
        * ``source=system`` —— 仅 admin。
        * ``source=agent`` —— owner(``created_by``)本人或 admin。
        已被 finding 引用 → 抛 ValueError 由 router 转 409（对齐删已指派模型卡 /
        删已命中关键词卡）。FK ondelete=RESTRICT 兜底。

        **agent 无删除工具**——删维度全在 UI/后端做。
        """
        result = await db.execute(
            select(AuditDimension).where(AuditDimension.id == dimension_id)
        )
        dim = result.scalar_one_or_none()
        if dim is None:
            raise LookupError("Dimension not found")

        is_admin = await check_admin_permission(db, user)
        if dim.source == SOURCE_SYSTEM:
            if not is_admin:
                raise PermissionError("仅 admin 可删除系统维度")
        else:  # source=agent
            if not is_admin and dim.created_by != user.id:
                raise PermissionError("仅维度创建者或 admin 可删除该维度")

        # 已被 finding 引用 → 409。
        ref_result = await db.execute(
            select(Finding.id)
            .where(Finding.dimension_id == dimension_id)
            .limit(1)
        )
        if ref_result.scalar_one_or_none() is not None:
            raise ValueError("该维度已被审查发现引用，请先解除关联再删除")

        await db.delete(dim)
        logger.info("删除维度: id=%s name=%s", dimension_id, dim.name)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_steps(steps: list[dict] | None) -> list[dict]:
        """校验 steps：list[{tool, params}]，tool 限只读白名单 + query_findings。"""
        from app.llm.analysis import READONLY_TOOL_WHITELIST

        if not isinstance(steps, list) or not steps:
            raise ValueError("steps 必须是非空 list[{tool, params}]")
        clean: list[dict] = []
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError(f"steps[{idx}] 必须是 dict {{tool, params}}")
            tool = str(step.get("tool") or "").strip()
            if tool not in READONLY_TOOL_WHITELIST:
                raise ValueError(
                    f"steps[{idx}].tool '{tool}' 不在白名单 "
                    f"({sorted(READONLY_TOOL_WHITELIST)})"
                )
            params = step.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError(f"steps[{idx}].params 必须是 dict")
            clean.append({"tool": tool, "params": params})
        return clean

    @staticmethod
    def _to_dict(d: AuditDimension) -> dict:
        return {
            "id": d.id,
            "name": d.name,
            "source": d.source,
            "purpose": d.purpose,
            "severity": d.severity,
            "enabled": d.enabled,
            "created_by": d.created_by,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }


# 模块级单例（router 复用）。
dimension_service = DimensionService()
