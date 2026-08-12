from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CalendarAgent"
    debug: bool = False
    secret_key: str = "change-me"
    base_url: str = "http://localhost:8000"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    groq_api_key: str = ""
    groq_api_keys: str | list[str] = ""
    groq_model: str = "llama-3.3-70b-versatile"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    database_url: str = "postgresql+asyncpg://calendar:calendar@localhost:5432/calendar_agent"
    default_timezone: str = "America/Argentina/Buenos_Aires"

    google_scopes: list[str] = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
    ]

    # Google Sheets settings for tutor management
    google_sheets_spreadsheet_id: str = ""
    google_sheets_tab_name: str = "Tutores"
    google_sheets_credentials_file: str = ""
    google_sheets_service_account_json: str = ""
    google_sheets_api_key: str = ""

    # Coordinator email for reading tutor calendars
    coordinator_email: str = ""

    # Flexible column mapping for Google Sheets
    sheets_col_name: str = "name"
    sheets_col_status: str = "status"
    sheets_col_email: str = "email"
    sheets_col_working_hours: str = "working_hours"

    # Dynamic token limit for logging
    token_limit: int = 100000

    def get_groq_api_key_details(self) -> list[dict[str, str]]:
        """
        Extrae todas las API keys de Groq disponibles con sus nombres de variable (ej: GROQ_API_KEY_3).
        Retorna lista de diccionarios con 'name' y 'key'.
        """
        import os
        import re
        from pathlib import Path

        details: list[dict[str, str]] = []
        seen_keys: set[str] = set()

        raw_env_items: list[tuple[str, str]] = []

        env_file = Path(".env")
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        raw_env_items.append((k.strip(), v.strip()))
            except Exception:
                pass

        for k, v in os.environ.items():
            raw_env_items.append((k.strip(), v.strip()))

        groq_vars: list[tuple[str, str]] = []
        for k, v in raw_env_items:
            k_upper = k.upper()
            if (
                k_upper.startswith("GROQ_API_KEY")
                and k_upper != "GROQ_API_KEYS"
                and k_upper != "GROQ_MODEL"
                and v.strip()
            ):
                groq_vars.append((k, v.strip()))

        def sort_key(item: tuple[str, str]):
            name = item[0]
            numbers = re.findall(r"\d+", name)
            if numbers:
                return (0, int(numbers[0]))
            return (1, name)

        groq_vars.sort(key=sort_key)

        for name, val in groq_vars:
            if val not in seen_keys:
                seen_keys.add(val)
                details.append({"name": name, "key": val})

        if isinstance(self.groq_api_keys, list):
            extra_keys = [k.strip() for k in self.groq_api_keys if k.strip()]
        elif isinstance(self.groq_api_keys, str) and self.groq_api_keys.strip():
            extra_keys = [k.strip() for k in self.groq_api_keys.split(",") if k.strip()]
        else:
            extra_keys = []

        for idx, k_val in enumerate(extra_keys, 1):
            if k_val not in seen_keys:
                seen_keys.add(k_val)
                details.append({"name": f"GROQ_API_KEYS[{idx}]", "key": k_val})

        if isinstance(self.groq_api_key, str) and self.groq_api_key.strip():
            for k in self.groq_api_key.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in seen_keys:
                    seen_keys.add(k_clean)
                    details.append({"name": "GROQ_API_KEY", "key": k_clean})

        return details

    def get_groq_api_keys(self) -> list[str]:
        """Extrae todas las API keys de Groq disponibles en variables de entorno o en .env."""
        return [d["key"] for d in self.get_groq_api_key_details()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

