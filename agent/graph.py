from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None

from agent.prompts import SYSTEM_PROMPT
from agent.state import get_current_datetime_context
from config.settings import settings
from tools.base import ToolContext
from tools.registry import get_tool_instances


class CalendarAgent:
    def __init__(self, context: ToolContext):
        self.context = context
        models = []

        # 1. Cargar todas las API keys de Groq configuradas en .env
        groq_keys = settings.get_groq_api_keys()
        if ChatGroq is not None and groq_keys:
            for key in groq_keys:
                models.append(
                    ChatGroq(
                        model=settings.groq_model,
                        groq_api_key=key,
                        temperature=0,
                    )
                )

        # 2. Si no hay Groq pero hay Gemini, usar Gemini
        if not models and settings.gemini_api_key:
            models.append(
                ChatGoogleGenerativeAI(
                    model=settings.gemini_model,
                    google_api_key=settings.gemini_api_key,
                    temperature=0,
                )
            )

        if not models:
            raise ValueError("No se ha configurado ninguna API Key válida para LLM (Groq o Gemini).")

        # 3. Encadenar los modelos con .with_fallbacks(): si una key falla (ej. 429 Rate Limit), pasa automáticamente a la siguiente
        if len(models) > 1:
            self.llm = models[0].with_fallbacks(models[1:])
        else:
            self.llm = models[0]

        self.tools = get_tool_instances(context)
        self._agent = self._build_agent()




    def _build_agent(self):
        current_dt = get_current_datetime_context(self.context.timezone)
        system_message = SYSTEM_PROMPT.format(
            timezone=self.context.timezone,
            current_datetime=current_dt,
            user_name=self.context.user_name,
        )

        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=SystemMessage(content=system_message),
        )

    async def run(self, user_message: str) -> str:
        result = await self._agent.ainvoke(
            {"messages": [HumanMessage(content=user_message)]}
        )
        return result["messages"][-1].content
