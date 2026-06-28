"""add findings.document_id column (06-28-balance-column-check)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-28 11:00:00.000000+00:00

余额校验 finding（source='balance_check'）关联到产出它的文档，用于按文档范围删旧
重算（多文档任务 / append 追加新文档时不误删其它文档的校验结果）。维度 finding
（source='rule'）不设该列 → NULL，不受影响。ondelete=CASCADE：文档删除时其余额
校验 finding 脱离文档无意义，跟随删除。additive only — 不动现有列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'findings',
        sa.Column(
            'document_id',
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        'fk_findings_document_id_documents',
        'findings',
        'documents',
        ['document_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_findings_document_id_documents',
        'findings',
        type_='foreignkey',
    )
    op.drop_column('findings', 'document_id')
