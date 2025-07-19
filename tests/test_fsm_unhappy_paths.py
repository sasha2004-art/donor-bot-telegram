import pytest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession
from bot.states.states import EventCreation
from bot.handlers.admin import event_management as event_handlers
from bot.handlers import common as common_handlers
from bot.utils.text_messages import Text

pytestmark = pytest.mark.asyncio

# --- Используем уже существующие моки из других тестов для консистентности ---

class MockMessage:
    def __init__(self, text=None, from_user_id=1, command=None):
        self.text = text
        self.from_user = Mock(id=from_user_id)
        self.answer = AsyncMock()
        self.delete = AsyncMock()
        # Для FSM /cancel
        self.bot = Mock(id=1)
        self.chat = Mock(id=1)

class MockCallbackQuery:
    def __init__(self, data, from_user_id=1, message=None):
        self.data = data
        self.from_user = Mock(id=from_user_id)
        self.message = message or MockMessage(from_user_id=from_user_id)
        setattr(self.message, 'edit_text', AsyncMock())
        self.answer = AsyncMock()

class MockFSMContext:
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

# --- Тесты ---

async def test_event_creation_fsm_invalid_date(session: AsyncSession):
    """
    Тест: Пользователь вводит текст "завтра" вместо даты при создании мероприятия.
    Ожидаемый результат: Бот должен ответить ошибкой формата, состояние FSM не меняется.
    """
    state = MockFSMContext()
    await state.set_state(EventCreation.awaiting_datetime) # Устанавливаем FSM в нужное состояние

    message = MockMessage(text="завтра")
    
    await event_handlers.process_event_datetime(message, state)

    # Проверяем, что состояние не изменилось
    assert await state.get_state() == EventCreation.awaiting_datetime
    # Проверяем, что бот отправил сообщение об ошибке
    message.answer.assert_called_once_with(Text.DATE_FORMAT_ERROR, parse_mode="HTML")

async def test_event_creation_fsm_invalid_limit(session: AsyncSession):
    """
    Тест: Пользователь вводит текст "сто" вместо числа для лимита участников.
    Ожидаемый результат: Бот должен ответить ошибкой формата, состояние FSM не меняется.
    """
    state = MockFSMContext()
    await state.set_state(EventCreation.awaiting_limit)
    await state.update_data(
        name="Test",
        event_datetime="2030-01-01T10:00:00",
        location="Test", latitude=0.0, longitude=0.0,
        donation_type="test", points_per_donation=100
    )

    message = MockMessage(text="сто")

    await event_handlers.process_event_limit(message, state, session)
    
    assert await state.get_state() == EventCreation.awaiting_limit
    message.answer.assert_called_once_with(Text.EVENT_LIMIT_NAN_ERROR)

async def test_fsm_cancel_command(session: AsyncSession):
    """
    Тест: Пользователь отправляет команду /cancel в середине FSM.
    Ожидаемый результат: Состояние FSM сбрасывается, отправляется сообщение об отмене.
    """
    state = MockFSMContext()
    await state.set_state(EventCreation.awaiting_name)

    # Мокаем необходимую структуру для хендлера
    message = MockMessage(text="/cancel")
    message.answer = AsyncMock()
    # common_handlers.send_or_edit_main_menu ожидает, что у message будет message
    setattr(message, 'message', message)
    
    # Мокаем функцию отправки главного меню, чтобы изолировать тест
    common_handlers.send_or_edit_main_menu = AsyncMock()

    await common_handlers.cancel_fsm_handler(message, state, session)
    
    assert await state.get_state() is None
    message.answer.assert_called_once_with(Text.ACTION_CANCELLED)
    # Проверяем, что после отмены была вызвана функция показа главного меню
    common_handlers.send_or_edit_main_menu.assert_called_once()