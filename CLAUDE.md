# 覆盖率反馈的迭代式单元测试生成

## 这个目录解决什么

输入一个被测函数，生成 pytest 用例，跑覆盖率，把没走到的语句和分支写回下一轮提示词。当前实验不调用真实大模型 API。

## 目录

| 路径 | 放什么 | 不放什么 |
| --- | --- | --- |
| `src/testgen/` | 闭环：提示词、模型适配、执行、覆盖率解析 | 被测业务函数 |
| `src/subjects/` | 被测函数，仅标准库 | 测试、密钥 |
| `tests/` | 系统自身的回归测试 | 生成出来的用例 |
| `experiments/` | 实验入口、报告和 PPT 的生成脚本 | 手改的覆盖率数字 |
| `artifacts/` | 每轮测试、提示词、coverage json、截图用页面 | 密钥、虚拟环境 |
| `docs/` | 实验报告 docx、演示 pptx | 源码 |

生成物可以删掉重跑。不要把 `artifacts/` 里的数字手改进报告；报告脚本只读 `artifacts/summary.json`。

## 运行

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[report]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python experiments\run_experiment.py
.\.venv\Scripts\python experiments\render_preview.py
.\.venv\Scripts\python experiments\build_docs.py
```

默认 `--provider mock`。`openai` 适配器在没有 `LLM_API_KEY` 时直接失败，实验脚本禁止使用它。

## 命名

- 模块、函数、变量用英文。
- 一轮实验一个目录：`artifacts/<subject>_<mode>/round_<n>/`。
- 生成的测试函数名：`test_iter<轮次>_<序号>_<被测函数名>`。

## 何时清理

- `.venv/` 只在本机，不提交。
- 重跑实验前可以删掉整个 `artifacts/`。
- 不要把 API key 写进代码、日志或文档。
