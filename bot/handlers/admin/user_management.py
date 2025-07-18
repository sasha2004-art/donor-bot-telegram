import logging
import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold, hcode
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import admin_requests, user_requests, event_requests
from bot.filters.role import RoleFilter
from bot.states.states import (
    PointsChange,
    ManualWaiver,
    UserSearch,
    BlockUser,
    AdminAddUser,
)
from bot.keyboards import inline
from bot.utils.text_messages import Text

router = Router(name="admin_user_management")
logger = logging.getLogger(__name__)


# =============================================================================
# --- 👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ---
# =============================================================================

@router.callback_query(F.data == "admin_manage_users", RoleFilter('admin'))
async def manage_users_main_menu(callback: types.CallbackQuery):
    """Показывает главное меню управления пользователями."""
    await callback.message.edit_text(
        Text.ADMIN_USERS_HEADER,
        reply_markup=inline.get_user_management_main_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# --- Список пользователей с пагинацией ---
@router.callback_query(F.data.startswith("admin_users_list_page_"), RoleFilter('admin'))
async def show_users_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split('_')[-1])
    page_size = 10

    users, total_pages = await admin_requests.get_users_page(session, page, page_size)

    if not users:
        await callback.message.edit_text(Text.ADMIN_NO_USERS_IN_DB, reply_markup=inline.get_user_management_main_keyboard())
        await callback.answer()
        return

    text = Text.USERS_LIST_HEADER.format(page=page, total_pages=total_pages)
    builder = InlineKeyboardBuilder()
    for user in users:
        builder.row(types.InlineKeyboardButton(text=f"👤 {user.full_name}", callback_data=f"admin_show_user_{user.id}"))

    pagination_keyboard = inline.get_users_list_pagination_keyboard(page, total_pages)
    for row in pagination_keyboard.inline_keyboard:
        builder.row(*row)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

# --- Поиск пользователя ---
@router.callback_query(F.data == "admin_search_user", RoleFilter('admin'))
async def search_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Запускает FSM для поиска пользователя."""
    await state.clear()
    await state.set_state(UserSearch.awaiting_query)
    await callback.message.edit_text(Text.USER_SEARCH_PROMPT)
    await callback.answer()

@router.message(UserSearch.awaiting_query)
async def process_user_search(message: types.Message, state: FSMContext, session: AsyncSession):
    """Ищет пользователей по запросу и выводит результат."""
    await state.clear()
    query = message.text
    users_found = await admin_requests.find_user_for_admin(session, query)

    if not users_found:
        await message.answer(Text.USER_SEARCH_NO_RESULTS, reply_markup=inline.get_user_management_main_keyboard())
        return

    text = Text.USER_SEARCH_RESULTS_HEADER.format(query=query)
    builder = InlineKeyboardBuilder()
    for user in users_found:
        builder.row(types.InlineKeyboardButton(text=f"👤 {user.full_name}", callback_data=f"admin_show_user_{user.id}"))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_manage_users"))

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- Карточка пользователя и управление им ---
@router.callback_query(F.data.startswith("admin_show_user_"), RoleFilter('admin'))
async def show_single_user_card(callback: types.CallbackQuery, session: AsyncSession):
    """Показывает карточку одного пользователя с динамической клавиатурой."""
    viewer = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not viewer: return

    target_user_id = int(callback.data.split('_')[-1])
    target_user = await user_requests.get_user_by_id(session, target_user_id)
    if not target_user:
        await callback.answer(Text.USER_NOT_FOUND, show_alert=True)
        return

    block_status = "ЗАБЛОКИРОВАН" if target_user.is_blocked else "Активен"

    text = "\n".join([
        hbold(Text.USER_CARD_HEADER.format(full_name=target_user.full_name)),
        "",
        Text.USER_CARD_TEMPLATE.format(
            full_name=Text.escape_html(target_user.full_name),
            telegram_id=target_user.telegram_id,
            username=Text.escape_html(target_user.telegram_username or 'не указан'),
            phone_number=target_user.phone_number,
            role=target_user.role,
            points=target_user.points,
            block_status=block_status
        )
    ])

    await callback.message.edit_text(
        text,
        reply_markup=inline.get_user_management_keyboard(
            target_user_id=target_user.id,
            target_user_role=target_user.role,
            viewer_role=viewer.role,
            is_blocked=target_user.is_blocked
        ),
        parse_mode="HTML"
    )
    await callback.answer()

# --- +/- Баллы (FSM) ---
@router.callback_query(F.data.startswith("admin_points_"), RoleFilter('admin'))
async def change_points_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(user_id=user_id)
    await state.set_state(PointsChange.awaiting_points_amount)
    await callback.message.edit_text(Text.CHANGE_POINTS_PROMPT)
    await callback.answer()

@router.message(PointsChange.awaiting_points_amount)
async def change_points_amount(message: types.Message, state: FSMContext):
    try:
        points = int(message.text)
        await state.update_data(points=points)
        await state.set_state(PointsChange.awaiting_reason)
        await message.answer(Text.CHANGE_POINTS_REASON_PROMPT)
    except ValueError:
        await message.answer(Text.EVENT_POINTS_NAN_ERROR)

@router.message(PointsChange.awaiting_reason)
async def change_points_reason(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    reason, user_id, points_change = message.text, data['user_id'], data['points']
    
    user = await user_requests.get_user_by_id(session, user_id)
    if not user:
        await message.answer(Text.USER_NOT_FOUND)
        await state.clear()
        return

    await admin_requests.add_points_to_user(session, user_id, points_change, reason)
    await session.commit()
    await state.clear()

    new_balance = user.points
    await message.answer(
        Text.CHANGE_POINTS_SUCCESS.format(name=user.full_name, balance=new_balance),
        reply_markup=inline.get_back_to_admin_panel_keyboard()
    )

    try:
        await bot.send_message(
            chat_id=user.telegram_id, # ИСПРАВЛЕНО
            text=Text.USER_POINTS_CHANGED_NOTIFICATION.format(points=points_change, reason=reason, balance=new_balance),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about points change: {e}")

# --- Ручное управление ролями ---
@router.callback_query(F.data.startswith("admin_promote_volunteer_"), RoleFilter('admin'))
async def promote_to_volunteer(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = int(callback.data.split('_')[-1])
    await admin_requests.change_user_role(session, user_id, 'volunteer')
    await session.commit()
    user = await user_requests.get_user_by_id(session, user_id)
    await callback.answer(Text.USER_PROMOTED_VOLUNTEER.format(name=user.full_name), show_alert=True)
    try:
        await bot.send_message(chat_id=user.telegram_id, text=Text.USER_PROMOTED_VOLUNTEER_NOTIFY)
    except Exception as e:
        logger.error(f"Failed to notify user {user.id} about promotion: {e}")
    await show_single_user_card(callback, session)

@router.callback_query(F.data.startswith("admin_demote_volunteer_"), RoleFilter('admin'))
async def demote_from_volunteer(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = int(callback.data.split('_')[-1])
    await admin_requests.change_user_role(session, user_id, 'student')
    await session.commit()
    user = await user_requests.get_user_by_id(session, user_id)
    await callback.answer(Text.USER_DEMOTED_VOLUNTEER.format(name=user.full_name), show_alert=True)
    try:
        await bot.send_message(chat_id=user.telegram_id, text=Text.USER_DEMOTED_VOLUNTEER_NOTIFY)
    except Exception as e:
        logger.error(f"Failed to notify user {user.id} about demotion: {e}")
    await show_single_user_card(callback, session)

@router.callback_query(F.data.startswith("ma_promote_admin_"), RoleFilter('main_admin'))
async def promote_to_admin(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    target_user_id = int(callback.data.split('_')[-1])
    await admin_requests.change_user_role(session, target_user_id, 'admin')
    await session.commit()
    target_user = await user_requests.get_user_by_id(session, target_user_id)
    await callback.answer(Text.USER_PROMOTED_ADMIN.format(name=target_user.full_name), show_alert=True)
    try:
        await bot.send_message(chat_id=target_user.telegram_id, text=Text.USER_PROMOTED_ADMIN_NOTIFY)
    except Exception as e:
        logger.error(f"Failed to notify user {target_user.id} about admin promotion: {e}")
    await show_single_user_card(callback, session)

@router.callback_query(F.data.startswith("ma_demote_admin_"), RoleFilter('main_admin'))
async def demote_from_admin(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    target_user_id = int(callback.data.split('_')[-1])
    await admin_requests.change_user_role(session, target_user_id, 'student')
    await session.commit()
    target_user = await user_requests.get_user_by_id(session, target_user_id)
    await callback.answer(Text.USER_DEMOTED_ADMIN.format(name=target_user.full_name), show_alert=True)
    try:
        await bot.send_message(chat_id=target_user.telegram_id, text=Text.USER_DEMOTED_ADMIN_NOTIFY)
    except Exception as e:
        logger.error(f"Failed to notify user {target_user.id} about admin demotion: {e}")
    await show_single_user_card(callback, session)

# --- Управление блокировками ---
@router.callback_query(F.data.startswith("ma_block_user_"), RoleFilter('main_admin'))
async def block_user_from_card(callback: types.CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split('_')[-1])
    await state.clear()
    await state.update_data(user_id=target_user_id)
    await state.set_state(BlockUser.awaiting_reason)
    await callback.message.edit_text(Text.BLOCK_USER_REASON_PROMPT)
    await callback.answer()

@router.message(BlockUser.awaiting_reason)
async def process_block_reason(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    reason = message.text
    target_user_id = data['user_id']

    admin_user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    if not admin_user:
        await message.answer(Text.ADMIN_ID_ERROR)
        await state.clear()
        return

    target_user = await user_requests.get_user_by_id(session, target_user_id)
    if not target_user:
        await message.answer(Text.BLOCK_TARGET_USER_NOT_FOUND)
        await state.clear()
        return

    await admin_requests.block_user(session, target_user_id, admin_user.id, reason)
    await session.commit()
    await state.clear()

    await message.answer(
        Text.USER_BLOCKED_SUCCESS.format(name=target_user.full_name, reason=reason),
        reply_markup=inline.get_back_to_admin_panel_keyboard()
    )
    try:
        await bot.send_message(chat_id=target_user.telegram_id, text=Text.USER_BLOCKED_NOTIFY.format(reason=reason))
    except Exception as e:
        logger.error(f"Failed to notify user {target_user.id} about block: {e}")

@router.callback_query(F.data.startswith("ma_unblock_user_"), RoleFilter('main_admin'))
async def unblock_user_from_card(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    target_user_id = int(callback.data.split('_')[-1])
    await admin_requests.unblock_user(session, target_user_id)
    await session.commit()
    target_user = await user_requests.get_user_by_id(session, target_user_id)
    if not target_user:
        await callback.answer(Text.USER_NOT_FOUND, show_alert=True)
        return

    await callback.answer(Text.USER_UNBLOCKED_SUCCESS.format(name=target_user.full_name), show_alert=True)
    try:
        await bot.send_message(chat_id=target_user.telegram_id, text=Text.USER_UNBLOCKED_NOTIFY)
    except Exception as e:
        logger.error(f"Failed to notify user {target_user.id} about unblock: {e}")
    await show_single_user_card(callback, session)


# --- Ручное управление регистрациями ---
@router.callback_query(F.data.startswith("admin_manage_user_regs_"), RoleFilter('admin'))
async def manage_user_registrations_menu(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split('_')[-1])
    user = await user_requests.get_user_by_id(session, user_id)
    if not user:
        await callback.answer(Text.USER_NOT_FOUND, show_alert=True)
        return

    await callback.message.edit_text(
        Text.MANAGE_USER_REGS_HEADER.format(name=user.full_name),
        reply_markup=inline.get_manual_registration_management_keyboard(user_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_reg_start_"), RoleFilter('admin'))
async def show_events_for_manual_registration(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split('_')[-1])
    events = await event_requests.get_upcoming_events(session)
    if not events:
        await callback.answer(Text.MANUAL_REG_NO_EVENTS, show_alert=True)
        return

    await callback.message.edit_text(
        Text.MANUAL_REG_CHOOSE_EVENT,
        reply_markup=inline.get_events_for_manual_registration_keyboard(user_id, events)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("adminReg_"), RoleFilter('admin'))
async def confirm_manual_registration(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    _, user_id_str, event_id_str = callback.data.split('_')
    user_id, event_id = int(user_id_str), int(event_id_str)
    
    user = await user_requests.get_user_by_id(session, user_id)
    event = await event_requests.get_event_by_id(session, event_id)
    if not user or not event:
        await callback.answer(Text.ERROR_GENERIC_ALERT, show_alert=True)
        return

    success, message = await admin_requests.manually_register_user(session, user, event)
    if success:
        await session.commit()
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=Text.MANUAL_REG_SUCCESS_NOTIFY.format(event_name=event.name, date=event.event_datetime.strftime('%d.%m.%Y')),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about manual registration: {e}")
            await callback.message.answer(Text.NOTIFY_USER_FAILED.format(name=user.full_name))
    else:
        await session.rollback()

    await callback.answer(message, show_alert=True)
    # This might fail if the original message was deleted, need a robust way to return to menu
    try:
        await manage_user_registrations_menu(callback, session)
    except Exception:
        await callback.message.answer("Возврат в меню...", reply_markup=inline.get_back_to_admin_panel_keyboard())


@router.callback_query(F.data.startswith("admin_cancel_start_"), RoleFilter('admin'))
async def show_registrations_for_cancellation(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split('_')[-1])
    registrations = await admin_requests.get_user_registrations(session, user_id)
    
    if not registrations:
        await callback.answer(Text.MANUAL_CANCEL_NO_REGS, show_alert=True)
        return

    await callback.message.edit_text(
        Text.MANUAL_CANCEL_CHOOSE_REG,
        reply_markup=inline.get_registrations_for_cancellation_keyboard(user_id, registrations)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("adminCancel_"), RoleFilter('admin'))
async def confirm_manual_cancellation(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    _, user_id_str, event_id_str = callback.data.split('_')
    user_id, event_id = int(user_id_str), int(event_id_str)

    user = await user_requests.get_user_by_id(session, user_id)
    event = await event_requests.get_event_by_id(session, event_id)
    if not user or not event:
        await callback.answer(Text.ERROR_GENERIC_ALERT, show_alert=True)
        return
        
    success = await event_requests.cancel_registration(session, user_id, event_id)
    if success:
        await session.commit()
        await callback.answer(Text.MANUAL_CANCEL_SUCCESS.format(name=user.full_name, event_name=event.name), show_alert=True)
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=Text.MANUAL_CANCEL_SUCCESS_NOTIFY.format(event_name=event.name),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about manual cancellation: {e}")
            await callback.message.answer(Text.NOTIFY_USER_FAILED.format(name=user.full_name))
    else:
        await session.rollback()
        await callback.answer(Text.MANUAL_CANCEL_FAIL, show_alert=True)
    
    try:
        await manage_user_registrations_menu(callback, session)
    except Exception:
         await callback.message.answer("Возврат в меню...", reply_markup=inline.get_back_to_admin_panel_keyboard())


# --- Управление медотводами ---
@router.callback_query(F.data.startswith("admin_manage_waivers_"), RoleFilter('admin'))
async def admin_manage_user_waivers_menu(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split('_')[-1])
    user = await user_requests.get_user_by_id(session, user_id)
    if not user:
        await callback.answer(Text.USER_NOT_FOUND, show_alert=True)
        return

    waivers = await admin_requests.get_all_user_active_waivers(session, user_id)
    text_header = Text.MANAGE_WAIVERS_HEADER.format(name=user.full_name)
    if not waivers:
        text = text_header + Text.MANAGE_WAIVERS_NO_WAIVERS
    else:
        text = text_header + Text.MANAGE_WAIVERS_WITH_WAIVERS

    await callback.message.edit_text(
        text,
        reply_markup=inline.get_admin_waiver_management_keyboard(user_id, waivers),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_waiver_"), RoleFilter('admin'))
async def set_waiver_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = int(callback.data.split('_')[-1])
    await state.update_data(user_id=user_id)
    await state.set_state(ManualWaiver.awaiting_end_date)
    await callback.message.edit_text(Text.MANUAL_WAIVER_DATE_PROMPT)
    await callback.answer()

@router.message(ManualWaiver.awaiting_end_date)
async def set_waiver_date(message: types.Message, state: FSMContext):
    try:
        end_date = datetime.datetime.strptime(message.text, "%d.%m.%Y").date()
        await state.update_data(end_date=end_date)
        await state.set_state(ManualWaiver.awaiting_reason)
        await message.answer(Text.MANUAL_WAIVER_REASON_PROMPT)
    except ValueError:
        await message.answer(Text.DATE_FORMAT_ERROR, parse_mode="HTML")

@router.message(ManualWaiver.awaiting_reason)
async def set_waiver_reason(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    reason, user_id, end_date = message.text, data['user_id'], data['end_date']
    
    admin_user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    user = await user_requests.get_user_by_id(session, user_id)

    await admin_requests.create_manual_waiver(session, user_id, end_date, reason, admin_user.id)
    await session.commit()
    await state.clear()

    await message.answer(
        Text.MANUAL_WAIVER_SUCCESS.format(name=user.full_name, date=end_date.strftime('%d.%m.%Y')),
        reply_markup=inline.get_back_to_admin_panel_keyboard()
    )
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=Text.MANUAL_WAIVER_NOTIFY.format(date=end_date.strftime('%d.%m.%Y'), reason=reason),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about manual waiver: {e}")

@router.callback_query(F.data.startswith("admin_del_waiver_"), RoleFilter('admin'))
async def admin_delete_waiver(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    try:
        _, _, _, waiver_id_str, user_id_str = callback.data.split('_')
        waiver_id, user_id = int(waiver_id_str), int(user_id_str)
    except ValueError:
        await callback.answer(Text.ADMIN_DELETE_WAIVER_DATA_ERROR, show_alert=True)
        return

    success = await admin_requests.force_delete_waiver(session, waiver_id)
    if success:
        await session.commit()
        await callback.answer(Text.ADMIN_DELETE_WAIVER_SUCCESS, show_alert=True)
        try:
            user = await user_requests.get_user_by_id(session, user_id)
            if user:
                await bot.send_message(chat_id=user.telegram_id, text=Text.ADMIN_DELETE_WAIVER_NOTIFY)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about admin waiver deletion: {e}")
    else:
        await session.rollback()
        await callback.answer(Text.ADMIN_DELETE_WAIVER_FAIL, show_alert=True)
    
    try:
        await admin_manage_user_waivers_menu(callback, session)
    except Exception:
        await callback.message.answer("Возврат в меню...", reply_markup=inline.get_back_to_admin_panel_keyboard())
        
        
        
        
@router.callback_query(F.data == "admin_add_user_start", RoleFilter('admin'))
async def add_user_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало FSM добавления пользователя."""
    await state.clear()
    await state.set_state(AdminAddUser.awaiting_phone)
    await callback.message.edit_text("<b>Шаг 1/9:</b> Введите номер телефона нового пользователя в формате <code>+7...</code>")
    await callback.answer()

@router.message(AdminAddUser.awaiting_phone)
async def add_user_phone(message: types.Message, state: FSMContext, session: AsyncSession):
    phone_number = message.text
    if not phone_number.startswith('+') or not phone_number[1:].isdigit() or len(phone_number) < 11:
        await message.answer("❌ Неверный формат номера. Введите в формате <code>+7...</code>")
        return

    existing_user = await user_requests.get_user_by_phone(session, phone_number)
    if existing_user:
        await message.answer(f"❌ Пользователь с номером {phone_number} уже существует: {existing_user.full_name}.")
        await state.clear()
        return

    await state.update_data(
        phone_number=phone_number,
        telegram_id=0, # Временный ID, т.к. пользователь еще не запускал бота
        telegram_username=f"manual_{phone_number}"
    )
    await state.set_state(AdminAddUser.awaiting_full_name)
    await message.answer("<b>Шаг 2/9:</b> Введите ФИО пользователя.")

# Далее мы можем использовать почти те же шаги, что и при обычной регистрации.
# Просто привязываем их к нашему новому состоянию AdminAddUser.
# Этот код можно добавить в конец файла user_management.py

@router.message(AdminAddUser.awaiting_full_name)
async def add_user_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(AdminAddUser.awaiting_category)
    await message.answer("<b>Шаг 3/9:</b> Выберите категорию пользователя.", reply_markup=inline.get_category_keyboard())

@router.callback_query(AdminAddUser.awaiting_category, F.data.startswith('category_'))
async def add_user_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split('_', 1)[1]
    await state.update_data(category=category)
    await callback.message.edit_text("<b>Шаг 4/9:</b> Выберите ВУЗ.", reply_markup=inline.get_university_keyboard())
    await state.set_state(AdminAddUser.awaiting_university)
    await callback.answer()

@router.callback_query(AdminAddUser.awaiting_university, F.data.startswith('university_'))
async def add_user_university(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split('_', 1)[1]
    if choice == 'mifi':
        await state.update_data(university="НИЯУ МИФИ")
        await callback.message.edit_text("<b>Шаг 5/9:</b> Выберите факультет.", reply_markup=inline.get_faculties_keyboard())
        await state.set_state(AdminAddUser.awaiting_faculty)
    else:
        await callback.message.edit_text("<b>Шаг 5/9:</b> Введите название ВУЗа.")
        await state.set_state(AdminAddUser.awaiting_custom_university_name)
    await callback.answer()

@router.message(AdminAddUser.awaiting_custom_university_name)
async def add_user_custom_university(message: types.Message, state: FSMContext):
    await state.update_data(university=message.text)
    await message.answer("<b>Шаг 6/9:</b> Введите факультет.")
    await state.set_state(AdminAddUser.awaiting_custom_faculty_name)

@router.callback_query(AdminAddUser.awaiting_faculty, F.data.startswith('faculty_'))
async def add_user_faculty(callback: types.CallbackQuery, state: FSMContext):
    faculty = callback.data.split('_', 1)[1]
    if faculty == 'Other':
        await callback.message.edit_text("<b>Шаг 6/9:</b> Введите название факультета.")
        await state.set_state(AdminAddUser.awaiting_custom_faculty_name)
    else:
        await state.update_data(faculty=faculty)
        await callback.message.edit_text("<b>Шаг 7/9:</b> Введите номер группы (или 'нет').")
        await state.set_state(AdminAddUser.awaiting_study_group)
    await callback.answer()
    
@router.message(AdminAddUser.awaiting_custom_faculty_name)
async def add_user_custom_faculty(message: types.Message, state: FSMContext):
    await state.update_data(faculty=message.text)
    await message.answer("<b>Шаг 7/9:</b> Введите номер группы (или 'нет').")
    await state.set_state(AdminAddUser.awaiting_study_group)

@router.message(AdminAddUser.awaiting_study_group)
async def add_user_study_group(message: types.Message, state: FSMContext):
    await state.update_data(study_group=message.text)
    await state.set_state(AdminAddUser.awaiting_gender)
    await message.answer("<b>Шаг 8/9:</b> Укажите пол.", reply_markup=inline.get_gender_inline_keyboard())

@router.callback_query(AdminAddUser.awaiting_gender, F.data.startswith("gender_"))
async def add_user_gender(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Последний шаг - сохранение."""
    gender = callback.data.split('_', 1)[1]
    await state.update_data(gender=gender, consent_given=True) # Согласие подразумевается, т.к. добавляет админ
    
    user_data = await state.get_data()
    # Заполняем недостающие поля по умолчанию
    user_data.setdefault('blood_type', 'Не указан')
    user_data.setdefault('rh_factor', '?')

    await user_requests.add_user(session, user_data)
    await session.commit()
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ Пользователь <b>{user_data['full_name']}</b> успешно добавлен в базу данных.",
        reply_markup=inline.get_user_management_main_keyboard()
    )
    await callback.answer("Пользователь добавлен!", show_alert=True)