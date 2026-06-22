"""add findings table (S6 AI analysis skeleton)

Revision ID: 1d08c3cec268
Revises: 42add7788eef
Create Date: 2026-06-22 08:30:00.000000+00:00

S6 AI 分析骨架闭环：新建 ``findings`` 表，存 AI 分析 agent 产出的异常发现。
全标量字段（无 jsonb，决策1）：type / severity(high|medium|low) / description /
counterparty / amount / confidence(0-1) / status(pending|accepted|ignored) /
comment。关联 ``tasks.id``（owner-only 复用 _load_owned_task）。多轮对话历史
不在此表，存 ``Task.config.analysis_chat_history``（决策3）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1d08c3cec268'
down_revision: Union[str, Sequence[str], None] = '42add7788eef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'findings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('counterparty', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.String(length=100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_findings_task_id_severity_status',
        'findings',
        ['task_id', 'severity', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_findings_task_id_severity_status', table_name='findings')
    op.drop_table('findings')
