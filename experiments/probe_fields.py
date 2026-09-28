"""Find which request fields this gateway accepts, then stop. Does not print the key."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def post(payload: dict) -> tuple[int, str]:
    base = os.environ["LLM_BASE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> None:
    load_env()
    model = os.environ["LLM_MODEL"]
    base_messages = [{"role": "user", "content": "只回答数字 2。"}]
    base = {"model": model, "messages": base_messages, "max_tokens": 64, "temperature": 1}
    candidates = [
        ("plain", {}),
        ("top_p", {"top_p": 0.95}),
        ("presence_penalty", {"presence_penalty": 1.5}),
        ("top_k", {"top_k": 20}),
        ("min_p", {"min_p": 0}),
        ("repetition_penalty", {"repetition_penalty": 1}),
        ("enable_thinking", {"enable_thinking": True}),
        ("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": True}}),
        ("reasoning_effort", {"reasoning_effort": "high"}),
        ("thinking", {"thinking": {"type": "enabled"}}),
    ]
    for name, extra in candidates:
        status, body = post({**base, **extra})
        secret = os.environ["LLM_API_KEY"]
        snippet = body.replace(secret, "[REDACTED]")[:240].replace("\n", " ")
        print(f"{name} status={status} body={snippet}")


if __name__ == "__main__":
    main()
