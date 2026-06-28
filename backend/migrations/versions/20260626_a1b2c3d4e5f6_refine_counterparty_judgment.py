"""refine 重复对手方 judgment：支付聚合平台降为 low (06-26-ai-agent 修订)

Revision ID: a1b2c3d4e5f6
Revises: f0e1d2c3b4a5
Create Date: 2026-06-26 21:00:00.000000+00:00

06-26-ai-agent 修订（user feedback）：「重复对手方」维度原本只按笔数判 severity，
导致财付通/微信支付/支付宝这类**支付聚合平台**的正常高频往来被判成 high ——
高频不等于高风险。``system_dimensions.py`` 已改 judgment（聚合平台一律 low），
但 ``audit_dimensions.prompt`` 是 DB 缓存的成品，已 seed 的旧行不会自动更新。

本迁移按运行时定义重拼「重复对手方」prompt，回写 judgment + prompt，保持
「迁移 vs 运行时」单源真相（code-reuse-thinking-guide）。其余维度不动。

SQLite 测试路径走 ``create_all`` + 运行时 seed（不经迁移），故本迁移只对生产 pg 生效；
``op.execute(sa.text(...))`` + bindparams 跨方言中性。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f0e1d2c3b4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.services.audit.system_dimensions import SYSTEM_DIMENSIONS, build_prompt

    # 单源真相：从运行时定义取最新 judgment 并重拼 prompt，回写 DB 缓存行。
    dim = next((d for d in SYSTEM_DIMENSIONS if d["name"] == "重复对手方"), None)
    if dim is None:  # 防御：定义被改名时跳过，不阻塞迁移。
        return
    op.execute(
        sa.text(
            "UPDATE audit_dimensions "
            "SET judgment = :judgment, prompt = :prompt "
            "WHERE name = '重复对手方' AND source = 'system'"
        ).bindparams(judgment=dim["judgment"], prompt=build_prompt(dim))
    )


def downgrade() -> None:
    # 回退到旧 judgment（聚合平台也按笔数判 severity）。
    old_judgment = "≥10 笔 high；3-9 笔 medium。"
    from app.services.audit.dimension_prompt import build_dimension_prompt

    old_prompt = build_dimension_prompt(
        name="重复对手方",
        purpose="检测同一对手方高频往来（≥3 笔）。",
        steps=[{"tool": "query_by_counterparty", "params": {"min_count": 3}}],
        judgment=old_judgment,
        severity="medium",
    )
    op.execute(
        sa.text(
            "UPDATE audit_dimensions "
            "SET judgment = :judgment, prompt = :prompt "
            "WHERE name = '重复对手方' AND source = 'system'"
        ).bindparams(judgment=old_judgment, prompt=old_prompt)
    )
