import datetime
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import user_requests, event_requests
from bot.filters.role import RoleFilter
from bot.states.states import VolunteerActions
from bot.utils.qr_service import read_qr
from bot.keyboards import inline
from bot.utils.text_messages import Text

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "volunteer_panel", RoleFilter("volunteer"))
async def show_volunteer_panel(callback: types.CallbackQuery):
    await callback.message.edit_text(
        Text.VOLUNTEER_MENU_HEADER,
        reply_markup=inline.get_volunteer_panel_keyboard(),
        parse_mode="HTML",  # ИСПРАВЛЕНО
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_donation_qr", RoleFilter("volunteer"))
async def start_qr_confirmation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(VolunteerActions.awaiting_qr_photo)
    await callback.message.edit_text(Text.VOLUNTEER_SEND_QR_PROMPT)
    await callback.answer()


@router.message(VolunteerActions.awaiting_qr_photo, F.photo)
async def process_qr_photo(
    message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    photo_bytes = (await bot.download(message.photo[-1].file_id)).read()
    qr_data = await read_qr(photo_bytes)

    if not qr_data or "user_id" not in qr_data or "event_id" not in qr_data:
        await message.answer(Text.QR_READ_ERROR)
        await state.clear()
        return

    try:
        donor_tg_id = int(qr_data["user_id"])
        event_id_from_qr = int(qr_data["event_id"])
    except (ValueError, TypeError):
        await message.answer(Text.QR_INVALID_DATA_ERROR)
        await state.clear()
        return

    donor = await user_requests.get_user_by_tg_id(session, donor_tg_id)
    event = await event_requests.get_event_by_id(session, event_id_from_qr)

    if not donor or not event:
        await message.answer(Text.QR_DB_LOOKUP_ERROR)
        await state.clear()
        return

    registration = await event_requests.find_specific_registration(
        session, donor.id, event.id
    )
    if not registration:
        # Для этой строки parse_mode не нужен, т.к. в тексте ошибки нет тегов, но лучше быть последовательным
        await message.answer(
            Text.QR_DONOR_NOT_REGISTERED_ERROR.format(donor_name=donor.full_name),
            parse_mode="HTML",
        )
        await state.clear()
        return

    if event.event_datetime.date() != datetime.date.today():
        await message.answer(
            Text.QR_WRONG_DAY_ERROR
        )  # Здесь нет форматирования, parse_mode не нужен
        await state.clear()
        return

    await state.update_data(
        donor_id=donor.id,
        event_id=event.id,
        donor_tg_id=donor.telegram_id,
        donor_name=donor.full_name,
        event_name=event.name,
    )
    await state.set_state(VolunteerActions.awaiting_confirmation)

    await message.answer(
        Text.VOLUNTEER_CONFIRMATION_PROMPT.format(
            donor_name=donor.full_name, event_name=event.name
        ),
        reply_markup=inline.get_donation_confirmation_keyboard(donor.id, event.id),
        parse_mode="HTML",  # ИСПРАВЛЕНО
    )


@router.callback_query(
    VolunteerActions.awaiting_confirmation, F.data.startswith("confirm_donation_")
)
async def process_donation_confirmation(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
):
    data = await state.get_data()
    donor_id_from_state = data.get("donor_id")
    event_id_from_state = data.get("event_id")

    parts = callback.data.split("_")
    donor_id_from_cb = parts[2]
    event_id_from_cb = parts[3]

    if not (
        donor_id_from_state == int(donor_id_from_cb)
        and event_id_from_state == int(event_id_from_cb)
    ):
        await callback.message.edit_text(Text.VOLUNTEER_CONFIRMATION_ERROR)
        await state.clear()
        return

    await state.clear()
    await callback.message.edit_text(Text.DONATION_CONFIRMING)

    donor = await user_requests.get_user_by_id(session, donor_id_from_state)
    registration = await event_requests.find_specific_registration(
        session, donor_id_from_state, event_id_from_state
    )

    if not donor or not registration:
        await callback.message.edit_text(Text.DONATION_CONFIRM_ERROR_NO_REG)
        return

    try:
        points_awarded, waiver_end_date = (
            await event_requests.confirm_donation_transaction(
                session, donor, registration
            )
        )

        success_text = Text.DONATION_CONFIRM_SUCCESS.format(
            donor_name=donor.full_name,
            event_name=registration.event.name,
            points=points_awarded,
        )
        await callback.message.edit_text(
            success_text,
            reply_markup=inline.get_volunteer_panel_keyboard(),
            parse_mode="HTML",  # ИСПРАВЛЕНО
        )
    except Exception as e:
        logger.error(
            f"Critical error during donation confirmation for user {donor.id}: {e}",
            exc_info=True,
        )
        await callback.message.edit_text(
            Text.DONATION_CONFIRM_CRITICAL_ERROR.format(error=e)
        )

    await callback.answer()


@router.message(VolunteerActions.awaiting_qr_photo)
async def process_qr_invalid_input(message: types.Message):
    await message.answer(Text.VOLUNTEER_INVALID_INPUT_QR)
