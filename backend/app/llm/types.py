"""pydantic-ai ``output_type`` 模型 —— 三模块的结构化输出契约。

为什么不复用 ``app.parsers.base.FlowRecord``：那个是 ``@dataclass``，且缺
``raw_amount`` / ``is_valid`` / ``row_index`` 三个 LLM 实际输出的字段。硬塞会
丢字段，违反"清洗不删减"底线。这里用 pydantic ``BaseModel`` 作为
``output_type``，agent 返回后再由 extractor 映射成 ``FlowRecord``。

字段定义逐字对齐三模块旧提示词的"返回JSON格式"段，提示词本身不动。
"""

from typing import Literal

from pydantic import BaseModel, Field


class FlowClassification(BaseModel):
    """classifier 输出：是否流水表格。对齐 classifier 提示词返回格式。"""

    is_flow_table: bool
    confidence: int = Field(ge=0, le=100)
    reason: str = ""
    header_row_index: int = -1
    data_start_row: int = 0


class NormalizedRow(BaseModel):
    """normalizer 单行输出。对齐 normalizer 提示词返回格式里的单行结构。"""

    row_index: int
    is_valid: bool
    transaction_time: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount: str = ""
    raw_amount: str = ""
    summary: str = ""
    transaction_type: str = ""
    source_file: str = ""
    balance: str = ""


class NormalizedRows(BaseModel):
    """normalizer 输出：行列表。对齐提示词 ``{"rows": [...]}`` 外层结构。"""

    rows: list[NormalizedRow]


AccountType = Literal[
    "credit_card", "debit_card", "alipay", "wechat", "bank_general", "unknown"
]
AmountSignRule = Literal[
    "pos_income", "pos_expense", "no_sign", "split_cols", "unknown"
]


class DocumentPortrait(BaseModel):
    """portrait 输出：文档画像 + 列映射。对齐 portrait 提示词返回格式。"""

    account_type: AccountType = "unknown"
    account_holder: str = ""
    account_number_masked: str = ""
    institution: str = ""
    statement_period: str = ""
    key_observations: list[str] = Field(default_factory=list)
    amount_sign_rule: AmountSignRule = "unknown"
    header_attributes: list[str] = Field(default_factory=list)
    column_mapping: list[str | list[str] | None] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# S6 AI 分析 agent output_type (analysis.py).
# 新 agent（非 legacy 搬运），instructions 占位但结构要对。findings 是 agent
# 产出的异常发现列表，summary 是整体推理摘要。落地后由 tasks.py 端点落库成
# Finding 行（含 status/comment 等复核字段，这些不属于 agent 输出）。
# ---------------------------------------------------------------------------

Severity = Literal["high", "medium", "low"]


class FindingItem(BaseModel):
    """analysis agent 输出的单条异常发现（对齐 AnalysisResult.findings 项）。

    字段是 agent 推理产物（type/severity/description/counterparty/amount/
    confidence）；复核状态（status/comment）由人工在 Finding 表里维护，不属
    于 agent 输出。
    """

    type: str = Field(description="异常类型，如 大额/高频/对手异常")
    severity: Severity
    description: str = Field(description="异常说明，含推理依据")
    counterparty: str | None = None
    amount: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    """analysis agent 输出：异常发现列表 + 整体摘要。"""

    findings: list[FindingItem] = Field(default_factory=list)
    summary: str = Field(description="整体推理摘要，供前端右侧详情区展示")


# ---------------------------------------------------------------------------
# 06-26-ai-agent 维度 agent output_type.
# 维度 agent 一次 run 产出**一条聚合 finding**（PRD §五 Q2）；零命中 → 不建
# finding，由 service 层据 output 判断。detail_text 是右侧详情区正文，引用
# 真实笔数与样本；evidence_record_ids 是命中 flow_record id（关联记录下钻）。
# ---------------------------------------------------------------------------


class DimensionFinding(BaseModel):
    """维度 agent 输出的单条聚合异常发现（PRD §五结构体）。

    字段是 agent 推理产物；复核状态（status/comment）由人工在 Finding 表维护，
    不属于 agent 输出。服务端落库时映射成 Finding 行（含 dimension_id /
    detail_text / evidence_record_ids / source='rule'）。
    """

    type: str = Field(description="异常类型，如 夜间交易/大额交易/整数金额")
    severity: Severity
    counterparty: str | None = None
    amount: str | None = Field(default=None, description="合计金额")
    detail_text: str = Field(description="自然语言分析，引用真实笔数与样本")
    evidence_record_ids: list[int] = Field(
        default_factory=list, description="命中 flow_record id"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class DimensionFindingResult(BaseModel):
    """维度 agent 输出容器：findings 列表（零命中为空）+ 摘要。

    agent.run 的 output_type 用此容器（list 形式以便零命中返空列表，避免 union
    类型注解复杂度）。跑分析 service 取 ``findings``：非空 → 落一条聚合 finding；
    空 → 不建 finding，记 task.config 摘要。
    """

    findings: list[DimensionFinding] = Field(default_factory=list)
    summary: str = Field(
        default="",
        description="本维度推理摘要（零命中时为「未发现X异常」）",
    )


# ---------------------------------------------------------------------------
# AI 关键词生成 agent output_type (keyword_generator.py).
# 用于「关键词库」页「新建关键词卡片」dialog 的 AI 生成按钮。
# 输入：卡片 name + risk_level + note；输出：约 50 个语义相关的关键词列表。
# ---------------------------------------------------------------------------
class KeywordTerms(BaseModel):
    """keyword generation agent 输出：关键词列表容器。

    用于「关键词库」新建卡片 dialog 的 AI 生成按钮。
    agent.run 后由调用方去重（对齐 service._dedup_terms 逻辑），再填入前端表单态。
    生成结果**只填表单态，不自动落库**；用户仍需点「保存」才建卡。
    """

    terms: list[str] = Field(
        default_factory=list,
        description="AI 生成的关键词列表（约 50 个，语义相关于 name+note）。",
    )
