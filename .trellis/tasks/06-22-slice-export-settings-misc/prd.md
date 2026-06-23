# S8 — 导出+设置+辅助页闭环 (slice-export-settings-misc)

垂直切片：导出（报告多格式 + 数据多范围 + 历史 + 预览）+ 设置页（4 Tab）+ 辅助页（空状态/404/500）。父任务 `06-22-zhixing-full-delivery` 第 10 个切片（最后一个），umbrella 9/10 → 10/10。

## 范围边界（决策对齐结果）

- **PDF 用 reportlab**（纯 Python，无系统依赖，Windows 友好）。**不装 weasyprint**（Windows 需 GTK/Pango）。
- **Word 用已装的 python-docx**，**HTML 用模板字符串**。
- **S8 一次性全做**（导出+设置+辅助页）。
- **设置后端全做**：change-password + users/me PATCH + settings/schema + 新设置项种子。
- **数据导出 3 范围 × 2 格式**：原始/标准化/异常 × Excel/CSV。
- **导出预览 = 后端取样**：返回前几行/前几章样本，前端单色渲染，不生成完整产物。
- **辅助页全做**：空状态组件 + 404 catch-all + 500 errorComponent。

## 硬底线（不可违反）

1. **Chrome 108 渲染**：构建 CSS 的 color-mix 必须在 `@supports (color:color-mix(in lab,red,red))` 守护块内且有 fallback；禁裸 oklch/lab/color-mix，只用 9 级 ink token。
2. **单色原则**：全站禁彩色；**错误页禁红**（§D3 黑白表达避免慌乱感）；导出 toggle 灰阶（关浅灰 / 开黑底白圆，不用彩色）；空状态线框 1px 灰线不加填充；设置页安静，分组标题字重建立层级。
3. **不删减精神**：导出只读原数据 + 复制产物，不删原记录；导出历史产物文件保留可重新下载（不删 ExportFile 行/不删产物文件）。
4. **不污染主分支**：全程 `feat/web-split`，禁 git commit（主 agent 驱动）。
5. **不引入新重依赖**：PDF 用 reportlab（需确认是否已装，未装则装纯 Python 包），不装 weasyprint。

## 后端

### 导出扩展（`backend/app/routers/exports.py` + `services/export_service.py`）

ExportFile 表加 `scope` String(50) nullable（记录导出范围：report / raw / standard / findings；旧 excel/bundle 行 scope=null 兼容）。Alembic migration revises `a8f4c2e1b9d3`（S7 head）。

新端点（owner-only 复用 `_load_owned_task`）：

1. `POST /api/tasks/{task_id}/export/report` — body `{format: "pdf"|"docx"|"html", include_annotations: bool}`。基于该 task 当前章节化报告（S7 ReportChapter）+ 可选批注（ReportAnnotation）生成：
   - **pdf**：reportlab 黑白年报排版（章节标题粗体 + 正文段落 + 异常卡片块 + 批注附录）。
   - **docx**：python-docx（标题样式 + 段落 + 批注附录）。
   - **html**：模板字符串生成自包含 HTML（单色内联样式，黑白年报）。
   - 落 ExportFile(scope="report", format=<fmt>, file_path)。返回 ExportResponse。
   - 报告不存在 → 404。
2. `POST /api/tasks/{task_id}/export/data` — body `{scope: "raw"|"standard"|"findings", format: "excel"|"csv"}`。
   - **raw**：flow_records 全部（含 raw_payload）。
   - **standard**：flow_records record_type="standard"。
   - **findings**：S6 findings 全部。
   - Excel 用 openpyxl（黑白表头），CSV UTF-8 BOM。
   - 落 ExportFile(scope=<scope>, format=<fmt>)。
3. `GET /api/tasks/{task_id}/exports` — 导出历史列表（ExportFile 按 created_at 降序，含 scope/format/file_path/created_at）。
4. `GET /api/tasks/{task_id}/export/preview` — query `scope=report|raw|standard|findings`。取样：report 返前 2 章 content 文本；data 返前 20 行 JSON。不生成产物。
5. 沿用现有 `GET /api/exports/{export_id}/download`（owner 校验）。

### 设置后端

6. `POST /api/auth/change-password` — body `{old_password, new_password}`。校验旧密码（错→400/401），新密码长度校验，更新 User.hashed_password。
7. `PATCH /api/users/me` — body `{username?, email?, ...}`（个人信息，当前用户改自己，非 admin-only）。
8. `GET /api/settings/schema` — 返回设置项元数据（key/category/type/label/description/options），供前端表单渲染。type: string|number|boolean|select。
9. 沿用现有 `GET /api/settings/` + `PUT /api/settings/{key}`。

`backend/app/services/settings_service.py` 的 DEFAULT_SETTINGS 扩展：加 `audit.fuzzy_threshold`（float）、`audit.default_confidence_threshold`（float）、`llm.temperature`（float）、`llm.max_tokens`（int）、`audit.default_analysis_mode`（select: quick|deep）、`audit.default_cleaning_ruleset`（string）等设置项（若不存在则加，已存在跳过）。

`backend/app/main.py`：确认 exports/settings/auth/users router 挂载；新增端点若在现有 router 下无需改。

## 前端

### 导出页（`frontend/src/routes/__authenticated/tasks/$id/export.tsx`，§C6）

替换占位为完整导出页：

- **单列卡片分两组**：
  - **报告导出**：格式单选（PDF/Word/HTML，灰阶 segmented）+ 含批注开关（toggle 灰阶：关浅灰 / 开黑底白圆）+ 导出主按钮 → POST export/report。
  - **数据导出**：范围单选（原始/标准化/异常）+ 格式单选（Excel/CSV）+ 导出主按钮 → POST export/data。
- **导出历史列表**：表格（格式/范围/时间/重新下载描边按钮）→ GET exports。
- **预览**：导出前「预览」描边按钮 → GET export/preview，单色渲染报告前几章 / 数据前几行（modal 或卡片展开）。
- **toggle 组件**：灰阶（关浅灰底 / 开黑底白圆），禁彩色。

新增 `frontend/src/hooks/use-exports.ts`：useExportHistory/useExportReport/useExportData/useExportPreview。`api.ts` 追加类型与函数（append-only）。

### 设置页（`frontend/src/routes/__authenticated/settings.tsx`，§D1）

替换占位为完整 4 Tab 设置页：

- **账户 Tab**：个人信息（用户名/邮箱等 → PATCH users/me）+ 改密码（旧/新/确认 → POST auth/change-password）+ 登录设备（占位列表，本轮可静态）。
- **审查参数 Tab**：默认风险阈值/默认分析模式/清洗规则默认集 → 从 settings/schema 渲染表单 → PUT settings/{key}。
- **渠道与解析 Tab**：各渠道启用 + MinerU 配置 → settings 项表单。
- **集成与模型 Tab**：LLM 模型选择 + temperature + max_tokens → settings 项表单。
- 统一表单组件（基于 settings/schema 的 type 渲染 input/number/toggle/select），分组卡片，每组「保存」主按钮。

新增 `frontend/src/hooks/use-settings.ts`（若没有）：useSettings/useSettingsSchema/useUpdateSetting/useChangePassword/useUpdateMe。

### 辅助页

- **空状态组件** `frontend/src/components/layout/empty-state.tsx`：居中线框盾形/文件夹（1px 灰线 SVG，不加填充）+ 标题 + 说明 + 主 CTA。任务列表空时复用。
- **404 catch-all**：TanStack Router `$splat` 路由或 notFoundComponent，大号粗体 404 + 解释 + 返回 Dashboard 主按钮 + 返回上一页描边。
- **500 errorComponent**：TanStack Router errorComponent，大号粗体 500 + 解释 + 返回 Dashboard + 返回上一页。黑白不用红色。

## 验收

- Chrome 108 渲染正常（color-mix 全在 @supports 守护块内）。
- 4 种报告格式可导出（PDF/Word/HTML + 数据 Excel/CSV）。
- 导出历史可重新下载。
- 导出前可预览（单色渲染）。
- 设置可改密码 + 改参数（落 Setting 表）。
- 空状态与 404/500 单色表达（禁红）。
- 后端：`pytest tests/ -x` 全绿（含新增导出/设置/改密码单测）。
- 前端：`pnpm build`（tsc + vite chrome108）通过。

## 不做（避免范围蔓延）

- 关键词词库+三层匹配+注入 AI（后续切片，本轮设置项可预留 key 但不实现匹配逻辑）。
- AI 聊天改造。
- 富文本/真实 LLM 报告重生成。
- 登录设备真实列表（占位静态）。
- weasyprint（用 reportlab 替代）。
