# 智行卫士全流程交付 — 总规划

> 本文件是全流程交付的主索引。grill 决策、任务拆分、关键约束、落地参考全部在此。
> 生成于 2026-06-22，分支 feat/web-split。

## 一、grill 决策总表（已闭合）

| # | 决策 | 定论 |
|---|---|---|
| Q1 | Chrome 最低版本 | **108**（硬底线，客户底线） |
| Q2 | 前端栈 | 新建 `frontend/`，**Vite + React 18 + TanStack Router + TanStack Query + Tailwind 4 + lightningcss(chrome108) + shadcn/ui**，纯 SPA |
| Q3 | 路由/数据 | TanStack Router（文件路由）+ TanStack Query |
| Q4 | 部署/鉴权 | 开发分离代理、生产 **FastAPI 一体挂静态**；JWT **access+refresh 存 httpOnly cookie**（SameSite=Strict） |
| Q5 | 页面范围 | 13 视图：6 页中文化+修正 / 7 页新设计；新建任务**弹窗**；AI 分析**多轮对话**；报告**结构化+章节重生成+批注+定稿** |
| Q6 | 清洗不删减 | 记录 **1:1 + 字段全保留(raw_payload JSONB)**；非流水表**保留+标记 excluded 可捞回**；清洗规则**固定+只展示对照，不可调不重洗** |
| Q7 | 数据库 | **PostgreSQL（本地+生产）**，Docker 本地实例；**空库起步重新 seed**；**上 Alembic** |
| Q8 | LLM | **pydantic-ai 全量替换** classifier/normalizer/portrait + 新增 AI 分析 agent；**OpenAI 兼容 provider**，复用 llm.* settings |
| Q9 | 提示词 | **逐字搬运 + output_type schema 校验 + output_validator 兜底**；换框架后**跑回归对比**验证不删减 |
| Q10 | Trellis 拆分 | **中粒度垂直切片**；基建拆**前端基建/后端基建**两个；task.py 脚本归档 |
| Q11 | 联调 | **契约先行**（每切片先定 OpenAPI 契约，前后端并行） |
| Q12 | 旧 web/ | **归档重命名**到 `archive/web-legacy/` |

## 二、任务拆分（已建入 trellis）

伞任务 `06-22-zhixing-full-delivery`（P0）下 10 子任务：

| 编号 | 任务 | 优先级 | 依赖 |
|---|---|---|---|
| B1 | 后端基建 pg迁移+pydantic-ai+cookie鉴权 | P0 | — |
| B2 | 前端基建 frontend栈搭建+设计系统+布局壳 | P0 | — |
| S1 | 登录闭环 | P0 | B1, B2 |
| S2 | Dashboard 闭环 | P1 | B1, B2 |
| S3 | 任务列表 + 新建任务弹窗闭环 | P1 | B1, B2 |
| S4 | 数据导入闭环 | P1 | B1, B2, S3 |
| S5 | 清洗标准化闭环（含不删减回归） | P0 | B1, B2, S4 |
| S6 | AI 分析骨架闭环（agent tools 留接口） | P1 | B1, B2, S5 |
| S7 | 审查报告闭环 | P1 | B1, B2, S5, S6 |
| S8 | 导出 + 设置 + 辅助页闭环 | P2 | B1, B2, S7 |

执行顺序建议：B1/B2 并行 → S1（登录先通，后续切片都要鉴权）→ S2/S3 并行 → S4 → S5（核心底线，P0）→ S6 → S7 → S8。

## 三、硬底线（不可违反）

1. **Chrome 108 渲染** — 前端所有产物必须在 Chrome 108 正常渲染。lightningcss 降级 oklch/lab/color-mix→rgb；Tailwind 4 的 @property/@layer 在 108 均支持。每切片验收必须含"chrome108 渲染正常"。
2. **清洗不删减** — 记录 1:1 + 字段全保留（raw_payload JSONB）；非流水表保留+标记 excluded；换 pydantic-ai 后跑回归 diff 验证无字段丢失。
3. **提示词保真** — classifier/normalizer/portrait 提示词逐字搬进 instructions，不重写；用 output_type + output_validator 做 schema 校验兜底。
4. **单色原则** — 全站禁用彩色（红绿黄）；错误/告警/高风险用黑底白字+粗体+2px 黑边；状态用灰阶胶囊递进。stitch cleaning 页的 #ba1a1a 红色违规必须修正。
5. **不污染主分支** — 全程在 feat/web-split 开发，PR 目标 master。
6. **pydantic-ai 按官方规范** — 严格遵循 docs/research/pydantic-ai-conventions.md（v1.107.0）。output_type 非 result_type；result.output 非 result.data；OpenAIChatModel+OpenAIProvider；await agent.run 禁 run_sync；agent 模块级单例。

## 四、落地参考文档

- `docs/web-pages-design.md` — 13 页面设计规范（含英中对照表，中文化依据）
- `docs/research/pydantic-ai-conventions.md` — pydantic-ai v1.107.0 官方规范落地参考
- `stitch_/monochrome_precision/DESIGN.md` — 单色设计系统（9 级明度、双字体、组件规范）
- `stitch_/*/code.html` — 7 页设计稿源码（中文化+修正依据）

## 五、遗留事项

- **旧 web/ 归档**：`git mv web archive/web-legacy` 因 node_modules 文件锁失败，留到 B2 前端基建任务执行时处理（届时先删 web/node_modules 再 git mv，或用 git rm + 保留副本）。
- **AI 分析 agent 真实 tools/prompt**：本次 S6 只做骨架+占位，agent 的查询工具实现与异常发现 prompt 由用户后续接入（用户明确"保留入口后续完善"）。
- **生产 pg 实例**：本地用 Docker，生产部署时对接客户内网 pg 实例（B1 范围内配好连接字符串可切换）。

## 六、执行入口

按 trellis workflow：每个子任务进入 `start` 前，先在该任务目录下用 `trellis-brainstorm` 完善 prd.md（对齐细节），curate implement.jsonl/check.jsonl（引用 spec + research 文件），再 `task.py start <dir>` 进入 in_progress。

建议从 B1 后端基建开始（pg + pydantic-ai 是后续所有切片的地基）。
