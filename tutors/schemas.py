import re
from datetime import datetime, time, timedelta
from pydantic import BaseModel, Field


def parse_working_hours(raw: str) -> list[tuple[time, time]]:
    """
    Parsea cadenas de horarios de trabajo en tuplas (time_inicio, time_fin).
    Soporta múltiples rangos separados por coma o punto y coma (ej: '08:00-12:00, 14:00-18:00').
    Soporta formatos HH:MM, H:MM, H-H, con o sin prefijos/sufijos como 'hs', 'hrs', 'horas', 'a', 'to'.
    """
    if not raw or not isinstance(raw, str):
        return []

    intervals: list[tuple[time, time]] = []
    # Limpiar sufijos como 'hs', 'hrs', 'horas'
    cleaned = re.sub(r"(?i)\b(hs|hrs|horas)\b", "", raw)
    parts = re.split(r"[,;]", cleaned)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Intentar coincidencia con HH:MM - HH:MM o H:MM - H:MM
        match = re.match(r"^(\d{1,2}:\d{2})\s*(?:[-–—aA]|\bto\b|\ba\b)\s*(\d{1,2}:\d{2})$", part, re.IGNORECASE)
        if not match:
            # Intentar coincidencia con horas enteras tipo H - H (ej: "8 - 17" o "8 a 17")
            match_h = re.match(r"^(\d{1,2})\s*(?:[-–—aA]|\bto\b|\ba\b)\s*(\d{1,2})$", part, re.IGNORECASE)
            if match_h:
                h1, h2 = match_h.groups()
                start_str, end_str = f"{h1}:00", f"{h2}:00"
            else:
                continue
        else:
            start_str, end_str = match.groups()

        try:
            h_start, m_start = map(int, start_str.split(":"))
            h_end, m_end = map(int, end_str.split(":"))

            t_start = time(h_start, m_start)

            if h_end == 24 or (h_end == 0 and m_end == 0 and (h_start > 0 or m_start > 0)):
                t_end = time(23, 59, 59, 999999)
            else:
                t_end = time(h_end, m_end)

            intervals.append((t_start, t_end))
        except ValueError:
            continue

    return intervals


class Tutor(BaseModel):
    name: str = Field(description="Nombre del tutor/capacitador")
    status: str = Field(description="Estado del tutor ('active' / 'inactive')")
    email: str = Field(description="Email del tutor para Google Calendar")
    working_hours_raw: str = Field(default="", description="Cadena original del horario")
    working_hours: list[tuple[time, time]] = Field(
        default_factory=list,
        description="Lista de intervalos parsed (time_inicio, time_fin)",
    )

    def model_post_init(self, __context) -> None:
        if not self.working_hours and self.working_hours_raw:
            self.working_hours = parse_working_hours(self.working_hours_raw)

    @property
    def is_active(self) -> bool:
        """Determina si el tutor está activo (insensible a mayúsculas/minúsculas y espacios)."""
        return self.status.strip().lower() == "active"

    def is_within_working_hours(self, start_dt: datetime, end_dt: datetime) -> bool:
        """
        Verifica si el intervalo [start_dt, end_dt] está COMPLETAMENTE contenido
        dentro de al menos uno de los horarios laborales del tutor.
        """
        if not self.is_active:
            return False

        if not self.working_hours:
            return False

        if end_dt <= start_dt:
            return False

        # Extraer hora de inicio y fin en el reloj local
        start_time = start_dt.time()

        if end_dt.date() != start_dt.date():
            if (
                end_dt.date() == start_dt.date() + timedelta(days=1)
                and end_dt.time() == time(0, 0)
            ):
                end_time = time(23, 59, 59, 999999)
            else:
                # La reunión abarca más de un día, no cabe en el horario diario
                return False
        else:
            end_time = end_dt.time()

        for wh_start, wh_end in self.working_hours:
            if start_time >= wh_start and end_time <= wh_end:
                return True

        return False
