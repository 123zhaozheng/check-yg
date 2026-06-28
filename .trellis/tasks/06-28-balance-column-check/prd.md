# 余额列 + 余额防篡改校验

> 领导要求：流水标准化多一列**余额**。用「上一行余额 ± 本笔收支金额 = 本行余额」
> 逐行复核，对不上就指出——用来发现员工篡改金额 / 删除流水行。校验虽是确定性算术，
> 但 OCR + 大模型清洗有不确定性，故不符行支持**采纳/忽略**人工复核（复用 Finding
> 状态机）。无余额列的文档（信用卡等）跳过。

## 现状（代码事实）

- 字段映射驱动：`portrait.py` 用 LLM 把源表头映射到 **8 个标准字段**
  （`transaction_time/counterparty_name/counterparty_account/amount/raw_amount/
  summary/transaction_type/source_file`，见 `portrait.py:56`），存 `DocumentPortrait`
  （`types.py:55`，`column_mapping` 数组）。**无 balance 字段**。
- normalizer（`normalizer.py`）按 `column_mapping` 抽字段，输出 `NormalizedRow`
  （`types.py:26`，`amount/raw_amount/transaction_type`…）。**关键坑**：normalizer
  把含「余额」的行当噪音过滤（`is_valid=false`，`normalizer.py:15,60`）——现在
  「余额」被当汇总噪音，不是逐行数据列。
- `extractor.py:757-820`：normalizer 输出 → 落 `FlowRecordRow`（`flow_record.py:25`），
  `record_type=standard`。模型现有 `amount/raw_amount`，**无 balance 列**。
- `NormalizedRow.transaction_type` = "收入"/"支出"（normalizer 清洗出的收支方向），
  **校验方向就用它**（user 定：用大模型清洗的收/支，不用 amount_sign_rule 再判）。
- `Finding` 模型（`finding.py`）已有 `source` 列（ai-agent 任务加的，`rule`|历史占位）+
  `status`(pending|accepted|ignored) + `comment` + `evidence_record_ids`。**校验不符行
  复用它**：`source="balance_check"`，状态机/PATCH/报告取 accepted 全现成。
- 金额解析复用 `app/services/audit/parsing.py::parse_amount`（ai-agent 任务，多格式）。
- clean 页（`tasks/$id/clean.tsx`）流水表 + records hook（`use-records.ts`）。

---

## 一、portrait 加 `balance` 标准字段（8 → 9）

- `types.py:55 DocumentPortrait`：标准字段词表加 `balance`（`column_mapping` 里出现
  `"balance"` 即可）。**不加** opening/closing 画像字段——期初/期末从 portrait 抽不靠谱
  （少见 + LLM 不稳），改用余额列**首尾两条**当锚点（见 §四）。
- `portrait.py` 提示词（`SYSTEM_PROMPT_DOCUMENT_PORTRAIT`）：
  - 「映射指导」段 8 字段 → 9 字段，加 `balance`（账户余额/当前余额列）。
  - 教 LLM：源表头含「余额/账户余额/当前余额/结余」→ 映射 `balance`。
  - few-shot `column_mapping` 样例加一列 balance。
- `PORTRAIT_FIELDS`（`portrait.py:83`）注释同步。

## 二、normalizer 抽取 balance（核心坑）

- `types.py:26 NormalizedRow`：加 `balance: str = ""`。
- `normalizer.py` 提示词：
  - 标准字段段加 `balance - 账户余额（本笔交易后的账户余额，原封不动还原）`。
  - 输出 JSON 样例每行加 `"balance": "..."`。
  - **坑①（必须精准）**：区分「余额**列**的逐行数据」（`is_valid=true`，保留进 balance）
    vs「余额**汇总行**」（如「期末余额」「账户余额：xxx」独占一行，`is_valid=false` 噪音）。
    判据：该行若**同时有交易时间/金额等流水字段** → 是流水行，余额进 `balance`；
    若**只有余额没有交易** → 汇总噪音行，照旧 `is_valid=false`。
- `extractor.py:757-820`：落 `FlowRecordRow` 时 `balance=row.balance`。

## 三、`FlowRecordRow` 加 balance 列（additive Alembic 迁移）

- `flow_record.py`：`balance: Mapped[str | None] = mapped_column(String(100), nullable=True)`
  （跟 `amount` 同形，nullable——无余额列文档为空）。
- 新迁移 `add_balance_column`：`op.add_column('flow_records', balance)`。
  `migrations/env.py` 无需改（模型已登记）。downgrade drop column。
- 不动现有字段；raw_payload 仍存原始全部单元格（清洗不删减底线不变）。

## 四、余额校验算法（首尾锚点 + 时分秒 gate，顺序可靠）

> **设计转向（user feedback）**：原「逐行余额链」按 row_index 排，但流水**并发分批清洗**
> 行序不保证是原文档顺序 → 不可靠。改用：**余额列首尾两条当锚点 + 按时分秒排时序**。
> 时分秒是真实交易时刻（不像 row_index 受清洗顺序影响）→ 时序可靠。期初/期末不靠 portrait
> 抽（少见 + LLM 不稳），直接用列里首条/末条余额。代价：只标「该文档对不上」，不定位行——
> 领导要的是**标可疑文档让人复核**，够用。

**触发（gate）**：每个文档 standard 行落库后，若该文档 `column_mapping` 含 `balance`
（有余额列）**且**有「时分秒」的行（可按时序排）→ 跑校验；**无时分秒**（行只有日期 /
00:00:00）→ **默认通过、跳过不报错**（user 定）。

**算法**（按时序，首尾锚点）：
```
rows = 该文档 record_type='standard' 行里：交易时间带时分秒（_has_hms）且 balance 非空
if len(rows) < 2: 跳过（无/不足时分秒数据 → 默认通过）
rows 按 parse_datetime(transaction_time) 升序   # 时分秒 → 时序可靠
B1 = parse_amount(rows[0].balance)    # 首条余额（锚点）
BN = parse_amount(rows[-1].balance)   # 末条余额
# 净收支：第 2 条起，收入 +、支出 −；transaction_type 非收/支的行不计入（保守）
net = Σ (+parse_amount(r.amount) if r.transaction_type=="收入"
         −parse_amount(r.amount) if r.transaction_type=="支出"
         else 0)  for r in rows[1:]
expected = B1 + net
if abs(expected - BN) > max(0.01, 0.0001*abs(BN)):   # 容差：绝对 0.01 或 万分之一
    生成 Finding(source="balance_check", document_id=该文档, type="余额不符",
      severity="medium", confidence=1.0, counterparty=None,
      amount=f"¥{abs(net):,.2f}",
      detail_text=f"余额对账不符（按时序）：首条余额 {B1:,.2f} + 后续净收支 "
                  f"{net:+,.2f} = 期望末条 {expected:,.2f}，实际末条 {BN:,.2f}，"
                  f"差 {BN-expected:+,.2f}。疑似金额被修改或流水被删/增。",
      evidence_record_ids=[])   # 文档级，无单行证据
```

- **等式直觉**：从第一笔余额出发，把后面所有收支加加减减，应正好等于最后一笔余额。
- **时分秒的作用**：只让有时分秒的行参与（才能可靠按时序排）；没时分秒的文档直接放过。
- **改金额/删行**：改任一金额 → net 变 → expected 变 → 对不上；删/增行 → 求和项变 → 对不上。
  一个文档**最多一条**不符 finding。
- 容差：绝对 0.01 + 相对万分之一（大金额浮点/分级兜底）。
- `_has_hms` 复用 `app/llm/analysis.py`（已判 00:00:00 噪音）——若不便跨模块 import，
  在 balance_check 内同名小工具实现（剔全 0 时分秒）。
- parse_datetime 复用 `app/services/audit/parsing.py`。
- 校验服务 `app/services/audit/balance_check.py`：纯函数 `check_balance_totals` +
  异步 `run_balance_check`（取该文档 hms+balance 行 → 求和）。runner hook 不变（per-doc
  standard 落库后调）。

## 五、校验结果 = `source="balance_check"` Finding（复用状态机）

- 不符**文档**落 `Finding`（`source="balance_check"`，`document_id`=该文档），每文档**最多一条**，
  默认 `status=pending`、`severity=medium`。
- **复用**：现有 `PATCH /findings/{id}`（status/comment）、状态机、报告取 accepted。
- **AI 分析页不污染**：`GET /tasks/{id}/findings` 默认排除 `source=balance_check`
  （`?source=balance_check` 单取）；analyze 页只显维度 finding。
- **重跑**：重新标准化某文档 → 先删该文档（`task_id + source + document_id`）的旧 finding
  再重算（已有 `Finding.document_id`，多文档/append 都正确，不互相覆盖）。

## 六、UI（clean 页 `tasks/$id/clean.tsx`）

1. 流水表加一列**余额**（读 `FlowRecordRow.balance`，空则「—」）。
2. 「**余额校验**」区：列出该任务所有 `source="balance_check"` 的 finding（每文档一条），
   显 detail_text（期初/净收支/期望期末/实际期末/差额，等宽数字）+ 状态 pill + **采纳/忽略**
   按钮（复用 `usePatchFinding`）。
3. 空态：「暂无余额校验异常」（无余额列文档不产 finding，任务级不细分）。

---

## 七、数据模型

- `FlowRecordRow.balance`（String(100), nullable）—— additive（已加）。
- `Finding.document_id`（Integer FK documents.id CASCADE, nullable）—— additive（已加），
  用于余额校验 finding 按文档范围重算。`source` 新增值 `"balance_check"`。
- 不动 portrait（不抽期初/期末，首尾锚点直接读 balance 列）。

## 八、验收标准

- [ ] portrait 把「余额」列映射到 `balance`；normalizer 逐行抽 balance（余额列数据保留、
      汇总行过滤）。
- [ ] `FlowRecordRow.balance` 落库；clean 页流水表显余额列。
- [ ] **有余额列 + 有时分秒行**的文档标准化后自动跑余额对账，不符产 1 条 finding；
      无余额列 / 无时分秒行 → 跳过不报错（默认通过）。
- [ ] 校验按时序（时分秒）：首条余额 + 后续净收支 ≟ 末条余额，容差内过、超容差产 finding
      （detail_text 含首条/净收支/期望末条/实际末条/差额）。
- [ ] 改任一金额 / 删增行 → 对不上；transaction_type 非收/支的行不计入净收支。
- [ ] 校验 finding 走采纳/忽略（PATCH），AI 分析页不显 balance_check，报告取 accepted。
- [ ] 重新标准化按文档清旧 balance_check finding 重算；多文档互不覆盖。
- [ ] 单测：对账纯逻辑（相符/改金额不符/删行不符/方向不明行不计入/无时分秒跳过/
      无余额列跳过/容差边界）、多文档不覆盖；normalizer balance 抽取不丢不混噪音。

## 九、风险

| 风险 | 缓解 |
|---|---|
| normalizer 把余额列数据当噪音丢 / 汇总行混进流水 | 提示词精准判据 + 单测 |
| 无时分秒行无法定时序 | gate：无时分秒 → 默认通过跳过（不报错） |
| 方向不明（transaction_type 非收/支）行 | 不计入净收支（保守跳过） |
| 浮点/分级精度 | 容差 = max(0.01, 万分之一×\|末条余额\|) |
| 误报（OCR/模型误差） | 默认 medium + 采纳/忽略人工复核 |
| 重跑/多文档 finding 覆盖 | `Finding.document_id` 按文档范围删+重算 |

## 十、已落地（实现进展）

- balance 列、portrait balance 字段、normalizer 抽取、`FlowRecordRow.balance` + 迁移、
  extractor 落库、`Finding.document_id` + 迁移、runner 校验 hook、findings source 过滤、
  clean 页余额列 + 余额校验区（采纳/忽略）——**均已完成**（逐行法版本，258 测试过）。
- **本转向待做**：把 `check_balance_chain`（逐行）换成 `check_balance_totals`（总额对账，
  顺序无关）+ portrait 加 `opening_balance`/`closing_balance`；其余复用。
