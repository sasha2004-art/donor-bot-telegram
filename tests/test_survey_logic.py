# ФАЙЛ: tests/test_survey_logic.py

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

# ИСПРАВЛЕНО: Создаем полный набор "здоровых" ответов, соответствующий новой модели
full_healthy_answers = {
    "age": "yes",
    "weight": "yes",
    "health_issues_last_month": "no",
    "symptoms": "no",
    "pressure": "ok",
    "hemoglobin_level": "ok",
    "diet_followed": "yes",
    "alcohol_last_48h": "no",
    "medication_last_72h": "no",
    "sleep_last_night": "yes",
    "smoking_last_hour": "no",
    "tattoo_or_piercing": "no",
    "tooth_removal_last_10_days": "no",
    "antibiotics_last_2_weeks": "no",
    "analgesics_last_3_days": "no",
    "has_hiv_or_hepatitis": "no",
    "has_cancer_or_blood_disease": "no",
    "has_chronic_disease": "no",
}


# --- Тест 1: Проверка "движка правил" ---
@pytest.mark.parametrize(
    "modified_answer, user_gender, expected_status, expected_days, expected_reason_part",
    [
        # Сценарий "OK"
        ({}, "male", "ok", 0, "Противопоказаний не выявлено"),
        # Сценарии временных отводов
        ({"age": "no"}, "male", "temp_waiver", 365000, "Возраст"),
        ({"weight": "no"}, "male", "temp_waiver", 365000, "Вес менее 50 кг"),
        ({"health_issues_last_month": "yes"}, "male", "temp_waiver", 30, "ОРВИ"),
        ({"symptoms": "yes"}, "male", "temp_waiver", 30, "ОРВИ"),
        (
            {"tooth_removal_last_10_days": "yes"},
            "male",
            "temp_waiver",
            10,
            "Удаление зуба",
        ),
        (
            {"tattoo_or_piercing": "yes"},
            "male",
            "temp_waiver",
            120,
            "татуировки/пирсинга",
        ),
        (
            {"antibiotics_last_2_weeks": "yes"},
            "male",
            "temp_waiver",
            14,
            "антибиотиков",
        ),
        ({"analgesics_last_3_days": "yes"}, "male", "temp_waiver", 3, "анальгетиков"),
        ({"medication_last_72h": "yes"}, "male", "temp_waiver", 3, "лекарств"),
        ({"alcohol_last_48h": "yes"}, "male", "temp_waiver", 2, "алкоголя"),
        # Сценарии "мягких" рекомендаций (статус 'ok')
        ({"diet_followed": "no"}, "male", "ok", 0, "диеты"),
        ({"sleep_last_night": "no"}, "male", "ok", 0, "Недостаточный сон"),
        ({"smoking_last_hour": "yes"}, "male", "ok", 0, "Курение"),
        # Сценарии абсолютных противопоказаний (отвод на 1000 лет)
        (
            {"has_hiv_or_hepatitis": "yes"},
            "male",
            "temp_waiver",
            365000,
            "Абсолютное противопоказание",
        ),
        (
            {"has_cancer_or_blood_disease": "yes"},
            "male",
            "temp_waiver",
            365000,
            "Абсолютное противопоказание",
        ),
        (
            {"has_chronic_disease": "yes"},
            "male",
            "temp_waiver",
            365000,
            "Абсолютное противопоказание",
        ),
    ],
)
async def test_process_survey_rules(
    modified_answer, user_gender, expected_status, expected_days, expected_reason_part
):
    """Тестирует обновленный движок правил с новой моделью данных."""
    answers_dict = full_healthy_answers.copy()
    answers_dict.update(modified_answer)
    answers_obj = SurveyAnswers(**answers_dict)

    status, days, reason = await process_survey_rules(answers_obj, user_gender)

    assert status == expected_status
    assert days == expected_days
    assert expected_reason_part in reason


# --- Тесты 2: Проверка логики submit_survey_logic ---


async def create_test_user(
    session: AsyncSession, tg_id=123, is_blocked=False, gender="male"
):
    """Вспомогательная функция для создания тестового пользователя."""
    user = User(
        phone_number=f"+{tg_id}",
        telegram_id=tg_id,
        full_name="Test User",
        university="Test",
        is_blocked=is_blocked,
        gender=gender,
    )
    session.add(user)
    await session.commit()
    return user


async def test_api_submit_survey_ok(session: AsyncSession):
    """Тестирует успешный сценарий: submit_survey_logic должна вернуть данные для отправки сообщения."""
    user = await create_test_user(session)
    answers = SurveyAnswers(**full_healthy_answers)  # ИСПОЛЬЗУЕМ НОВЫЙ СЛОВАРЬ
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")

    # Мокаем валидатор, чтобы не проверять хеши в этом юнит-тесте
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "main.validate_telegram_data", lambda auth_data: {"id": user.telegram_id}
        )

        # Вызываем логику и получаем результат
        chat_id, text, markup = await submit_survey_logic(session, payload)

    # Проверяем, что в БД появилась запись об опросе
    survey_record = (
        await session.execute(select(Survey).where(Survey.user_id == user.id))
    ).scalar_one()
    assert survey_record.passed is True
    assert "Противопоказаний не выявлено" in survey_record.verdict_text

    # Проверяем, что не создался медотвод
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one_or_none()
    assert waiver is None

    # Проверяем, что функция вернула правильные данные для отправки
    assert chat_id == user.telegram_id
    assert "Противопоказаний не найдено" in text
    assert (
        "мероприятий для записи сейчас нет" in text
    )  # т.к. мероприятий мы не создавали
    assert markup is None  # Клавиатуры нет, т.к. нет мероприятий


async def test_api_submit_survey_temp_waiver(session: AsyncSession):
    """Тестирует сценарий временного отвода: submit_survey_logic должна создать медотвод."""
    user = await create_test_user(session)
    answers_dict = full_healthy_answers.copy()
    answers_dict["symptoms"] = "yes"
    answers = SurveyAnswers(**answers_dict)  # ИСПОЛЬЗУЕМ НОВЫЙ СЛОВАРЬ
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "main.validate_telegram_data", lambda auth_data: {"id": user.telegram_id}
        )
        chat_id, text, markup = await submit_survey_logic(session, payload)

    # Проверяем, что создался медотвод на 30 дней
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one()
    expected_end_date = datetime.date.today() + datetime.timedelta(days=30)
    assert waiver is not None
    assert waiver.user_id == user.id
    assert waiver.end_date == expected_end_date
    assert "ОРВИ" in waiver.reason

    # Проверяем возвращенные данные
    assert chat_id == user.telegram_id
    assert "выявлено противопоказание" in text
    assert expected_end_date.strftime("%d.%m.%Y") in text


async def test_api_submit_survey_perm_waiver_is_now_temp(session: AsyncSession):
    """Тестирует, что постоянный отвод теперь работает как временный на 1000 лет."""
    user = await create_test_user(session)
    answers_dict = full_healthy_answers.copy()
    answers_dict["has_hiv_or_hepatitis"] = "yes"
    answers = SurveyAnswers(**answers_dict)  # ИСПОЛЬЗУЕМ НОВЫЙ СЛОВАРЬ
    payload = SurveyPayload(survey_data=answers, auth_string="valid_auth_string")

    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "main.validate_telegram_data", lambda auth_data: {"id": user.telegram_id}
        )
        chat_id, text, markup = await submit_survey_logic(session, payload)

    # Проверяем, что НЕ создалась запись о блокировке
    block_record = (
        await session.execute(select(UserBlock).where(UserBlock.user_id == user.id))
    ).scalar_one_or_none()
    assert block_record is None

    # Проверяем, что пользователь НЕ заблокирован
    await session.refresh(user)
    assert user.is_blocked is False

    # Проверяем, что создался медотвод на 365000 дней
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one()
    expected_end_date = datetime.date.today() + datetime.timedelta(days=365000)
    assert waiver is not None
    assert "Абсолютное противопоказание" in waiver.reason
    assert waiver.end_date == expected_end_date

    # Проверяем возвращенные данные
    assert "установили вам медотвод" in text
    assert expected_end_date.strftime("%d.%m.%Y") in text
