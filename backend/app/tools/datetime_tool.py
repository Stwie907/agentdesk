from typing import Any, Dict, Union
from datetime import datetime

from app.tools.base import BaseTool


class DateTimeTool(BaseTool):
    name = "datetime"

    description = (
        "Return the current local date and time."
    )

    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def run(
        self,
        arguments: Union[str, Dict[str, Any]],
    ) -> str:
        # Backward compatibility:
        # old runtime may still pass an empty string.
        if isinstance(arguments, str):
            arguments = {}

        now = datetime.now()

        return now.strftime("%Y-%m-%d %H:%M:%S")
