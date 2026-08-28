from datetime import datetime

from app.tools.base import BaseTool


class DateTimeTool(BaseTool):
    name = "datetime"

    description = (
        "Return the current local date and time."
    )

    input_schema = {
        "type": "string",
        "description": (
            "Optional user text. This tool does not require a specific input."
        ),
    }

    def run(self, input_text: str) -> str:
        now = datetime.now()

        return now.strftime("%Y-%m-%d %H:%M:%S")
