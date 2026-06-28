"""ReportChapter model — S7 章节化审查报告.

一张报告拆成 8 章（概述/被审查对象/数据范围/完整性校验（余额）/关键词审查/
异常发现汇总/风险评估/结论建议），每章独立存 Markdown content，支持行内编辑
与拖拽排序（``order_index``）。``content`` 是确定性模板拼装的派生数据——单章/全
报告重生成重写 content，不改原始记录（S5 flow_records.raw_payload 已兜底
"不删减"）。

关系 ``report`` back_populates ``Report.chapters``，``Report.chapters`` 设
``cascade="all, delete-orphan"`` + ``order_by="ReportChapter.order_index"``。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReportChapter(Base):
    """One chapter of a chaptered review report (S7)."""

    __tablename__ = "report_chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reports.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 拖拽排序：0-7 对应 8 章固定顺序，重生成不改 order_index。
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="chapters")  # noqa: F821
    annotations: Mapped[list["ReportAnnotation"]] = relationship(  # noqa: F821
        "ReportAnnotation",
        back_populates="chapter",
        cascade="all, delete-orphan",
    )
