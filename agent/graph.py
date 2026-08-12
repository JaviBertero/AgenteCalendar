from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None

from agent.prompts import SYSTEM_PROMPT
from agent.state import get_current_datetime_context
from agent.token_tracker import KeyTokenCallbackHandler, token_tracker
from config.settings import settings
from tools.base import ToolContext
from tools.registry import get_tool_instances

# Instancia compartida en memoria para persistir el historial de conversación por thread_id (telegram_id)
shared_checkpointer = MemorySaver()


class CalendarAgent:
    def __init__(self, context: ToolContext):
        self.context = context
        models = []

        token_tracker.set_token_limit(settings.token_limit)

        # 1. Cargar todas las API keys de Groq configuradas en .env con sus nombres
        groq_details = settings.get_groq_api_key_details()
        if ChatGroq is not None and groq_details:
            for detail in groq_details:
                key_name = detail["name"]
                key_val = detail["key"]
                handler = KeyTokenCallbackHandler(key_name=key_name)
                models.append(
                    ChatGroq(
                        model=settings.groq_model,
                        groq_api_key=key_val,
                        temperature=0,
                        callbacks=[handler],
                    )
                )

        # 2. Si no hay Groq pero hay Gemini, usar Gemini
        if not models and settings.gemini_api_key:
            handler = KeyTokenCallbackHandler(key_name="GEMINI_API_KEY")
            models.append(
                ChatGoogleGenerativeAI(
                    model=settings.gemini_model,
                    google_api_key=settings.gemini_api_key,
                    temperature=0,
                    callbacks=[handler],
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
            checkpointer=shared_checkpointer,
        )

    async def run(self, user_message: str, thread_id: str | None = None) -> str:
        config = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}

        start_total = token_tracker.total_tokens
        start_prompt = token_tracker.total_prompt_tokens
        start_completion = token_tracker.total_completion_tokens

        result = await self._agent.ainvoke(
            {"messages": [HumanMessage(content=user_message)]},
            config=config if config else None,
        )

        turn_total = token_tracker.total_tokens - start_total
        turn_prompt = token_tracker.total_prompt_tokens - start_prompt
        turn_completion = token_tracker.total_completion_tokens - start_completion

        # Identificar qué keys tuvieron uso durante esta pregunta
        keys_used = [
            k for k, stats in token_tracker.key_stats.items() if stats.get("total", 0) > 0
        ]
        if turn_total > 0:
            token_tracker.log_turn_summary(
                turn_prompt=turn_prompt,
                turn_completion=turn_completion,
                turn_total=turn_total,
                keys_used=keys_used,
            )

        return result["messages"][-1].content

