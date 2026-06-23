"""add documents.portrait (S-web-4 文档画像持久化)

Revision ID: c4a1e9f8b2d7
Revises: b9e7f3a2c1d4
Create Date: 2026-06-23 09:00:00.000000+00:00

文档画像（account_type/持有人/机构/对账期间/收支规则/表头属性等）在 stage1
生成后落库，供数据导入页 hover 弹窗展示，无需二次 LLM 调用。additive nullable，
不破坏旧数据（未跑 stage1 的文档 portrait=null，前端显示「画像待生成」占位）.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4a1e9f8b2d7'
down_revision: Union[str, Sequence[str], None] = 'b9e7f3a2c1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # documents.portrait — stage1 生成的文档画像（jsonb），additive nullable.
    op.add_column(
        'documents',
        sa.Column(
            'portrait',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('documents', 'portrait')
