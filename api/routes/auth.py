import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from auth.google_oauth import GoogleOAuthService
from database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.get("/login")
async def google_login(
    telegram_id: int = Query(..., description="Telegram user ID"),
):
    oauth = GoogleOAuthService()
    state = str(telegram_id)
    auth_url = oauth.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
):
    try:
        telegram_id = int(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    oauth = GoogleOAuthService()
    user_repo = UserRepository(session)

    try:
        tokens = oauth.exchange_code(code)
    except Exception:
        logger.exception("OAuth token exchange failed for telegram_id=%s", telegram_id)
        raise HTTPException(status_code=400, detail="OAuth authorization failed")

    user = await user_repo.get_or_create(telegram_id)
    expiry = oauth.parse_expiry(tokens.expires_at)

    await user_repo.update_google_tokens(
        user,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expiry=expiry,
        email=tokens.email,
    )

    return HTMLResponse(
        content="""
        <html>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>✅ Google Calendar conectado</h1>
            <p>Ya podés volver a Telegram y empezar a usar el asistente.</p>
        </body>
        </html>
        """,
        status_code=200,
    )
