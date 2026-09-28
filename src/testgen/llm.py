"""OpenAI-compatible adapter for TokenRhythm NeoHorse.

Thinking is on by default: the gateway returns reasoning_content and rejects
explicit reasoning switches for this model. Sampling follows the NeoHorse
evaluation settings that the gateway accepts. max_tokens uses the account
limit of 32768 so the answer is not cut short.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Protocol

from testgen.mock_provider import MockProvider
from testgen.models import GeneratedTest, GenerationContext

_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)
_DEF = re.compile(r"(?m)^def test_[\w]+\(.*?(?=^def test_|\Z)", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class Provider(Protocol):
    def generate(self, ctx: GenerationContext) -> list[GeneratedTest]:
        """Return new test functions only."""


def load_project_env() -> None:
    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def build_provider(name: str) -> Provider:
    if name == "mock":
        return MockProvider()
    if name in {"openai", "neohorse"}:
        load_project_env()
        return OpenAICompatibleProvider()
    raise ValueError(f"unknown provider: {name}")


def extract_test_functions(text: str) -> list[str]:
    visible = _THINK.sub("", text)
    fenced = _FENCE.findall(visible)
    body = max(fenced, key=len) if fenced else visible
    return [block.strip() + "\n" for block in _DEF.findall(body) if block.strip()]


class OpenAICompatibleProvider:
    """Calls the configured OpenAI-compatible endpoint. The key stays in the environment."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        load_project_env()
        self.api_key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "https://tokenrhythm.studio/v1").rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or "neohorse-1-9b"

    def generate(self, ctx: GenerationContext) -> list[GeneratedTest]:
        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is not set. Use --provider mock.")
        from testgen.prompts import render_prompt

        payload = {
            "model": self.model,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repetition_penalty": 1.0,
            "max_tokens": 32768,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 pytest 作者。先把未覆盖路径想清楚，再只输出新增测试函数。"
                        "测试要具体、可执行、覆盖反馈里的每条缺口。不要解释。"
                    ),
                },
                {"role": "user", "content": render_prompt(ctx)},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=900) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        content = message.get("content") or ""
        tests: list[GeneratedTest] = []
        for index, source in enumerate(extract_test_functions(content), start=1):
            tests.append(
                GeneratedTest(
                    name=f"neohorse_{ctx.iteration}_{index}",
                    source=source,
                    key=("neohorse", ctx.iteration, index, source),
                )
            )
        return tests
