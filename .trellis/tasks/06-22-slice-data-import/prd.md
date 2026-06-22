# S4 数据导入闭环

## 目标
垂直切片：数据导入页完整闭环。前端中文化对齐 `stitch_/data_import/code.html`，后端补 channel 维度 + documents 列表/删除端点。Chrome 108 可渲染。

## 硬底线（全程不可违反）
1. **Chrome 108 渲染**：lightningcss 已降级 oklch/lab/color-mix→rgb，CSS color-mix 都在 `@supports` 守护块内且有 fallback。新增样式禁用 color-mix/oklch 裸写，用 9 级 ink token。
2. **清洗不删减**：本切片只做导入，不动清洗逻辑；Document 删除走软删（status 标记，不删行），保留 raw_payload 可捞回。
3. **单色原则**：禁彩色，9 级 ink 灰阶；error/失败态黑底白字粗体；状态胶囊灰阶递进（Pending 浅灰 / Parsing 中灰带转圈 / Done 深灰 / Failed 黑底白字重试）。
4. **MinerU 单次 fetch**：PDF 解析复用现有 `extract_tables_and_context`，不二次调用。
5. **path-aware identity**：`name|posix_path` md5，run-{n} 子目录隔离同名文件。

## 前端范围（`frontend/src/routes/__authenticated/tasks/$id/import.tsx`）
替换 TabPlaceholder 为完整数据导入页：
- **左渠道列表**：银行流水 / 支付渠道 / 证券交易 / 票据凭证 / 其他；选中项左侧黑竖条；每渠道已导入文件数角标。
- **右上传区**：渠道标题 + 大号虚线拖拽框（"拖拽文件到此处"，支持 PDF/XLSX/CSV/DOCX）+ 描边"选择文件"按钮 + 黑底"开始处理"主按钮。
- **文件表**：文件名 / 类型 / 大小 / 解析状态灰阶胶囊 / 上传时间 / 操作（查看 + 删除）。
- **状态轮询**：TanStack Query refetchInterval 轮询 documents 列表，pending/processing 期间持续轮询，全完成停止。
- **失败重试**：Failed 胶囊附 Retry 按钮。

## 后端范围（`backend/app/routers/tasks.py` + `backend/app/models/document.py` + 新 migration）
- **Document 加 `channel` 字段**（String，nullable）+ Alembic migration（revises 79b320f02b84，env.py 登记新模型无新增模型则只加列）。
- **`POST /api/tasks/{task_id}/upload`**：multipart 多文件 + `channel` 表单参数，复用 `_save_uploads` + run-{n} 目录 + 启动 extraction（在现有 append-upload 基础上支持 channel 透传到 Document）。
- **`GET /api/tasks/{task_id}/documents?channel=`**：返回该任务（可选按渠道过滤）的文件列表 + 解析状态 + 大小 + 上传时间。
- **`DELETE /api/tasks/{task_id}/documents/{doc_id}`**：软删（status→"deleted" 或 archived 标记，不删行）。
- WebSocket 进度推送保留（不在本切片扩展）。

## 契约先行
先定 DocumentResponse schema + 端点签名，前后端对齐后再实现。

## 实施决策（2026-06-22 切片定稿）

- **channel 端点选择**：现有 `POST /{task_id}/append-upload` 已满足"已存在 task 上传"。**不新增 `/upload` 重复端点**，只在 `POST /upload`（建任务即传）和 `POST /{task_id}/append-upload`（追加传）两个端点各加 `channel: str = Form(None)` 表单参数。
- **Document channel 持久化路径**：采用 **upload 时预建 Document 行**（status="pending"，带 channel/filename/original_path/size_bytes），runner `_persist_result_documents` 改为 **按 filename 匹配并 update 现有行**（更新 flow_tables + status="completed"），不再 `delete ... where(task_id=...)`。无匹配行则 fallback 创建（channel=None）。这样：① 软删（status="deleted"）的行不被复删，永留；② 跨 run 的 channel 由预建行保留，runner 不覆盖；③ 现有 `test_runner_persists_result_records_for_review_services`（无预建行，直接调 `_persist_result_documents`）走 fallback 创建路径，仍绿。
- **Document 新增字段**：`channel` String(50) nullable + `size_bytes` Integer nullable（DocumentResponse 需要）。单条 Alembic migration（revises `79b320f02b84`），同时加进 `_run_lightweight_migrations` 的 sqlite ALTER 列分支。
- **GET /documents 软删可见性**：默认 **不含** status="deleted"（与 `list_tasks` 默认隐藏 archived 一致）。提供 `include_deleted: bool = Query(False)` 可显式取回。前端导入页用默认（隐藏已删）。
- **渠道 key**：用中文 label 直接作 channel 值（"银行流水"/"支付渠道"/"证券交易"/"票据凭证"/"其他"），与 Task.expected_channels 语义一致。
- **前端文件类型校验**：后端 scanner 实际支持 {.pdf,.docx,.xlsx,.xls}，不支持 .csv。前端文案改 "PDF / Excel / Word"，校验白名单对齐后端。
- **失败重试**：无后端 retry 端点；前端"重试" = 用缓存原 File 对象重新触发上传（调同一 upload mutation）。
- **多 channel 跨 run append 的 channel 覆盖问题**：本切片不专门处理（边缘场景）；预建行 + runner update 方案已天然保留各 run 的 channel，仅"同 filename 跨 run"这种既有歧义场景仍按首次匹配行更新，属可接受局限。

## 验收
- chrome108 拖拽上传正常渲染。
- 解析状态实时更新（轮询），失败可重试。
- 按渠道归集文件，渠道切换文件列表随之过滤。
- 大文件解析不阻塞 UI（轮询 + 后台 extraction）。
- 后端测试：channel 透传、documents 列表过滤、delete 软删、422 无支持文件回归。

## 不做（留给后续切片）
- 清洗标准化（S5）、AI 分析（S6）、报告（S7）、导出（S8）。
- WebSocket 扩展（保留现有，不新增）。
