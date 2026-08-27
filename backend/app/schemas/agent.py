import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


DEFAULT_ALLOWED_TOOLS = ["calculator", "datetime"]


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    model: str = "qwen2.5"
    project_id: int

    allowed_tools: list[str] = Field(
        default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy()
    )

    @field_validator("allowed_tools")
    @classmethod
    def validate_allowed_tools(cls, value: list[str]) -> list[str]:
        """
        Keep tool names clean and prevent duplicates.
        """

        cleaned = []

        for tool_name in value:
            tool_name = tool_name.strip()

            if not tool_name:
                continue

            if tool_name not in cleaned:
                cleaned.append(tool_name)

        return cleaned


class AgentResponse(BaseModel):
    id: int
    name: str
    description: str | None
    model: str
    project_id: int
    allowed_tools: list[str]
    created_at: datetime

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def parse_allowed_tools(cls, value):
        """
        SQLAlchemy stores allowed_tools as JSON text.

        Convert:
            '["calculator", "datetime"]'

        into:
            ["calculator", "datetime"]
        """

        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            try:
                parsed = json.loads(value)

                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        return []

    model_config = {"from_attributes": True}
