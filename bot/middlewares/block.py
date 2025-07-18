from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from bot.db import user_requests

class BlockUserMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        if not session:
            return await handler(event, data)

        user = await user_requests.get_user_by_tg_id(session, event.from_user.id)

        if user and user.is_blocked:
            if isinstance(event, Message):
                await event.answer("❌ Вы заблокированы и не можете использовать этого бота.")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Вы заблокированы.", show_alert=True)
            return  # Прерываем дальнейшую обработку

        return await handler(event, data)