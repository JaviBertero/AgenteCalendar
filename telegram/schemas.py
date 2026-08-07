from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    id: int
    type: str = "private"
    first_name: str | None = None
    username: str | None = None


class TelegramMessage(BaseModel):
    message_id: int
    from_: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    date: int
    text: str | None = None

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
