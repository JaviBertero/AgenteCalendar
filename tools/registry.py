from tools.base import BaseAgentTool
from tools.calendar_tools import (
    CancelMeetingTool,
    CreateMeetingTool,
    FindFreeSlotsTool,
    ListMeetingsTool,
    RescheduleMeetingTool,
)
from tools.contact_tools import GetContactTool, SaveContactTool
from tools.tutor_tools import FindAvailableTutorsTool

# Register all available tools here. Add new tools to this list.
ALL_TOOLS: list[type[BaseAgentTool]] = [
    CreateMeetingTool,
    ListMeetingsTool,
    FindFreeSlotsTool,
    RescheduleMeetingTool,
    CancelMeetingTool,
    GetContactTool,
    SaveContactTool,
    FindAvailableTutorsTool,
]


def get_tool_instances(context) -> list:
    """Instantiate all registered tools bound to the given context."""
    return [tool_cls().to_langchain_tool(context) for tool_cls in ALL_TOOLS]
