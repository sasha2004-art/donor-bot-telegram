import pytest
from unittest.mock import Mock
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.filters.role import RoleFilter

# Маркируем все тесты в этом файле для pytest-asyncio
pytestmark = pytest.mark.asyncio

# Создадим "заглушку" для объекта CallbackQuery, чтобы не импортировать aiogram
class MockUser:
    def __init__(self, id):
        self.id = id

class MockCallback:
    def __init__(self, user_id):
        self.from_user = MockUser(id=user_id)

async def test_role_filter(session: AsyncSession):
    """
    Тестирует логику фильтра RoleFilter для разных ролей и статусов.
    """
    # 1. Подготовка: создаем пользователей с разными ролями
    # --- ИСПРАВЛЕНИЕ: Добавляем обязательное поле university ---
    student = User(phone_number="+1", telegram_id=101, full_name="Student", role="student", university="TestUni")
    volunteer = User(phone_number="+2", telegram_id=102, full_name="Volunteer", role="volunteer", university="TestUni")
    admin = User(phone_number="+3", telegram_id=103, full_name="Admin", role="admin", university="TestUni")
    main_admin = User(phone_number="+4", telegram_id=104, full_name="Main Admin", role="main_admin", university="TestUni")
    blocked_admin = User(phone_number="+5", telegram_id=105, full_name="Blocked Admin", role="admin", is_blocked=True, university="TestUni")
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    session.add_all([student, volunteer, admin, main_admin, blocked_admin])
    await session.commit()

    # 2. Выполнение и Проверка
    
    # --- Проверяем доступ к "admin" уровню ---
    admin_filter = RoleFilter(required_role="admin")
    
    # Студент не должен пройти
    assert not await admin_filter(MockCallback(user_id=101), session)
    # Волонтер не должен пройти
    assert not await admin_filter(MockCallback(user_id=102), session)
    # Админ должен пройти
    assert await admin_filter(MockCallback(user_id=103), session)
    # Главный админ тоже должен пройти (иерархия)
    assert await admin_filter(MockCallback(user_id=104), session)
    # Заблокированный админ не должен пройти
    assert not await admin_filter(MockCallback(user_id=105), session)
    # Несуществующий пользователь не должен пройти
    assert not await admin_filter(MockCallback(user_id=999), session)

    # --- Проверяем доступ к "volunteer" уровню ---
    volunteer_filter = RoleFilter(required_role="volunteer")
    
    # Студент не должен пройти
    assert not await volunteer_filter(MockCallback(user_id=101), session)
    # Волонтер должен пройти
    assert await volunteer_filter(MockCallback(user_id=102), session)
    # Админ должен пройти (иерархия)
    assert await volunteer_filter(MockCallback(user_id=103), session)