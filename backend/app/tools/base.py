from abc import ABC, abstractmethod
from typing import Any, Dict, Union


class ToolArgumentsError(ValueError):
    """
    Raised when tool arguments do not satisfy the tool input contract.
    """


class BaseTool(ABC):
    """
    Base contract for every AgentDesk tool.

    Every tool must provide:
    - name: unique registry name
    - description: human-readable purpose
    - input_schema: metadata describing expected input
    - run(): actual tool execution

    Structured arguments are validated against input_schema before
    execution.

    Legacy string input remains supported during the migration to the
    structured tool contract.
    """

    name: str = ""
    description: str = ""

    input_schema: dict = {
        "type": "string",
    }

    def validate_arguments(
        self,
        arguments: Union[str, Dict[str, Any]],
    ) -> None:
        """
        Perform lightweight validation using the tool's input_schema.

        This intentionally supports the subset of JSON Schema currently
        required by AgentDesk:
        - type
        - properties
        - required
        - additionalProperties
        """

        # Legacy string contract.
        if isinstance(arguments, str):
            return

        if not isinstance(arguments, dict):
            raise ToolArgumentsError(
                "tool arguments must be a string or object"
            )

        schema = self.input_schema or {}

        if schema.get("type") != "object":
            raise ToolArgumentsError(
                f"tool '{self.name}' does not accept structured arguments"
            )

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for field in required:
            if field not in arguments:
                raise ToolArgumentsError(
                    f"missing required argument: '{field}'"
                )

        if schema.get("additionalProperties") is False:
            unknown = set(arguments) - set(properties)

            if unknown:
                raise ToolArgumentsError(
                    f"unknown arguments: {sorted(unknown)}"
                )

        for field, value in arguments.items():
            field_schema = properties.get(field)

            if not field_schema:
                continue

            expected_type = field_schema.get("type")

            if expected_type == "string" and not isinstance(value, str):
                raise ToolArgumentsError(
                    f"argument '{field}' must be a string"
                )

    def execute(
        self,
        arguments: Union[str, Dict[str, Any]],
    ):
        """
        Validate arguments and execute the tool.
        """

        self.validate_arguments(arguments)
        return self.run(arguments)

    @abstractmethod
    def run(
        self,
        arguments: Union[str, Dict[str, Any]],
    ):
        """
        Execute the tool.
        """
        raise NotImplementedError
