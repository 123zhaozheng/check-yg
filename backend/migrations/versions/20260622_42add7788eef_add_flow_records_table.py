"""add flow_records table (S5 cleaning 不删减)

Revision ID: 42add7788eef
Revises: a1c3e5f7b9d2
Create Date: 2026-06-22 07:00:00.000000+00:00

S5 清洗标准化闭环：新建 ``flow_records`` 表作为流水记录真源。
每条原始表格行 1:1 持久化（standard / unparsed / excluded），
``raw_payload`` JSONB 保存原始全部单元格——清洗不删减的物理兜底。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '42add7788eef'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'flow_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(length=50), nullable=True),
        sa.Column('record_type', sa.String(length=20), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=False),
        sa.Column('is_valid', sa.Boolean(), nullable=False),
        sa.Column('transaction_time', sa.String(length=100), nullable=True),
        sa.Column('counterparty_name', sa.String(length=255), nullable=True),
        sa.Column('counterparty_account', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.String(length=100), nullable=True),
        sa.Column('raw_amount', sa.String(length=100), nullable=True),
        sa.Column('summary', sa.String(length=500), nullable=True),
        sa.Column('transaction_type', sa.String(length=20), nullable=True),
        sa.Column(
            'raw_payload',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('exclude_reason', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_flow_records_task_id_type_status',
        'flow_records',
        ['task_id', 'record_type', 'status'],
    )
    op.create_index(
        'ix_flow_records_document_id',
        'flow_records',
        ['document_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_flow_records_document_id', table_name='flow_records')
    op.drop_index('ix_flow_records_task_id_type_status', table_name='flow_records')
    op.drop_table('flow_records')
