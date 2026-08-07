from pydantic import BaseModel


class GoogleTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: str | None = None
    email: str | None = None
