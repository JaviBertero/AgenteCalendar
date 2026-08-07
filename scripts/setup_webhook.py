"""Script para registrar el webhook de Telegram."""

import asyncio
from pathlib import Path
import sys

# Agregar la raíz del proyecto al sys.path para resolver los módulos locales
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from telegram.bot import TelegramBot


async def main() -> None:
    webhook_url = f"{settings.base_url}/telegram/webhook"
    bot = TelegramBot()

    print(f"Registrando webhook: {webhook_url}")
    result = await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.telegram_webhook_secret or None,
    )
    print(f"Resultado: {result}")


if __name__ == "__main__":
    if not settings.telegram_bot_token:
        print("Error: TELEGRAM_BOT_TOKEN no configurado en .env")
        sys.exit(1)
    asyncio.run(main())
