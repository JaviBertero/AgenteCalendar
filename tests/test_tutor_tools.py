from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from tools.base import ToolContext
from tools.tutor_tools import FindAvailableTutorsTool
from tutors.repository import MockTutorRepository
from tutors.schemas import Tutor

TZ_NAME = "America/Argentina/Buenos_Aires"


@pytest.mark.asyncio
async def test_find_available_tutors_tool_execution_one_available():
    t1 = Tutor(name="María López", status="active", email="maria@gmail.com", working_hours_raw="09:00-17:00")
    repo = MockTutorRepository([t1])
    tool = FindAvailableTutorsTool(repository=repo)

    context = ToolContext(telegram_id=12345, user_name="Javi", timezone=TZ_NAME)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = False  # Libre

    with patch("tools.tutor_tools._run_with_calendar") as mock_run:
        async def fake_run_with_calendar(ctx, op):
            return await op(mock_client, MagicMock(), MagicMock())

        mock_run.side_effect = fake_run_with_calendar

        result = await tool.execute(
            context,
            start_datetime="2026-08-11T10:00:00",
            duration_minutes=60,
        )

        assert "María López" in result
        assert "maria@gmail.com" in result


@pytest.mark.asyncio
async def test_find_available_tutors_tool_execution_multiple_available():
    t1 = Tutor(name="María López", status="active", email="maria@gmail.com", working_hours_raw="09:00-17:00")
    t2 = Tutor(name="Carlos Rodríguez", status="active", email="carlos@gmail.com", working_hours_raw="09:00-17:00")
    repo = MockTutorRepository([t1, t2])
    tool = FindAvailableTutorsTool(repository=repo)

    context = ToolContext(telegram_id=12345, user_name="Javi", timezone=TZ_NAME)

    mock_client = MagicMock()
    mock_client.check_calendar_has_conflict.return_value = False

    with patch("tools.tutor_tools._run_with_calendar") as mock_run:
        async def fake_run_with_calendar(ctx, op):
            return await op(mock_client, MagicMock(), MagicMock())

        mock_run.side_effect = fake_run_with_calendar

        result = await tool.execute(
            context,
            start_datetime="2026-08-11T10:00:00",
            duration_minutes=60,
        )

        assert "1. María López" in result
        assert "2. Carlos Rodríguez" in result
        assert "¿Cuál prefieres?" in result


@pytest.mark.asyncio
async def test_find_available_tutors_tool_execution_none_working():
    t1 = Tutor(name="Juan Pérez", status="active", email="juan@gmail.com", working_hours_raw="08:00-12:00")
    repo = MockTutorRepository([t1])
    tool = FindAvailableTutorsTool(repository=repo)

    context = ToolContext(telegram_id=12345, user_name="Javi", timezone=TZ_NAME)

    mock_client = MagicMock()

    with patch("tools.tutor_tools._run_with_calendar") as mock_run:
        async def fake_run_with_calendar(ctx, op):
            return await op(mock_client, MagicMock(), MagicMock())

        mock_run.side_effect = fake_run_with_calendar

        # Request at 14:00 (Juan works 08:00-12:00)
        result = await tool.execute(
            context,
            start_datetime="2026-08-11T14:00:00",
            duration_minutes=60,
        )

        assert "No hay tutores con horario de trabajo disponible" in result
