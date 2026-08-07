from pydantic import BaseModel, Field

from database.connection import async_session_factory
from database.repositories.contact_repository import ContactRepository
from database.repositories.user_repository import UserRepository
from tools.base import BaseAgentTool, ToolContext


class GetContactArgs(BaseModel):
    name: str = Field(description="Nombre de la persona a buscar")


class GetContactTool(BaseAgentTool):
    name = "get_contact"
    description = (
        "Busca en los contactos guardados del usuario el correo electrónico correspondiente a un nombre. "
        "Usar siempre antes de agendar una reunión para comprobar si ya se tiene el email del contacto."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return GetContactArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = GetContactArgs(**kwargs)
        session = async_session_factory()
        try:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(context.telegram_id)
            if not user:
                return "Usuario no encontrado"

            repo = ContactRepository(session)
            contact = await repo.get_by_name(user.id, args.name)
            if contact:
                return f"Contacto encontrado: {contact.name} -> {contact.email}"
            return f"No se encontró ningún contacto guardado para '{args.name}'."
        finally:
            await session.close()


class SaveContactArgs(BaseModel):
    name: str = Field(description="Nombre de la persona")
    email: str = Field(description="Dirección de correo electrónico a guardar")


class SaveContactTool(BaseAgentTool):
    name = "save_contact"
    description = (
        "Guarda o actualiza el correo electrónico de un contacto para el usuario. "
        "Usar cuando el usuario proporciona el email de un contacto por primera vez."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return SaveContactArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = SaveContactArgs(**kwargs)
        session = async_session_factory()
        try:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(context.telegram_id)
            if not user:
                return "Usuario no encontrado"

            repo = ContactRepository(session)
            from database.validators import verify_email_domain_exists
            valid = await verify_email_domain_exists(args.email)
            if not valid:
                return f"No se guardó el contacto '{args.name}' porque la cuenta de correo '{args.email}' no es válida o su dominio no existe."

            contact = await repo.save_or_update(user.id, args.name, args.email)
            if not contact:
                return f"No se guardó el contacto '{args.name}' porque la cuenta de correo '{args.email}' no es válida o su dominio no existe."
            await session.commit()
            return f"Contacto guardado exitosamente: {contact.name} ({contact.email})"

        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

