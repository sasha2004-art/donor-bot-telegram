from aiogram import Router, types
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db import user_requests
from bot.keyboards import reply
from bot.utils.text_messages import Text

router = Router()

@router.message()
async def handle_unknown_message(message: types.Message, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    if not user:
        await message.answer(Text.WELCOME, reply_markup=reply.get_contact_keyboard())
    else:
        await message.answer(Text.UNKNOWN_COMMAND)