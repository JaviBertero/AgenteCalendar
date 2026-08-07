import httpx

from config.settings import settings


class TelegramBot:
    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, token: str | None = None):
        self.token = token or settings.telegram_bot_token
        self.api_url = self.BASE_URL.format(token=self.token)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> dict:
        payload: dict = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json()

    async def send_typing_action(self, chat_id: int) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self.api_url}/sendChatAction",
                json={"chat_id": chat_id, "action": "typing"},
            )

    async def set_webhook(self, url: str, secret_token: str | None = None) -> dict:
        payload: dict = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/setWebhook", json=payload)
            response.raise_for_status()
            return response.json()

    async def delete_webhook(self) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/deleteWebhook")
            response.raise_for_status()
            return response.json()
