from aiogram import Router, F, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.role import RoleFilter
from bot.db import user_requests
from bot.keyboards import inline
from bot.utils.text_messages import Text

from .user_management import router as user_management_router
from .event_management import router as event_management_router
# from .merch_management import router as merch_management_router
from .mailing import router as mailing_router
from .system import router as system_router
from .analytics import router as analytics_router
from .info_management import router as info_management_router
from .qa_management import router as qa_management_router

admin_router = Router(name="admin")

admin_router.include_routers(
    user_management_router,
    event_management_router,
    # merch_management_router,
    mailing_router,
    system_router,
    analytics_router,
    info_management_router,
    qa_management_router,
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