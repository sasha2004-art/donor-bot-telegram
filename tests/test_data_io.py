import pytest
import pandas as pd
import io
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.handlers.admin.system import create_full_backup_xlsx
from bot.utils.data_import import import_data_from_file
from bot.db.models import User, Donation

pytestmark = pytest.mark.asyncio

# --- Тест Экспорта ---


async def test_create_full_backup_xlsx(session: AsyncSession):
    """Тест: Проверяет, что экспорт создает корректный XLSX файл."""
    # 1. Подготовка: Наполняем БД тестовыми данными
    user1 = User(
        id=1,
        phone_number="+1",
        telegram_id=1,
        full_name="User Export",
        university="Test",
        #points=50,
    )
    donation1 = Donation(
        id=1,
        user_id=1,
        donation_date=date(2024, 1, 1),
        donation_type="test",
        #points_awarded=50,
    )
    session.add_all([user1, donation1])
    await session.commit()

    # 2. Выполнение: Вызываем функцию экспорта
    xlsx_bytes_io = await create_full_backup_xlsx(session)

    # 3. Проверка
    assert isinstance(xlsx_bytes_io, io.BytesIO)
    xlsx_bytes_io.seek(0)  # Перематываем "файл" в начало для чтения

    # Читаем XLSX с помощью pandas
    xls = pd.ExcelFile(xlsx_bytes_io)

    # Проверяем наличие нужных листов
    assert "Users" in xls.sheet_names
    assert "Donations" in xls.sheet_names

    # Читаем данные с листа и проверяем содержимое
    users_df = pd.read_excel(xls, sheet_name="Users")
    assert len(users_df) == 1
    assert users_df.iloc[0]["full_name"] == "User Export"
    # assert users_df.iloc[0]["#points"] == 50


# --- Тесты Импорта ---


async def test_import_data_from_file_create_and_update(session: AsyncSession):
    """Тест: Проверяет создание новых и обновление существующих пользователей при импорте."""
    # 1. Подготовка
    # Пользователь, который уже есть в БД
    existing_user = User(
        id=1,
        phone_number="+79000000000",
        telegram_id=1,
        full_name="Старое Имя",
        university="Test",
    )
    session.add(existing_user)
    await session.commit()

    # Готовим "файл" для импорта
    import_data = {
        "ФИО": ["Старое Имя", "Новый Пользователь"],
        "Телефон": ["79000000000", "79111111111"],
        "Группа": ["Б20-505", "сотрудник"],
    }
    df = pd.DataFrame(import_data)

    output_buffer = io.BytesIO()
    df.to_excel(output_buffer, index=False, engine="openpyxl")
    output_buffer.seek(0)

    # 2. Выполнение
    created_count, updated_count = await import_data_from_file(session, output_buffer)

    # 3. Проверка
    assert created_count == 1
    assert updated_count == 1

    # Проверяем обновленного пользователя
    await session.refresh(existing_user)
    assert existing_user.study_group == "Б20-505"

    # Проверяем нового пользователя
    new_user = (
        await session.execute(select(User).where(User.phone_number == "+79111111111"))
    ).scalar_one()
    assert new_user.full_name == "Новый Пользователь"
    assert new_user.faculty == "Сотрудник"
    assert new_user.telegram_id < 0  # Убеждаемся, что ID временный


async def test_import_data_missing_column_raises_error():
    """Тест: Проверяет, что импорт падает с ошибкой, если нет обязательных колонок."""
    # 1. Подготовка: Создаем "плохой" файл без колонки 'Телефон'
    import_data = {"ФИО": ["Какой-то Пользователь"]}
    df = pd.DataFrame(import_data)

    output_buffer = io.BytesIO()
    df.to_excel(output_buffer, index=False, engine="openpyxl")
    output_buffer.seek(0)

    # 2. Выполнение и Проверка: Ожидаем ValueError
    with pytest.raises(ValueError, match="отсутствуют обязательные колонки"):
        # Передаем None вместо сессии, так как до работы с ней не дойдет
        await import_data_from_file(None, output_buffer)
