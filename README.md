# 基于覆盖率反馈的迭代式单元测试生成

输入被测函数，生成 pytest，收集语句覆盖率和分支覆盖率，把没走到的路径写进下一轮提示词。

默认生成器仍是 `mock`，不需要密钥。要用基元律动的 NeoHorse-1-9B，把密钥放在项目根目录的 `.env`（已忽略，不会进 Git），然后加 `--provider neohorse`。

这个网关的 `neohorse-1-9b` 会自己返回 `reasoning_content`。`enable_thinking`、`reasoning_effort` 会被拒绝。输出上限是 32768，思考默认开着，采样用评测那组：temperature 1.0、top_p 0.95、top_k 20、presence_penalty 1.5。

## 为什么是这条路径

一次生成很容易只覆盖正常路径。把未覆盖语句和未覆盖分支塞回提示词，下一轮只补缺口，覆盖率才会往上走。语句和分支一起看，是因为某行已经执行过，条件的另一侧仍可能没走过。

对使用者的影响：没有密钥也能复现实验曲线；以后要换真实模型，只换 provider，测试执行和覆盖率收集不用改。

## 环境

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[report]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python experiments\run_experiment.py
.\.venv\Scripts\python experiments\render_preview.py
.\.venv\Scripts\python experiments\build_docs.py
```

单次运行：

```powershell
.\.venv\Scripts\python -m testgen.cli --module subjects.shipping --function shipping_fee
.\.venv\Scripts\python -m testgen.cli --module subjects.shipping --function shipping_fee --provider neohorse
```

对照实验（不把未覆盖路径喂回去）：

```powershell
.\.venv\Scripts\python -m testgen.cli --module subjects.shipping --function shipping_fee --no-feedback --out artifacts\shipping_fee_blind
```
