import re
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.exceptions import TelegramBadRequest

from bot.db import user_requests
from bot.states.states import Registration
from bot.keyboards import reply, inline
from bot.utils.text_messages import Text
from bot.utils.graduation import calculate_graduation_year
from bot.filters.role import RoleFilter

ROLE_MENU_MAP = {
    "student": inline.get_student_main_menu,
    "volunteer": inline.get_volunteer_main_menu,
    "admin": inline.get_admin_main_menu,
    "main_admin": inline.get_main_admin_main_menu,
}

router = Router()

# =============================================================================
# --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ОТПРАВКИ/РЕДАКТИРОВАНИЯ МЕНЮ ---
# =============================================================================


async def send_or_edit_main_menu(
    event: types.Message | types.CallbackQuery,
    session: AsyncSession,
    welcome_text: str = None,
    force_role: str = None,
):
    """
    Универсальная функция для отправки или редактирования главного меню ОДНИМ сообщением.
    """
    user = await user_requests.get_user_by_tg_id(session, event.from_user.id)
    message_to_handle = getattr(event, "message", event)

    if not user:
        if isinstance(event, types.CallbackQuery):
            await event.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        else:
            await message_to_handle.answer(
                Text.WELCOME, reply_markup=reply.get_contact_keyboard()
            )
        return

    if user.is_blocked:
        await message_to_handle.answer(
            Text.USER_BLOCKED_MESSAGE, reply_markup=ReplyKeyboardRemove()
        )
        return

    if welcome_text:
        greeting = welcome_text
    elif force_role == "student":
        greeting = Text.SWITCH_TO_DONOR_VIEW
    else:
        greeting = Text.WELCOME_BACK.format(name=user.full_name)

    combined_text = f"{greeting}\n\n{Text.MAIN_MENU_PROMPT}"
    effective_role = force_role if force_role else user.role
    menu_func = ROLE_MENU_MAP.get(effective_role, inline.get_student_main_menu)
    inline_kbd = menu_func(viewer_role=user.role)

    if isinstance(event, types.Message):
        await message_to_handle.answer(
            combined_text, reply_markup=inline_kbd, parse_mode="HTML"
        )
    elif isinstance(event, types.CallbackQuery):
        try:
            await message_to_handle.edit_text(
                combined_text, reply_markup=inline_kbd, parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                await event.answer()
            else:
                await message_to_handle.delete()
                await message_to_handle.answer(
                    combined_text, reply_markup=inline_kbd, parse_mode="HTML"
                )
        await event.answer()


@router.message(F.text == "🏠 Домой")
@router.message(CommandStart())
async def cmd_start_or_home(message: types.Message, session: AsyncSession):
    await send_or_edit_main_menu(message, session)


@router.callback_query(F.data == "back_to_main_menu")
async def handle_back_to_main_menu(
    callback: types.CallbackQuery, session: AsyncSession
):
    await send_or_edit_main_menu(callback, session)


@router.callback_query(F.data == "switch_to_donor_view")
async def handle_switch_to_donor_view(
    callback: types.CallbackQuery, session: AsyncSession
):
    await send_or_edit_main_menu(callback, session, force_role="student")


# =============================================================================
# --- ЛОГИКА РЕГИСТРАЦИИ (ИСПРАВЛЕННАЯ ВЕРСИЯ) ---
# =============================================================================


@router.message(F.contact)
async def handle_contact(
    message: types.Message, session: AsyncSession, state: FSMContext
):
    user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    if user:
        await send_or_edit_main_menu(
            message,
            session,
            welcome_text=Text.ALREADY_REGISTERED.format(name=user.full_name),
        )
        return

    contact = message.contact
    phone_number = contact.phone_number
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number

    user_by_phone = await user_requests.get_user_by_phone(session, phone_number)
    if user_by_phone:
        if user_by_phone.is_blocked:
            await message.answer(
                Text.USER_BLOCKED_ON_AUTH, reply_markup=ReplyKeyboardRemove()
            )
            return

        await user_requests.update_user_credentials(
            session, user_by_phone.id, message.from_user.id, message.from_user.username
        )
        await session.commit()

        if not await user_requests.is_profile_complete(session, user_by_phone.id):
            await message.answer(
                "Ваш профиль был найден, но он не полон. Давайте его дозаполним."
            )
            await state.update_data(
                phone_number=user_by_phone.phone_number,
                telegram_id=message.from_user.id,
                telegram_username=message.from_user.username,
            )
            await state.set_state(Registration.awaiting_full_name)
            await message.answer(Text.GET_FULL_NAME)
        else:
            await send_or_edit_main_menu(
                message,
                session,
                welcome_text=Text.AUTH_SUCCESS.format(name=user_by_phone.full_name),
            )
    else:
        await state.update_data(
            phone_number=phone_number,
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
        )
        await message.answer(
            Text.START_REGISTRATION, reply_markup=ReplyKeyboardRemove()
        )
        await message.answer(Text.GET_FULL_NAME)
        await state.set_state(Registration.awaiting_full_name)


@router.message(Registration.awaiting_full_name)
async def process_full_name(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    full_name = message.text.strip()

    # Закомментированный старый блок валидации
    # allowed_chars = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя-"
    # if not all(c.lower() in allowed_chars or c.isspace() for c in full_name):
    #     await message.answer(Text.FIO_VALIDATION_ERROR)
    #     return
    #
    # name_parts = full_name.split()
    # if len(name_parts) < 2:
    #     await message.answer("Пожалуйста, введите как минимум Фамилию и Имя.")
    #     return

    # Новая логика: ФИО должно состоять как минимум из 2-х слов
    # и не должно содержать цифр или спецсимволов, кроме дефиса.
    name_parts = full_name.split()
    # Python's `isalpha()` handles Unicode, so it works for Cyrillic.
    # It returns False for digits and most special characters.
    has_invalid_chars = any(
        not (c.isalpha() or c.isspace() or c == "-") for c in full_name
    )

    if len(name_parts) < 2 or has_invalid_chars:
        await message.answer(
            "Пожалуйста, введите корректные Фамилию, Имя и (если есть) Отчество, используя только буквы."
        )
        return

    corrected_name = " ".join([part.strip().capitalize() for part in name_parts])

    user_by_fio = await user_requests.get_unlinked_user_by_fio(session, corrected_name)
    if user_by_fio:
        user_data = await state.get_data()
        await user_requests.update_user_credentials(
            session,
            user_by_fio.id,
            user_data["telegram_id"],
            user_data["telegram_username"],
        )
        await session.commit()

        if not await user_requests.is_profile_complete(session, user_by_fio.id):
            await message.answer(
                "Ваш профиль был найден, но он не полон. Давайте его дозаполним."
            )
            await state.update_data(full_name=corrected_name)
            await message.answer(
                Text.GET_CATEGORY, reply_markup=inline.get_category_keyboard()
            )
            await state.set_state(Registration.awaiting_category)
        else:
            await state.clear()
            await send_or_edit_main_menu(
                message,
                session,
                welcome_text=Text.AUTH_SUCCESS.format(name=user_by_fio.full_name),
            )
        return

    await state.update_data(full_name=corrected_name)

    await message.answer(Text.GET_CATEGORY, reply_markup=inline.get_category_keyboard())
    await state.set_state(Registration.awaiting_category)


# --- НОВЫЙ ХЕНДЛЕР: Обработка категории ---
@router.callback_query(Registration.awaiting_category, F.data.startswith("category_"))
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split("_", 1)[1]
    await state.update_data(category=category)

    if category == "external":
        await state.update_data(
            university="Внешний донор", faculty="Не применимо", study_group="-"
        )
        await callback.message.edit_text(
            Text.GET_GENDER, reply_markup=inline.get_gender_inline_keyboard()
        )
        await state.set_state(Registration.awaiting_gender)
    elif category == "student":
        # Сбор данных о факультетах убран
        await state.update_data(university="НИЯУ МИФИ", faculty="Не указан")
        await callback.message.edit_text(Text.GET_GROUP)
        await state.set_state(Registration.awaiting_study_group)
    elif category == "employee":
        await state.update_data(
            university="НИЯУ МИФИ", faculty="Сотрудник", study_group="-"
        )
        await callback.message.edit_text(
            Text.GET_GENDER, reply_markup=inline.get_gender_inline_keyboard()
        )
        await state.set_state(Registration.awaiting_gender)

    await callback.answer()


# @router.callback_query(Registration.awaiting_faculty, F.data.startswith('faculty_'))
# async def process_faculty(callback: types.CallbackQuery, state: FSMContext):
#     faculty_name = callback.data.split('_', 1)[1]
#
#     if faculty_name == 'Other':
#         await callback.message.edit_text(Text.GET_CUSTOM_FACULTY)
#         await state.set_state(Registration.awaiting_custom_faculty_name)
#     else:
#         await state.update_data(faculty=faculty_name)
#         user_data = await state.get_data()
#         if user_data.get("category") == "employee":
#             await state.update_data(study_group="-")
#             await callback.message.edit_text(Text.GET_GENDER, reply_markup=inline.get_gender_inline_keyboard())
#             await state.set_state(Registration.awaiting_gender)
#         else:
#             await callback.message.edit_text(Text.FACULTY_SELECTED.format(faculty=faculty_name))
#             await callback.message.answer(Text.GET_GROUP)
#             await state.set_state(Registration.awaiting_study_group)
#
#     await callback.answer()
#
#
# @router.message(Registration.awaiting_custom_faculty_name)
# async def process_custom_faculty_name(message: types.Message, state: FSMContext):
#     await state.update_data(faculty=message.text)
#     await message.answer(Text.GET_GROUP)
#     await state.set_state(Registration.awaiting_study_group)


@router.message(Registration.awaiting_study_group)
async def process_study_group(message: types.Message, state: FSMContext):
    group_name = message.text.strip()

    # Закомментированная старая проверка
    # if group_name and group_name[0].lower() not in ['б', 'с', 'м', 'а']:
    #     await message.answer(
    #         "Название учебной группы некорректно.\n"
    #         "Первая буква должна быть одной из следующих: "
    #         "б - бакалавриат, с - специалитет, м - магистратура, а - аспирантура."
    #     )
    #     return

    # Новая, более строгая проверка с помощью регулярного выражения
    if not re.match(r"^[БСМАбсма]\d{2}-\d{3}$", group_name):
        await message.answer(
            "Формат учебной группы некорректен.\n"
            "Пожалуйста, введите название в формате, например, 'Б23-101', где:\n"
            "• Первая буква: Б/С/М/А\n"
            "• Далее 2 цифры, дефис и еще 3 цифры."
        )
        return

    await state.update_data(study_group=group_name.upper())
    await message.answer(
        Text.GET_GENDER, reply_markup=inline.get_gender_inline_keyboard()
    )
    await state.set_state(Registration.awaiting_gender)


@router.callback_query(Registration.awaiting_gender, F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = callback.data.split("_", 1)[1]
    gender_text = "Мужской" if gender == "male" else "Женский"

    await callback.message.edit_text(Text.GENDER_SELECTED.format(gender=gender_text))
    await state.update_data(gender=gender)

    await callback.message.answer(
        Text.CONSENT_TEXT, reply_markup=inline.get_consent_keyboard(), parse_mode="HTML"
    )
    await state.set_state(Registration.awaiting_consent)
    await callback.answer()


@router.callback_query(Registration.awaiting_consent, F.data == "consent_given")
async def process_consent(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    user_data = await state.get_data()
    telegram_id = user_data.get("telegram_id")

    existing_user = await user_requests.get_user_by_tg_id(session, telegram_id)

    if existing_user:
        update_data = {
            "full_name": user_data.get("full_name"),
            "university": user_data.get("university"),
            "faculty": user_data.get("faculty"),
            "study_group": user_data.get("study_group"),
            "gender": user_data.get("gender"),
            "graduation_year": calculate_graduation_year(user_data.get("study_group")),
        }
        await user_requests.update_user_profile(session, existing_user.id, update_data)
        user_to_greet = await user_requests.get_user_by_id(session, existing_user.id)
    else:
        user_data["consent_given"] = True
        user_data["graduation_year"] = calculate_graduation_year(
            user_data.get("study_group")
        )
        user_to_greet = await user_requests.add_user(session, user_data)

    await session.commit()
    await state.clear()

    await callback.message.delete()

    await callback.message.answer(
        text=f"{Text.REGISTRATION_COMPLETE.format(name=user_to_greet.full_name)}\n\n{Text.MAIN_MENU_PROMPT}",
        reply_markup=ROLE_MENU_MAP.get(
            user_to_greet.role, inline.get_student_main_menu
        )(viewer_role=user_to_greet.role),
    )

    await callback.message.answer(
        # text="Теперь вам доступно главное меню.",
        reply_markup=reply.get_home_keyboard()
    )

    await callback.answer()


# =============================================================================
# ПРОЧИЕ ОБРАБОТЧИКИ
# =============================================================================


@router.message(Command("cancel"), StateFilter(any_state))
@router.callback_query(F.data == "cancel_fsm", StateFilter(any_state))
async def cancel_fsm_handler(
    event: types.Message | types.CallbackQuery, state: FSMContext, session: AsyncSession
):
    current_state = await state.get_state()
    if current_state is None:
        if isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    await state.clear()

    message_to_use = event.message if isinstance(event, types.CallbackQuery) else event

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(Text.ACTION_CANCELLED)
    else:
        await event.answer(Text.ACTION_CANCELLED)

    await send_or_edit_main_menu(message_to_use, session)
    if isinstance(event, types.CallbackQuery):
        await event.answer()


@router.message(Command("secret_admin_123"), RoleFilter("admin"))
async def secret_admin_panel(message: types.Message, session: AsyncSession):
    fake_callback = types.CallbackQuery(
        id=str(message.message_id),
        from_user=message.from_user,
        chat_instance="instance",
        message=message,
        data="admin_panel",
    )

    from .admin import show_admin_panel

    await show_admin_panel(fake_callback, session)
    await message.delete()


@router.callback_query(F.data == "switch_to_volunteer_view", RoleFilter("admin"))
async def switch_to_volunteer_view_handler(callback: types.CallbackQuery):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="📷 Подтвердить донацию (QR)", callback_data="confirm_donation_qr"
        )
    )
    builder.row(
        types.InlineKeyboardButton(
            text="↩️ Назад в меню донора", callback_data="switch_to_donor_view"
        )
    )
    await callback.message.edit_text(
        Text.ADMIN_SWITCH_TO_VOLUNTEER_VIEW,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()
