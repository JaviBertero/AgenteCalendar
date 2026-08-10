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

    def get_groq_api_keys(self) -> list[str]:
        """Extrae todas las API keys de Groq disponibles en variables de entorno o en .env."""
        import os
        from pathlib import Path
        keys: list[str] = []

        # 1. groq_api_keys (lista o string separado por comas)
        if isinstance(self.groq_api_keys, list):
            keys.extend([k.strip() for k in self.groq_api_keys if k.strip()])
        elif isinstance(self.groq_api_keys, str) and self.groq_api_keys.strip():
            keys.extend([k.strip() for k in self.groq_api_keys.split(",") if k.strip()])

        # 2. groq_api_key (string o separado por comas)
        if isinstance(self.groq_api_key, str) and self.groq_api_key.strip():
            for k in self.groq_api_key.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)

        # 3. Variables numeradas GROQ_API_KEY_... en os.environ y .env
        env_dict = dict(os.environ)
        env_file = Path(".env")
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_dict[k.strip()] = v.strip()
            except Exception:
                pass

        for env_var, val in env_dict.items():
            if env_var.startswith("GROQ_API_KEY_") and val.strip():
                clean_val = val.strip()
                if clean_val not in keys:
                    keys.append(clean_val)

        return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

