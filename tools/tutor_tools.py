import logging
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from gcalendar.client import GoogleCalendarClient
from tools.base import BaseAgentTool, ToolContext
from tools.calendar_tools import _format_dt, _parse_local_datetime, _run_with_calendar
from tutors.repository import BaseTutorRepository, GoogleSheetsTutorRepository
from tutors.service import TutorAvailabilityService

logger = logging.getLogger(__name__)


class FindAvailableTutorsArgs(BaseModel):
    start_datetime: str = Field(
        description="Fecha y hora de inicio de la reunión deseada en formato ISO 8601 local (ej: 2026-08-11T10:00:00)."
    )
    duration_minutes: int = Field(
        default=60,
        description="Duración deseada de la reunión en minutos (por defecto 60).",
    )


class FindAvailableTutorsTool(BaseAgentTool):
    name = "find_available_tutors"
    description = (
        "Busca tutores o capacitadores disponibles para una reunión en una fecha y hora específica. "
        "Consulta la fuente de información de tutores (Google Sheets) y sus calendarios de Google Calendar. "
        "Devuelve la lista de tutores activos que trabajan en el horario solicitado y no tienen conflictos."
    )

    def __init__(self, repository: BaseTutorRepository | None = None):
        self.repository = repository or GoogleSheetsTutorRepository()

    def get_args_schema(self) -> type[BaseModel]:
        return FindAvailableTutorsArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        args = FindAvailableTutorsArgs(**kwargs)

        start_dt = _parse_local_datetime(args.start_datetime, context.timezone)
        duration = args.duration_minutes or 60
        end_dt = start_dt + timedelta(minutes=duration)

        async def op(client: GoogleCalendarClient, session: AsyncSession, user: User) -> str:
            service = TutorAvailabilityService(self.repository)

            try:
                active_tutors = await self.repository.get_active_tutors()
            except Exception as e:
                logger.error("Error al obtener la lista de tutores: %s", e)
                return "No se pudo consultar la información de los tutores (Google Sheets) en este momento."

            if not active_tutors:
                return "No hay tutores activos registrados en la base de datos/Google Sheets."

            working_tutors = [
                t for t in active_tutors if t.is_within_working_hours(start_dt, end_dt)
            ]
            if not working_tutors:
                return (
                    f"No hay tutores con horario de trabajo disponible para la franja solicitada "
                    f"({_format_dt(start_dt, context.timezone)} - {_format_dt(end_dt, context.timezone)})."
                )

            available_tutors = await service.get_available_tutors(
                client, start_dt, end_dt, tutors=working_tutors
            )

            if not available_tutors:
                return (
                    f"Los tutores que trabajan en ese horario tienen eventos agendados en Google Calendar "
                    f"durante la franja {_format_dt(start_dt, context.timezone)} - {_format_dt(end_dt, context.timezone)}."
                )

            if len(available_tutors) == 1:
                t = available_tutors[0]
                return (
                    f"Para ese horario ({_format_dt(start_dt, context.timezone)}) "
                    f"tengo disponible a {t.name} (Email: {t.email})."
                )

            lines = [f"{i+1}. {t.name} (Email: {t.email})" for i, t in enumerate(available_tutors)]
            return (
                f"Para ese horario ({_format_dt(start_dt, context.timezone)}) tengo disponibles:\n"
                + "\n".join(lines)
                + "\n\n¿Cuál prefieres?"
            )

        return await _run_with_calendar(context, op, prefer_coordinator=True)
