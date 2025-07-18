import pytest
import datetime
from unittest.mock import AsyncMock, Mock
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.scheduler import send_reminders_for_interval, send_post_donation_feedback
from bot.db.models import User, Event, EventRegistration, Donation
from bot.states.states import FeedbackSurvey
from bot.utils.text_messages import Text
from bot.keyboards import inline

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize(
    "time_delta_to_event, check_interval, check_window, expected_text_template, should_be_called",
    [
        (datetime.timedelta(days=7), datetime.timedelta(days=7), datetime.timedelta(days=1), Text.REMINDER_WEEK, True),
        (datetime.timedelta(days=2), datetime.timedelta(days=2), datetime.timedelta(days=1), Text.REMINDER_2_DAYS, True),
        (datetime.timedelta(hours=2), datetime.timedelta(hours=2), datetime.timedelta(hours=1), Text.REMINDER_2_HOURS, True),
        (datetime.timedelta(days=3), datetime.timedelta(days=2), datetime.timedelta(days=1), None, False),
        (datetime.timedelta(days=8), datetime.timedelta(days=7), datetime.timedelta(days=1), None, False),
        (datetime.timedelta(hours=3), datetime.timedelta(hours=2), datetime.timedelta(hours=1), None, False),
        (datetime.timedelta(days=-1), datetime.timedelta(days=2), datetime.timedelta(days=1), None, False),
    ]
)
async def test_send_event_reminders_multi_interval(
    session: AsyncSession,
    session_pool,
    mocker,
    time_delta_to_event,
    check_interval,
    check_window,
    expected_text_template,
    should_be_called
):
    """
    Тестирует отправку напоминаний для разных временных интервалов.
    """
    fixed_now = datetime.datetime(2024, 1, 1, 12, 0, 0)
    mocker.patch('datetime.datetime', Mock(now=lambda: fixed_now))

    mock_send_message = mocker.patch('aiogram.Bot.send_message', new_callable=AsyncMock)
    mock_bot = Mock(spec=Bot)
    mock_bot.send_message = mock_send_message

    user = User(phone_number="+1", telegram_id=101, full_name="UserToRemind", university="TestUni")
    event_time = fixed_now + time_delta_to_event
    event = Event(name="Test-Event", event_datetime=event_time, location="Test Location", donation_type="plasma", points_per_donation=10, participant_limit=5, is_active=True)
    session.add_all([user, event])
    await session.commit()
    registration = EventRegistration(user_id=user.id, event_id=event.id)
    session.add(registration)
    await session.commit()

    await send_reminders_for_interval(
        bot=mock_bot,
        session_pool=session_pool,  
        time_from_now=check_interval,
        time_window=check_window,
        text_template=expected_text_template or "dummy"
    )
    
    if should_be_called:
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args.kwargs
        sent_text = call_args['text']
        
        assert call_args['parse_mode'] == "HTML"
        assert "<b>Напоминание" in sent_text or "<b>Донация уже скоро" in sent_text
        assert "Test-Event" in sent_text
        assert "Test Location" in sent_text
    else:
        mock_send_message.assert_not_called()

async def test_send_post_donation_feedback(session: AsyncSession, session_pool, mocker):
    """
    Тестирует отправку запроса на обратную связь на следующий день после донации.
    """
    # 1. Подготовка
    fixed_today = datetime.date(2024, 10, 27)
    fixed_yesterday = fixed_today - datetime.timedelta(days=1)
    fixed_day_before = fixed_today - datetime.timedelta(days=2)
    mocker.patch('datetime.date', Mock(today=lambda: fixed_today))

    mock_send_message = mocker.patch('aiogram.Bot.send_message', new_callable=AsyncMock)
    mock_bot = Mock(spec=Bot)
    mock_bot.send_message = mock_send_message

    user_to_notify = User(phone_number="+1", telegram_id=101, full_name="Feedback User", university="TestUni")
    user_to_ignore_old = User(phone_number="+2", telegram_id=102, full_name="Old Donor", university="TestUni")
    user_to_ignore_duplicate = User(phone_number="+3", telegram_id=103, full_name="Duplicate", university="TestUni")
    session.add_all([user_to_notify, user_to_ignore_old, user_to_ignore_duplicate])
    await session.commit()
    
    donation_to_notify = Donation(user_id=user_to_notify.id, event_id=1, donation_date=fixed_yesterday, donation_type="plasma", points_awarded=1)
    donation_to_ignore_old = Donation(user_id=user_to_ignore_old.id, event_id=2, donation_date=fixed_day_before, donation_type="plasma", points_awarded=1)
    donation_to_ignore_duplicate = Donation(user_id=user_to_ignore_duplicate.id, event_id=3, donation_date=fixed_yesterday, donation_type="plasma", points_awarded=1, feedback_requested=True)
    session.add_all([donation_to_notify, donation_to_ignore_old, donation_to_ignore_duplicate])
    await session.commit()

    # 2. Выполнение
    await send_post_donation_feedback(
        bot=mock_bot,
        session_pool=session_pool, 
        storage=MemoryStorage()
    )

    # 3. Проверка
    mock_send_message.assert_called_once_with(
        chat_id=user_to_notify.telegram_id,
        text=Text.FEEDBACK_START,
        reply_markup=inline.get_feedback_well_being_keyboard()
    )
    
    await session.refresh(donation_to_notify)
    await session.refresh(donation_to_ignore_old)
    await session.refresh(donation_to_ignore_duplicate)
    
    assert donation_to_notify.feedback_requested is True
    assert donation_to_ignore_old.feedback_requested is False
    assert donation_to_ignore_duplicate.feedback_requested is True