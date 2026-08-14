from app.runtime.planner import plan
import app.runtime.planner as planner


class FakeResponse:

    def json(self):
        return {
            "response": """
            {
                "tool": "calculator",
                "input": "12345*6789"
            }
            """
        }


def fake_post(*args, **kwargs):
    return FakeResponse()


def test_planner_calculator(monkeypatch):

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post
    )

    result = plan("计算12345*6789")

    assert result["tool"] == "calculator"
    assert result["input"] == "12345*6789"



def test_planner_datetime(monkeypatch):

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post
    )

    result = plan("现在几点？")

    assert result["tool"] == "calculator"



def test_planner_no_tool(monkeypatch):

    monkeypatch.setattr(
        planner.requests,
        "post",
        fake_post
    )

    result = plan("介绍一下AgentDesk项目")

    assert result["tool"] is not None
