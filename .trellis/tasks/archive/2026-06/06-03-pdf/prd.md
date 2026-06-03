# PDF文件名密码提取规则：支持括号格式取最后一个括号

## Goal

变更 `PDFDecryptor.extract_password_from_filename` 的密码提取规则：从"提取文件名开头连续数字"改为"提取文件名中最后一对括号内的内容"，同时支持全角和半角括号。

## Requirements

* 修改 `extract_password_from_filename` 方法，使用正则从文件名最后一对括号中提取密码
* 支持全角括号 `（）` 和半角括号 `()`
* 全角半角混配也算配对（如 `文件(密码）.pdf`）
* 取最后一个括号对的内容（如 `文件(注释)(123456).pdf` → `123456`）
* 括号内容去除首尾空白
* 无括号时返回 None（不兼容旧的"开头数字"规则）
* 空括号（如 `文件().pdf`）返回 None
* 为该方法添加单元测试

## Acceptance Criteria

- [ ] `文件名(123456).pdf` → 提取密码 `123456`
- [ ] `文件名（123456）.pdf` → 提取密码 `123456`
- [ ] `文件(注释)(123456).pdf` → 取最后一个括号，提取密码 `123456`
- [ ] `文件(注释)（123456）.pdf` → 取最后一个括号（全角），提取密码 `123456`
- [ ] `文件名(密码）.pdf` → 混配括号，提取密码 `密码`
- [ ] `文件名.pdf`（无括号）→ 返回 None
- [ ] `文件().pdf`（空括号）→ 返回 None
- [ ] `文件(  123  ).pdf`（有空白）→ 提取密码 `123`（strip 后）
- [ ] 单元测试全部通过

## Definition of Done

* 修改 `extract_password_from_filename` 实现
* 添加单元测试覆盖上述全部场景
* 不影响现有 `_get_markdown` 流程（调用方式不变）
* Lint / typecheck 通过

## Technical Approach

使用正则表达式 `[（(](.*?)[）)]` 匹配所有括号对，取最后一个 match 的内容。具体实现：

```python
@staticmethod
def extract_password_from_filename(filename: str) -> Optional[str]:
    # 去掉扩展名
    name = Path(filename).stem
    # 匹配所有括号对（全角半角混配），取最后一个
    matches = re.findall(r'[（(](.*?)[）)]', name)
    if not matches:
        return None
    password = matches[-1].strip()
    return password if password else None
```

关键设计点：
- `Path(filename).stem` 先去掉 `.pdf` 扩展名，避免括号出现在扩展名中
- `[（(]` 和 `[）)]` 字符类同时匹配全角和半角，允许混配
- `findall` 取所有匹配，`[-1]` 取最后一个
- `strip()` 去除首尾空白，空字符串返回 None

## Out of Scope

* 修改 `_get_markdown` 中的调用逻辑
* 修改 UI 层密码输入对话框
* 修改 `decrypt` 方法本身
* 兼容旧的"开头数字"命名规则

## Technical Notes

* 核心文件：`src/parsers/pdf_parser.py` 第 27-35 行
* 测试文件：`tests/test_pdf_parser.py`（当前未覆盖此方法）
* 方法签名不变：`extract_password_from_filename(filename: str) -> Optional[str]`
