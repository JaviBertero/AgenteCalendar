import os
from datetime import datetime, timezone
from urllib.parse import urlencode

# Permitir la expansión/transformación automática de scopes que realiza Google OAuth
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from auth.schemas import GoogleTokenResponse
from config.settings import settings
from database.models import User


class GoogleOAuthService:
    def __init__(self) -> None:
        self.client_config = {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        }

    def get_authorization_url(self, state: str) -> str:
        flow = Flow.from_client_config(
            self.client_config,
            scopes=settings.google_scopes,
            redirect_uri=settings.google_redirect_uri,
            autogenerate_code_verifier=False,
        )
        flow.code_verifier = None
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    def exchange_code(self, code: str) -> GoogleTokenResponse:
        flow = Flow.from_client_config(
            self.client_config,
            scopes=settings.google_scopes,
            redirect_uri=settings.google_redirect_uri,
            autogenerate_code_verifier=False,
        )
        flow.code_verifier = None
        flow.fetch_token(code=code)
        credentials = flow.credentials

        email = None
        if credentials.id_token:
            from google.oauth2 import id_token as google_id_token
            from google.auth.transport import requests as google_requests

            try:
                id_info = google_id_token.verify_oauth2_token(
                    credentials.id_token,
                    google_requests.Request(),
                    settings.google_client_id,
                )
                email = id_info.get("email")
            except Exception:
                pass

        expiry = credentials.expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        return GoogleTokenResponse(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_at=expiry.isoformat() if expiry else None,
            email=email,
        )

    def build_credentials(self, user: User) -> Credentials | None:
        if not user.google_access_token:
            return None

        expiry = user.google_token_expiry
        if expiry and expiry.tzinfo is not None:
            expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)

        return Credentials(
            token=user.google_access_token,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=settings.google_scopes,
            expiry=expiry,
        )

    def refresh_if_needed(self, credentials: Credentials) -> Credentials:
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        return credentials

    @staticmethod
    def parse_expiry(expires_at: str | None) -> datetime | None:
        if not expires_at:
            return None
        dt = datetime.fromisoformat(expires_at)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def build_auth_link_for_telegram(telegram_id: int) -> str:
        params = urlencode({"telegram_id": telegram_id})
        return f"{settings.base_url}/auth/google/login?{params}"
