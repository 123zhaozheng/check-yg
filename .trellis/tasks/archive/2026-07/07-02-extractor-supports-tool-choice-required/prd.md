# Extractor 三模块透传 supports_tool_choice_required

## 背景
normalization 阶段绑定 deepseek-v4-flash（卡片 `supports_tool_choice_required=false`），
DeepSeek 在 thinking 模式下拒绝 `tool_choice=required`，返回 400
`Thinking mode does not support this tool_choice`，导致整批流水行标准化失败。

卡片字段在 `analysis.py` / `keyword_generator.py` 已透传到 `get_agent`，但 extractor
的 classifier / portrait / normalizer 三模块没接 —— 走的是 `agent_factory.get_agent`
默认 `supports_tool_choice_required=True`，pydantic-ai 一直发 `tool_choice=required`。

## 目标
让 extractor 三模块对齐 `analysis.py` 的接法：卡片声明 `supports_tool_choice_required=false`
时 → `get_agent` 建 profile `openai_supports_tool_choice_required=False` → pydantic-ai
降级 `tool_choice=auto`，DeepSeek 不再 400。

## 改动范围
1. `backend/app/services/extraction/extractor.py::_resolve_stage_llm_params`
   - 无卡片：返回 `"supports_tool_choice_required": True`（默认，兼容旧行为）
   - 有卡片：`"supports_tool_choice_required": bool(model.supports_tool_choice_required)`
2. `backend/app/llm/classifier.py::FlowTableClassifier`
   - `__init__` 增参 `supports_tool_choice_required: bool = True`，存到 `self.`
   - `_agent()` 的 `get_agent(...)` 传 `supports_tool_choice_required=self.supports_tool_choice_required`
3. `backend/app/llm/normalizer.py::FlowDataNormalizer`
   - 同上（`__init__` + `_get_agent()`）
4. `backend/app/llm/portrait.py::DocumentPortraitExtractor`
   - 同上（`__init__` + `_agent()` / `_get_agent()` —— 视实际方法名）
5. `agent_factory.get_agent` 的缓存 key 已含 `supports_tool_choice_required`，无需改。

## 验证
- `backend/tests/test_llm_model_card.py` 现有用例通过；
- 新增/补充一个用例：normalization 阶段绑定 `supports_tool_choice_required=false` 卡片
  → `extractor.normalizer.supports_tool_choice_required is False`；
- deepseek-v4-flash 实跑标准化不再 400（手动跑一次流水导入，看日志确认）。

## 不做
- 不动 `thinking` 透传（已正确，off / 非 reasoning → None）。
- 不动 analysis.py / keyword_generator.py（已正确）。
- 不动 agent_factory。
