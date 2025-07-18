import pytest
from unittest.mock import AsyncMock, Mock
import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from bot.db.models import User, Event, MedicalWaiver, Feedback
from bot.states.states import Registration, EventCreation, PointsChange, FeedbackSurvey
from bot.handlers import common as common_handlers
from bot.handlers.admin import event_management
from bot.handlers.admin import user_management as user_management_handlers
from bot.handlers import student as student_handlers
from bot.keyboards import inline
from bot.utils.text_messages import Text

pytestmark = pytest.mark.asyncio

class MockMessage:
    """Полностью контролируемая заглушка для Message, не наследуется от Mock."""
    def __init__(self, text=None, from_user_id=123, from_user_username=None, location=None, contact=None):
        self.text = text
        self.from_user = Mock(id=from_user_id, username=from_user_username)
        self.location = location
        self.contact = contact
        self.message_id = 12345
        # Явно определяем все методы, которые могут быть вызваны
        self.answer = AsyncMock()
        self.edit_text = AsyncMock()
        self.delete = AsyncMock()
        self.answer_photo = AsyncMock()
        self.answer_document = AsyncMock()
        self.edit_reply_markup = AsyncMock()

class MockCallbackQuery:
    """Полностью контролируемая заглушка для CallbackQuery."""
    def __init__(self, data, from_user_id=123, from_user_username=None, message=None):
        self.data = data
        self.from_user = Mock(id=from_user_id, username=from_user_username)
        self.message = message if message else MockMessage(from_user_id=from_user_id)
        self.answer = AsyncMock()

class MockFSMContext:
    """Упрощенная заглушка для FSMContext, хранящая состояние в словаре"""
    def __init__(self):
        self._state = None
        self._data = {}
    async def get_state(self): return self._state
    async def set_state(self, state): self._state = state
    async def get_data(self): return self._data.copy()
    async def update_data(self, **kwargs): self._data.update(kwargs)
    async def clear(self):
        self._state = None
        self._data = {}

class MockLocation:
    """Упрощенная заглушка для объекта Location aiogram"""
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude



@pytest.mark.parametrize(
    "scenario, user_inputs, expected_fsm_data",
    [
        (
            "mifi_standard_faculty",
            [
                ("callback", "university_mifi"), 
                ("callback", "faculty_ИИКС"),
                ("message", "Б20-505"),
                ("callback", "bloodtype_A(II)"),
                ("callback", "rhfactor_+"),
                ("callback", "gender_male"),
            ],
            {"university": "НИЯУ МИФИ", "faculty": "ИИКС", "study_group": "Б20-505"}
        ),
        (
            "mifi_custom_faculty",
            [
                ("callback", "university_mifi"),
                ("callback", "faculty_Other"),
                ("message", "Институт ЛаПлаз"),
                ("message", "Л2-101"),
                ("callback", "bloodtype_O(I)"),
                ("callback", "rhfactor_-"),
                ("callback", "gender_female"),
            ],
            {"university": "НИЯУ МИФИ", "faculty": "Институт ЛаПлаз", "study_group": "Л2-101"}
        ),
        (
            "other_university",
            [
                ("callback", "university_other"),
                ("message", "МГУ"),
                ("message", "ВМК"),
                ("message", "231"),
                ("callback", "bloodtype_B(III)"),
                ("callback", "rhfactor_+"),
                ("callback", "gender_male"),
            ],
            {"university": "МГУ", "faculty": "ВМК", "study_group": "231"}
        )
    ]
)
async def test_registration_fsm_scenarios(scenario, user_inputs, expected_fsm_data, session: AsyncSession):
    """
    Тестирует различные сценарии прохождения регистрации FSM.
    """
    state = MockFSMContext()
    
    contact_mock = Mock(phone_number="+71234567890")
    start_message = MockMessage(contact=contact_mock, from_user_id=123, from_user_username="test_user_fsm")
    await common_handlers.handle_contact(start_message, session, state)
    assert await state.get_state() == Registration.awaiting_full_name
    
    fio_message = MockMessage("Тестовый Тест Тестович")
    await common_handlers.process_full_name(fio_message, state)
    assert await state.get_state() == Registration.awaiting_university
    
    for input_type, value in user_inputs:
        if input_type == "callback":
            callback = MockCallbackQuery(data=value)
            current_state = await state.get_state()
            if current_state == Registration.awaiting_university:
                await common_handlers.process_university_choice(callback, state)
            elif current_state == Registration.awaiting_faculty:
                await common_handlers.process_faculty(callback, state)
            elif current_state == Registration.awaiting_blood_type:
                await common_handlers.process_blood_type(callback, state)
            elif current_state == Registration.awaiting_rh_factor:
                await common_handlers.process_rh_factor(callback, state)
            elif current_state == Registration.awaiting_gender:
                await common_handlers.process_gender(callback, state, session)
        
        elif input_type == "message":
            message = MockMessage(text=value)
            current_state = await state.get_state()
            if current_state == Registration.awaiting_custom_university_name:
                await common_handlers.process_custom_university_name(message, state)
            elif current_state == Registration.awaiting_custom_faculty_name:
                await common_handlers.process_custom_faculty_name(message, state)
            elif current_state == Registration.awaiting_study_group:
                await common_handlers.process_study_group(message, state)
                
    assert await state.get_state() is None 
    
    created_user = await session.get(User, 1) 
    assert created_user is not None
    assert created_user.university == expected_fsm_data["university"]
    assert created_user.faculty == expected_fsm_data["faculty"]
    assert created_user.study_group == expected_fsm_data["study_group"]
    assert created_user.full_name == "Тестовый Тест Тестович"
    assert created_user.telegram_username == "test_user_fsm"


async def test_add_points_to_user(session: AsyncSession, mocker):
    """
    Тестирует логику добавления баллов администратором, включая уведомление.
    """
    mock_bot = Mock()
    mock_bot.send_message = AsyncMock()
    
    user = User(phone_number="+1", telegram_id=101, full_name="User For Points", points=100, university="TestUni")
    session.add(user)
    await session.commit()
    
    state = MockFSMContext()
    await state.set_state(PointsChange.awaiting_reason)
    await state.update_data(user_id=user.id, points=50)
    
    msg_reason = MockMessage("За хорошую работу")
    await user_management_handlers.change_points_reason(msg_reason, state, session, mock_bot)
    
    await session.refresh(user)
    assert user.points == 150
    
    mock_bot.send_message.assert_called_once()
    call_args = mock_bot.send_message.call_args
    assert call_args.kwargs['chat_id'] == user.telegram_id
    assert "изменил ваш баланс на 50" in call_args.kwargs['text']
    assert call_args.kwargs['parse_mode'] == "HTML"


async def test_user_receives_location_link_on_registration(session: AsyncSession, mocker):
    """
    Тестирует, что пользователь получает кликабельную ссылку на локацию
    в сообщении после успешной регистрации на мероприятие с координатами.
    """
    # 1. Подготовка
    mock_callback_message = MockMessage()
    mock_callback_message.edit_text = AsyncMock()

    user = User(phone_number="+1", telegram_id=101, full_name="Location User", university="TestUni")
    event = Event(
        name="Event With Coords",
        event_datetime=datetime.datetime.now() + datetime.timedelta(days=5),
        location="Москва, ул. Пушкина, д. Колотушкина",
        latitude=55.123,
        longitude=37.456,
        donation_type="plasma",
        points_per_donation=1,
        participant_limit=10,
        registration_is_open=True
    )
    session.add_all([user, event])
    await session.commit()
    
    callback = MockCallbackQuery(
        data=f"reg_event_{event.id}",
        from_user_id=user.telegram_id,
        message=mock_callback_message
    )
    
    # 2. Выполнение
    await student_handlers.process_event_registration(callback, session)

    # 3. Проверка
    mock_callback_message.edit_text.assert_called_once()
    call_args = mock_callback_message.edit_text.call_args.kwargs
    sent_text = call_args['text']
    
    expected_link_part = f'href="https://yandex.ru/maps/?pt={event.longitude},{event.latitude}&z=18&l=map"'
    assert expected_link_part in sent_text
    
    assert ">Москва, ул. Пушкина, д. Колотушкина</a>" in sent_text
    assert call_args['parse_mode'] == "HTML"


async def test_event_creation_fsm_with_rare_blood_and_datetime(session: AsyncSession, mocker):
    """
    Тестирует полную цепочку FSM создания мероприятия с выбором редких групп и времени.
    """
    state = MockFSMContext()
    bot = Mock(spec=Bot)
    bot.send_message = AsyncMock(return_value=MockMessage())

    await state.set_state(EventCreation.awaiting_name)
    await event_management.process_event_name(MockMessage("Full FSM Event"), state)
    
    await event_management.process_event_datetime(MockMessage("10.10.2030 11:45"), state)
    assert await state.get_state() == EventCreation.awaiting_location_text
    
    await event_management.process_event_location_text(MockMessage("Test location"), state)
    await event_management.process_event_location_point(MockMessage(location=MockLocation(1,1)), state)
    await event_management.process_event_donation_type(MockCallbackQuery(data="settype_plasma"), state)
    await event_management.process_event_points(MockMessage("100"), state)
    await event_management.process_event_bonus_points(MockMessage("50"), state)
    
    assert await state.get_state() == EventCreation.awaiting_rare_blood_types
    
    cb1 = MockCallbackQuery(data="select_rare_AB(IV) Rh-")
    await event_management.process_rare_blood_type_selection(cb1, state)
    cb1.message.edit_reply_markup.assert_called_once()
    
    cb_done = MockCallbackQuery(data="select_rare_done")
    await event_management.process_rare_blood_type_selection(cb_done, state)
    
    assert await state.get_state() == EventCreation.awaiting_limit
    
    await event_management.process_event_limit(MockMessage("20"), state)
    assert await state.get_state() == EventCreation.awaiting_confirmation

    cb_confirm = MockCallbackQuery(data="confirm_create_event")
    mocker.patch('bot.handlers.admin.event_management.send_new_event_notifications', new_callable=AsyncMock)
    
    await event_management.confirm_event_creation_and_notify(cb_confirm, state, session, bot)
    
    created_event = (await session.execute(select(Event).where(Event.name == "Full FSM Event"))).scalar_one()
    assert created_event is not None
    assert created_event.rare_blood_types == ["AB(IV) Rh-"]
    assert created_event.event_datetime == datetime.datetime(2030, 10, 10, 11, 45)
    
async def test_add_to_calendar_handler(session: AsyncSession, mocker):
    """
    Тестирует, что хендлер 'add_to_calendar' корректно формирует и отправляет .ics файл.
    """
    user = User(phone_number="+987", telegram_id=987, full_name="Calendar User", university="Test")
    event = Event(
        name="Calendar Event",
        event_datetime=datetime.datetime.now(),
        location="Test Location",
        donation_type="blood", points_per_donation=1, participant_limit=1
    )
    session.add_all([user, event])
    await session.commit()

    mock_message = MockMessage()
    mock_message.answer_document = AsyncMock()

    callback = MockCallbackQuery(
        data=f"add_to_calendar_{event.id}",
        from_user_id=user.telegram_id,
        message=mock_message
    )

    await student_handlers.send_calendar_file(callback, session)

    mock_message.answer_document.assert_called_once()
    
    call_args = mock_message.answer_document.call_args.kwargs
    document = call_args['document']
    
    assert "Календарный файл" in call_args['caption']
    assert f"event_{event.id}.ics" == document.filename
    
    mock_bot = Mock(spec=Bot)
    
    file_chunks = []
    async for chunk in document.read(bot=mock_bot):
        file_chunks.append(chunk)
    
    file_content_bytes = b"".join(file_chunks)
    file_content = file_content_bytes.decode('utf-8')

    assert "BEGIN:VCALENDAR" in file_content
    assert "SUMMARY:Донация: Calendar Event" in file_content
    
async def test_feedback_survey_fsm_full_pass(session: AsyncSession, mocker):
    """
    Тестирует полную цепочку FSM опроса с заполнением всех полей.
    """
    # 1. Подготовка
    user = User(phone_number="+1", telegram_id=101, full_name="Feedback User", university="TestUni")
    session.add(user)
    await session.commit()

    state = MockFSMContext()
    await state.set_state(FeedbackSurvey.awaiting_well_being)
    await state.update_data(event_id=1, donation_id=1)

    mock_message_to_edit = MockMessage()

    # 2. Прохождение FSM
    # Шаг 1: Оценка самочувствия
    cb_wb = MockCallbackQuery(data="fb_wb_5", from_user_id=user.telegram_id, message=mock_message_to_edit)
    await student_handlers.process_well_being(cb_wb, state)
    assert await state.get_state() == FeedbackSurvey.awaiting_organization_score

    # Шаг 2: Оценка организации
    cb_org = MockCallbackQuery(data="fb_org_9", from_user_id=user.telegram_id, message=mock_message_to_edit)
    await student_handlers.process_org_score(cb_org, state)
    assert await state.get_state() == FeedbackSurvey.awaiting_what_liked

    # Шаг 3: Что понравилось (отвечаем текстом)
    msg_liked = MockMessage(text="Вкусный чай", from_user_id=user.telegram_id)
    await student_handlers.process_what_liked(msg_liked, state)
    assert await state.get_state() == FeedbackSurvey.awaiting_what_disliked

    # Шаг 4: Что не понравилось (пропускаем)
    cb_skip_disliked = MockCallbackQuery(data="fb_skip_step", from_user_id=user.telegram_id, message=mock_message_to_edit)
    await student_handlers.process_what_disliked(cb_skip_disliked, state)
    assert await state.get_state() == FeedbackSurvey.awaiting_other_suggestions

    # Шаг 5: Предложения (отвечаем текстом)
    msg_suggestions = MockMessage(text="Давать больше печенья", from_user_id=user.telegram_id)
    await student_handlers.process_other_suggestions(msg_suggestions, state, session)

    # 3. Проверка
    assert await state.get_state() is None

    feedback_entry = (await session.execute(select(Feedback))).scalar_one_or_none()
    assert feedback_entry is not None
    assert feedback_entry.user_id == user.id
    assert feedback_entry.event_id == 1
    assert feedback_entry.well_being_score == 5
    assert feedback_entry.well_being_comment is None
    assert feedback_entry.organization_score == 9
    assert feedback_entry.what_liked == "Вкусный чай"
    assert feedback_entry.what_disliked == "Пропущено"
    assert feedback_entry.other_suggestions == "Давать больше печенья"

async def test_admin_can_view_feedback(session: AsyncSession):
    """
    Тестирует функцию просмотра отзывов администратором.
    """
    admin = User(phone_number="+0", telegram_id=100, full_name="Admin", university="TestUni")
    user1 = User(phone_number="+1", telegram_id=101, full_name="User One", university="TestUni")
    event = Event(name="Event With Feedback", event_datetime=datetime.datetime.now(), location="Loc", donation_type="d", points_per_donation=1, participant_limit=1)
    session.add_all([admin, user1, event])
    await session.commit()

    fb1 = Feedback(user_id=user1.id, event_id=event.id, organization_score=10, what_liked="Всё")
    session.add(fb1)
    await session.commit()

    mock_message = MockMessage()
    callback = MockCallbackQuery(data=f"admin_view_feedback_{event.id}", from_user_id=admin.telegram_id, message=mock_message)

    await event_management.view_event_feedback(callback, session)

    # Проверяем, что исходное сообщение было отредактировано
    mock_message.answer.assert_called_once()
    
    # Проверяем содержимое отредактированного сообщения
    call_args = mock_message.answer.call_args
    sent_text = call_args.args[0]
    
    assert "Отзывы по мероприятию" in sent_text
    assert "Event With Feedback" in sent_text
    assert "User One" in sent_text
    assert "Всё" in sent_text