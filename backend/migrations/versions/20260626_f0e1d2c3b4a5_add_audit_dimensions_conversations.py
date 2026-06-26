"""add audit_dimensions + audit_conversations + Finding additive (06-26-ai-agent)

Revision ID: f0e1d2c3b4a5
Revises: b7c3d1e4f2a9
Create Date: 2026-06-26 10:00:00.000000+00:00

06-26-ai-agent AI 审查维度落地 + 悬浮追问 Agent + 维度沉淀：

* ``audit_dimensions`` — 审查维度（维度 = 结构化提示词）。``source=system`` 5 条
  seed（enabled=true）；``source=agent`` 来自 create_dimension（enabled=false 草稿）。
  ``prompt`` 列存服务端拼好的成品（build_dimension_prompt 输出）。
* ``audit_conversations`` — 多轮追问会话（message_history jsonb，独立于 task.config）。
* ``findings`` additive 4 列：``dimension_id``(FK RESTRICT) / ``detail_text`` /
  ``evidence_record_ids``(jsonb) / ``source``。不动现有字段。

seed 5 个 system 维度：复用 ``app.services.audit.system_dimensions.system_dimension_rows``
+ ``build_dimension_prompt`` 拼好 prompt，避免「迁移手写 vs 运行时拼装」两套机制
漂移。``op.bulk_insert`` 参数绑定，跨 pg/sqlite 方言安全。

SQLite 测试路径由 ``create_all`` 覆盖（新模型已在 env.py / database.py 登记），
additive 列由 create_all 自动建（Finding 模型已加列）；seed 在生产 pg 走本迁移，
测试库由运行时按需补 seed。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0e1d2c3b4a5'
down_revision: Union[str, Sequence[str], None] = 'b7c3d1e4f2a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_dimensions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='system'),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=True),
        sa.Column('judgment', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('prompt', sa.Text(), nullable=False),
        # pg: true / sqlite: 1 — 均被 Boolean 列接受。
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'audit_conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('message_history', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # findings additive 4 列（不动现有字段）。
    op.add_column('findings', sa.Column('dimension_id', sa.Integer(), nullable=True))
    op.add_column('findings', sa.Column('detail_text', sa.Text(), nullable=True))
    op.add_column('findings', sa.Column('evidence_record_ids', sa.JSON(), nullable=True))
    op.add_column('findings', sa.Column('source', sa.String(length=20), nullable=True))
    op.create_foreign_key(
        'fk_findings_dimension_id_audit_dimensions',
        'findings',
        'audit_dimensions',
        ['dimension_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    # seed 5 个 system 维度（复用运行时拼装，零漂移）。
    from app.services.audit.system_dimensions import system_dimension_rows

    rows = system_dimension_rows()
    audit_dimensions = sa.Table(
        'audit_dimensions',
        sa.MetaData(),
        sa.Column('name', sa.String(length=50)),
        sa.Column('source', sa.String(length=20)),
        sa.Column('purpose', sa.Text()),
        sa.Column('steps', sa.JSON()),
        sa.Column('judgment', sa.Text()),
        sa.Column('severity', sa.String(length=20)),
        sa.Column('prompt', sa.Text()),
        sa.Column('enabled', sa.Boolean()),
        sa.Column('created_by', sa.Integer(), nullable=True),
    )
    op.bulk_insert(audit_dimensions, rows)


def downgrade() -> None:
    op.drop_constraint(
        'fk_findings_dimension_id_audit_dimensions', 'findings', type_='foreignkey'
    )
    op.drop_column('findings', 'source')
    op.drop_column('findings', 'evidence_record_ids')
    op.drop_column('findings', 'detail_text')
    op.drop_column('findings', 'dimension_id')
    op.drop_table('audit_conversations')
    op.drop_table('audit_dimensions')
