# Journal - zhaozheng (Part 1)

> AI development session journal
> Started: 2026-06-03

---



## Session 1: PDF文件名密码提取规则：括号格式取最后一个括号

**Date**: 2026-06-03
**Task**: PDF文件名密码提取规则：括号格式取最后一个括号
**Branch**: `master`

### Summary

修改 extract_password_from_filename 方法，从'提取文件名开头数字'改为'提取最后一对括号内容'，支持全角半角括号及混配，新增 9 个单元测试

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `9c26efe` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 已完成任务新增流水目录功能

**Date**: 2026-06-03
**Task**: 已完成任务新增流水目录功能
**Branch**: `master`

### Summary

在 completed 状态任务的三个点菜单增加'新增流水目录'选项，支持追加新文件夹文档继续处理。document_folder 改为 List[str]，旧数据自动兼容，追加时按路径去重跳过已有文档，空目录弹出提示，复用现有提取/取消流程。trellis-check 修复了 4 个问题（_is_append 重置、并发 worker 防护、死代码、测试类型断言）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `3bd54f1` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 设置页新增AI提示词Tab与文档画像注入

**Date**: 2026-06-03
**Task**: 设置页新增AI提示词Tab与文档画像注入
**Branch**: `master`

### Summary

在设置页新增第3个Tab「AI提示词」，内嵌3个子Tab管理提示词；新增DocumentPortraitExtractor从非表格文本提取结构化画像；画像与分类Stage1并行执行；提示词Jinja2模板渲染+变量高亮；金额规则改为始终正数+收支类型严格判断；自动保存+脏标记+恢复默认

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `a630e18` | (see git log) |
| `e42fe17` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: 标准化Excel导出增加星期几/休息日列+处理汇总Sheet页

**Date**: 2026-06-05
**Task**: 标准化Excel导出增加星期几/休息日列+处理汇总Sheet页
**Branch**: `master`

### Summary

流水明细Sheet追加星期几(周一~周日)和是否休息日(是/否/未知)两列，纯程序化计算基于transaction_time，使用chinesecalendar库判断法定节假日调休；新增处理汇总Sheet页(文档名称/标准化流水数/状态/失败原因)；ExtractionResult增加per_document_stats跟踪每文档统计

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `b766c44` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 5: 优化画像输入+标准化缺年推断

**Date**: 2026-06-05
**Task**: 优化画像输入+标准化缺年推断
**Branch**: `master`

### Summary

画像输入优化:非表格5000字(可配置)+全量表4行预览(硬编码)+触发条件放宽(有表格即可);画像提示词强调年份提取;标准化提示词增加缺年推断规则(信用卡跨年场景)

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `7e8e471` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 6: Onboarding: join Trellis project

**Date**: 2026-06-15
**Task**: Onboarding: join Trellis project
**Branch**: `feat/web-split`

### Summary

Completed joiner onboarding task 00-join-zhaozheng; learned Trellis workflow, runtime mechanics, and project conventions.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1ea5d3a` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 7: Web-Split Phase 1: 基础设施完成

**Date**: 2026-06-15
**Task**: Web-Split Phase 1: 基础设施完成
**Branch**: `feat/web-split`

### Summary

完成 Phase 1 基础设施搭建：1) web-infra: 修复 9 个 shadcn 组件导入问题，添加前端基础设施（API/WebSocket/Auth hooks）；2) backend-infra: FastAPI 入口、配置管理、12 张数据库模型、Pydantic schemas。所有验收标准通过。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `bf6c1d6` | (see git log) |
| `6e63285` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 8: Review export backend APIs

**Date**: 2026-06-16
**Task**: Review export backend APIs
**Branch**: `feat/web-split`

### Summary

Implemented backend review matching, report generation, Excel and skills bundle export APIs with SQLAlchemy models, permissions, tests, and backend spec contracts.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `c6ede60` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 9: WebSocket notifications

**Date**: 2026-06-16
**Task**: WebSocket notifications
**Branch**: `feat/web-split`

### Summary

Implemented authenticated WebSocket notifications for review, report, and export completion; wired frontend toast feedback and added focused backend tests.

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `d2d7e36` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
