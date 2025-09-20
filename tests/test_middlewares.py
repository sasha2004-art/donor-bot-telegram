# tests/test_middlewares.py

import pytest
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем Message, чтобы использовать его как спецификацию для Mock
from aiogram.types import Message, CallbackQuery

from bot.db.models import User
from bot.middlewares.block import BlockUserMiddleware
from bot.middlewares.db import DbSessionMiddleware

# Помечаем все тесты как асинхронные
pytestmark = pytest.mark.asyncio


# --- Фикстуры для подготовки пользователей ---


@pytest.fixture
async def blocked_user(session: AsyncSession) -> User:
    """Создает заблокированного пользователя в БД."""
    user = User(
        phone_number="+7-blocked",
        telegram_id=9001,
        full_name="Blocked User",
        university="Test",
        is_blocked=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
async def active_user(session: AsyncSession) -> User:
    """Создает активного (не заблокированного) пользователя в БД."""
    user = User(
        phone_number="+7-active",
        telegram_id=9002,
        full_name="Active User",
        university="Test",
        is_blocked=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# --- Тесты Middleware (ИСПРАВЛЕННАЯ ВЕРСИЯ) ---


async def test_block_middleware_for_blocked_user(
    session: AsyncSession, blocked_user: User
):
    """
    Тест: Middleware должна остановить обработку для заблокированного пользователя.
    """
    block_mw = BlockUserMiddleware()
    handler_mock = AsyncMock()

    # ИСПРАВЛЕНИЕ: Создаем mock, который является "похожим" на Message
    # и будет проходить проверку isinstance(event, Message)
    event = Mock(spec=Message)
    event.from_user = Mock(id=blocked_user.telegram_id)
    event.answer = AsyncMock()

    await block_mw(handler=handler_mock, event=event, data={"session": session})

    # Теперь handler не должен быть вызван
    handler_mock.assert_not_called()
    # А пользователю должно быть отправлено сообщение о блокировке
    event.answer.assert_called_once()
    assert "заблокированы" in event.answer.call_args.args[0]


async def test_block_middleware_for_active_user(
    session: AsyncSession, active_user: User
):
    """
    Тест: Middleware должна пропустить обработку для активного пользователя.
    """
    block_mw = BlockUserMiddleware()
    handler_mock = AsyncMock()

    # ИСПРАВЛЕНИЕ: Используем тот же корректный mock
    event = Mock(spec=Message)
    event.from_user = Mock(id=active_user.telegram_id)
    event.answer = AsyncMock()

    await block_mw(handler=handler_mock, event=event, data={"session": session})

    # Handler должен быть вызван, т.к. пользователь активен
    handler_mock.assert_called_once()
    # Сообщение о блокировке не отправляется
    event.answer.assert_not_called()


async def test_block_middleware_for_unregistered_user(session: AsyncSession):
    """
    Тест: Middleware должна пропустить обработку для пользователя, которого еще нет в БД.
    """
    block_mw = BlockUserMiddleware()
    handler_mock = AsyncMock()

    # ИСПРАВЛЕНИЕ: Используем тот же корректный mock
    event = Mock(spec=Message)
    event.from_user = Mock(id=999999)  # ID, которого нет в БД
    event.answer = AsyncMock()

    await block_mw(handler=handler_mock, event=event, data={"session": session})

    # Handler должен быть вызван, т.к. незарегистрированный пользователь не заблокирован
    handler_mock.assert_called_once()
    event.answer.assert_not_called()


async def test_db_middleware_adds_session(session_pool):  # <--- ИЗМЕНЕНИЕ ЗДЕСЬ
    """
    Тест для DbSessionMiddleware: проверяем, что он корректно добавляет сессию в данные.
    """
    # session_maker заменен на session_pool
    db_mw = DbSessionMiddleware(session_pool=session_pool)  # <--- ИЗМЕНЕНИЕ ЗДЕСЬ
    handler_mock = AsyncMock()
    event = Mock()
    data = {}

    await db_mw(handler=handler_mock, event=event, data=data)

    handler_mock.assert_called_once()
    data_passed_to_handler = handler_mock.call_args.args[1]
    assert "session" in data_passed_to_handler
    assert isinstance(data_passed_to_handler["session"], AsyncSession)
