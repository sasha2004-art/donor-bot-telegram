import io
import csv
import logging
import zipfile 
import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import admin_requests, user_requests
from bot.states.states import AdminManagement, BlockUser
from bot.keyboards import inline
from bot.filters.role import RoleFilter
from .admin import show_admin_panel as show_admin_panel_logic

# logging.basicConfig(level=logging.INFO)  # Логи закомментированы

router = Router()

@router.callback_query(F.data == "main_admin_panel", RoleFilter('main_admin'))
async def show_unified_admin_panel(callback: types.CallbackQuery, session: AsyncSession):
    # Главная админ-панель с доп. кнопками для главного админа
    viewer = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not viewer: 
        await callback.answer("Ошибка: не удалось найти ваш профиль.", show_alert=True)
        return

    # ИСПРАВЛЕНО: parse_mode="HTML" и текст с HTML тегами
    await callback.message.edit_text(
        text="⚙️ <b>Панель администратора</b>",
        reply_markup=inline.get_admin_panel_keyboard(viewer.role),
        parse_mode="HTML"
    )
    await callback.answer()


# @router.callback_query(F.data == "main_admin_panel", RoleFilter('main_admin'))
# async def show_main_admin_panel(callback: types.CallbackQuery):
#     await callback.message.edit_text(
#         text="👑 *Панель Главного Администратора*",
#         reply_markup=inline.get_main_admin_panel_keyboard(),
#         parse_mode="Markdown"
#     )
#     await callback.answer()

# @router.callback_query(F.data == "admin_panel", RoleFilter('main_admin'))
# async def show_admin_panel_for_main_admin(callback: types.CallbackQuery):
#     await show_admin_panel_logic(callback)