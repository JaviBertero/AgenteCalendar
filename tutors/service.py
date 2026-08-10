import logging
from datetime import datetime

from gcalendar.client import GoogleCalendarClient
from tutors.repository import BaseTutorRepository
from tutors.schemas import Tutor

logger = logging.getLogger(__name__)


class TutorAvailabilityService:
    """
    Servicio encargado de coordinar la búsqueda y filtrado de disponibilidad de tutores.
    """

    def __init__(self, repository: BaseTutorRepository):
        self.repository = repository

    async def get_available_tutors(
        self,
        calendar_client: GoogleCalendarClient,
        start_datetime: datetime,
        end_datetime: datetime,
        tutors: list[Tutor] | None = None,
    ) -> list[Tutor]:
        """
        Devuelve la lista de tutores que están activos, trabajando durante todo el intervalo
        [start_datetime, end_datetime] y sin ningún conflicto en su Google Calendar.
        """
        if tutors is None:
            tutors = await self.repository.get_active_tutors()

        if not tutors:
            logger.info("No hay tutores activos disponibles en el sistema.")
            return []

        available: list[Tutor] = []

        for tutor in tutors:
            # Regla 2 & 6: Filtrado estricto por horario de actividad
            if not tutor.is_within_working_hours(start_datetime, end_datetime):
                logger.debug(
                    "Tutor '%s' descartado: fuera de horario laboral (%s)",
                    tutor.name,
                    tutor.working_hours_raw,
                )
                continue  # NO consultar Google Calendar

            # Regla 3, 4, 5: Consulta a Google Calendar
            try:
                has_conflict = calendar_client.check_calendar_has_conflict(
                    tutor.email, start_datetime, end_datetime
                )
                if not has_conflict:
                    available.append(tutor)
                else:
                    logger.debug("Tutor '%s' descartado: conflicto en Google Calendar", tutor.name)
            except Exception as e:
                logger.error(
                    "Error al consultar el calendario del tutor '%s' (%s): %s. Tutor omitido.",
                    tutor.name,
                    tutor.email,
                    e,
                )
                # Manejo suave de error por tutor individual

        return available
