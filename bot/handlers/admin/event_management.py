import logging
import datetime
import asyncio
import io
import csv
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from bot.db import admin_requests, event_requests, user_requests
from bot.db.engine import async_session_maker
from bot.filters.role import RoleFilter
from bot.states.states import EventCreation, EventEditing, PostEventProcessing
from bot.keyboards import inline
from bot.db.models import Event, User
from bot.utils.text_messages import Text
from bot.db import analytics_requests


router = Router(name="admin_event_management")
logger = logging.getLogger(__name__)


# =============================================================================
# --- 🗓️ УПРАВЛЕНИЕ МЕРОПРИЯТИЯМИ ---
# =============================================================================

@router.callback_query(F.data == "admin_create_event", RoleFilter('admin'))
async def start_event_creation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(EventCreation.awaiting_name)
    await callback.message.edit_text(Text.EVENT_CREATE_STEP_1_NAME)
    await callback.answer()

@router.message(EventCreation.awaiting_name)
async def process_event_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(EventCreation.awaiting_datetime)
    await message.answer(Text.EVENT_CREATE_STEP_2_DATE, parse_mode="HTML")

@router.message(EventCreation.awaiting_datetime)
async def process_event_datetime(message: types.Message, state: FSMContext):
    try:
        event_dt = datetime.datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        await state.update_data(event_datetime=event_dt.isoformat())
        await state.set_state(EventCreation.awaiting_location_text)
        await message.answer(Text.EVENT_CREATE_STEP_3_LOCATION_TEXT)
    except ValueError:
        await message.answer(Text.DATE_FORMAT_ERROR, parse_mode="HTML")

@router.message(EventCreation.awaiting_location_text)
async def process_event_location_text(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text)
    await state.set_state(EventCreation.awaiting_location_point)
    await message.answer(Text.EVENT_CREATE_STEP_4_LOCATION_POINT)

@router.message(EventCreation.awaiting_location_point, F.location)
async def process_event_location_point(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.update_data(
        latitude=message.location.latitude,
        longitude=message.location.longitude
    )
    await state.set_state(EventCreation.awaiting_blood_center)

    blood_centers = await admin_requests.get_all_blood_centers(session)
    await message.answer(
        "Выберите центр крови или добавьте новый:",
        reply_markup=inline.get_blood_centers_keyboard(blood_centers)
    )


@router.callback_query(EventCreation.awaiting_blood_center, F.data.startswith("select_blood_center_"))
async def process_blood_center_selection(callback: types.CallbackQuery, state: FSMContext):
    blood_center_id = int(callback.data.split("_")[-1])
    await state.update_data(blood_center_id=blood_center_id)
    await state.set_state(EventCreation.awaiting_donation_type)
    await callback.message.edit_text(
        Text.EVENT_CREATE_STEP_5_TYPE,
        reply_markup=inline.get_donation_type_keyboard()
    )


@router.callback_query(EventCreation.awaiting_blood_center, F.data == "add_new_blood_center")
async def add_new_blood_center(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(EventCreation.awaiting_new_blood_center_name)
    await callback.message.edit_text("Введите название нового центра крови:")


@router.message(EventCreation.awaiting_new_blood_center_name)
async def process_new_blood_center_name(message: types.Message, state: FSMContext, session: AsyncSession):
    new_blood_center = await admin_requests.create_blood_center(session, message.text)
    await state.update_data(blood_center_id=new_blood_center.id)
    await state.set_state(EventCreation.awaiting_donation_type)
    await message.answer(
        Text.EVENT_CREATE_STEP_5_TYPE,
        reply_markup=inline.get_donation_type_keyboard()
    )

@router.callback_query(EventCreation.awaiting_donation_type, F.data.startswith("settype_"))
async def process_event_donation_type(callback: types.CallbackQuery, state: FSMContext):
    donation_type = callback.data.split('_', 1)[1]
    await state.update_data(donation_type=donation_type)
    await state.set_state(EventCreation.awaiting_points)
    await callback.message.edit_text(Text.EVENT_CREATE_STEP_6_POINTS.format(donation_type=donation_type))
    await callback.answer()

@router.message(EventCreation.awaiting_points)
async def process_event_points(message: types.Message, state: FSMContext):
    try:
        points = int(message.text)
        await state.update_data(points_per_donation=points)
        await state.set_state(EventCreation.awaiting_limit)
        await message.answer(Text.EVENT_CREATE_STEP_7_LIMIT)
    except ValueError:
        await message.answer(Text.EVENT_POINTS_NAN_ERROR)


@router.message(EventCreation.awaiting_limit)
async def process_event_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
        await state.update_data(participant_limit=limit)
        await state.set_state(EventCreation.awaiting_confirmation)
        
        event_data = await state.get_data()

        event_data = await state.get_data()

        blood_center = await admin_requests.get_blood_center_by_id(session, event_data['blood_center_id'])

        text = Text.EVENT_CREATE_CONFIRMATION.format(
            name=event_data['name'],
            datetime=datetime.datetime.fromisoformat(event_data['event_datetime']).strftime('%d.%m.%Y в %H:%M'),
            location=event_data['location'],
            blood_center_name=blood_center.name,
            location_set="Указана" if event_data.get('latitude') else "Не указана",
            type=event_data['donation_type'],
            points=event_data['points_per_donation'],
            limit=event_data['participant_limit']
        )
        
        await message.answer(text, reply_markup=inline.get_event_creation_confirmation_keyboard())
    except ValueError:
        await message.answer(Text.EVENT_LIMIT_NAN_ERROR)

@router.callback_query(EventCreation.awaiting_confirmation, F.data == "confirm_create_event")
async def confirm_event_creation_and_notify(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    await callback.message.edit_text(Text.EVENT_CREATING_IN_PROGRESS)
    
    event_data = await state.get_data()
    await state.clear()
    
    event_data['event_datetime'] = datetime.datetime.fromisoformat(event_data['event_datetime'])
    new_event = await admin_requests.create_event(session, event_data)
    await session.commit()
    
    await callback.message.answer(Text.EVENT_CREATE_SUCCESS, reply_markup=inline.get_back_to_admin_panel_keyboard())
    
    msg = await callback.message.answer(Text.MAILING_STARTED_NOTIFICATION)
    
    asyncio.create_task(send_new_event_notifications(new_event, bot, msg))
    
    await callback.answer()

async def _send_notification_safe(bot: Bot, user: User, text: str, **kwargs):
    """Безопасно отправляет сообщение одному пользователю, ловит ошибки."""
    try:
        await bot.send_message(chat_id=user.telegram_id, text=text, **kwargs)
        return True
    except TelegramForbiddenError:
        logger.warning(f"Failed to send notification to user {user.id}. Bot was blocked.")
    except TelegramBadRequest as e:
        if "chat not found" in str(e):
            logger.warning(f"Failed to send notification to user {user.id}. Chat not found.")
        else:
            logger.error(f"Failed to send new event notification to user {user.id}. Error: {e}")
    except Exception as e:
        logger.error(f"Failed to send new event notification to user {user.id}. Unexpected error: {e}")
    return False

async def send_new_event_notifications(event: Event, bot: Bot, status_message: types.Message):
    """
    Выполняет рассылку о новом мероприятии пользователям, используя asyncio.gather для параллелизма.
    """
    async with async_session_maker() as session:
        try:
            users_to_notify = await user_requests.get_users_for_event_notification(session, event)
            total_users = len(users_to_notify)
            logger.info(f"Starting mailing for event '{event.name}'. Found {total_users} users.")

            if total_users == 0:
                await status_message.edit_text("✅ Рассылка завершена. Подходящих пользователей для уведомления не найдено.")
                return

            tasks = []
            for user in users_to_notify:
                location_link = Text.format_location_link(event.location, event.latitude, event.longitude)
                safe_event_name = Text.escape_html(event.name)
                
                text = Text.NEW_EVENT_NOTIFICATION.format(
                    event_name=safe_event_name,
                    event_date=event.event_datetime.strftime('%d.%m.%Y'),
                    event_time=event.event_datetime.strftime('%H:%M'),
                    event_location=location_link 
                )
                tasks.append(
                    _send_notification_safe(
                        bot,
                        user, # Передаем весь объект user
                        text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                )
            
            # Запускаем все задачи параллельно
            results = await asyncio.gather(*tasks)
            
            success_count = sum(1 for r in results if r)
            fail_count = total_users - success_count
            
            await status_message.edit_text(Text.MAILING_FINISHED_NOTIFICATION.format(success=success_count, fail=fail_count))
        except Exception as e:
            logger.error(f"Critical error during new event mailing for event {event.id}: {e}", exc_info=True)
            await status_message.edit_text(Text.MAILING_ERROR)


@router.callback_query(F.data == "admin_view_events", RoleFilter('admin'))
async def view_active_events(callback: types.CallbackQuery, session: AsyncSession):
    events = await event_requests.get_active_events(session)
    if not events:
        await callback.message.edit_text(Text.ADMIN_NO_ACTIVE_EVENTS, reply_markup=inline.get_events_management_keyboard())
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for event in events:
        prefix = "✅" if event.registration_is_open else "🔒"
        builder.row(types.InlineKeyboardButton(
            text=f"{prefix} {event.event_datetime.strftime('%d.%m')} - {event.name}", 
            callback_data=f"admin_show_event_{event.id}"
        ))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_manage_events"))
    
    await callback.message.edit_text(Text.ADMIN_CHOOSE_EVENT_TO_MANAGE, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("admin_show_event_"), RoleFilter('admin'))
async def show_single_event_card(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    event = await event_requests.get_event_by_id(session, event_id)
    if not event:
        await callback.answer(Text.EVENT_NOT_FOUND, show_alert=True)
        return
    
    reg_count = await admin_requests.get_event_registrations_count(session, event_id)
    donation_type_ru = Text.DONATION_TYPE_RU.get(event.donation_type, event.donation_type)
    
    feedback_count = await session.scalar(select(func.count(admin_requests.Feedback.id)).where(admin_requests.Feedback.event_id == event_id))
        
    text = Text.EVENT_CARD_TEMPLATE.format(
        name=hbold(event.name),
        date_header=hbold('Дата:'),
        datetime=event.event_datetime.strftime('%d.%m.%Y в %H:%M'),
        location_header=hbold('Место:'),
        location=Text.escape_html(event.location),
        blood_center_name=event.blood_center.name if event.blood_center else "Не указан",
        type_header=hbold('Тип донации:'),
        donation_type=donation_type_ru,
        points_header=hbold('Баллы:'),
        points_per_donation=event.points_per_donation,
        limit_header=hbold('Записано/Лимит:'),
        reg_count=reg_count,
        participant_limit=event.participant_limit,
        status_header=hbold('Статус:'),
        is_active='Активно' if event.is_active else 'Архивировано',
        reg_status_header=hbold('Регистрация:'),
        reg_is_open='Открыта' if event.registration_is_open else 'Закрыта'
    )

    await callback.message.edit_text(
        text, 
        reply_markup=inline.get_single_event_management_keyboard(event.id, event.registration_is_open, has_feedback=(feedback_count > 0)), 
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_toggle_reg_"), RoleFilter('admin'))
async def toggle_event_registration(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    new_status = await admin_requests.toggle_event_registration_status(session, event_id)
    await session.commit()
    alert_text = Text.EVENT_TOGGLE_REG_OPEN if new_status else Text.EVENT_TOGGLE_REG_CLOSED
    await callback.answer(alert_text, show_alert=True)
    await show_single_event_card(callback, session)

@router.callback_query(F.data.startswith("admin_edit_event_"), RoleFilter('admin'))
async def start_event_editing(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    event_id = int(callback.data.split('_')[-1])
    event = await event_requests.get_event_by_id(session, event_id)
    if not event: return
    
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditing.choosing_field)
    
    fields = {"name": "Название", "event_date": "Дата", "location": "Место", "blood_center_id": "Центр крови", "points_per_donation": "Баллы", "participant_limit": "Лимит"}
    builder = InlineKeyboardBuilder()
    for key, name in fields.items():
        builder.row(types.InlineKeyboardButton(text=f"Изменить: {name}", callback_data=f"edit_field_{key}"))
    builder.row(types.InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_show_event_{event_id}"))
    
    await callback.message.edit_text(Text.EVENT_EDIT_PROMPT.format(event_name=event.name), reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(EventEditing.choosing_field, F.data.startswith("edit_field_"))
async def choose_field_to_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    field_to_edit = callback.data.split('_', 2)[-1]
    await state.update_data(field_to_edit=field_to_edit)

    if field_to_edit == "blood_center_id":
        await state.set_state(EventEditing.awaiting_new_value)
        blood_centers = await admin_requests.get_all_blood_centers(session)
        await callback.message.edit_text(
            "Выберите новый центр крови:",
            reply_markup=inline.get_blood_centers_keyboard(blood_centers)
        )
    else:
        await state.set_state(EventEditing.awaiting_new_value)
        prompt = Text.EVENT_EDIT_FIELD_PROMPTS.get(field_to_edit, "Введите новое значение:")
        await callback.message.edit_text(prompt)

    await callback.answer()

@router.message(EventEditing.awaiting_new_value, F.text)
async def process_new_value_for_event(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    field, event_id, new_value_str = data.get("field_to_edit"), data.get("event_id"), message.text
    
    try:
        if field == "event_date": update_value = datetime.datetime.strptime(new_value_str, "%d.%m.%Y %H:%M")
        elif field in ["points_per_donation", "participant_limit"]: update_value = int(new_value_str)
        else: update_value = new_value_str
    except ValueError:
        await message.answer(Text.EVENT_EDIT_INVALID_FORMAT)
        return
        
    await admin_requests.update_event_field(session, event_id, field, update_value)
    await session.commit()
    await state.clear()
    await message.answer(Text.EVENT_EDIT_SUCCESS, reply_markup=inline.get_back_to_admin_panel_keyboard())

@router.callback_query(EventEditing.awaiting_new_value, F.data.startswith("select_blood_center_"))
async def process_new_blood_center_for_event(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    event_id = data.get("event_id")
    new_blood_center_id = int(callback.data.split("_")[-1])

    await admin_requests.update_event_field(session, event_id, "blood_center_id", new_blood_center_id)
    await session.commit()
    await state.clear()
    await callback.message.edit_text(Text.EVENT_EDIT_SUCCESS, reply_markup=inline.get_back_to_admin_panel_keyboard())

@router.callback_query(F.data.startswith("admin_event_participants_"), RoleFilter('admin'))
async def get_event_participants(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    event, participants_regs = await admin_requests.get_event_with_participants(session, event_id)
    if not event: return await callback.answer(Text.EVENT_NOT_FOUND, show_alert=True)
    if not participants_regs: return await callback.answer(Text.EVENT_NO_PARTICIPANTS.format(event_name=event.name), show_alert=True)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['ID', 'ФИО', 'Телефон', 'Факультет', 'Группа', 'Статус'])
    for reg in participants_regs:
        writer.writerow([reg.user.id, reg.user.full_name, reg.user.phone_number, reg.user.faculty, reg.user.study_group, reg.status])
    
    output.seek(0)
    file = types.BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename=f"participants_{event.id}.csv")
    await callback.message.answer_document(file, caption=Text.EVENT_PARTICIPANTS_CAPTION.format(event_name=event.name))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_cancel_event_"), RoleFilter('admin'))
async def ask_for_cancellation_confirmation(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    event = await event_requests.get_event_by_id(session, event_id)
    if not event: return await callback.answer(Text.EVENT_NOT_FOUND, show_alert=True)
    reg_count = await admin_requests.get_event_registrations_count(session, event_id)
    await callback.message.edit_text(
        Text.EVENT_CANCEL_CONFIRMATION.format(event_name=event.name, reg_count=reg_count),
        reply_markup=inline.get_event_cancellation_confirmation_keyboard(event_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_confirm_cancel_"), RoleFilter('admin'))
async def confirm_and_cancel_event(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    await callback.message.edit_text(Text.EVENT_CANCELLING_IN_PROGRESS)
    event_id = int(callback.data.split('_')[-1])
    event, participants_regs = await admin_requests.get_event_with_participants(session, event_id)
    if not event: return

    success_count, fail_count = 0, 0
    for reg in participants_regs:
        try:
            safe_event_name = Text.escape_html(event.name)
            safe_datetime = Text.escape_html(event.event_datetime.strftime('%d.%m.%Y в %H:%M'))
            text = Text.EVENT_CANCEL_NOTIFICATION_TEXT.format(
                event_name=safe_event_name,
                datetime=safe_datetime
            )
            await bot.send_message(chat_id=reg.user.telegram_id, text=text, parse_mode="HTML")
            success_count += 1
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send cancellation to user {reg.user_id} for event {event.id}. Error: {e}")
        await asyncio.sleep(0.1)

    await admin_requests.deactivate_event(session, event_id)
    await session.commit()
    await callback.message.edit_text(
        Text.EVENT_CANCEL_SUCCESS_REPORT.format(event_name=event.name, success=success_count, fail=fail_count),
        reply_markup=inline.get_back_to_events_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("admin_view_feedback_"), RoleFilter('admin'))
async def view_event_feedback(callback: types.CallbackQuery, session: AsyncSession):
    event_id = int(callback.data.split('_')[-1])
    event = await event_requests.get_event_by_id(session, event_id)
    feedbacks = await admin_requests.get_feedback_for_event(session, event_id)

    if not feedbacks:
        await callback.answer(Text.FEEDBACK_ADMIN_NO_FEEDBACK, show_alert=True)
        return

    report = Text.FEEDBACK_ADMIN_HEADER.format(event_name=Text.escape_html(event.name))
    for fb in feedbacks:
        report += Text.FEEDBACK_ADMIN_ITEM.format(
            user_name=Text.escape_html(fb.user.full_name),
            wb_score=fb.well_being_score or "-",
            wb_comment=Text.escape_html(fb.well_being_comment or "-"),
            org_score=fb.organization_score or "-",
            liked=Text.escape_html(fb.what_liked or "-"),
            disliked=Text.escape_html(fb.what_disliked or "-"),
            suggestions=Text.escape_html(fb.other_suggestions or "-")
        )
    
    try:
        await callback.message.delete()
    except Exception:
        logger.warning("Could not delete message in view_event_feedback")

    if len(report) > 4000: # Telegram message limit
        await callback.message.answer("Отзывов слишком много, отправляю файлом.")
        file = types.BufferedInputFile(report.encode('utf-8'), filename=f"feedback_{event_id}.txt")
        await callback.message.answer_document(file)
    else:
        try:
            await callback.message.answer(
                report,
                reply_markup=inline.get_back_to_events_menu_keyboard(),
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            await callback.message.delete()
            await callback.message.answer(
                report,
                reply_markup=inline.get_back_to_events_menu_keyboard(),
                parse_mode="HTML"
            )
    
    await callback.answer()
    
    
    
@router.callback_query(F.data == "admin_post_process_dd", RoleFilter('admin'))
async def start_post_processing(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Начало FSM: Выбор прошедшего мероприятия."""
    await state.clear()
    past_events = await analytics_requests.get_past_events_for_analysis(session)
    if not past_events:
        await callback.answer("Нет прошедших мероприятий для обработки.", show_alert=True)
        return

    await state.set_state(PostEventProcessing.choosing_event)
    await callback.message.edit_text(
        "Выберите мероприятие, для которого хотите внести данные:",
        reply_markup=inline.get_events_for_post_processing_keyboard(past_events)
    )
    await callback.answer()

async def show_participant_marking_menu(message: types.Message, state: FSMContext, session: AsyncSession):
    """Вспомогательная функция для отображения и обновления меню отметки."""
    data = await state.get_data()
    event_id = data.get("event_id")
    marked_donations = data.get("marked_donations", set())
    marked_dkm = data.get("marked_dkm", set())

    _, participants = await admin_requests.get_event_with_participants(session, event_id)
    if not participants:
        await message.edit_text("На это мероприятие не было зарегистрировано участников.", reply_markup=inline.get_back_to_events_menu_keyboard())
        await state.clear()
        return

    await message.edit_text(
        "Отметьте, кто сдал кровь и/или вступил в регистр ДКМ.\n(🟢 - отмечено, ⚪️ - нет)",
        reply_markup=inline.get_participant_marking_keyboard(event_id, participants, marked_donations, marked_dkm)
    )

@router.callback_query(PostEventProcessing.choosing_event, F.data.startswith("post_process_event_"))
async def choose_event_for_processing(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Шаг 2: Мероприятие выбрано, показываем список участников."""
    event_id = int(callback.data.split("_")[-1])
    await state.update_data(event_id=event_id, marked_donations=set(), marked_dkm=set())
    await state.set_state(PostEventProcessing.marking_participants)
    await show_participant_marking_menu(callback.message, state, session)
    await callback.answer()
    
@router.callback_query(PostEventProcessing.marking_participants, F.data.startswith("mark_participant_"))
async def mark_participant(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Обработка нажатия на кнопку отметки (toggle)."""
    _, _, event_id_str, user_id_str, action = callback.data.split("_")
    user_id = int(user_id_str)

    data = await state.get_data()
    target_set_name = "marked_donations" if action == "donation" else "marked_dkm"
    target_set = data.get(target_set_name, set())

    if user_id in target_set:
        target_set.remove(user_id)
    else:
        target_set.add(user_id)
    
    await state.update_data(**{target_set_name: target_set})
    
    # Обновляем клавиатуру, чтобы показать изменение
    await show_participant_marking_menu(callback.message, state, session)
    await callback.answer()

@router.callback_query(PostEventProcessing.marking_participants, F.data.startswith("finish_marking_"))
async def finish_marking(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Завершение процесса: сохраняем все отметки в БД."""
    data = await state.get_data()
    event_id = data.get("event_id")
    marked_donations = data.get("marked_donations", set())
    marked_dkm = data.get("marked_dkm", set())
    await state.clear()

    if not marked_donations:
        await callback.answer("Ни один участник не отмечен как сдавший кровь.", show_alert=True)
        return
        
    await callback.message.edit_text("⏳ Сохраняю данные... Это может занять некоторое время.")

    report_lines = []
    for user_id in marked_donations:
        is_dkm = user_id in marked_dkm
        success, message = await admin_requests.manually_confirm_donation(session, user_id, event_id, is_dkm)
        report_lines.append(message)
    
    await session.commit()
    
    final_report = "✅ <b>Обработка завершена.</b>\n\n<b>Результаты:</b>\n" + "\n".join(report_lines)
    await callback.message.edit_text(final_report, reply_markup=inline.get_back_to_events_menu_keyboard())
    await callback.answer("Данные сохранены!", show_alert=True)