from typing import Union
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from bot.db import user_requests
from sqlalchemy.ext.asyncio import AsyncSession

ROLE_HIERARCHY = {
    'student': 0,
    'volunteer': 1,
    'admin': 2,
    'main_admin': 3
}

class RoleFilter(BaseFilter):
    def __init__(self, required_role: str):
        self.required_level = ROLE_HIERARCHY.get(required_role, 0)

    async def __call__(self, event: Union[Message, CallbackQuery], session: AsyncSession) -> bool:
        user = await user_requests.get_user_by_tg_id(session, event.from_user.id)
        if not user:
            return False
        
        if user.is_blocked:
            return False
            
        user_level = ROLE_HIERARCHY.get(user.role, 0)
        return user_level >= self.required_level