import pytest
import datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Мы тестируем process_survey_rules из main, так что импортируем оттуда
from main import process_survey_rules, SurveyAnswers
# А вот submit_survey_logic мы теперь тестируем по-новому
from main import submit_survey_logic, SurveyPayload 
from bot.db.models import User, Survey, MedicalWaiver, UserBlock

# Маркируем все тесты в этом файле для pytest-asyncio
pytestmark = pytest.mark.asyncio

# Создаем базовый набор "здоровых" ответов
default_answers = {
    "feeling": "good", "weight": "no", "symptoms": "no",
    "tattoo": "no", "tooth": "no", "vaccine": "no", "vaccine_type": None,
    "antibiotics": "no", "aspirin": "no", "contact_hepatitis": "no",
    "diseases_absolute": "no", "diseases_chronic": "no",
    "travel": "no", "alcohol": "no"
}

# --- Тест 1: Проверка "движка правил" ---
@pytest.mark.parametrize("modified_answer, expected_status, expected_days, expected_reason_part", [
    # Сценарий "OK"
    ({}, "ok", 0, "Противопоказаний не выявлено"),
    # Сценарии временных отводов
    ({"symptoms": "yes"}, "temp_waiver", 14, "Симптомы ОРВИ"),
    ({"feeling": "bad"}, "temp_waiver", 3, "Плохое самочувствие"),
    ({"tattoo": "yes"}, "temp_waiver", 120, "татуировки"),
    ({"alcohol": "yes"}, "temp_waiver", 2, "алкоголя"),
    ({"vaccine": "yes", "vaccine_type": "live"}, "temp_waiver", 30, "вакцинация"),
    ({"vaccine": "yes", "vaccine_type": "killed"}, "temp_waiver", 10, "вакцинация"),
    
    # --- ИСПРАВЛЕННЫЕ СЦЕНАРИИ "ПОСТОЯННЫХ" ОТВОДОВ ---
    # Теперь это временный отвод на 1000 лет
    ({"diseases_absolute": "yes"}, "temp_waiver", 365000, "Абсолютное противопоказание"),
    # Это тоже временный отвод на 1000 лет
    ({"weight": "yes"}, "temp_waiver", 365000, "Вес менее 50 кг"),
])
async def test_process_survey_rules(modified_answer, expected_status, expected_days, expected_reason_part):
    """Тестирует обновленный движок правил."""
    answers_dict = default_answers.copy()
    answers_dict.update(modified_answer)
    answers_obj = SurveyAnswers(**answers_dict)
    
    status, days, reason = await process_survey_rules(answers_obj)
    
    assert status == expected_status
    assert days == expected_days
    assert expected_reason_part in reason

# --- Тесты 2: Проверка логики submit_survey_logic ---

async def create_test_user(session: AsyncSession, tg_id=123, is_blocked=False):
    """Вспомогательная функция для создания тестового пользователя."""
    user = User(
        phone_number=f"+{tg_id}", telegram_id=tg_id, full_name="Test User",
        university="Test", is_blocked=is_blocked
    )
    session.add(user)
    await session.commit()
    return user

async def test_api_submit_survey_ok(session: AsyncSession):
    """Тестирует успешный сценарий: submit_survey_logic должна вернуть данные для отправки сообщения."""
    user = await create_test_user(session)
    answers = SurveyAnswers(**default_answers)
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")
    
    # Мокаем валидатор, чтобы не проверять хеши в этом юнит-тесте
    with pytest.MonkeyPatch.context() as m:
        m.setattr("main.validate_telegram_data", lambda auth_data: {'id': user.telegram_id})
        
        # Вызываем логику и получаем результат
        chat_id, text, markup = await submit_survey_logic(session, payload)

    # Проверяем, что в БД появилась запись об опросе
    survey_record = (await session.execute(select(Survey).where(Survey.user_id == user.id))).scalar_one()
    assert survey_record.passed is True
    assert "Противопоказаний не выявлено" in survey_record.verdict_text
    
    # Проверяем, что не создался медотвод
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one_or_none()
    assert waiver is None
    
    # Проверяем, что функция вернула правильные данные для отправки
    assert chat_id == user.telegram_id
    assert "Противопоказаний не найдено" in text
    assert "мероприятий для записи сейчас нет" in text # т.к. мероприятий мы не создавали
    assert markup is None # Клавиатуры нет, т.к. нет мероприятий

async def test_api_submit_survey_temp_waiver(session: AsyncSession):
    """Тестирует сценарий временного отвода: submit_survey_logic должна создать медотвод."""
    user = await create_test_user(session)
    answers_dict = default_answers.copy()
    answers_dict["symptoms"] = "yes"
    answers = SurveyAnswers(**answers_dict)
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")

    with pytest.MonkeyPatch.context() as m:
        m.setattr("main.validate_telegram_data", lambda auth_data: {'id': user.telegram_id})
        chat_id, text, markup = await submit_survey_logic(session, payload)
    
    # Проверяем, что создался медотвод на 14 дней
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one()
    expected_end_date = datetime.date.today() + datetime.timedelta(days=14)
    assert waiver is not None
    assert waiver.user_id == user.id
    assert waiver.end_date == expected_end_date
    assert "Симптомы ОРВИ" in waiver.reason
    
    # Проверяем возвращенные данные
    assert chat_id == user.telegram_id
    # --- ИСПРАВЛЕНИЕ 1 ---
    assert "выявлено противопоказание" in text
    assert expected_end_date.strftime('%d.%m.%Y') in text

async def test_api_submit_survey_perm_waiver_is_now_temp(session: AsyncSession):
    """Тестирует, что постоянный отвод теперь работает как временный на 1000 лет."""
    user = await create_test_user(session)
    answers_dict = default_answers.copy()
    answers_dict["diseases_absolute"] = "yes"
    answers = SurveyAnswers(**answers_dict)
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")

    with pytest.MonkeyPatch.context() as m:
        m.setattr("main.validate_telegram_data", lambda auth_data: {'id': user.telegram_id})
        chat_id, text, markup = await submit_survey_logic(session, payload)

    # Проверяем, что НЕ создалась запись о блокировке
    block_record = (await session.execute(select(UserBlock).where(UserBlock.user_id == user.id))).scalar_one_or_none()      
    assert block_record is None

    # Проверяем, что пользователь НЕ заблокирован
    await session.refresh(user)
    assert user.is_blocked is False

    # Проверяем, что создался медотвод на 365000 дней
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one()
    expected_end_date = datetime.date.today() + datetime.timedelta(days=365000)
    assert waiver is not None
    assert waiver.reason == "Абсолютное противопоказание (хронические/инфекционные заболевания)."
    assert waiver.end_date == expected_end_date

    # Проверяем возвращенные данные
    # --- ИСПРАВЛЕНИЕ 2 ---
    assert "установили вам медотвод" in text
    assert expected_end_date.strftime('%d.%m.%Y') in text