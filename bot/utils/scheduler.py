import logging
import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload
from bot.db.models import EventRegistration, MedicalWaiver, Event, User, Donation, NoShowReport
from bot.utils.text_messages import Text
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from bot.states.states import FeedbackSurvey
from bot.keyboards import inline


logger = logging.getLogger(__name__)

async def send_reminders_for_interval(
    bot: Bot, 
    session_pool: async_sessionmaker, 
    time_from_now: datetime.timedelta, 
    time_window: datetime.timedelta,
    text_template: str
):
    now = datetime.datetime.now()
    start_time = now + time_from_now
    end_time = start_time + time_window

    logger.info(f"Running reminder job. Checking for events between {start_time.strftime('%Y-%m-%d %H:%M')} and {end_time.strftime('%Y-%m-%d %H:%M')}")
    
    async with session_pool() as session:
        stmt = (
            select(EventRegistration)
            .join(Event, EventRegistration.event_id == Event.id)
            .where(
                and_(
                    Event.event_datetime >= start_time,
                    Event.event_datetime < end_time,
                    EventRegistration.status == 'registered',
                    Event.is_active == True
                )
            )
            .options(
                joinedload(EventRegistration.user),
                joinedload(EventRegistration.event)
            )
        )
        
        results = await session.execute(stmt)
        registrations = results.scalars().unique().all()
        
        if not registrations:
            logger.info("No registrations found for this time window.")
            return
            
        logger.info(f"Found {len(registrations)} registrations to notify.")
        success_count = 0
        for reg in registrations:
            try:
                user = reg.user
                event = reg.event
                
                if not user or not event:
                    continue

                formatted_datetime = event.event_datetime.strftime('%d.%m.%Y %H:%M')
                
                safe_event_name = Text.escape_html(event.name)
                safe_datetime = Text.escape_html(formatted_datetime)
                location_link = Text.format_location_link(event.location, event.latitude, event.longitude)
                
                text = text_template.format(
                    event_name=safe_event_name,
                    event_datetime=safe_datetime,
                    event_location=location_link
                )

                await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="HTML")
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to user {reg.user_id} for event {reg.event_id}. Error: {e}", exc_info=True)
        
        logger.info(f"Job finished. Sent {success_count}/{len(registrations)} reminders.")

async def send_post_donation_feedback(bot: Bot, session_pool: async_sessionmaker, storage: MemoryStorage):
    """Инициирует опрос обратной связи через день после донации."""
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    logger.info(f"Running post-donation feedback job for donations made on {yesterday}.")

    async with session_pool() as session:
        stmt = (
            select(Donation)
            .options(joinedload(Donation.user))
            .where(
                Donation.donation_date == yesterday,
                Donation.feedback_requested == False
            )
        )
        results = await session.execute(stmt)
        donations_to_process = results.scalars().all()

        if not donations_to_process:
            logger.info("No donations found for feedback request.")
            return

        logger.info(f"Found {len(donations_to_process)} donations for feedback request.")
        success_count = 0
        for donation in donations_to_process:
            try:
                user = donation.user
                if not user:
                    continue
                
                storage_key = StorageKey(bot_id=bot.id, chat_id=user.telegram_id, user_id=user.telegram_id)
                state = FSMContext(storage=storage, key=storage_key)               
                
                await state.set_state(FeedbackSurvey.awaiting_well_being)
                await state.update_data(
                    event_id=donation.event_id,
                    donation_id=donation.id
                )
                
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=Text.FEEDBACK_START,
                    reply_markup=inline.get_feedback_well_being_keyboard()
                )
                
                donation.feedback_requested = True
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to initiate feedback survey for user {donation.user_id}. Error: {e}", exc_info=True)
        
        if success_count > 0:
            await session.commit()
        
        logger.info(f"Post-donation feedback job finished. Initiated {success_count}/{len(donations_to_process)} surveys.")


async def check_waiver_expirations(bot: Bot, session_pool: async_sessionmaker):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    async with session_pool() as session:
        stmt = (
            select(MedicalWaiver.user_id)
            .where(MedicalWaiver.end_date == yesterday)
        )
        results = await session.execute(stmt)
        user_ids_to_notify = results.scalars().unique().all()
        if not user_ids_to_notify:
            return
        users_stmt = select(User).where(User.id.in_(user_ids_to_notify))
        users_result = await session.execute(users_stmt)
        users = users_result.scalars().all()
        for user in users:
            try:
                await bot.send_message(chat_id=user.telegram_id, text=Text.WAIVER_EXPIRED_NOTIFICATION)
            except Exception as e:
                logger.error(f"Failed to send waiver expiration notification to user {user.id}. Error: {e}")


async def check_student_status(bot: Bot, session_pool: async_sessionmaker):
    """Проверяет, не выпустился ли студент."""
    async with session_pool() as session:
        stmt = select(User).where(User.category == "student")
        results = await session.execute(stmt)
        students = results.scalars().all()

        for student in students:
            try:
                if student.study_group:
                    # Very simplified logic. A real implementation would be more complex.
                    study_group_year = int(student.study_group.split("-")[1][:2])
                    current_year = datetime.datetime.now().year % 100
                    if current_year - study_group_year > 4:
                        await bot.send_message(
                            chat_id=student.telegram_id,
                            text="Привет! Похоже, ты уже выпустился из университета. Пожалуйста, обнови свои данные."
                        )
            except Exception as e:
                logger.error(f"Failed to check student status for user {student.id}. Error: {e}", exc_info=True)

def setup_scheduler(bot: Bot, session_pool: async_sessionmaker, storage: MemoryStorage) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    scheduler.add_job(
        send_no_show_surveys,
        trigger='cron',
        hour='*',
        minute=5, 
        args=[bot, session_pool]
    )

    scheduler.add_job(
        send_reminders_for_interval,
        trigger='cron',
        hour=10,
        minute=0,
        args=[bot, session_pool, datetime.timedelta(days=7), datetime.timedelta(days=1), Text.REMINDER_WEEK]
    )
    scheduler.add_job(
        send_reminders_for_interval,
        trigger='cron',
        hour=10,
        minute=30,
        args=[bot, session_pool, datetime.timedelta(days=3), datetime.timedelta(days=1), Text.REMINDER_3_DAYS]
    )
    scheduler.add_job(
        send_reminders_for_interval,
        trigger='cron',
        hour=10,
        minute=30,
        args=[bot, session_pool, datetime.timedelta(days=1), datetime.timedelta(days=1), Text.REMINDER_1_DAY]
    )
    scheduler.add_job(
        send_reminders_for_interval,
        trigger='cron',
        hour='*',
        minute=0,
        args=[bot, session_pool, datetime.timedelta(hours=2), datetime.timedelta(hours=1), Text.REMINDER_2_HOURS]
    )
    scheduler.add_job(
        check_waiver_expirations,
        trigger='cron',
        hour=9,
        minute=0,
        args=[bot, session_pool]
    )
    
    scheduler.add_job(
        send_post_donation_feedback,
        trigger='cron',
        hour=11,
        minute=0,
        args=[bot, session_pool, storage]
    )
    
    scheduler.add_job(
        check_student_status,
        trigger='cron',
        month=9,
        day=1,
        hour=12,
        minute=0,
        args=[bot, session_pool]
    )

    logger.info("Scheduler configured successfully with 6 jobs.")
    return scheduler

async def send_no_show_surveys(bot: Bot, session_pool: async_sessionmaker):
    """Находит неявившихся участников и отправляет им опрос."""
    now = datetime.datetime.now()
    # Ищем мероприятия, которые закончились 3-4 часа назад
    start_window = now - datetime.timedelta(hours=4)
    end_window = now - datetime.timedelta(hours=3)

    logger.info(f"Running no-show survey job for events ended between {start_window} and {end_window}")

    async with session_pool() as session:
        stmt = (
            select(EventRegistration)
            .join(Event)
            .where(
                Event.event_datetime.between(start_window, end_window),
                EventRegistration.status == 'registered'
            )
            .options(joinedload(EventRegistration.user), joinedload(EventRegistration.event))
        )
        results = await session.execute(stmt)
        no_shows = results.scalars().unique().all()
        
        if not no_shows:
            logger.info("No participants found for no-show survey.")
            return

        for reg in no_shows:
            try:
                builder = types.InlineKeyboardBuilder()
                reasons = {
                    "medical": "Медотвод (болезнь)",
                    "personal": "Личные причины",
                    "forgot": "Забыл(а) / не захотел(а)"
                }
                for key, text in reasons.items():
                    builder.row(types.InlineKeyboardButton(
                        text=text,
                        callback_data=f"no_show_{reg.event_id}_{key}"
                    ))
                
                await bot.send_message(
                    chat_id=reg.user.telegram_id,
                    text=(
                        f"Добрый день! Вы были записаны на донорскую акцию «{reg.event.name}», "
                        "но не отметились у волонтеров. Подскажите, пожалуйста, почему не получилось прийти?"
                    ),
                    reply_markup=builder.as_markup()
                )
                # Меняем статус, чтобы не отправлять повторно
                reg.status = 'no_show_survey_sent'
            except Exception as e:
                logger.error(f"Failed to send no-show survey to user {reg.user_id}: {e}")
        
        await session.commit()