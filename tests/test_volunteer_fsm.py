import pytest
import datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select 
from aiogram import Bot

# Импортируем необходимые модели и запросы
from bot.db.models import User, Event, EventRegistration, Donation, MedicalWaiver
from bot.db import event_requests

# Импортируем состояния и хендлеры, которые будем тестировать
from bot.states.states import VolunteerActions
from bot.handlers.volunteer import (
    start_qr_confirmation, 
    process_qr_photo, 
    process_donation_confirmation,
    process_qr_invalid_input
)
from bot.utils.text_messages import Text

# Помечаем все тесты как асинхронные
pytestmark = pytest.mark.asyncio

# --- Вспомогательные классы-заглушки (Mocks) ---

class MockMessage:
    """Упрощенная заглушка для объекта Message."""
    def __init__(self, text=None, from_user_id=1, photo=None):
        self.text = text
        self.from_user = Mock(id=from_user_id)
        # Имитируем структуру F.photo (список с последним элементом лучшего качества)
        self.photo = [Mock(file_id="photo_file_id_123")] if photo else None
        self.answer = AsyncMock()
        self.edit_text = AsyncMock()

class MockCallbackQuery:
    """Упрощенная заглушка для объекта CallbackQuery."""
    def __init__(self, data, from_user_id=1, message=None):
        self.data = data
        self.from_user = Mock(id=from_user_id)
        self.message = message if message else MockMessage(from_user_id=from_user_id)
        self.answer = AsyncMock()

class MockFSMContext:
    """Упрощенная заглушка для FSMContext."""
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

# --- Фикстуры для подготовки данных в БД ---

@pytest.fixture
async def volunteer_user(session: AsyncSession) -> User:
    user = User(
        phone_number="+7-volunteer", telegram_id=1001, full_name="Волонтер Тестов", 
        role="volunteer", university="TestUni"
    )
    session.add(user)
    await session.commit()
    return user

@pytest.fixture
async def donor_user(session: AsyncSession) -> User:
    user = User(
        phone_number="+7-donor", telegram_id=2002, full_name="Донор Тестов", 
        role="student", university="TestUni", gender="male", points=0
    )
    session.add(user)
    await session.commit()
    return user

@pytest.fixture
async def today_event(session: AsyncSession) -> Event:
    event = Event(
        name="Сегодняшнее Мероприятие", 
        event_datetime=datetime.datetime.now(), 
        location="Тестовая локация", donation_type="whole_blood", 
        points_per_donation=50, participant_limit=10
    )
    session.add(event)
    await session.commit()
    return event

@pytest.fixture
async def future_event(session: AsyncSession) -> Event:
    event = Event(
        name="Будущее Мероприятие", 
        event_datetime=datetime.datetime.now() + datetime.timedelta(days=5), 
        location="Другая локация", donation_type="plasma", 
        points_per_donation=20, participant_limit=5
    )
    session.add(event)
    await session.commit()
    return event

@pytest.fixture
async def registration(session: AsyncSession, donor_user: User, today_event: Event) -> EventRegistration:
    """Создает регистрацию донора на сегодняшнее мероприятие."""
    reg = EventRegistration(user_id=donor_user.id, event_id=today_event.id)
    session.add(reg)
    await session.commit()
    return reg



async def test_volunteer_fsm_happy_path(
    session: AsyncSession, mocker, volunteer_user: User, donor_user: User, today_event: Event, registration: EventRegistration
):
    """
    Тестирует полный успешный сценарий: от сканирования QR до подтверждения донации.
    """
    state = MockFSMContext()
    
    # Мокаем Bot и его метод download, т.к. мы не будем реально скачивать файл
    mock_bot = Mock(spec=Bot)
    mock_bot.download.return_value = AsyncMock(read=AsyncMock(return_value=b'fake_photo_bytes'))

    # Мокаем `read_qr`, чтобы он возвращал нужные нам данные без реального QR
    qr_data = {"user_id": donor_user.telegram_id, "event_id": today_event.id}
    mocker.patch('bot.handlers.volunteer.read_qr', new_callable=AsyncMock, return_value=qr_data)
    
    # 2. ACT & ASSERT (Действие и Проверка)
    
    # --- Шаг 1: Волонтер инициирует процесс ---
    callback_start = MockCallbackQuery(data="confirm_donation_qr", from_user_id=volunteer_user.telegram_id)
    await start_qr_confirmation(callback_start, state)
    
    assert await state.get_state() == VolunteerActions.awaiting_qr_photo
    callback_start.message.edit_text.assert_called_once_with(Text.VOLUNTEER_SEND_QR_PROMPT)

    # --- Шаг 2: Волонтер отправляет фото с QR ---
    message_photo = MockMessage(from_user_id=volunteer_user.telegram_id, photo=True)
    await process_qr_photo(message_photo, state, session, mock_bot)

    assert await state.get_state() == VolunteerActions.awaiting_confirmation
    message_photo.answer.assert_called_once()
    
    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # Получаем аргументы вызова mock'а
    args, kwargs = message_photo.answer.call_args
    # Текст передается как первый позиционный аргумент
    sent_text = args[0] 
    
    assert donor_user.full_name in sent_text
    assert today_event.name in sent_text
    assert kwargs['parse_mode'] == "HTML"
    
    # --- Шаг 3: Волонтер подтверждает донацию ---
    callback_confirm = MockCallbackQuery(
        data=f"confirm_donation_{donor_user.id}_{today_event.id}",
        from_user_id=volunteer_user.telegram_id
    )
    await process_donation_confirmation(callback_confirm, state, session, mock_bot)
    
    assert await state.get_state() is None # Состояние должно сброситься
    callback_confirm.message.edit_text.assert_called_with(
        Text.DONATION_CONFIRM_SUCCESS.format(
            donor_name=donor_user.full_name,
            event_name=today_event.name,
            points=today_event.points_per_donation
        ),
        reply_markup=mocker.ANY, # Проверяем, что клавиатура была, не важен ее тип
        parse_mode="HTML"
    )

    # --- Финальная проверка изменений в БД ---
    await session.refresh(donor_user)
    await session.refresh(registration)
    
    assert donor_user.points == today_event.points_per_donation
    
    # Теперь этот код будет работать, так как select импортирован
    donation_record_query = await session.execute(
        select(Donation).where(
            Donation.user_id == donor_user.id,
            Donation.event_id == today_event.id
        )
    )
    donation_record = donation_record_query.scalar_one_or_none()
    
    waiver_record_query = await session.execute(
        select(MedicalWaiver).where(MedicalWaiver.user_id == donor_user.id)
    )
    waiver_record = waiver_record_query.scalar_one_or_none()

    assert donation_record is not None
    assert donation_record.user_id == donor_user.id
    
    assert waiver_record is not None
    assert waiver_record.user_id == donor_user.id

# --- Тесты "несчастливых" путей ---

async def test_volunteer_fsm_invalid_input(volunteer_user: User):
    """Тест: волонтер отправляет текст вместо фото."""
    message = MockMessage(text="это не фото", from_user_id=volunteer_user.telegram_id)
    await process_qr_invalid_input(message)
    message.answer.assert_called_once_with(Text.VOLUNTEER_INVALID_INPUT_QR)


async def test_volunteer_fsm_qr_read_fails(mocker, session, volunteer_user: User):
    """Тест: QR-код не распознан."""
    state = MockFSMContext()
    mocker.patch('bot.handlers.volunteer.read_qr', new_callable=AsyncMock, return_value=None)
    mock_bot = Mock(spec=Bot)
    mock_bot.download.return_value = AsyncMock(read=AsyncMock(return_value=b''))

    message_photo = MockMessage(from_user_id=volunteer_user.telegram_id, photo=True)
    await process_qr_photo(message_photo, state, session, mock_bot)

    assert await state.get_state() is None # Состояние сбрасывается при ошибке
    message_photo.answer.assert_called_once_with(Text.QR_READ_ERROR)


async def test_volunteer_fsm_donor_not_registered(mocker, session, volunteer_user, donor_user, today_event):
    """Тест: Донор не зарегистрирован на это мероприятие."""
    # Важно: фикстура 'registration' здесь не используется, т.е. записи в БД нет
    state = MockFSMContext()
    qr_data = {"user_id": donor_user.telegram_id, "event_id": today_event.id}
    mocker.patch('bot.handlers.volunteer.read_qr', new_callable=AsyncMock, return_value=qr_data)
    mock_bot = Mock(spec=Bot)
    mock_bot.download.return_value = AsyncMock(read=AsyncMock(return_value=b''))

    message_photo = MockMessage(from_user_id=volunteer_user.telegram_id, photo=True)
    await process_qr_photo(message_photo, state, session, mock_bot)

    assert await state.get_state() is None
    message_photo.answer.assert_called_once_with(
        Text.QR_DONOR_NOT_REGISTERED_ERROR.format(donor_name=donor_user.full_name),
        parse_mode="HTML"
    )

async def test_volunteer_fsm_wrong_day(mocker, session, volunteer_user, donor_user, future_event):
    """Тест: QR-код от мероприятия, которое проходит не сегодня."""
    state = MockFSMContext()
    # Регистрируем донора на БУДУЩЕЕ мероприятие
    reg = EventRegistration(user_id=donor_user.id, event_id=future_event.id)
    session.add(reg)
    await session.commit()

    qr_data = {"user_id": donor_user.telegram_id, "event_id": future_event.id}
    mocker.patch('bot.handlers.volunteer.read_qr', new_callable=AsyncMock, return_value=qr_data)
    mock_bot = Mock(spec=Bot)
    mock_bot.download.return_value = AsyncMock(read=AsyncMock(return_value=b''))

    message_photo = MockMessage(from_user_id=volunteer_user.telegram_id, photo=True)
    await process_qr_photo(message_photo, state, session, mock_bot)

    assert await state.get_state() is None
    message_photo.answer.assert_called_once_with(Text.QR_WRONG_DAY_ERROR)