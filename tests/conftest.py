# tests/conftest.py

import pytest
import sys
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

# --- Настройка путей ---
# Добавляем корневую папку проекта в sys.path, чтобы pytest мог найти модули бота.
# Это стандартная практика для корректной работы импортов в тестах.
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bot.db.models import Base

# --- Настройка тестовой БД ---

# URL для асинхронной базы данных SQLite в памяти.
# Это идеальный выбор для быстрых и полностью изолированных тестов,
# так как база данных создается в оперативной памяти и исчезает после завершения тестов.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Создаем тестовый движок БД. Он будет жить в течение всей тестовой сессии.
test_engine: AsyncEngine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Создаем фабрику сессий для тестов.
# Она будет использоваться для создания новых сессий для каждого теста.
TestSessionMaker = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:
    """
    Фикстура уровня сессии для подготовки базы данных.

    `scope="session"`: код выполняется один раз перед запуском всех тестов.
    `autouse=True`: фикстура активируется автоматически, ее не нужно указывать в тестах.

    Действия:
    1. Перед тестами: создает все таблицы на основе моделей SQLAlchemy.
    2. После тестов: удаляет все таблицы, очищая окружение.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield  # В этот момент выполняются все тесты

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def session(setup_database: None) -> AsyncGenerator[AsyncSession, None]:
    """
    Основная фикстура для предоставления сессии в каждый тестовый кейс.

    `scope="function"`: код выполняется для каждой отдельной тестовой функции.
    `setup_database`: зависимость от фикстуры, которая гарантирует, что таблицы уже созданы.

    Принцип работы для изоляции тестов:
    1. Устанавливается соединение с БД.
    2. Начинается транзакция.
    3. Создается сессия, привязанная к этой транзакции.
    4. Сессия передается в тест (`yield session`).
    5. Тест выполняет свои операции с БД (добавление, изменение данных).
    6. После завершения теста транзакция откатывается (`rollback`), отменяя все изменения,
       сделанные в тесте.
    7. Соединение закрывается.

    Таким образом, каждый тест начинается с абсолютно чистой БД.
    """
    connection = await test_engine.connect()
    transaction = await connection.begin()

    try:
        # Создаем сессию, привязанную к транзакции
        session_for_test = TestSessionMaker(bind=connection)
        yield session_for_test
    finally:
        # Откатываем транзакцию и закрываем соединение в любом случае
        await transaction.rollback()
        await connection.close()
        
@pytest.fixture(scope="session")
def session_pool() -> async_sessionmaker:
    """
    Фикстура, которая предоставляет фабрику сессий (session maker).
    Она нужна для компонентов, которые сами управляют созданием сессий,
    например, для планировщика.
    """
    return TestSessionMaker