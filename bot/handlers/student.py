import datetime
import math
import logging
import time
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State 
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db import user_requests, event_requests, merch_requests
from bot.config_reader import config
from bot.keyboards import inline
from bot.utils.qr_service import generate_qr
from bot.utils.text_messages import Text
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from bot.db.models import MerchItem, Feedback, NoShowReport
from bot.states.states import UserWaiver, FeedbackSurvey
from aiogram.types import BufferedInputFile, WebAppInfo
from bot.utils.calendar_service import generate_ics_file
from bot.db import info_requests

from bot.states.states import UserWaiver, FeedbackSurvey, AskQuestion
from bot.db import user_requests, event_requests, merch_requests, question_requests 


router = Router()
logger = logging.getLogger(__name__)

# --- НОВАЯ УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ---
async def show_events_for_registration(message: types.Message, session: AsyncSession, user_id: int):
    """
    Показывает пользователю список доступных мероприятий для регистрации.
    Эта функция будет вызываться в нескольких местах.
    """
    events = await event_requests.get_active_events_for_user(session, user_id)
    text = ""
    reply_markup = None

    if not events:
        text = "✅ Противопоказаний не найдено.\n\nК сожалению, активных мероприятий для записи сейчас нет."
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
        reply_markup = builder.as_markup()
    else:
        text = "✅ Противопоказаний не найдено.\n\nВот список доступных мероприятий:"
        builder = InlineKeyboardBuilder()
        for event in events:
            builder.row(types.InlineKeyboardButton(
                text=f"{event.event_datetime.strftime('%d.%m.%Y')} - {event.name}",
                callback_data=f"reg_event_{event.id}"
            ))
        builder.row(types.InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
        reply_markup = builder.as_markup()
    
    # Редактируем сообщение, если это возможно, иначе отправляем новое
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await message.delete()
        except TelegramBadRequest:
            pass # Если не удалось удалить - не страшно
        await message.answer(text, reply_markup=reply_markup)


# --- 👤 МОЙ ПРОФИЛЬ ---

@router.callback_query(F.data == "my_profile")
async def show_profile_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=Text.PROFILE_MENU_HEADER,
        reply_markup=inline.get_profile_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "profile_data")
async def show_profile_data(callback: types.CallbackQuery, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    profile_data = await user_requests.get_user_profile_info(session, user.id)
    if not profile_data:
        await callback.answer(Text.PROFILE_LOAD_ERROR, show_alert=True)
        return
    
    user_obj = profile_data['user']
    last_donation = profile_data['last_donation']
    
    if last_donation:
        blood_center = last_donation.event.blood_center_name if last_donation.event else "Не указан"
        last_donation_info = f"{last_donation.donation_date.strftime('%d.%m.%Y')} ({Text.escape_html(blood_center)})"
    else:
        last_donation_info = "Еще не было"

    dkm_status = "Да" if user_obj.is_dkm_donor else "Нет"

    text = Text.PROFILE_DATA_TEMPLATE.format(
        full_name=Text.escape_html(user_obj.full_name),
        university=Text.escape_html(user_obj.university),
        faculty=Text.escape_html(user_obj.faculty or 'Не указан'),
        study_group=Text.escape_html(user_obj.study_group or 'Не указана'),
        points=user_obj.points,
        total_donations=profile_data['total_donations'],
        next_date=profile_data['next_possible_donation'].strftime('%d.%m.%Y'),
        last_donation_info=last_donation_info,
        dkm_status=dkm_status
    )
    
    await callback.message.edit_text(text, reply_markup=inline.get_back_to_profile_menu_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "profile_history")
async def show_donation_history(callback: types.CallbackQuery, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    donations = await user_requests.get_user_donation_history(session, user.id)
    if not donations:
        await callback.message.edit_text(Text.NO_DONATION_HISTORY, reply_markup=inline.get_back_to_profile_menu_keyboard())
        return
    history_text = Text.DONATION_HISTORY_HEADER
    for donation in donations:
        donation_type_ru = Text.DONATION_TYPE_RU.get(donation.donation_type, donation.donation_type)
        history_text += Text.DONATION_HISTORY_ITEM.format(
            date=donation.donation_date.strftime('%d.%m.%Y'),
            type=Text.escape_html(donation_type_ru), 
            points=donation.points_awarded
        )
    await callback.message.edit_text(history_text, reply_markup=inline.get_back_to_profile_menu_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- 📅 ЗАПИСЬ НА ДОНАЦИЮ ---

@router.callback_query(F.data == "register_donation")
async def show_survey_or_events(callback: types.CallbackQuery, session: AsyncSession, ngrok_url: str):
    """
    Главный хендлер для "Записаться на донацию".
    Проверяет наличие свежей анкеты. Если она есть - показывает мероприятия.
    Если нет - показывает WebApp для прохождения опроса.
    """
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not user:
        await callback.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        return

    # Проверяем, есть ли сегодня мероприятие
    events = await event_requests.get_active_events_for_user(session, user.id)
    today = datetime.date.today()
    is_today_event_available = any(event.event_datetime.date() == today for event in events)

    if is_today_event_available:
        await show_events_for_registration(callback.message, session, user.id)
        return

    # Проверяем наличие недавнего успешного опросника
    has_recent_survey = await user_requests.check_recent_survey(session, user.id)

    if has_recent_survey:
        # Если опросник пройден, сразу показываем мероприятия
        await callback.answer("Вы уже проходили опросник. Показываю доступные мероприятия.")
        await show_events_for_registration(callback.message, session, user.id)
    else:
        # Если опросника нет, отправляем в WebApp
        if not ngrok_url:
            await callback.answer("Ошибка: Сервис временно недоступен. Попробуйте позже.", show_alert=True)
            return

        cache_buster = int(time.time())
        webapp_url = f"{ngrok_url}/webapp/index.html?v={cache_buster}"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="📝 Пройти опрос перед донацией",
                    web_app=WebAppInfo(url=webapp_url)
                )
            ],[
                types.InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu")
            ]]
        )
        
        try:
            await callback.message.edit_text(
                "Перед записью на донацию необходимо пройти небольшой опрос для выявления противопоказаний. "
                "Это займет не более минуты. Пожалуйста, отвечайте честно.",
                reply_markup=keyboard
            )
        except TelegramBadRequest:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(
                "Перед записью на донацию необходимо пройти небольшой опрос для выявления противопоказаний. "
                "Это займет не более минуты. Пожалуйста, отвечайте честно.",
                reply_markup=keyboard
            )
        await callback.answer()


@router.callback_query(F.data.startswith("reg_event_"))
async def process_event_registration(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    event = await event_requests.get_event_by_id(session, event_id)
    if not user or not event:
        await callback.answer(Text.ERROR_GENERIC_ALERT, show_alert=True)
        return

    safe_event_name = Text.escape_html(event.name)
    
    # Переопределяем клавиатуру прямо здесь для надежности
    def get_reg_success_kbd(ev_id: int):
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔲 Мой QR-код для этого мероприятия", callback_data=f"get_event_qr_{ev_id}"))
        builder.row(types.InlineKeyboardButton(text="🗓️ Добавить в календарь", callback_data=f"add_to_calendar_{ev_id}"))
        builder.row(types.InlineKeyboardButton(text="❌ Отменить мою регистрацию", callback_data=f"cancel_reg_{ev_id}"))
        builder.row(types.InlineKeyboardButton(text="↩️ К списку мероприятий", callback_data="register_donation"))
        return builder.as_markup()

    existing_registration = await event_requests.find_specific_registration(session, user.id, event.id)
    if existing_registration:
        await callback.message.edit_text(
            text=Text.ALREADY_REGISTERED_FOR_EVENT.format(event_name=safe_event_name),
            reply_markup=get_reg_success_kbd(event.id),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    is_eligible, reason = await event_requests.check_registration_eligibility(session, user, event)
    if is_eligible:
        await event_requests.add_event_registration(session, user.id, event_id)
        location_link = Text.format_location_link(event.location, event.latitude, event.longitude)
        
        await callback.message.edit_text(
            text=Text.REGISTRATION_SUCCESSFUL.format(
                event_name=safe_event_name,
                event_location=location_link,
                blood_center_name=event.blood_center.name if event.blood_center else "Не указан"
            ),
            reply_markup=get_reg_success_kbd(event.id),
            parse_mode="HTML",
            disable_web_page_preview=True 
        )
    else:
        await callback.answer(Text.REGISTRATION_FAILED.format(reason=reason), show_alert=True)


@router.callback_query(F.data.startswith("cancel_reg_"))
async def cancel_my_registration(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    telegram_id = callback.from_user.id
    user = await user_requests.get_user_by_tg_id(session, telegram_id)
    if not user:
        await callback.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        return
    success = await event_requests.cancel_registration(session, user.id, event_id)
    if success:
        await callback.message.edit_text(
            Text.REGISTRATION_CANCELLED_SUCCESS,
            reply_markup=inline.get_back_to_main_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            Text.REGISTRATION_CANCELLED_FAIL,
            reply_markup=inline.get_back_to_main_menu_keyboard()
        )
    await callback.answer()

# --- 🎁 МАГАЗИН МЕРЧА ---

@router.callback_query(F.data == "merch_store")
@router.callback_query(F.data.startswith("merch_page_"))
async def show_merch_store(callback: types.CallbackQuery, session: AsyncSession):
    page = 1
    if callback.data.startswith("merch_page_"):
        page = int(callback.data.split('_')[-1])
    item, total_items = await merch_requests.get_merch_page(session, page=page)
    if not item:
        await callback.answer(Text.MERCH_NO_ITEMS, show_alert=True)
        return
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    caption = Text.MERCH_ITEM_CAPTION.format(
        item_name=item.name,
        item_description=item.description,
        item_price=item.price,
        user_points=user.points
    )
    keyboard = inline.get_merch_store_keyboard(item, page, total_items)
    try:
        await callback.message.edit_media(
            media=types.InputMediaPhoto(media=item.photo_file_id, caption=caption, parse_mode="HTML"),
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
             await callback.answer()
             return
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=item.photo_file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("buy_merch_"))
async def confirm_purchase(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    item = await merch_requests.get_merch_item_by_id(session, item_id)
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not item:
        await callback.answer(Text.MERCH_ITEM_NOT_FOUND, show_alert=True)
        return
    if user.points < item.price:
        await callback.answer(Text.MERCH_PURCHASE_INSUFFICIENT_FUNDS.format(price=item.price, points=user.points), show_alert=True)
        return
    text = Text.MERCH_PURCHASE_CONFIRMATION.format(
        item_name=item.name,
        item_price=item.price,
        new_balance=user.points - item.price
    )
    await callback.message.edit_caption(
        caption=text,
        reply_markup=inline.get_purchase_confirmation_keyboard(item_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_buy_"))
async def process_purchase(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    item = await merch_requests.get_merch_item_by_id(session, item_id)
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    success, message = await merch_requests.create_merch_order(session, user, item)
    if success:
        await session.commit() 
        await callback.message.edit_caption(
            caption=Text.MERCH_PURCHASE_SUCCESS.format(message=message),
            reply_markup=inline.get_back_to_merch_keyboard()
        )
    else:
        await session.rollback() 
        await callback.answer(Text.MERCH_PURCHASE_ERROR.format(message=message), show_alert=True)
    await callback.answer()

@router.callback_query(F.data == "my_orders")
async def show_my_orders(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    user = await user_requests.get_user_by_tg_id(session, user_id)
    orders = await merch_requests.get_user_orders(session, user.id)
    if not orders:
        text = Text.MERCH_NO_ORDERS
    else:
        text = Text.MERCH_ORDERS_HEADER
        for order in orders:
            text += Text.MERCH_ORDER_ITEM.format(
                item_name=Text.escape_html(order.item.name),
                date=order.order_date.strftime('%d.%m.%Y'),
                status=Text.escape_html(Text.MERCH_STATUS_MAP.get(order.status, 'Неизвестен'))
            )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=inline.get_back_to_merch_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        await callback.answer(Text.MERCH_UPDATE_ERROR, show_alert=True)
    await callback.answer()


# --- ⚕️ МОИ МЕДОТВОДЫ ---

async def send_waivers_menu(message_to_answer: types.Message, user_tg_id: int, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, user_tg_id)
    
    if not user:
        await message_to_answer.answer(Text.ERROR_PROFILE_NOT_FOUND)
        return

    all_waivers = await user_requests.get_user_active_waivers(session, user.id)
    
    user_created_waivers = [w for w in all_waivers if w.created_by == 'user']
    system_waivers = [w for w in all_waivers if w.created_by != 'user']

    text_parts = [Text.WAIVERS_MENU_HEADER]

    if not all_waivers:
        text_parts.append(Text.NO_ACTIVE_WAIVERS)
    else:
        if system_waivers:
            text_parts.append(Text.SYSTEM_WAIVERS_HEADER)
            for waiver in system_waivers:
                text_parts.append(Text.WAIVER_ITEM_FORMAT.format(
                    end_date=waiver.end_date.strftime('%d.%m.%Y'),
                    reason=Text.escape_html(waiver.reason)
                ))
        
        if user_created_waivers:
            text_parts.append(Text.USER_WAIVERS_HEADER)
            for waiver in user_created_waivers:
                text_parts.append(Text.WAIVER_ITEM_FORMAT.format(
                    end_date=waiver.end_date.strftime('%d.%m.%Y'),
                    reason=Text.escape_html(waiver.reason)
                ))

    text = "\n".join(text_parts)
    keyboard = inline.get_my_waivers_keyboard(user_waivers_exist=bool(user_created_waivers))

    await message_to_answer.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "my_waivers")
async def show_my_waivers(callback: types.CallbackQuery, session: AsyncSession):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        logger.warning("Could not delete message in show_my_waivers, it might have been deleted already.")
    
    await send_waivers_menu(callback.message, callback.from_user.id, session)
    await callback.answer()


@router.callback_query(F.data == "set_user_waiver")
async def set_user_waiver_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserWaiver.awaiting_end_date)
    await callback.message.edit_text(Text.WAIVER_SET_PROMPT, parse_mode="HTML")
    await callback.answer()

@router.message(UserWaiver.awaiting_end_date)
async def process_user_waiver_date(message: types.Message, state: FSMContext):
    try:
        end_date = datetime.datetime.strptime(message.text, "%d.%m.%Y").date()
        if end_date <= datetime.date.today():
            await message.answer(Text.WAIVER_DATE_IN_PAST_ERROR)
            return
            
        await state.update_data(end_date=end_date)
        await state.set_state(UserWaiver.awaiting_reason)
        await message.answer(Text.WAIVER_REASON_PROMPT)
    except ValueError:
        await message.answer(Text.DATE_FORMAT_ERROR, parse_mode="HTML")

@router.message(UserWaiver.awaiting_reason)
async def process_user_waiver_reason(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    end_date = data['end_date']
    reason = message.text

    user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    await user_requests.add_user_waiver(session, user.id, end_date, reason)
    
    await state.clear()
    
    await message.answer(Text.WAIVER_SET_SUCCESS.format(end_date=end_date.strftime('%d.%m.%Y')))
    
    await send_waivers_menu(message, message.from_user.id, session)

@router.callback_query(F.data == "cancel_user_waiver")
async def cancel_user_waiver_start(callback: types.CallbackQuery, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    all_waivers = await user_requests.get_user_active_waivers(session, user.id)
    user_created_waivers = [w for w in all_waivers if w.created_by == 'user']
    
    if not user_created_waivers:
        await callback.answer(Text.WAIVER_NOTHING_TO_CANCEL, show_alert=True)
        return

    await callback.message.edit_text(
        Text.WAIVER_CANCELLATION_PROMPT,
        reply_markup=inline.get_waiver_cancellation_keyboard(user_created_waivers)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("delete_waiver_"))
async def process_waiver_deletion(callback: types.CallbackQuery, session: AsyncSession):
    waiver_id = int(callback.data.split('_')[-1])
    
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not user:
        await callback.answer(Text.ERROR_PROFILE_NOT_FOUND, show_alert=True)
        return

    user_internal_id = user.id
    success = await user_requests.delete_user_waiver(session, waiver_id, user_internal_id)
    
    if success:
        await callback.answer(Text.WAIVER_CANCEL_SUCCESS, show_alert=True)
    else:
        await callback.answer(Text.WAIVER_CANCEL_FAIL, show_alert=True)
    
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        logger.warning("Could not delete message in process_waiver_deletion.")

    await send_waivers_menu(callback.message, callback.from_user.id, session)


# --- ℹ️ ПОЛЕЗНАЯ ИНФОРМАЦИЯ ---

@router.callback_query(F.data == "info")
async def show_info_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=Text.INFO_MENU_HEADER,
        reply_markup=inline.get_info_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("info_"))
async def show_info_text(callback: types.CallbackQuery, session: AsyncSession):
    section = callback.data.split('_', 1)[1]
    text_to_show = await info_requests.get_info_text(session, section)

    await callback.message.edit_text(text_to_show, reply_markup=inline.get_back_to_info_menu_keyboard(), parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

# --- 🔲 МОЙ QR-КОД ---

@router.callback_query(F.data == "my_qr_code")
async def send_qr_code(callback: types.CallbackQuery):
    await callback.answer(Text.QR_GENERATING)
    qr_data = {"user_id": callback.from_user.id} 
    qr_image_bytes = await generate_qr(qr_data)
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(qr_image_bytes, filename="my_qr.png"),
        caption=Text.QR_GENERAL_CAPTION
    )

@router.callback_query(F.data.startswith("get_event_qr_"))
async def send_event_qr_code(callback: types.CallbackQuery):
    event_id = int(callback.data.split('_')[-1])
    user_id = callback.from_user.id
    qr_data = {
        "user_id": user_id,
        "event_id": event_id
    }
    await callback.answer(Text.QR_GENERATING)
    qr_image_bytes = await generate_qr(qr_data)
    await callback.message.answer_photo(
        photo=types.BufferedInputFile(qr_image_bytes, filename="event_qr.png"),
        caption=Text.QR_EVENT_CAPTION
    )

# --- НОВЫЙ ХЕНДЛЕР: Добавление в календарь ---
@router.callback_query(F.data.startswith("add_to_calendar_"))
async def send_calendar_file(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    event = await event_requests.get_event_by_id(session, event_id)
    if not event:
        await callback.answer("Мероприятие не найдено.", show_alert=True)
        return

    ics_content = generate_ics_file(event)
    file_to_send = BufferedInputFile(
        file=ics_content.encode('utf-8'),
        filename=f"event_{event.id}.ics"
    )
    
    await callback.message.answer_document(
        document=file_to_send,
        caption=f"🗓️ Календарный файл для мероприятия «{event.name}».\nОткройте его, чтобы добавить событие в ваш календарь."
    )
    await callback.answer()

# --- FSM ДЛЯ ОБРАТНОЙ СВЯЗИ ---

feedback_router = Router()

@feedback_router.callback_query(FeedbackSurvey.awaiting_well_being, F.data.startswith("fb_wb_"))
async def process_well_being(callback: types.CallbackQuery, state: FSMContext):
    score = int(callback.data.split('_')[-1])
    await state.update_data(well_being_score=score)
    
    if score <= 3: 
        await callback.message.edit_text(Text.FEEDBACK_WELL_BEING_BAD)
        await state.set_state(FeedbackSurvey.awaiting_well_being_comment)
    else:
        await callback.message.edit_text(Text.FEEDBACK_GET_ORGANIZATION_SCORE, reply_markup=inline.get_feedback_organization_keyboard())
        await state.set_state(FeedbackSurvey.awaiting_organization_score)
    await callback.answer()

@feedback_router.message(FeedbackSurvey.awaiting_well_being_comment)
async def process_well_being_comment(message: types.Message, state: FSMContext):
    await state.update_data(well_being_comment=message.text)
    await message.answer(Text.FEEDBACK_GET_ORGANIZATION_SCORE, reply_markup=inline.get_feedback_organization_keyboard())
    await state.set_state(FeedbackSurvey.awaiting_organization_score)

@feedback_router.callback_query(FeedbackSurvey.awaiting_organization_score, F.data.startswith("fb_org_"))
async def process_org_score(callback: types.CallbackQuery, state: FSMContext):
    score = int(callback.data.split('_')[-1])
    await state.update_data(organization_score=score)
    await callback.message.edit_text(Text.FEEDBACK_GET_WHAT_LIKED, reply_markup=inline.get_feedback_skip_keyboard())
    await state.set_state(FeedbackSurvey.awaiting_what_liked)
    await callback.answer()

async def skip_or_process_text(event: types.Message | types.CallbackQuery, state: FSMContext, field_name: str, next_state: State, next_text: str, next_keyboard=None):
    is_callback = hasattr(event, 'message')
    message_to_edit = event.message if is_callback else event
    
    if not is_callback: 
        await state.update_data(**{field_name: event.text})
        try:
            await event.delete()
        except TelegramBadRequest:
            pass
    else:
        await state.update_data(**{field_name: "Пропущено"})
        await event.answer()

    try:
        await message_to_edit.edit_text(next_text, reply_markup=next_keyboard)
    except TelegramBadRequest:
        await message_to_edit.delete()
        await message_to_edit.answer(next_text, reply_markup=next_keyboard)
        
    await state.set_state(next_state)

@feedback_router.message(FeedbackSurvey.awaiting_what_liked)
@feedback_router.callback_query(FeedbackSurvey.awaiting_what_liked, F.data == "fb_skip_step")
async def process_what_liked(event: types.Message | types.CallbackQuery, state: FSMContext):
    await skip_or_process_text(event, state, 'what_liked', FeedbackSurvey.awaiting_what_disliked, Text.FEEDBACK_GET_WHAT_DISLIKED, inline.get_feedback_skip_keyboard())

@feedback_router.message(FeedbackSurvey.awaiting_what_disliked)
@feedback_router.callback_query(FeedbackSurvey.awaiting_what_disliked, F.data == "fb_skip_step")
async def process_what_disliked(event: types.Message | types.CallbackQuery, state: FSMContext):
    await skip_or_process_text(event, state, 'what_disliked', FeedbackSurvey.awaiting_other_suggestions, Text.FEEDBACK_GET_OTHER_SUGGESTIONS, inline.get_feedback_skip_keyboard())

@feedback_router.message(FeedbackSurvey.awaiting_other_suggestions)
@feedback_router.callback_query(FeedbackSurvey.awaiting_other_suggestions, F.data == "fb_skip_step")
async def process_other_suggestions(event: types.Message | types.CallbackQuery, state: FSMContext, session: AsyncSession):
    is_callback = hasattr(event, 'message')
    message_to_use = event.message if is_callback else event
    data = await state.get_data()

    if not is_callback:
        final_suggestion = event.text
    else:  
        final_suggestion = "Пропущено"
        await event.answer()

    user = await user_requests.get_user_by_tg_id(session, event.from_user.id)
    
    feedback = Feedback(
        user_id=user.id,
        event_id=data.get('event_id'),
        well_being_score=data.get('well_being_score'),
        well_being_comment=data.get('well_being_comment'),
        organization_score=data.get('organization_score'),
        what_liked=data.get('what_liked'),
        what_disliked=data.get('what_disliked'),
        other_suggestions=final_suggestion
    )
    session.add(feedback)
    await session.commit()
    
    await state.clear()
    
    try:
        await message_to_use.edit_text(Text.FEEDBACK_FINISH)
    except TelegramBadRequest:
        await message_to_use.answer(Text.FEEDBACK_FINISH)
        
        
@router.callback_query(F.data == "ask_question")
async def start_asking_question(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AskQuestion.awaiting_question)
    await callback.message.edit_text("Напишите ваш вопрос, и организаторы скоро на него ответят.")
    await callback.answer()

@router.message(AskQuestion.awaiting_question)
async def process_question(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    await question_requests.create_question(session, user.id, message.text)
    await state.clear()
    await message.answer(
        "Спасибо! Ваш вопрос отправлен организаторам. Ответ придет сюда же, в этот чат.",
        reply_markup=inline.get_back_to_main_menu_keyboard()
    )
    
    
@router.callback_query(F.data.startswith("no_show_"))
async def process_no_show_reason(callback: types.CallbackQuery, session: AsyncSession):
    _, event_id_str, reason = callback.data.split("_")
    event_id = int(event_id_str)
    user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)

    report = NoShowReport(user_id=user.id, event_id=event_id, reason=reason)
    session.add(report)
    await session.commit()
    
    await callback.message.edit_text("Спасибо за ваш ответ! Это поможет нам в организации будущих мероприятий.")
    await callback.answer()