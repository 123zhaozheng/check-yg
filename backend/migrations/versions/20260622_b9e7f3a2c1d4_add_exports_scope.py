"""add exports.scope (S8 导出+设置+辅助页闭环)

Revision ID: b9e7f3a2c1d4
Revises: a8f4c2e1b9d3
Create Date: 2026-06-22 10:30:00.000000+00:00

S8 导出扩展：ExportFile 加 ``scope`` String(50) nullable，记录导出范围
（report / raw / standard / findings）。旧 excel/bundle 行 scope=null 兼容。
additive nullable，不破坏旧数据（不删减精神：导出历史产物文件保留可重新下载）.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e7f3a2c1d4'
down_revision: Union[str, Sequence[str], None] = 'a8f4c2e1b9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # exports.scope — S8 导出范围（report / raw / standard / findings）.
    # additive nullable：旧 excel/bundle 行保持 null 兼容.
    op.add_column(
        'exports',
        sa.Column('scope', sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('exports', 'scope')
