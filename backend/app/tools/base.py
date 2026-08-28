from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    Base contract for every AgentDesk tool.

    Every tool must provide:
    - name: unique registry name
    - description: human-readable purpose
    - input_schema: metadata describing expected input
    - run(): actual tool execution
    """

    name: str = ""
    description: str = ""

    input_schema: dict = {
        "type": "string",
    }

    @abstractmethod
    def run(self, input: str) -> str:
        """
        Execute the tool and return a string result.
        """
        raise NotImplementedError
