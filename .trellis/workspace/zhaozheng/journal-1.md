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
