"""add llm_models + llm_model_assignments (06-23-llm-model-card 模型卡片)

Revision ID: a5b2c0d3e1f8
Revises: c4a1e9f8b2d7
Create Date: 2026-06-23 14:00:00.000000+00:00

模型卡片 + 按阶段指派。两张新表：
* ``llm_models``：可复用的 LLM 连接 + 模型元信息（显示名 / model id / 端点 /
  api_key 明文 / 上下文 / 最大输出 / 工具调用 / 推理模式 / 流式 / 默认
  max_tokens / 默认 thinking / 默认 temperature）。api_key 明文存，API/日志
  脱敏。不设 is_active 全局布尔——用 assignments 按阶段选。
* ``llm_model_assignments``：stage（unique）→ llm_model_id（nullable，nullable
  表示未指派，回退兜底）。

seed 默认卡片（step-3.7-flash / deepseek-chat / qwen-plus / kimi-k2.6）。
assignments 留空（grill 决策：用户在设置页手动给每阶段选卡片）。

SQLite 测试路径由 ``create_all`` 覆盖（新模型已在 env.py / database.py 登记），
无需额外 ALTER；seed 在生产 pg 走本迁移，测试库走 ``init_db`` 后的 seed。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5b2c0d3e1f8'
down_revision: Union[str, Sequence[str], None] = 'c4a1e9f8b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('model_name', sa.String(length=200), nullable=False),
        sa.Column('provider_base_url', sa.String(length=500), nullable=False),
        sa.Column('api_key', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('context_length', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_output', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('supports_tool_call', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('supports_tool_choice_required', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_reasoning', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('supports_streaming', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('default_thinking', sa.String(length=20), nullable=False, server_default='off'),
        sa.Column('default_max_tokens', sa.Integer(), nullable=False, server_default='4000'),
        sa.Column('default_temperature', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'llm_model_assignments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('llm_model_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['llm_model_id'], ['llm_models.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stage', name='uq_llm_model_assignments_stage'),
    )

    # seed 默认卡片（research §5）。assignments 留空（grill 决策）。
    # api_key 留空——用户在设置页填。kimi 32K 最大输出未独立核实，按已知写。
    op.execute(
        """
        INSERT INTO llm_models
            (display_name, model_name, provider_base_url, api_key,
             context_length, max_output, supports_tool_call,
             supports_tool_choice_required, is_reasoning, supports_streaming,
             default_thinking, default_max_tokens, default_temperature)
        VALUES
            ('step-3.7-flash', 'step-3.7-flash', 'https://api.stepfun.com/v1', '',
             262144, 8192, true, true, true, true, 'low', 6000, NULL),
            ('deepseek-chat', 'deepseek-chat', 'https://api.deepseek.com/v1', '',
             1000000, 384000, true, true, false, true, 'off', 4000, NULL),
            ('qwen-plus', 'qwen-plus', 'https://dashscope.aliyuncs.com/compatible-mode/v1', '',
             1000000, 8192, true, false, false, true, 'off', 4000, NULL),
            ('kimi-k2.6', 'kimi-k2.6', 'https://api.moonshot.ai/v1', '',
             262144, 32768, true, true, true, true, 'low', 6000, NULL)
        """
    )


def downgrade() -> None:
    op.drop_table('llm_model_assignments')
    op.drop_table('llm_models')
