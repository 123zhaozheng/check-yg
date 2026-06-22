"""add report_chapters + report_annotations + reports.status (S7 审查报告闭环)

Revision ID: a8f4c2e1b9d3
Revises: 1d08c3cec268
Create Date: 2026-06-22 09:30:00.000000+00:00

S7 审查报告闭环：章节化审查报告 + 章节级批注 + 定稿软态。

* ``reports.status`` String(20) default 'draft' nullable=False（draft|final，
  定稿不改章节内容、不删行，只改本软态——不删减精神）。
* ``report_chapters`` 表：6 章独立存 Markdown content + order_index（拖拽
  排序）。content 是确定性模板拼装的派生数据，单章/全报告重生成重写 content
  不违反不删减（原始记录在 S5 flow_records.raw_payload 已兜底）。
* ``report_annotations`` 表：章节级批注（chapter_id nullable），灰阶呈现，
  resolved 软态，定稿后新建/切换均 409。

新模型已在 migrations/env.py + database.py init_db import 登记。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8f4c2e1b9d3'
down_revision: Union[str, Sequence[str], None] = '1d08c3cec268'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # reports.status — S7 软态（draft|final）.
    op.add_column(
        'reports',
        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='draft',
        ),
    )

    op.create_table(
        'report_chapters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column(
            'generated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_report_chapters_report_id_order',
        'report_chapters',
        ['report_id', 'order_index'],
    )

    op.create_table(
        'report_annotations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('author', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'resolved',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['chapter_id'], ['report_chapters.id'], ),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_report_annotations_report_id',
        'report_annotations',
        ['report_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_report_annotations_report_id', table_name='report_annotations')
    op.drop_table('report_annotations')
    op.drop_index('ix_report_chapters_report_id_order', table_name='report_chapters')
    op.drop_table('report_chapters')
    op.drop_column('reports', 'status')
