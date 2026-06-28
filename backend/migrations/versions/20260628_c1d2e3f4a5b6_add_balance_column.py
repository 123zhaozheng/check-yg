"""add flow_records.balance column (06-28-balance-column-check)

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28 10:00:00.000000+00:00

余额列（账户余额）：normalizer 逐行抽出 balance（仅流水行，余额汇总行仍过滤），
落库到 flow_records.balance。无余额列文档（信用卡等）为空（nullable）。有余额列
时供 balance_check 算法复核篡改/删行。additive only — 不动现有列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('flow_records', sa.Column('balance', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('flow_records', 'balance')
