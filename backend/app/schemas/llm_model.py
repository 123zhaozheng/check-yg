# -*- coding: utf-8 -*-
"""LLM 模型卡片 + 阶段指派 pydantic schemas (06-23-llm-model-card)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.llm_model import THINKING_LEVELS
from app.models.llm_model_assignment import STAGES


class LLMModelBase(BaseModel):
    """LLM 模型卡片可写字段（新建/编辑共用）。"""

    display_name: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1, max_length=200)
    provider_base_url: str = Field(..., min_length=1, max_length=500)
    # api_key：新建可空（默认空串）；编辑时为空/脱敏串表示不改原值。
    api_key: Optional[str] = None
    context_length: int = Field(..., ge=0)
    max_output: int = Field(..., ge=0)
    supports_tool_call: bool = True
    supports_tool_choice_required: bool = True
    is_reasoning: bool = False
    supports_streaming: bool = True
    default_thinking: str = Field(default="off", pattern="^(%s)$" % "|".join(THINKING_LEVELS))
    default_max_tokens: int = Field(..., ge=1)
    default_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class LLMModelCreate(LLMModelBase):
    """新建模型卡片请求体。api_key 可空（默认空串）。"""

    pass


class LLMModelUpdate(BaseModel):
    """编辑模型卡片请求体（所有字段可选；api_key 空/脱敏串不改原值）。"""

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    model_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    provider_base_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    api_key: Optional[str] = None
    context_length: Optional[int] = Field(default=None, ge=0)
    max_output: Optional[int] = Field(default=None, ge=0)
    supports_tool_call: Optional[bool] = None
    supports_tool_choice_required: Optional[bool] = None
    is_reasoning: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    default_thinking: Optional[str] = Field(
        default=None, pattern="^(%s)$" % "|".join(THINKING_LEVELS)
    )
    default_max_tokens: Optional[int] = Field(default=None, ge=1)
    default_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


def mask_api_key(api_key: str) -> str:
    """脱敏 api_key：返 ``********XXXX``（后 4 位），空串返空串。"""
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "********" + api_key
    return "********" + api_key[-4:]


def is_masked_api_key(value: Optional[str]) -> bool:
    """判断 api_key 值是否为脱敏占位（以 ``********`` 开头）或空（编辑留空不改）。"""
    if value is None or value == "":
        return True
    return value.startswith("********")


class LLMModelResponse(BaseModel):
    """模型卡片响应——api_key 脱敏（``********XXXX``），不返明文。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    model_name: str
    provider_base_url: str
    api_key: str
    context_length: int
    max_output: int
    supports_tool_call: bool
    supports_tool_choice_required: bool
    is_reasoning: bool
    supports_streaming: bool
    default_thinking: str
    default_max_tokens: int
    default_temperature: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class LLMModelAssignmentResponse(BaseModel):
    """阶段指派响应——stage + 指派的卡片（未指派时 llm_model=None）。"""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    stage: str
    llm_model_id: Optional[int] = None
    llm_model: Optional[LLMModelResponse] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LLMModelAssignmentUpdate(BaseModel):
    """阶段指派请求体——``llm_model_id`` 为 null 表示解除指派（回退兜底）。"""

    llm_model_id: Optional[int] = None


def is_valid_stage(stage: str) -> bool:
    """stage 是否在枚举内。"""
    return stage in STAGES
