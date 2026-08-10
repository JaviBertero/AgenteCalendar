import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from tutors.schemas import Tutor, parse_working_hours
from tutors.repository import MockTutorRepository, GoogleSheetsTutorRepository
from tutors.service import TutorAvailabilityService
from tools.tutor_tools import FindAvailableTutorsTool
from tools.base import ToolContext

TZ_NAME = "America/Argentina/Buenos_Aires"
TZ = ZoneInfo(TZ_NAME)


def dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Helper for timezone-aware local datetimes."""
    return datetime(year, month, day, hour, minute, 0, tzinfo=TZ)


# ============================================================================
# 1. Tests for Tutor Schema & Working Hours Parsing
# ============================================================================

def test_parse_working_hours_various_formats():
    # Standard format HH:MM-HH:MM
    res1 = parse_working_hours("08:00-12:00")
    assert res1 == [(time(8, 0), time(12, 0))]

    # Multiple intervals with spaces & spanish words
    res2 = parse_working_hours("08:00 a 12:00, 14:00hs - 18:00hs")
    assert res2 == [(time(8, 0), time(12, 0)), (time(14, 0), time(18, 0))]

    # Hour-only format
    res3 = parse_working_hours("9 - 17")
    assert res3 == [(time(9, 0), time(17, 0))]

    # Empty / Invalid
    assert parse_working_hours("") == []
    assert parse_working_hours(None) == []
    assert parse_working_hours("invalid string") == []


def test_tutor_is_active():
    t_active = Tutor(name="Juan", status="active", email="juan@gmail.com")
    t_active_caps = Tutor(name="Maria", status=" ACTIVE ", email="maria@gmail.com")
    t_inactive = Tutor(name="Pedro", status="inactive", email="pedro@gmail.com")

    assert t_active.is_active is True
    assert t_active_caps.is_active is True
    assert t_inactive.is_active is False


def test_is_within_working_hours_rule5_and_rule6():
    tutor = Tutor(
        name="Juan",
        status="active",
        email="juan@gmail.com",
        working_hours_raw="09:00-12:00",
    )

    # 1. Meeting completely inside working hours (09:30-10:30)
    assert tutor.is_within_working_hours(
        dt(2026, 8, 11, 9, 30), dt(2026, 8, 11, 10, 30)
    ) is True

    # 2. Meeting exactly matching working hours (09:00-12:00)
    assert tutor.is_within_working_hours(
        dt(2026, 8, 11, 9, 0), dt(2026, 8, 11, 12, 0)
    ) is True

    # 3. Meeting starting inside but ending outside working hours (11:30-12:30) - RULE 6
    assert tutor.is_within_working_hours(
        dt(2026, 8, 11, 11, 30), dt(2026, 8, 11, 12, 30)
    ) is False

    # 4. Meeting completely outside working hours (13:00-14:00) - RULE 2
    assert tutor.is_within_working_hours(
        dt(2026, 8, 11, 13, 0), dt(2026, 8, 11, 14, 0)
    ) is False


# ============================================================================
# 2. Tests for TutorAvailabilityService (Core Business Logic)
# ============================================================================

@pytest.mark.asyncio
async def test_case_1_active_tutor_within_hours_calendar_free():
    """1. Tutor activo dentro de horario y calendario libre → disponible."""
    tutor = Tutor(
        name="María López",
        status="active",
        email="maria@gmail.com",
        working_hours_raw="09:00-17:00",
    )
    repo = MockTutorRepository([tutor])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = False  # Libre

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 1
    assert available[0].name == "María López"
    mock_client.check_calendar_has_conflict.assert_called_once_with(
        "maria@gmail.com", start_dt, end_dt
    )


@pytest.mark.asyncio
async def test_case_2_active_tutor_within_hours_calendar_busy():
    """2. Tutor activo dentro de horario pero calendario ocupado → no disponible."""
    tutor = Tutor(
        name="Juan Pérez",
        status="active",
        email="juan@gmail.com",
        working_hours_raw="08:00-12:00",
    )
    repo = MockTutorRepository([tutor])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = True  # Ocupado

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 0
    mock_client.check_calendar_has_conflict.assert_called_once_with(
        "juan@gmail.com", start_dt, end_dt
    )


@pytest.mark.asyncio
async def test_case_3_inactive_tutor_discarded_without_calling_calendar():
    """3. Tutor inactivo → descartado sin consultar Calendar."""
    tutor_inactive = Tutor(
        name="Pedro Gómez",
        status="inactive",
        email="pedro@gmail.com",
        working_hours_raw="08:00-18:00",
    )
    repo = MockTutorRepository([tutor_inactive])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 0
    # Regla: NUNCA consultar su calendario
    mock_client.check_calendar_has_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_case_4_active_tutor_outside_working_hours():
    """4. Tutor activo fuera de horario → descartado sin consultar Calendar."""
    tutor = Tutor(
        name="Juan Pérez",
        status="active",
        email="juan@gmail.com",
        working_hours_raw="08:00-12:00",
    )
    repo = MockTutorRepository([tutor])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()

    # Usuario solicita 13:00-14:00 (Tutor trabaja 08:00-12:00)
    start_dt = dt(2026, 8, 11, 13, 0)
    end_dt = dt(2026, 8, 11, 14, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 0
    # Regla: NO consultar Google Calendar si está fuera de horario
    mock_client.check_calendar_has_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_case_5_meeting_starts_inside_ends_outside():
    """5. Reunión que comienza dentro del horario pero termina fuera → no disponible."""
    tutor = Tutor(
        name="Ana García",
        status="active",
        email="ana@gmail.com",
        working_hours_raw="09:00-12:00",
    )
    repo = MockTutorRepository([tutor])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()

    # Reunión 11:30 - 12:30 (Horario tutor termina a las 12:00)
    start_dt = dt(2026, 8, 11, 11, 30)
    end_dt = dt(2026, 8, 11, 12, 30)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 0
    mock_client.check_calendar_has_conflict.assert_not_called()


@pytest.mark.asyncio
async def test_case_6_multiple_tutors_available():
    """6. Varios tutores disponibles."""
    t1 = Tutor(name="María López", status="active", email="maria@gmail.com", working_hours_raw="09:00-17:00")
    t2 = Tutor(name="Carlos Rodríguez", status="active", email="carlos@gmail.com", working_hours_raw="09:00-17:00")
    t3 = Tutor(name="Ana García", status="active", email="ana@gmail.com", working_hours_raw="09:00-17:00")
    repo = MockTutorRepository([t1, t2, t3])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = False  # Todos libres

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 3
    assert [t.name for t in available] == ["María López", "Carlos Rodríguez", "Ana García"]


@pytest.mark.asyncio
async def test_case_7_no_tutors_available():
    """7. Ningún tutor disponible (todos ocupados)."""
    t1 = Tutor(name="María López", status="active", email="maria@gmail.com", working_hours_raw="09:00-17:00")
    t2 = Tutor(name="Carlos Rodríguez", status="active", email="carlos@gmail.com", working_hours_raw="09:00-17:00")
    repo = MockTutorRepository([t1, t2])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = True  # Todos ocupados

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 0


@pytest.mark.asyncio
async def test_case_8_calendar_error_handled_gracefully():
    """8. Error al consultar Calendar → manejado en forma controlada sin fallar todo el sistema."""
    t1 = Tutor(name="María López", status="active", email="maria@gmail.com", working_hours_raw="09:00-17:00")
    t2 = Tutor(name="Carlos Rodríguez", status="active", email="carlos@gmail.com", working_hours_raw="09:00-17:00")
    repo = MockTutorRepository([t1, t2])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()

    def side_effect(email, start, end):
        if email == "maria@gmail.com":
            raise Exception("API rate limit or connection error")
        return False  # Carlos libre

    mock_client.check_calendar_has_conflict.side_effect = side_effect

    start_dt = dt(2026, 8, 11, 10, 0)
    end_dt = dt(2026, 8, 11, 11, 0)

    # Debe completarse sin lanzar excepción
    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    assert len(available) == 1
    assert available[0].name == "Carlos Rodríguez"


@pytest.mark.asyncio
async def test_case_9_different_working_hours_between_tutors():
    """9. Diferentes horarios de trabajo entre tutores."""
    t_morning = Tutor(name="Juan (Mañana)", status="active", email="juan@gmail.com", working_hours_raw="08:00-12:00")
    t_afternoon = Tutor(name="María (Tarde)", status="active", email="maria@gmail.com", working_hours_raw="13:00-17:00")
    t_all_day = Tutor(name="Pedro (Todo el día)", status="active", email="pedro@gmail.com", working_hours_raw="08:00-17:00")

    repo = MockTutorRepository([t_morning, t_afternoon, t_all_day])
    service = TutorAvailabilityService(repo)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = False

    # Consulta a las 14:00
    start_dt = dt(2026, 8, 11, 14, 0)
    end_dt = dt(2026, 8, 11, 15, 0)

    available = await service.get_available_tutors(mock_client, start_dt, end_dt)

    # Juan (mañana) no trabaja a las 14:00, solo María y Pedro
    assert len(available) == 2
    assert set(t.name for t in available) == {"María (Tarde)", "Pedro (Todo el día)"}
    # Calendar solo se consultó para María y Pedro
    mock_client.check_calendar_has_conflict.assert_any_call("maria@gmail.com", start_dt, end_dt)
    mock_client.check_calendar_has_conflict.assert_any_call("pedro@gmail.com", start_dt, end_dt)
    assert mock_client.check_calendar_has_conflict.call_count == 2


# ============================================================================
# 3. Tests for Google Sheets Repository Header Parsing & Fallbacks
# ============================================================================

def test_google_sheets_repository_parse_rows():
    repo = GoogleSheetsTutorRepository()

    rows = [
        ["Name", "Status", "Email", "Working Hours"],
        ["Juan Pérez", "active", "juan@gmail.com", "08:00-12:00"],
        ["María López", "active", "maria@gmail.com", "09:00-17:00"],
        ["Pedro Gómez", "inactive", "pedro@gmail.com", "10:00-18:00"],
    ]

    tutors = repo._parse_rows(rows)

    assert len(tutors) == 3
    assert tutors[0].name == "Juan Pérez"
    assert tutors[0].is_active is True
    assert tutors[1].name == "María López"
    assert tutors[1].is_active is True
    assert tutors[2].name == "Pedro Gómez"
    assert tutors[2].is_active is False


def test_google_sheets_repository_flexible_spanish_headers():
    repo = GoogleSheetsTutorRepository()

    rows = [
        ["Capacitador", "Estado", "Correo Electrónico", "Horario de Actividad"],
        ["Carlos Rodríguez", "active", "carlos@gmail.com", "09:00 a 18:00"],
    ]

    tutors = repo._parse_rows(rows)

    assert len(tutors) == 1
    assert tutors[0].name == "Carlos Rodríguez"
    assert tutors[0].email == "carlos@gmail.com"
    assert tutors[0].is_active is True
    assert tutors[0].working_hours == [(time(9, 0), time(18, 0))]
