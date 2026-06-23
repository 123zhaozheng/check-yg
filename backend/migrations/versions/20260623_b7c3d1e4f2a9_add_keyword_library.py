"""add keyword_cards + keyword_terms + keyword_hits (06-23-tab 关键词库 + 关键词审查)

Revision ID: b7c3d1e4f2a9
Revises: a5b2c0d3e1f8
Create Date: 2026-06-23 16:00:00.000000+00:00

三张新表（06-23-tab）:
* ``keyword_cards`` — 全局关键词卡片（卡片名 + 卡片级风险等级 高/中/低 + 备注）。
* ``keyword_terms`` — 卡片下的关键词，``(card_id, term)`` 唯一，删卡 CASCADE 连带删词。
* ``keyword_hits`` — 任务关键词审查命中行。引用 flow_records / keyword_cards /
  keyword_terms。删卡时若该卡已有命中 → router 返 409（对齐删已指派模型卡）。

SQLite 测试路径由 ``create_all`` 覆盖（新模型已在 env.py / database.py 登记），
无需额外 ALTER；本迁移建三表 + 约束，不 seed 数据（用户自己导入/建）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c3d1e4f2a9'
down_revision: Union[str, Sequence[str], None] = 'a5b2c0d3e1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'keyword_cards',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('risk_level', sa.String(length=10), nullable=False, server_default='中'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'keyword_terms',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('term', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['card_id'], ['keyword_cards.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('card_id', 'term', name='uq_keyword_terms_card_id_term'),
    )

    op.create_table(
        'keyword_hits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('flow_record_id', sa.Integer(), nullable=False),
        sa.Column('keyword_card_id', sa.Integer(), nullable=False),
        sa.Column('keyword_term_id', sa.Integer(), nullable=False),
        sa.Column('match_type', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('risk_level', sa.String(length=10), nullable=False),
        sa.Column('matched_field', sa.String(length=50), nullable=False),
        sa.Column('matched_snippet', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['flow_record_id'], ['flow_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['keyword_card_id'], ['keyword_cards.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['keyword_term_id'], ['keyword_terms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('keyword_hits')
    op.drop_table('keyword_terms')
    op.drop_table('keyword_cards')
