from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from auth.google_oauth import GoogleOAuthService
from database.models import User
from gcalendar.schemas import (
    CalendarEvent,
    CreateEventRequest,
    FreeSlot,
    UpdateEventRequest,
)


class GoogleCalendarClient:
    CALENDAR_ID = "primary"

    def __init__(self, user: User):
        self.user = user
        self._oauth = GoogleOAuthService()
        self.token_refreshed = False

    def _get_service(self):
        credentials = self._oauth.build_credentials(self.user)
        if not credentials:
            raise ValueError("Usuario sin credenciales de Google Calendar")

        if credentials.expired and credentials.refresh_token:
            credentials = self._oauth.refresh_if_needed(credentials)
            self.user.google_access_token = credentials.token
            self.user.google_token_expiry = credentials.expiry
            self.token_refreshed = True

        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def _parse_event(self, item: dict) -> CalendarEvent:
        start = item["start"].get("dateTime") or item["start"].get("date")
        end = item["end"].get("dateTime") or item["end"].get("date")

        attendees = [
            a.get("email", "")
            for a in item.get("attendees", [])
            if a.get("email")
        ]

        return CalendarEvent(
            id=item["id"],
            summary=item.get("summary", "(Sin título)"),
            start=datetime.fromisoformat(start.replace("Z", "+00:00")),
            end=datetime.fromisoformat(end.replace("Z", "+00:00")),
            description=item.get("description"),
            attendees=attendees,
        )

    def list_events(
        self,
        time_min: datetime,
        time_max: datetime,
        query: str | None = None,
        max_results: int = 20,
    ) -> list[CalendarEvent]:
        service = self._get_service()
        params: dict = {
            "calendarId": self.CALENDAR_ID,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if query:
            params["q"] = query

        result = service.events().list(**params).execute()
        return [self._parse_event(item) for item in result.get("items", [])]

    def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        service = self._get_service()
        body: dict = {
            "summary": request.summary,
            "start": {"dateTime": request.start.isoformat(), "timeZone": self.user.timezone},
            "end": {"dateTime": request.end.isoformat(), "timeZone": self.user.timezone},
        }
        if request.description:
            body["description"] = request.description
        if request.attendees:
            body["attendees"] = [{"email": email} for email in request.attendees]

        created = (
            service.events()
            .insert(
                calendarId=self.CALENDAR_ID,
                body=body,
                sendUpdates="all",
                sendNotifications=True,
            )
            .execute()
        )

        return self._parse_event(created)

    def update_event(self, event_id: str, request: UpdateEventRequest) -> CalendarEvent:
        service = self._get_service()
        existing = service.events().get(calendarId=self.CALENDAR_ID, eventId=event_id).execute()

        if request.summary is not None:
            existing["summary"] = request.summary
        if request.start is not None:
            existing["start"] = {
                "dateTime": request.start.isoformat(),
                "timeZone": self.user.timezone,
            }
        if request.end is not None:
            existing["end"] = {
                "dateTime": request.end.isoformat(),
                "timeZone": self.user.timezone,
            }
        if request.description is not None:
            existing["description"] = request.description

        updated = (
            service.events()
            .update(
                calendarId=self.CALENDAR_ID,
                eventId=event_id,
                body=existing,
                sendUpdates="all",
            )
            .execute()
        )
        return self._parse_event(updated)

    def delete_event(self, event_id: str) -> None:
        service = self._get_service()
        service.events().delete(
            calendarId=self.CALENDAR_ID, eventId=event_id, sendUpdates="all"
        ).execute()

    def find_free_slots(
        self,
        day: datetime,
        duration_minutes: int = 60,
        working_hours: tuple[int, int] = (9, 18),
    ) -> list[FreeSlot]:
        tz = ZoneInfo(self.user.timezone)
        day_local = day.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        work_start = day_local.replace(hour=working_hours[0])
        work_end = day_local.replace(hour=working_hours[1])

        events = self.list_events(
            time_min=work_start,
            time_max=work_end,
        )

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            start = event.start.astimezone(tz)
            end = event.end.astimezone(tz)
            busy.append((start, end))

        busy.sort(key=lambda x: x[0])
        duration = timedelta(minutes=duration_minutes)
        free_slots: list[FreeSlot] = []
        cursor = work_start

        for start, end in busy:
            if start - cursor >= duration:
                free_slots.append(FreeSlot(start=cursor, end=start))
            cursor = max(cursor, end)

        if work_end - cursor >= duration:
            free_slots.append(FreeSlot(start=cursor, end=work_end))

        return free_slots

    def check_calendar_has_conflict(
        self,
        calendar_email: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> bool:
        """
        Verifica si existe algún conflicto o evento en el calendario especificado por `calendar_email`
        durante el intervalo completo [start_datetime, end_datetime].
        Devuelve True si hay conflicto (ocupado), False si está totalmente libre.
        """
        service = self._get_service()
        time_min = start_datetime.isoformat()
        time_max = end_datetime.isoformat()

        # 1. Consultar freebusy API
        try:
            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "items": [{"id": calendar_email}],
            }
            res = service.freebusy().query(body=body).execute()
            calendars = res.get("calendars", {})
            cal_data = calendars.get(calendar_email, {})
            if "errors" not in cal_data and "busy" in cal_data:
                busy_slots = cal_data.get("busy", [])
                return len(busy_slots) > 0
        except Exception:
            # Fallback a list_events si freebusy falla o no está soportado
            pass

        # 2. Consultar events.list para el calendario especificado
        events_result = (
            service.events()
            .list(
                calendarId=calendar_email,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
            )
            .execute()
        )

        for item in events_result.get("items", []):
            if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
                continue

            event = self._parse_event(item)
            # Verificar solapamiento estricto: event.start < end_datetime y event.end > start_datetime
            if event.start < end_datetime and event.end > start_datetime:
                return True

        return False

