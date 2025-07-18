from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import user_requests
from bot.states.states import Registration
from bot.keyboards import reply, inline
from bot.utils.text_messages import Text
from bot.filters.role import RoleFilter

ROLE_MENU_MAP = {
    'student': inline.get_student_main_menu,
    'volunteer': inline.get_volunteer_main_menu,
    'admin': inline.get_admin_main_menu,
    'main_admin': inline.get_main_admin_main_menu
}

router = Router()

# =============================================================================
# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ОТПРАВКИ/РЕДАКТИРОВАНИЯ МЕНЮ ---
# =============================================================================

async def send_or_edit_main_menu(
    event: types.Message | types.CallbackQuery, 
    session: AsyncSession, 
    welcome_text: str = None, 
    force_role: str = None
):
    """
    Универсальная функция для отправки или редактирования главного меню ОДНИМ сообщением.
    """
    user = await user_requests.get_user_by_tg_id(session, event.from_user.id)
    message_to_handle = getattr(event, 'message', event)
    
    
    if not user:
        if isinstance(event, types.CallbackQuery):
            await event.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        else:
            await message_to_handle.answer(Text.WELCOME, reply_markup=reply.get_contact_keyboard())
        return

    if user.is_blocked:
        await message_to_handle.answer(Text.USER_BLOCKED_MESSAGE, reply_markup=ReplyKeyboardRemove())
        return

    # 1. Определяем текст приветствия
    if welcome_text:
        greeting = welcome_text
    elif force_role == 'student':
        greeting = Text.SWITCH_TO_DONOR_VIEW
    else:
        greeting = Text.WELCOME_BACK.format(name=user.full_name)

    # 2. Собираем единый текст для сообщения
    combined_text = f"{greeting}\n\n{Text.MAIN_MENU_PROMPT}"

    # 3. Определяем, какую inline-клавиатуру показать
    effective_role = force_role if force_role else user.role
    menu_func = ROLE_MENU_MAP.get(effective_role, inline.get_student_main_menu)
    inline_kbd = menu_func(viewer_role=user.role)

    # 4. Отправляем или редактируем сообщение
    if isinstance(event, types.Message):
        # Для новых сообщений (/start, "Домой") - отправляем одно новое сообщение с меню
        await message_to_handle.answer(
            combined_text,
            reply_markup=inline_kbd,
            parse_mode="HTML"
        )
    elif isinstance(event, types.CallbackQuery):
        # Для колбэков ("Назад в меню") - редактируем существующее
        try:
            await message_to_handle.edit_text(combined_text, reply_markup=inline_kbd, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await event.answer() # Игнорируем ошибку, если сообщение не изменилось
            else:
                # Если отредактировать не удалось (например, сообщение слишком старое), удаляем его и отправляем новое
                await message_to_handle.delete()
                await message_to_handle.answer(combined_text, reply_markup=inline_kbd, parse_mode="HTML")
        await event.answer()

# --- ИСПРАВЛЕННЫЕ ХЕНДЛЕРЫ ---
@router.message(F.text == "🏠 Домой")
@router.message(CommandStart())
async def cmd_start_or_home(message: types.Message, session: AsyncSession):
    """
    Устанавливает Reply-клавиатуру и показывает главное меню.
    Теперь это делается более "незаметно".
    """
    # Сначала устанавливаем постоянную клавиатуру с кнопкой "Домой"
    # await message.answer("Меню обновлено.", reply_markup=reply.get_home_keyboard())
    # И сразу же отправляем основное меню с inline-кнопками
    await send_or_edit_main_menu(message, session)


@router.callback_query(F.data == "back_to_main_menu")
async def handle_back_to_main_menu(callback: types.CallbackQuery, session: AsyncSession):
    """Обрабатывает все стандартные кнопки 'Назад в меню'."""
    await send_or_edit_main_menu(callback, session)


@router.callback_query(F.data == "switch_to_donor_view")
async def handle_switch_to_donor_view(callback: types.CallbackQuery, session: AsyncSession):
    """Обрабатывает переход в режим донора, принудительно показывая меню студента."""
    await send_or_edit_main_menu(callback, session, force_role='student')

# =============================================================================
# --- ЛОГИКА РЕГИСТРАЦИИ ---
# =============================================================================

@router.message(F.contact)
async def handle_contact(message: types.Message, session: AsyncSession, state: FSMContext):
    user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    if user:
        # Устанавливаем клавиатуру и показываем меню
        # await message.answer("Меню обновлено.", reply_markup=reply.get_home_keyboard())
        await send_or_edit_main_menu(message, session, welcome_text=Text.ALREADY_REGISTERED.format(name=user.full_name))
        return
        
    contact = message.contact
    phone_number = contact.phone_number
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number
        
    user_by_phone = await user_requests.get_user_by_phone(session, phone_number)
    if user_by_phone:
        if user_by_phone.is_blocked:
            await message.answer(Text.USER_BLOCKED_ON_AUTH, reply_markup=ReplyKeyboardRemove())
            return
            
        await user_requests.update_user_credentials(session, user_by_phone.id, message.from_user.id, message.from_user.username)
        # Устанавливаем клавиатуру и показываем меню
        # await message.answer("Меню обновлено.", reply_markup=reply.get_home_keyboard())
        await send_or_edit_main_menu(message, session, welcome_text=Text.AUTH_SUCCESS.format(name=user_by_phone.full_name))
    else:
        await state.update_data(
            phone_number=phone_number,
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username
        )
        await message.answer(Text.START_REGISTRATION, reply_markup=ReplyKeyboardRemove())
        await message.answer(Text.GET_FULL_NAME)
        await state.set_state(Registration.awaiting_full_name)


@router.message(Registration.awaiting_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer(Text.GET_UNIVERSITY, reply_markup=inline.get_university_keyboard())
    await state.set_state(Registration.awaiting_university)


@router.callback_query(Registration.awaiting_university, F.data.startswith('university_'))
async def process_university_choice(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split('_', 1)[1]
    
    if choice == 'mifi':
        await state.update_data(university="НИЯУ МИФИ")
        await callback.message.edit_text(Text.GET_FACULTY, reply_markup=inline.get_faculties_keyboard())
        await state.set_state(Registration.awaiting_faculty)
    else: # choice == 'other'
        await callback.message.edit_text(Text.GET_CUSTOM_UNIVERSITY)
        await state.set_state(Registration.awaiting_custom_university_name)
    
    await callback.answer()


@router.message(Registration.awaiting_custom_university_name)
async def process_custom_university_name(message: types.Message, state: FSMContext):
    await state.update_data(university=message.text)
    await message.answer(Text.GET_CUSTOM_FACULTY)
    await state.set_state(Registration.awaiting_custom_faculty_name)


@router.callback_query(Registration.awaiting_faculty, F.data.startswith('faculty_'))
async def process_faculty(callback: types.CallbackQuery, state: FSMContext):
    faculty = callback.data.split('_', 1)[1]
    
    if faculty == 'Other':
        await callback.message.edit_text(Text.GET_CUSTOM_FACULTY)
        await state.set_state(Registration.awaiting_custom_faculty_name)
    else:
        await state.update_data(faculty=faculty)
        await callback.message.edit_text(Text.FACULTY_SELECTED.format(faculty=faculty))
        await callback.message.answer(Text.GET_GROUP)
        await state.set_state(Registration.awaiting_study_group)
    
    await callback.answer()


@router.message(Registration.awaiting_custom_faculty_name)
async def process_custom_faculty_name(message: types.Message, state: FSMContext):
    await state.update_data(faculty=message.text)
    await message.answer(Text.GET_GROUP)
    await state.set_state(Registration.awaiting_study_group)


@router.message(Registration.awaiting_study_group)
async def process_study_group(message: types.Message, state: FSMContext):
    await state.update_data(study_group=message.text)
    await message.answer(Text.GET_BLOOD_TYPE, reply_markup=inline.get_blood_type_keyboard())
    await state.set_state(Registration.awaiting_blood_type)


@router.callback_query(Registration.awaiting_blood_type, F.data.startswith('bloodtype_'))
async def process_blood_type(callback: types.CallbackQuery, state: FSMContext):
    blood_type = callback.data.split('_', 1)[1]
    await state.update_data(blood_type=blood_type)
    await callback.message.edit_text(Text.BLOOD_TYPE_SELECTED.format(blood_type=blood_type))
    await callback.message.answer(Text.GET_RH_FACTOR, reply_markup=inline.get_rh_factor_keyboard())
    await state.set_state(Registration.awaiting_rh_factor)


@router.callback_query(Registration.awaiting_rh_factor, F.data.startswith('rhfactor_'))
async def process_rh_factor(callback: types.CallbackQuery, state: FSMContext):
    rh_factor = callback.data.split('_', 1)[1]
    await state.update_data(rh_factor=rh_factor)
    await callback.message.edit_text(Text.RH_FACTOR_SELECTED.format(rh_factor=rh_factor))
    await callback.message.answer(Text.GET_GENDER, reply_markup=inline.get_gender_inline_keyboard())
    await state.set_state(Registration.awaiting_gender)


@router.callback_query(Registration.awaiting_gender, F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    gender = callback.data.split('_', 1)[1]
    gender_text = "Мужской" if gender == "male" else "Женский"
    
    await callback.message.edit_text(Text.GENDER_SELECTED.format(gender=gender_text))
    
    await state.update_data(gender=gender)
    user_data = await state.get_data()
    user_data.setdefault('faculty', 'Не указан')
    user_data.setdefault('study_group', 'Не указана')
    
    new_user = await user_requests.add_user(session, user_data)
    await session.commit()
    await state.clear()
    
    # После регистрации устанавливаем клавиатуру и показываем меню
    # await callback.message.answer("Меню обновлено.", reply_markup=reply.get_home_keyboard())
    await send_or_edit_main_menu(callback.message, session, welcome_text=Text.REGISTRATION_COMPLETE.format(name=new_user.full_name))
    await callback.answer()


# =============================================================================
# ПРОЧИЕ ОБРАБОТЧИКИ
# =============================================================================

@router.message(Command("cancel"), StateFilter(any_state))
@router.callback_query(F.data == "cancel_fsm", StateFilter(any_state))
async def cancel_fsm_handler(event: types.Message | types.CallbackQuery, state: FSMContext, session: AsyncSession):
    current_state = await state.get_state()
    if current_state is None:
        if isinstance(event, types.CallbackQuery): await event.answer()
        return

    await state.clear()
    
    message_to_use = event.message if isinstance(event, types.CallbackQuery) else event
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(Text.ACTION_CANCELLED)
    else:
        await event.answer(Text.ACTION_CANCELLED)
    
    # После отмены тоже показываем единое меню
    await send_or_edit_main_menu(message_to_use, session)
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.message(Command("secret_admin_123"), RoleFilter('admin'))
async def secret_admin_panel(message: types.Message, session: AsyncSession):
    fake_callback = types.CallbackQuery(
        id=str(message.message_id),
        from_user=message.from_user,
        chat_instance="instance",
        message=message,
        data="admin_panel"
    )
    
    from .admin import show_admin_panel
    await show_admin_panel(fake_callback, session)
    await message.delete()


@router.callback_query(F.data == "switch_to_volunteer_view", RoleFilter('admin'))
async def switch_to_volunteer_view_handler(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📷 Подтвердить донацию (QR)", callback_data="confirm_donation_qr"))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад в меню донора", callback_data="switch_to_donor_view"))
    await callback.message.edit_text(
        Text.ADMIN_SWITCH_TO_VOLUNTEER_VIEW,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()