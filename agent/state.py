from datetime import datetime
from typing import Annotated, TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def get_current_datetime_context(timezone: str) -> str:
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%A %d de %B de %Y, %H:%M (%Z)")
