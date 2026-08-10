from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        from sqlalchemy import func
        clean_email = email.strip().lower()
        result = await self.session.execute(
            select(User).where(func.lower(User.email) == clean_email)
        )
        return result.scalar_one_or_none()

    async def get_all_registered_emails(self) -> list[str]:
        result = await self.session.execute(
            select(User.email).where(User.email.isnot(None))
        )
        return [e for e in result.scalars().all() if e]

    async def get_or_create(
        self,
        telegram_id: int,
        telegram_username: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            if telegram_username and user.telegram_username != telegram_username:
                user.telegram_username = telegram_username
            return user

        user = User(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_google_tokens(
        self,
        user: User,
        access_token: str,
        refresh_token: str | None,
        expiry: datetime | None,
        email: str | None = None,
    ) -> User:
        user.google_access_token = access_token
        if refresh_token:
            user.google_refresh_token = refresh_token
        user.google_token_expiry = expiry
        if email:
            user.email = email
        await self.session.flush()
        return user
