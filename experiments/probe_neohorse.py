"""Verify NeoHorse-1-9B, then ask it for a long, hard, runnable module.

The gateway returns reasoning_content by default and rejects explicit
reasoning switches. A single 32768-token call hits the load balancer's
timeout, so a failed long call is retried as several streamed parts.
The API key is never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "neohorse_probe"


def load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def redact(text: str) -> str:
    secret = os.environ.get("LLM_API_KEY", "")
    if secret:
        return text.replace(secret, "[REDACTED]")
    return text


def request_json(method: str, url: str, payload: dict | None, timeout: int) -> tuple[int, dict | str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def stream_chat(payload: dict) -> tuple[int, str, str]:
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    body = dict(payload)
    body["stream"] = True
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    content: list[str] = []
    reasoning: list[str] = []
    try:
        response = urllib.request.urlopen(req, timeout=900)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        (OUT / "error.txt").write_text(redact(err), encoding="utf-8")
        print(f"stream_status={exc.code}", flush=True)
        return exc.code, "", ""
    with response:
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("reasoning_content"):
                reasoning.append(delta["reasoning_content"])
            if delta.get("content"):
                content.append(delta["content"])
    print(
        f"stream_status=200 reasoning_chars={sum(map(len, reasoning))} content_chars={sum(map(len, content))}",
        flush=True,
    )
    return 200, "".join(content), "".join(reasoning)


def sampling(model: str, messages: list[dict], max_tokens: int) -> dict:
    return {
        "model": model,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repetition_penalty": 1.0,
        "max_tokens": max_tokens,
        "messages": messages,
    }


PARTS = [
    "只写实现，不写测试。实现一个完整可运行的多币种复式分录结算器，代码要长、分支要多，不要省略函数体。包含账户、会计期间、汇率表、分录行。规则：同币种入账、跨币种按汇率折到本位币、红字冲销、部分结清、尾差进汇兑损益、关账后只允许调整分录。借贷不平、关账后普通入账、未知币种、汇率缺失、结算超额都要抛出不同异常。正文必须给出完整 ```python 代码。",
    "不要重写实现。只写 pytest，至少 24 个测试函数，名字从 test_01 开始连续编号。覆盖同币种平衡入账、借贷不平、未知币种、汇率缺失、跨币种折算、汇兑损益、红字冲销、部分结清、结算超额、关账、关账后拒绝普通分录、关账后允许调整分录。每个测试都要能直接运行，使用具体数字或 pytest.raises。正文只输出一个 ```python 代码块。",
]


def main() -> int:
    load_env(ROOT / ".env")
    if not os.environ.get("LLM_API_KEY"):
        print("missing LLM_API_KEY")
        return 1
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    model = os.environ.get("LLM_MODEL", "neohorse-1-9b")
    OUT.mkdir(parents=True, exist_ok=True)

    status, models = request_json("GET", f"{base}/models", None, 60)
    (OUT / "models_status.txt").write_text(f"{status}\n", encoding="utf-8")
    ids = []
    if isinstance(models, dict):
        ids = [str(item.get("id")) for item in models.get("data") or [] if isinstance(item, dict)]
    horse = [item for item in ids if "horse" in item.lower()]
    print(f"models_status={status} count={len(ids)} horse={horse}", flush=True)
    if model not in ids:
        print("model_missing")
        return 1

    system = "你是严谨的 Python 工程师。思考放在推理里，正文只输出一个 ```python 代码块。"
    transcript = [{"role": "system", "content": system}]
    contents: list[str] = []
    reasonings: list[str] = []
    for index, part in enumerate(PARTS, start=1):
        transcript.append({"role": "user", "content": part})
        print(f"part={index} start", flush=True)
        code, content, reasoning = stream_chat(sampling(model, transcript, 32768))
        if not content.strip() and "```python" in reasoning:
            content = reasoning
        (OUT / f"part_{index}_answer.md").write_text(content, encoding="utf-8")
        (OUT / f"part_{index}_reasoning.md").write_text(reasoning, encoding="utf-8")
        if code != 200 or not content.strip():
            print(f"part={index} failed status={code}")
            return 1
        contents.append(content)
        reasonings.append(reasoning)
        transcript.append({"role": "assistant", "content": content})
    (OUT / "answer.md").write_text("\n\n".join(contents), encoding="utf-8")
    (OUT / "reasoning.md").write_text("\n\n".join(reasonings), encoding="utf-8")
    summary = {
        "model": model,
        "parts": len(contents),
        "content_chars": sum(len(item) for item in contents),
        "reasoning_chars": sum(len(item) for item in reasonings),
        "thinking": any(item.strip() for item in reasonings),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
