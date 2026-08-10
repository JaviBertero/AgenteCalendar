import csv
import io
import json
import logging
from abc import ABC, abstractmethod

import httpx

from config.settings import settings
from tutors.schemas import Tutor, parse_working_hours

logger = logging.getLogger(__name__)


class BaseTutorRepository(ABC):
    """Interfaz abstracta para obtener tutores."""

    @abstractmethod
    async def get_all_tutors(self) -> list[Tutor]:
        """Devuelve todos los tutores."""
        ...

    async def get_active_tutors(self) -> list[Tutor]:
        """Devuelve únicamente los tutores activos."""
        all_tutors = await self.get_all_tutors()
        return [t for t in all_tutors if t.is_active]


class MockTutorRepository(BaseTutorRepository):
    """Repositorio en memoria utilizado principalmente para tests."""

    def __init__(self, tutors: list[Tutor] | None = None):
        self._tutors = tutors or []

    def set_tutors(self, tutors: list[Tutor]) -> None:
        self._tutors = tutors

    async def get_all_tutors(self) -> list[Tutor]:
        return list(self._tutors)


class GoogleSheetsTutorRepository(BaseTutorRepository):
    """
    Repositorio desacoplado para obtener la lista de tutores desde Google Sheets.
    Soporta autenticación oficial de Google (Service Account / API Key)
    y respaldo de exportación CSV si la planilla es pública.
    """

    def __init__(
        self,
        spreadsheet_id: str | None = None,
        tab_name: str | None = None,
        credentials_file: str | None = None,
        service_account_json: str | None = None,
        api_key: str | None = None,
    ):
        self.spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        self.tab_name = tab_name or settings.google_sheets_tab_name or "Tutores"
        self.credentials_file = credentials_file or settings.google_sheets_credentials_file
        self.service_account_json = service_account_json or settings.google_sheets_service_account_json
        self.api_key = api_key or settings.google_sheets_api_key

    def _normalize_key(self, key: str) -> str:
        return key.strip().lower().replace(" ", "_").replace("-", "_")

    def _find_col_idx(self, headers: list[str], configured_name: str, alternatives: list[str]) -> int:
        norm_headers = [self._normalize_key(h) for h in headers]
        targets = [self._normalize_key(configured_name)] + [self._normalize_key(a) for a in alternatives]

        for target in targets:
            if target in norm_headers:
                return norm_headers.index(target)
        return -1

    def _parse_rows(self, raw_rows: list[list[str]]) -> list[Tutor]:
        if not raw_rows or len(raw_rows) < 2:
            return []

        headers = [str(cell) for cell in raw_rows[0]]

        idx_name = self._find_col_idx(
            headers, settings.sheets_col_name, ["nombre", "tutor", "capacitador", "nombre_tutor"]
        )
        idx_status = self._find_col_idx(
            headers, settings.sheets_col_status, ["estado", "state", "activo"]
        )
        idx_email = self._find_col_idx(
            headers, settings.sheets_col_email, ["correo", "mail", "gmail", "correo_electronico"]
        )
        idx_hours = self._find_col_idx(
            headers, settings.sheets_col_working_hours, ["horario", "horario_laboral", "horario_de_actividad", "workinghours"]
        )

        if idx_name == -1 or idx_email == -1:
            logger.warning(
                "No se pudieron identificar las columnas requeridas (name, email) en Google Sheets. Headers: %s",
                headers,
            )

        tutors: list[Tutor] = []
        for row in raw_rows[1:]:
            if not row:
                continue

            def get_cell(idx: int) -> str:
                return row[idx].strip() if 0 <= idx < len(row) and row[idx] else ""

            name = get_cell(idx_name)
            status = get_cell(idx_status) or "active"
            email = get_cell(idx_email)
            hours_raw = get_cell(idx_hours)

            if not name and not email:
                continue

            working_hours = parse_working_hours(hours_raw)

            tutors.append(
                Tutor(
                    name=name,
                    status=status,
                    email=email,
                    working_hours_raw=hours_raw,
                    working_hours=working_hours,
                )
            )

        return tutors

    async def _fetch_from_api(self) -> list[list[str]] | None:
        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account

            creds = None
            if self.service_account_json:
                info = json.loads(self.service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
                )
            elif self.credentials_file:
                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_file, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
                )

            if creds:
                service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            elif self.api_key:
                service = build("sheets", "v4", developerKey=self.api_key, cache_discovery=False)
            else:
                return None

            range_name = f"'{self.tab_name}'!A1:Z100" if self.tab_name else "A1:Z100"
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=range_name)
                .execute()
            )
            return result.get("values", [])
        except Exception as e:
            logger.warning("Fallo la lectura directa vía Google Sheets API: %s", e)
            return None

    async def _fetch_from_csv(self) -> list[list[str]] | None:
        if not self.spreadsheet_id:
            return None

        url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/gviz/tq?tqx=out:csv"
        if self.tab_name:
            url += f"&sheet={self.tab_name}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("Respuesta HTTP %s al descargar CSV de Google Sheet", resp.status_code)
                    return None

                reader = csv.reader(io.StringIO(resp.text))
                return [row for row in reader]
        except Exception as e:
            logger.error("Error al descargar CSV de Google Sheet: %s", e)
            return None

    async def get_all_tutors(self) -> list[Tutor]:
        if not self.spreadsheet_id:
            logger.warning("GOOGLE_SHEETS_SPREADSHEET_ID no está configurado.")
            return []

        rows = await self._fetch_from_api()
        if rows is None:
            rows = await self._fetch_from_csv()

        if not rows:
            logger.error("No se pudieron obtener datos de la Google Sheet con ID '%s'", self.spreadsheet_id)
            return []

        return self._parse_rows(rows)
