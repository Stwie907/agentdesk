from app.runtime.planner import plan


def test_planner_calculator():
    result = plan("计算12345*6789")

    assert result["tool"] == "calculator"
    assert result["input"] == "12345*6789"


def test_planner_datetime():
    result = plan("现在几点？")

    assert result["tool"] == "datetime"


def test_planner_no_tool():
    result = plan("介绍一下AgentDesk项目")

    assert result["tool"] is None
    assert result["input"] == "介绍一下AgentDesk项目"
