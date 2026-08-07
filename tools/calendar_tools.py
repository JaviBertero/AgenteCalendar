import inspect
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session_factory
from database.models import User
from database.repositories.contact_repository import ContactRepository
from database.repositories.user_repository import UserRepository
from gcalendar.client import GoogleCalendarClient
from gcalendar.schemas import CreateEventRequest, UpdateEventRequest
from tools.base import BaseAgentTool, ToolContext


async def _run_with_calendar(
    context: ToolContext,
    operation: Callable[..., str],
) -> str:
    session = async_session_factory()
    try:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(context.telegram_id)
        if not user:
            raise ValueError("Usuario no encontrado")

        client = GoogleCalendarClient(user)
        if inspect.iscoroutinefunction(operation):
            result = await operation(client, session, user)
        else:
            result = operation(client)

        if client.token_refreshed:
            await repo.update_google_tokens(
                user,
                access_token=user.google_access_token,
                refresh_token=None,
                expiry=user.google_token_expiry,
            )
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _format_dt(dt: datetime, tz_name: str) -> str:
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%d/%m/%Y %H:%M")


def _parse_local_datetime(dt_str: str, tz_name: str) -> datetime:
    """Parsea una cadena ISO respetando la hora local especificada en la zona horaria del usuario."""
    tz = ZoneInfo(tz_name)
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        return dt.astimezone(tz)
    return dt.replace(tzinfo=tz)



class CreateMeetingArgs(BaseModel):
    title: str = Field(description="Título o asunto de la reunión")
    attendee_name: str = Field(description="Nombre de la persona con quien reunirse")
    attendee_email: str = Field(
        default="",
        description="Dirección de correo electrónico del invitado (opcional)",
    )
    start_datetime: str = Field(
        description="Fecha y hora de inicio en ISO 8601 local"
    )
    duration_minutes: int = Field(default=60, description="Duración en minutos")


class CreateMeetingTool(BaseAgentTool):
    name = "create_meeting"
    description = (
        "Crea una nueva reunión en Google Calendar. "
        "Usar ÚNICAMENTE cuando el usuario confirme explícitamente la CREACIÓN de una nueva reunión. "
        "NUNCA invocar esta herramienta cuando el usuario solicita o confirma cancelar o reprogramar una reunión."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return CreateMeetingArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = CreateMeetingArgs(**kwargs)

        start = _parse_local_datetime(args.start_datetime, context.timezone)
        end = start + timedelta(minutes=args.duration_minutes)

        from database.validators import verify_email_domain_exists
        email = args.attendee_email.strip() if args.attendee_email else None
        if email:
            valid = await verify_email_domain_exists(email)
            if not valid:
                email = None

        attendees = [email] if email else []

        async def op(client: GoogleCalendarClient, session: AsyncSession, user: User) -> str:
            if email:
                contact_repo = ContactRepository(session)
                await contact_repo.save_or_update(user.id, args.attendee_name, email)

            event = client.create_event(
                CreateEventRequest(
                    summary=args.title,
                    start=start,
                    end=end,
                    description=f"Reunión solicitada vía Telegram con {args.attendee_name}",
                    attendees=attendees,
                )
            )

            invite_info = f" (Invitación enviada a {email})" if email else ""
            return (
                f"Reunión creada: '{event.summary}' "
                f"el {_format_dt(event.start, context.timezone)} "
                f"({args.duration_minutes} min).{invite_info}"
            )

        return await _run_with_calendar(context, op)


class ListMeetingsArgs(BaseModel):
    start_date: str = Field(
        description="Fecha/hora de inicio del rango en ISO 8601 (ej: 2026-08-07T00:00:00)."
    )
    end_date: str = Field(
        description="Fecha/hora de fin del rango en ISO 8601 (ej: 2026-08-07T23:59:59)."
    )
    search_query: str = Field(
        default="", description="Texto opcional para filtrar reuniones"
    )


class ListMeetingsTool(BaseAgentTool):
    name = "list_meetings"
    description = (
        "Lista reuniones existentes en un rango de fechas. "
        "Usar para consultar la agenda o buscar reuniones. Para 'hoy', especificar el rango completo del día (00:00 a 23:59)."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return ListMeetingsArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = ListMeetingsArgs(**kwargs)

        time_min = _parse_local_datetime(args.start_date, context.timezone)
        time_max = _parse_local_datetime(args.end_date, context.timezone)
        query = args.search_query.strip() if args.search_query else None

        def op(client: GoogleCalendarClient) -> str:
            events = client.list_events(time_min, time_max, query=query)
            if not events:
                return "No hay reuniones en ese período."

            lines = []
            for e in events:
                lines.append(
                    f"- [{e.id}] {e.summary}: "
                    f"{_format_dt(e.start, context.timezone)} → {_format_dt(e.end, context.timezone)}"
                )
            return "Reuniones encontradas:\n" + "\n".join(lines)

        return await _run_with_calendar(context, op)


class FindFreeSlotsArgs(BaseModel):
    date: str = Field(description="Fecha para buscar disponibilidad en ISO 8601 (ej: 2026-08-07)")
    duration_minutes: int = Field(default=60, description="Duración deseada en minutos")


class FindFreeSlotsTool(BaseAgentTool):
    name = "find_free_slots"
    description = (
        "Encuentra horarios libres en un día específico. "
        "Usar cuando el usuario pregunta cuándo está disponible o libre."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return FindFreeSlotsArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = FindFreeSlotsArgs(**kwargs)

        day = _parse_local_datetime(args.date, context.timezone)

        def op(client: GoogleCalendarClient) -> str:
            slots = client.find_free_slots(day, duration_minutes=args.duration_minutes)
            if not slots:
                return f"No hay bloques libres de {args.duration_minutes} min ese día."

            lines = [
                f"- {_format_dt(s.start, context.timezone)} → {_format_dt(s.end, context.timezone)}"
                for s in slots
            ]
            return f"Horarios libres ({args.duration_minutes} min):\n" + "\n".join(lines)

        return await _run_with_calendar(context, op)


class RescheduleMeetingArgs(BaseModel):
    event_id: str = Field(description="ID del evento a reprogramar")
    new_start_datetime: str = Field(description="Nueva fecha/hora de inicio en ISO 8601 local")
    new_duration_minutes: int = Field(
        default=60, description="Nueva duración en minutos"
    )


class RescheduleMeetingTool(BaseAgentTool):
    name = "reschedule_meeting"
    description = (
        "Reprograma una reunión existente a una nueva fecha/hora. "
        "Primero usa list_meetings para obtener el event_id si no lo tienes."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return RescheduleMeetingArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = RescheduleMeetingArgs(**kwargs)

        new_start = _parse_local_datetime(args.new_start_datetime, context.timezone)
        duration = args.new_duration_minutes or 60
        new_end = new_start + timedelta(minutes=duration)

        def op(client: GoogleCalendarClient) -> str:
            event = client.update_event(
                args.event_id,
                UpdateEventRequest(start=new_start, end=new_end),
            )
            return (
                f"Reunión reprogramada: '{event.summary}' "
                f"para el {_format_dt(event.start, context.timezone)}."
            )

        return await _run_with_calendar(context, op)


class CancelMeetingArgs(BaseModel):
    event_id: str = Field(description="ID del evento a cancelar")


class CancelMeetingTool(BaseAgentTool):
    name = "cancel_meeting"
    description = (
        "Cancela y elimina una reunión existente del calendario. "
        "Usar ÚNICAMENTE cuando el usuario confirme explícitamente la CANCELACIÓN de una reunión. "
        "Requiere el event_id exacto obtenido previamente con list_meetings."
    )

    def get_args_schema(self) -> type[BaseModel]:
        return CancelMeetingArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = CancelMeetingArgs(**kwargs)

        def op(client: GoogleCalendarClient) -> str:
            client.delete_event(args.event_id)
            return f"Reunión {args.event_id} cancelada correctamente."

        return await _run_with_calendar(context, op)
