from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.connection import get_session


async def verify_telegram_secret(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")


async def get_db_session() -> AsyncSession:
    async for session in get_session():
        yield session
