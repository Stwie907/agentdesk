def plan(user_input: str):

    if any(
        op in user_input
        for op in ["+", "-", "*", "/"]
    ):
        return {
            "tool": "calculator",
            "input": user_input
        }


    return {
        "tool": None,
        "input": user_input
    }

