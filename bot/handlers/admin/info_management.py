import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import info_requests
from bot.filters.role import RoleFilter
from bot.states.states import EditInfoSection
from bot.keyboards import inline

router = Router(name="admin_info_management")
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "admin_edit_info", RoleFilter('admin'))
async def start_info_editing(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    sections = await info_requests.get_all_info_sections(session)
    if not sections:
        await callback.answer("Информационные разделы не найдены в базе данных.", show_alert=True)
        return
        
    await state.set_state(EditInfoSection.choosing_section)
    await callback.message.edit_text(
        "Выберите раздел, который хотите отредактировать:",
        reply_markup=inline.get_info_sections_for_editing_keyboard(sections)
    )
    await callback.answer()

@router.callback_query(EditInfoSection.choosing_section, F.data.startswith("edit_info_"))
async def choose_section_to_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    section_key = callback.data.split("_", 2)[-1]
    current_text = await info_requests.get_info_text(session, section_key)
    
    await state.update_data(section_key=section_key)
    await state.set_state(EditInfoSection.awaiting_new_text)
    
    await callback.message.edit_text(
        f"<b>Текущий текст раздела (для справки):</b>\n\n{current_text}\n\n"
        f"<b>Отправьте новый текст. Можно использовать HTML-теги.</b>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EditInfoSection.awaiting_new_text)
async def process_new_info_text(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    section_key = data.get("section_key")
    
    if not section_key:
        await message.answer("Произошла ошибка, попробуйте снова.")
        await state.clear()
        return

    await info_requests.update_info_text(session, section_key, message.html_text)
    await state.clear()
    
    await message.answer(
        "✅ Текст раздела успешно обновлен!",
        reply_markup=inline.get_back_to_admin_panel_keyboard()
    )