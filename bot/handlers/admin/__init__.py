from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role import RoleFilter
from bot.db import user_requests
from bot.keyboards import inline
from bot.utils.text_messages import Text

from . import user_management, event_management, merch_management, mailing, system, analytics


admin_router = Router(name="admin")


admin_router.include_routers(
    user_management.router,
    event_management.router,
    merch_management.router,
    mailing.router,
    system.router,
    analytics.router, 
)

@admin_router.callback_query(F.data == "admin_panel", RoleFilter('admin'))
async def show_admin_panel(callback: types.CallbackQuery, session: AsyncSession):
    """
    Отображает главную панель администратора.
    Клавиатура динамически подстраивается под роль (admin или main_admin).
    """
    viewer = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not viewer:
        await callback.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        return

    await callback.message.edit_text(
        text=Text.ADMIN_PANEL_HEADER,
        reply_markup=inline.get_admin_panel_keyboard(viewer.role),
        parse_mode="HTML"
    )
    await callback.answer()
    

@admin_router.callback_query(F.data == "admin_manage_events")
async def manage_events_panel_test(callback: types.CallbackQuery):

    await callback.message.edit_text(Text.ADMIN_EVENTS_HEADER, reply_markup=inline.get_events_management_keyboard(), parse_mode="HTML")
    await callback.answer()
