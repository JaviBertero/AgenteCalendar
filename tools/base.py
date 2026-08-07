from abc import ABC, abstractmethod
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


class ToolContext(BaseModel):
    """Context passed to every tool invocation."""

    model_config = {"arbitrary_types_allowed": True}

    user_id: int
    telegram_id: int
    timezone: str
    user_name: str = "Usuario"


class BaseAgentTool(ABC):
    """Base class for agent tools. Subclass to add new capabilities."""

    name: str
    description: str

    @abstractmethod
    def get_args_schema(self) -> type[BaseModel]:
        ...

    @abstractmethod
    async def execute(self, context: ToolContext, **kwargs: Any) -> str:
        ...

    def to_langchain_tool(self, context: ToolContext) -> StructuredTool:
        args_schema = self.get_args_schema()

        async def _run(**kwargs: Any) -> str:
            return await self.execute(context, **kwargs)

        return StructuredTool.from_function(
            coroutine=_run,
            name=self.name,
            description=self.description,
            args_schema=args_schema,
        )
