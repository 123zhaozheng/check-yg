# -*- coding: utf-8 -*-
"""审查维度 + 追问会话 pydantic schemas (06-26-ai-agent)."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.audit_dimension import (
    DIMENSION_SEVERITIES,
    DIMENSION_SOURCES,
    SEVERITY_MEDIUM,
)


# ---------------------------------------------------------------------------
# 审查维度
# ---------------------------------------------------------------------------


class DimensionStep(BaseModel):
    """维度步骤项 ``{tool, params}``。"""

    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class AuditDimensionBase(BaseModel):
    """维度可写字段（新建/编辑共用）。"""

    name: str = Field(..., min_length=1, max_length=50)
    purpose: str = Field(..., min_length=1)
    steps: list[DimensionStep] = Field(..., min_length=1)
    judgment: str = Field(..., min_length=1)
    severity: str = Field(default=SEVERITY_MEDIUM, pattern="^(%s)$" % "|".join(DIMENSION_SEVERITIES))


class AuditDimensionCreate(AuditDimensionBase):
    """新建维度请求体（admin）。``source`` 可选，默认 system。"""

    source: str = Field(default="system", pattern="^(%s)$" % "|".join(DIMENSION_SOURCES))
    enabled: bool = True


class AuditDimensionUpdate(BaseModel):
    """编辑维度请求体（所有字段可选）。任一字段变化时重拼 prompt。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    purpose: Optional[str] = None
    steps: Optional[list[DimensionStep]] = None
    judgment: Optional[str] = None
    severity: Optional[str] = Field(
        default=None, pattern="^(%s)$" % "|".join(DIMENSION_SEVERITIES)
    )
    enabled: Optional[bool] = None


class AuditDimensionListItem(BaseModel):
    """维度列表项。"""

    id: int
    name: str
    source: str
    purpose: str
    severity: str
    enabled: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class AuditDimensionDetail(BaseModel):
    """维度详情（含 steps / judgment / prompt）。"""

    id: int
    name: str
    source: str
    purpose: str
    steps: list[DimensionStep]
    judgment: str
    severity: str
    prompt: str
    enabled: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 追问会话
# ---------------------------------------------------------------------------


class ConversationItem(BaseModel):
    """会话列表项。"""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表响应。"""

    items: list[ConversationItem]
    total: int


class ConversationMessage(BaseModel):
    """会话历史中抽取出的单条可读消息（GET 会话历史用）.

    ``role``: user（用户提问）/ ai（追问 agent 回复）。文本对话回放；
    工具调用痕迹不在历史里显（仅当前轮 live 显）.
    """

    role: str = Field(..., pattern="^(user|ai)$")
    text: str


class ConversationDetail(BaseModel):
    """GET /tasks/{id}/analyze/conversations/{cid} 响应：会话 + 抽取后的消息历史."""

    id: int
    title: str
    messages: list[ConversationMessage]
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    """POST /tasks/{id}/analyze/chat 请求体。"""

    message: str
    conversation_id: Optional[int] = None


class ChatToolTrace(BaseModel):
    """单次工具调用痕迹（前端气泡小字「🔍 已查询：…」）."""

    tool: str
    summary: str


class ChatSedimentedDimension(BaseModel):
    """本轮流问沉淀出的草稿维度（前端气泡「已沉淀维度：XXX（草稿，待启用）」）."""

    name: str
    severity: str


class ChatResponse(BaseModel):
    """POST /tasks/{id}/analyze/chat 响应（含 conversation_id，多会话）.

    ``tool_traces`` / ``sedimented_dimension`` 为 06-26-ai-agent 新增（向后
    兼容旧前端：均可选，缺省空/None）。
    """

    reply: str
    conversation_id: int
    tool_traces: list[ChatToolTrace] = Field(default_factory=list)
    sedimented_dimension: Optional[ChatSedimentedDimension] = None


class CreateConversationRequest(BaseModel):
    """POST /tasks/{id}/analyze/conversations 新建会话请求体。"""

    title: Optional[str] = None  # 缺省由首问题前 10 字定
