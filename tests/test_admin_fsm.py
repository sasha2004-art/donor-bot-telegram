import pytest
import datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from aiogram import Bot

# Импортируем тестируемые хендлеры и состояния
from bot.handlers.admin import merch_management as merch_handlers
from bot.handlers.admin import user_management as user_handlers
from bot.handlers.admin import event_management as event_handlers
from bot.handlers.admin import mailing as mailing_handlers
from bot.states.states import MerchCreation, BlockUser, ManualWaiver, EventEditing, UserSearch, Mailing

# Импортируем модели для проверки результатов в БД
from bot.db.models import MerchItem, User, UserBlock, MedicalWaiver, Event

# Помечаем все тесты как асинхронные
pytestmark = pytest.mark.asyncio


# --- Вспомогательные классы-заглушки (Mocks) ---
# (Можно вынести в общий conftest.py, но для примера оставим здесь)

class MockMessage:
    def __init__(self, text=None, from_user_id=1, photo=None):
        self.text = text
        self.from_user = Mock(id=from_user_id)
        # Имитируем F.photo/html_text
        self.photo = [Mock(file_id="photo_file_id_123")] if photo else None
        self.html_text = text
        self.answer = AsyncMock()
        self.delete = AsyncMock()

class MockCallbackQuery:
    def __init__(self, data, from_user_id=1, message=None):
        self.data = data
        self.from_user = Mock(id=from_user_id)
        if not message:
            self.message = MockMessage(from_user_id=from_user_id)
        else:
            self.message = message
        
        for method_name in ['edit_text', 'delete', 'answer']:
            if not hasattr(self.message, method_name):
                 setattr(self.message, method_name, AsyncMock())

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


# --- Существующие тесты (без изменений, кроме исправленных) ---

async def test_merch_creation_fsm_full_path(session: AsyncSession):
    # ... (этот тест был в порядке, оставляем без изменений)
    admin_user_id = 1001
    state = MockFSMContext()
    callback_start = MockCallbackQuery(data="admin_create_merch", from_user_id=admin_user_id)
    await merch_handlers.start_merch_creation(callback_start, state)
    assert await state.get_state() == MerchCreation.awaiting_photo
    msg_photo = MockMessage(from_user_id=admin_user_id, photo=True)
    await merch_handlers.process_merch_photo(msg_photo, state)
    assert await state.get_state() == MerchCreation.awaiting_name
    msg_name = MockMessage(text="Крутая кружка", from_user_id=admin_user_id)
    await merch_handlers.process_merch_name(msg_name, state)
    assert await state.get_state() == MerchCreation.awaiting_description
    msg_desc = MockMessage(text="Очень крутая кружка для доноров", from_user_id=admin_user_id)
    await merch_handlers.process_merch_description(msg_desc, state)
    assert await state.get_state() == MerchCreation.awaiting_price
    msg_price = MockMessage(text="150", from_user_id=admin_user_id)
    await merch_handlers.process_merch_price(msg_price, state, session)
    assert await state.get_state() is None
    created_item = (await session.execute(select(MerchItem))).scalar_one_or_none()
    assert created_item is not None
    assert created_item.name == "Крутая кружка"


async def test_block_user_fsm_full_path(session: AsyncSession, mocker):
    # ... (этот тест был в порядке, оставляем без изменений)
    mock_bot = Mock(spec=Bot)
    mock_bot.send_message = AsyncMock()
    main_admin = User(phone_number="+1", telegram_id=1001, full_name="Main Admin", university="Test")
    target_user = User(phone_number="+2", telegram_id=2002, full_name="Target User", university="Test")
    session.add_all([main_admin, target_user])
    await session.commit()
    state = MockFSMContext()
    callback_start = MockCallbackQuery(data=f"ma_block_user_{target_user.id}", from_user_id=main_admin.telegram_id)
    await user_handlers.block_user_from_card(callback_start, state)
    assert await state.get_state() == BlockUser.awaiting_reason
    msg_reason = MockMessage(text="Нарушение правил", from_user_id=main_admin.telegram_id)
    await user_handlers.process_block_reason(msg_reason, state, session, mock_bot)
    assert await state.get_state() is None
    await session.refresh(target_user)
    assert target_user.is_blocked is True
    mock_bot.send_message.assert_called_once()

async def test_manual_waiver_fsm_full_path(session: AsyncSession, mocker):
    # ... (этот тест был в порядке, оставляем без изменений)
    mock_bot = Mock(spec=Bot)
    mock_bot.send_message = AsyncMock()
    admin = User(phone_number="+1", telegram_id=1001, full_name="Admin", university="Test")
    target_user = User(phone_number="+2", telegram_id=2002, full_name="Target User", university="Test")
    session.add_all([admin, target_user])
    await session.commit()
    state = MockFSMContext()
    callback_start = MockCallbackQuery(data=f"admin_waiver_{target_user.id}", from_user_id=admin.telegram_id)
    await user_handlers.set_waiver_start(callback_start, state)
    assert await state.get_state() == ManualWaiver.awaiting_end_date
    msg_date = MockMessage(text="01.01.2099", from_user_id=admin.telegram_id)
    await user_handlers.set_waiver_date(msg_date, state)
    assert await state.get_state() == ManualWaiver.awaiting_reason
    msg_reason = MockMessage(text="Медицинские показания", from_user_id=admin.telegram_id)
    await user_handlers.set_waiver_reason(msg_reason, state, session, mock_bot)
    assert await state.get_state() is None
    waiver_record = (await session.execute(select(MedicalWaiver))).scalar_one_or_none()
    assert waiver_record is not None
    mock_bot.send_message.assert_called_once()

# --- ИСПРАВЛЕННЫЕ И НОВЫЕ ТЕСТЫ ---

async def test_user_search_fsm_full_path(session: AsyncSession):
    """
    Тестирует FSM поиска пользователя.
    """
    admin_id = 1001
    user_to_find = User(phone_number="+7123", telegram_id=123, full_name="Иванов Иван", university="Test")
    session.add(user_to_find)
    await session.commit()
    
    state = MockFSMContext()
    
    callback = MockCallbackQuery(data="admin_search_user", from_user_id=admin_id)
    await user_handlers.search_user_start(callback, state)
    assert await state.get_state() == UserSearch.awaiting_query
    
    message = MockMessage(text="Иванов", from_user_id=admin_id)
    await user_handlers.process_user_search(message, state, session)
    
    assert await state.get_state() is None
    message.answer.assert_called_once()
    
    # ИСПРАВЛЕНИЕ 1: Проверяем позиционный аргумент `args`
    args, kwargs = message.answer.call_args
    assert "Результаты поиска" in args[0]
    assert "Иванов Иван" in str(kwargs['reply_markup'])


async def test_event_editing_fsm_full_path(session: AsyncSession, mocker): # <-- ИСПРАВЛЕНИЕ 2: Добавлен mocker
    """
    Тестирует FSM редактирования мероприятия.
    """
    admin_id = 1001
    event = Event(name="Старое Название", event_datetime=datetime.datetime.now(), location="Test", donation_type="d", points_per_donation=1, participant_limit=1)
    session.add(event)
    await session.commit()
    
    state = MockFSMContext()

    callback_start = MockCallbackQuery(data=f"admin_edit_event_{event.id}", from_user_id=admin_id)
    await event_handlers.start_event_editing(callback_start, state, session)
    assert await state.get_state() == EventEditing.choosing_field

    callback_choose_field = MockCallbackQuery(data="edit_field_name", from_user_id=admin_id)
    await event_handlers.choose_field_to_edit(callback_choose_field, state)
    assert await state.get_state() == EventEditing.awaiting_new_value
    
    message = MockMessage(text="Новое Шикарное Название", from_user_id=admin_id)
    await event_handlers.process_new_value_for_event(message, state, session)
    
    assert await state.get_state() is None
    await session.refresh(event)
    assert event.name == "Новое Шикарное Название"
    # ИСПРАВЛЕНИЕ 2: mocker теперь определён
    message.answer.assert_called_once_with("✅ Поле успешно обновлено!", reply_markup=mocker.ANY)


async def test_mailing_fsm_full_path(session: AsyncSession, mocker):
    """
    Тестирует полную FSM-цепочку создания и запуска рассылки с фото и фильтрами.
    """
    mock_do_mailing = mocker.patch("bot.handlers.admin.mailing.do_mailing", new_callable=AsyncMock)
    
    admin = User(id=1001, phone_number="+1", telegram_id=1001, full_name="Admin", university="НИЯУ МИФИ", role="admin")
    # Добавляем еще одного пользователя, который должен попасть в рассылку
    user_mifi = User(id=1, phone_number="+2", telegram_id=1, full_name="User1", university="НИЯУ МИФИ", role="student")
    user_mgu = User(id=2, phone_number="+3", telegram_id=2, full_name="User2", university="МГУ", role="student")
    session.add_all([admin, user_mifi, user_mgu])
    await session.commit()

    state = MockFSMContext()
    
    cb_start = MockCallbackQuery(data="admin_mailing", from_user_id=admin.id)
    await mailing_handlers.start_mailing(cb_start, state)
    assert await state.get_state() == Mailing.awaiting_message_text
    
    msg_text = MockMessage(text="<b>Всем привет!</b>", from_user_id=admin.id)
    await mailing_handlers.get_mailing_text(msg_text, state)
    assert await state.get_state() == Mailing.awaiting_media
    
    msg_photo = MockMessage(from_user_id=admin.id, photo=True)
    await mailing_handlers.get_mailing_photo(msg_photo, state)
    assert await state.get_state() == Mailing.awaiting_audience_choice
    
    cb_choose_filter = MockCallbackQuery(data="mail_audience_type_university", from_user_id=admin.id)
    await mailing_handlers.choose_audience_filter_type(cb_choose_filter, state, session)
    
    cb_set_filter = MockCallbackQuery(data="mail_filter_university_НИЯУ МИФИ", from_user_id=admin.id)
    await mailing_handlers.set_audience_filter(cb_set_filter, state)
    
    cb_finish_audience = MockCallbackQuery(data="mail_audience_finish", from_user_id=admin.id)
    await mailing_handlers.finish_audience_selection(cb_finish_audience, state, session)
    assert await state.get_state() == Mailing.awaiting_confirmation
    
    cb_finish_audience.message.answer.assert_called_once()
    args, _ = cb_finish_audience.message.answer.call_args
    assert "<b>👥 Получателей:</b> 2" in args[0]
    assert "Прикреплено фото" in args[0]
    
    cb_confirm = MockCallbackQuery(data="confirm_mailing", from_user_id=admin.id)
    await mailing_handlers.confirm_and_start_mailing(cb_confirm, state, Mock(spec=Bot))
    
    assert await state.get_state() is None
    mock_do_mailing.assert_called_once()