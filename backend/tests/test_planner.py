import json

from app.runtime.planner import plan
import app.runtime.planner as planner


class FakeResponse:
    def __init__(self, tool, tool_input):
        self.tool = tool
        self.tool_input = tool_input

    def json(self):
        return {
            "response": json.dumps(
                {
                    "tool": self.tool,
                    "input": self.tool_input,
                }
            )
        }


def test_planner_calculator(monkeypatch):
    def fake_post(*args, **kwargs):
        return FakeResponse(
            "calculator",
            "12345*6789",
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan(
        "计算12345*6789",
        allowed_tools=["calculator", "datetime"],
    )

    assert result["tool"] == "calculator"
    assert result["input"] == "12345*6789"


def test_planner_datetime(monkeypatch):
    def fake_post(*args, **kwargs):
        return FakeResponse(
            "datetime",
            "",
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan(
        "现在几点？",
        allowed_tools=["calculator", "datetime"],
    )

    assert result["tool"] == "datetime"
    assert result["input"] == ""


def test_planner_rejects_disallowed_tool(monkeypatch):
    def fake_post(*args, **kwargs):
        # Simulate the LLM ignoring the prompt and attempting
        # to select a tool the Agent is not allowed to use.
        return FakeResponse(
            "datetime",
            "",
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan(
        "现在几点？",
        allowed_tools=["calculator"],
    )

    assert result["tool"] is None
    assert result["input"] == "现在几点？"


def test_planner_prompt_only_contains_allowed_tools(
    monkeypatch,
):
    captured = {}

    def fake_post(*args, **kwargs):
        captured["prompt"] = kwargs["json"]["prompt"]

        return FakeResponse(
            "calculator",
            "1+1",
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan(
        "计算1+1",
        allowed_tools=["calculator"],
    )

    assert result["tool"] == "calculator"

    prompt = captured["prompt"]

    assert "calculator" in prompt
    assert "2. datetime" not in prompt


def test_planner_no_allowed_tools_skips_llm(
    monkeypatch,
):
    called = {
        "value": False,
    }

    def fake_post(*args, **kwargs):
        called["value"] = True

        raise AssertionError(
            "LLM should not be called when no tools are allowed"
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan(
        "现在几点？",
        allowed_tools=[],
    )

    assert result == {
        "tool": None,
        "input": "现在几点？",
    }

    assert called["value"] is False


def test_planner_none_permissions_keeps_backward_compatibility(
    monkeypatch,
):
    def fake_post(*args, **kwargs):
        return FakeResponse(
            "calculator",
            "2+3",
        )

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post,
    )

    result = plan("计算2+3")

    assert result["tool"] == "calculator"
    assert result["input"] == "2+3"
