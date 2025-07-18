# tests/test_mailing_logic.py

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db import user_requests, admin_requests

# Маркируем все тесты в этом файле для pytest-asyncio
pytestmark = pytest.mark.asyncio

# Данные для тестовых пользователей
users_data = [
    # ... (данные без изменений) ...
    {"id": 1, "university": "НИЯУ МИФИ", "faculty": "ИИКС", "blood_type": "O(I)", "role": "student"},
    {"id": 2, "university": "НИЯУ МИФИ", "faculty": "ИИКС", "blood_type": "A(II)", "role": "student"},
    {"id": 3, "university": "НИЯУ МИФИ", "faculty": "ИФИБ", "blood_type": "O(I)", "role": "volunteer"},
    {"id": 4, "university": "МГУ", "faculty": "ВМК", "blood_type": "B(III)", "role": "student"},
    {"id": 5, "university": "МГУ", "faculty": "ВМК", "blood_type": "A(II)", "role": "admin"},
    {"id": 6, "university": "Другой ВУЗ", "faculty": None, "blood_type": "AB(IV)", "role": "student"},
    {"id": 7, "university": "НИЯУ МИФИ", "faculty": "Администрация", "blood_type": "AB(IV)", "role": "main_admin"},
]

# --- ИЗМЕНЕНИЕ ФИКСТУРЫ ---
@pytest.fixture(scope="function", autouse=True)
async def setup_users(session: AsyncSession):
    """
    Фикстура для создания пользователей перед каждым тестом в этом файле.
    Теперь имеет scope="function" и использует фикстуру session.
    """
    users_to_add = [
        User(
            id=u["id"], phone_number=f"+{u['id']}", telegram_id=u["id"],
            full_name=f"User {u['id']}", university=u["university"],
            faculty=u.get("faculty"), blood_type=u.get("blood_type"), role=u.get("role")
        ) for u in users_data
    ]
    session.add_all(users_to_add)
    await session.commit()
    yield # Передаем управление тесту
# --- КОНЕЦ ИЗМЕНЕНИЙ В ФИКСТУРЕ ---


@pytest.mark.parametrize(
    "filters, expected_user_ids",
    [
        # --- ПРОСТЫЕ ФИЛЬТРЫ ---
        ({}, {1, 2, 3, 4, 5, 6, 7}), # Фильтр 'all' или пустой -> все пользователи
        ({"role": "all"}, {1, 2, 3, 4, 5, 6, 7}),
        ({"university": "НИЯУ МИФИ"}, {1, 2, 3, 7}),
        ({"faculty": "ИИКС"}, {1, 2}),
        ({"blood_type": "O(I)"}, {1, 3}),
        
        # --- РОЛЕВЫЕ ФИЛЬТРЫ ---
        ({"role": "volunteers"}, {3, 5, 7}), # volunteer, admin, main_admin
        ({"role": "admins"}, {5, 7}), # admin, main_admin
        
        # --- КОМПЛЕКСНЫЕ ФИЛЬТРЫ С РОЛЯМИ ---
        # Сценарий 1: Волонтеры из НИЯУ МИФИ
        ({"role": "volunteers", "university": "НИЯУ МИФИ"}, {3, 7}),
        
        # Сценарий 2: Админы с группой крови A(II) -> только пользователь 5
        ({"role": "admins", "blood_type": "A(II)"}, {5}),
        
        # Сценарий 3: Волонтеры с факультета ВМК -> только пользователь 5 (т.к. админ - тоже волонтер)
        ({"role": "volunteers", "faculty": "ВМК"}, {5}),
        
        # Сценарий 4: Студенты из НИЯУ МИФИ с I группой крови (роль "all" игнорируется, если есть другие фильтры)
        ({"role": "all", "university": "НИЯУ МИФИ", "blood_type": "O(I)"}, {1, 3}),
        
        # Сценарий 5: Админы из НИЯУ МИФИ
        ({"role": "admins", "university": "НИЯУ МИФИ"}, {7}),
    ]
)
# --- ВАЖНО: УБИРАЕМ session ИЗ ПАРАМЕТРОВ ТЕСТА, Т.К. ОН НЕ ИСПОЛЬЗУЕТСЯ НАПРЯМУЮ, А НУЖЕН ФИКСТУРЕ ---
async def test_get_users_for_mailing_complex_with_roles(session: AsyncSession, filters, expected_user_ids):
    """
    Тестирует функцию фильтрации пользователей с комплексными фильтрами, включая роли.
    """
    # Фикстура setup_users уже выполнилась и создала пользователей
    users = await user_requests.get_users_for_mailing(session, filters)
    actual_user_ids = {user.id for user in users}
    assert actual_user_ids == expected_user_ids

# Этот тест также будет использовать фикстуру setup_users
async def test_get_distinct_faculties(session: AsyncSession):
    """Тестирует получение списка уникальных факультетов, исключая None."""
    faculties = await admin_requests.get_distinct_faculties(session)
    assert sorted(faculties) == ["Администрация", "ВМК", "ИИКС", "ИФИБ"]