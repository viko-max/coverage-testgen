import ast

from testgen.llm import OpenAICompatibleProvider, extract_test_functions
from testgen.mock_provider import MockProvider, _enumerate
from testgen.models import Feedback, GenerationContext
from testgen.prompts import render_prompt
from subjects.shipping import shipping_fee


def _shipping_source() -> str:
    import inspect

    return inspect.getsource(shipping_fee)


def test_mock_finds_raise_and_region_paths():
    tree = ast.parse(_shipping_source())
    func = tree.body[0]
    candidates = _enumerate(shipping_fee, func)
    keys = {item.key for item in candidates}
    assert any(item.exc_type == "ValueError" for item in candidates)
    assert any(item.args.get("region") == "remote" for item in candidates)
    assert any(item.args.get("member") is True for item in candidates)
    assert len(keys) >= 4


def test_prompt_includes_uncovered_lines():
    ctx = GenerationContext(
        module_name="subjects.shipping",
        function_name="shipping_fee",
        source=_shipping_source(),
        existing_tests="def test_old():\n    pass\n",
        iteration=2,
        feedback=Feedback(
            statement_percent=40.0,
            branch_percent=25.0,
            missing_lines=[8],
            missing_line_text=['raise ValueError("weight must be positive")'],
            missing_branches=[],
        ),
        use_feedback=True,
    )
    text = render_prompt(ctx)
    assert "未覆盖语句" in text
    assert "L8:" in text
    assert "weight must be positive" in text
    assert "40.0%" in text


def test_first_round_prompt_has_no_gap_list():
    ctx = GenerationContext(
        module_name="subjects.shipping",
        function_name="shipping_fee",
        source="def shipping_fee():\n    return 0\n",
        existing_tests="",
        iteration=0,
        feedback=Feedback(),
        use_feedback=True,
    )
    text = render_prompt(ctx)
    assert "本轮不提供未覆盖路径" in text


def test_openai_adapter_refuses_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = OpenAICompatibleProvider(api_key="")
    ctx = GenerationContext(
        module_name="subjects.shipping",
        function_name="shipping_fee",
        source="def shipping_fee():\n    return 0\n",
        existing_tests="",
        iteration=0,
        feedback=Feedback(),
        use_feedback=False,
    )
    try:
        provider.generate(ctx)
    except RuntimeError as exc:
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("expected the adapter to refuse")


def test_extract_test_functions_from_fence():
    text = """说明文字
```python
def test_one():
    assert True

def test_two():
    assert 1 == 1
```
"""
    found = extract_test_functions(text)
    assert len(found) == 2
    assert found[0].startswith("def test_one")


def test_mock_feedback_prefers_a_missing_line():
    provider = MockProvider()
    base = GenerationContext(
        module_name="subjects.shipping",
        function_name="shipping_fee",
        source=_shipping_source(),
        existing_tests="",
        iteration=0,
        feedback=Feedback(),
        use_feedback=False,
    )
    first = provider.generate(base)
    assert len(first) == 1
    seen = {first[0].key}
    follow = GenerationContext(
        module_name="subjects.shipping",
        function_name="shipping_fee",
        source=_shipping_source(),
        existing_tests=first[0].source,
        iteration=1,
        feedback=Feedback(
            statement_percent=10,
            branch_percent=10,
            missing_lines=[7, 8],
            missing_line_text=["if weight <= 0:", 'raise ValueError("weight must be positive")'],
            missing_branches=[],
        ),
        use_feedback=True,
        seen_keys=seen,
    )
    second = provider.generate(follow)
    assert second
    assert second[0].key not in seen
    assert "pytest.raises" in second[0].source
