import logging

from sqlalchemy.ext.asyncio import AsyncSession

from agent.graph import CalendarAgent
from auth.google_oauth import GoogleOAuthService
from database.repositories.user_repository import UserRepository
from telegram.bot import TelegramBot
from telegram.schemas import TelegramUpdate
from tools.base import ToolContext

logger = logging.getLogger(__name__)


class WebhookHandler:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.bot = TelegramBot()
        self.oauth = GoogleOAuthService()

    async def handle_update(self, update: TelegramUpdate) -> None:
        if not update.message or not update.message.text:
            return

        message = update.message
        if not message.from_:
            return

        chat_id = message.chat.id
        telegram_id = message.from_.id
        username = message.from_.username
        text = message.text.strip()

        if text.startswith("/start"):
            await self._handle_start(chat_id, telegram_id, username)
            return

        user = await self.user_repo.get_or_create(telegram_id, username)

        if not user.has_google_auth:
            auth_link = self.oauth.build_auth_link_for_telegram(telegram_id)
            await self.bot.send_message(
                chat_id,
                "Para usar el asistente de calendario, primero conectá tu Google Calendar:\n"
                f"{auth_link}",
            )
            return

        await self.bot.send_typing_action(chat_id)

        display_name = (message.from_.first_name or username or "Usuario").strip()
        try:
            context = ToolContext(
                user_id=user.id,
                telegram_id=telegram_id,
                timezone=user.timezone,
                user_name=display_name,
            )
            agent = CalendarAgent(context)
            response = await agent.run(text, thread_id=str(telegram_id))
            await self.bot.send_message(chat_id, response)
        except Exception as e:
            logger.exception("Error processing message from telegram_id=%s", telegram_id)
            err_msg = str(e).lower()
            if "rate limit" in err_msg or "429" in err_msg or "quota" in err_msg:
                user_friendly = "El servicio de IA ha alcanzado su límite de cuota o consultas momentáneo. Por favor intentá de nuevo en unos instantes."
            else:
                user_friendly = "Ocurrió un error al procesar tu solicitud. Intentá de nuevo."
            await self.bot.send_message(chat_id, user_friendly)


    async def _handle_start(
        self,
        chat_id: int,
        telegram_id: int,
        username: str | None,
    ) -> None:
        await self.user_repo.get_or_create(telegram_id, username)
        auth_link = self.oauth.build_auth_link_for_telegram(telegram_id)

        await self.bot.send_message(
            chat_id,
            "¡Hola! Soy tu asistente de calendario.\n\n"
            "Puedo ayudarte a:\n"
            "• Agendar reuniones\n"
            "• Consultar tu agenda\n"
            "• Encontrar horarios libres\n"
            "• Reprogramar o cancelar reuniones\n\n"
            "Para empezar, conectá tu Google Calendar:\n"
            f"{auth_link}\n\n"
            "Luego escribime en lenguaje natural, por ejemplo:\n"
            '"Agenda una reunión con Juan mañana a las 15 hs."',
        )
