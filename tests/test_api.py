# ФАЙЛ: tests/test_api.py

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from main import app, SurveyPayload, SurveyAnswers
from bot.db.models import User, Survey, MedicalWaiver
from tests.test_security import generate_test_auth_data
from bot.config_reader import config
from tests.conftest import TestSessionMaker


async def override_get_session():
    async with TestSessionMaker() as session:
        yield session


from main import app, get_session
from tests.conftest import TestSessionMaker


async def override_get_session():
    async with TestSessionMaker() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}


# --- Тесты ---


async def test_health_check(client: AsyncClient):
    """Тестирует эндпоинт /health."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_submit_survey_failure_bad_payload(client: AsyncClient):
    """Тест: Отправка некорректного JSON."""
    response = await client.post("/api/submit_survey", content="this is not json")
    assert response.status_code == 400


async def test_submit_survey_failure_invalid_auth(client: AsyncClient):
    """Тест: Отправка данных с неверным хешем."""
    # ИСПРАВЛЕНО: Payload теперь содержит все обязательные поля для SurveyAnswers
    payload = {
        "survey_data": {
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
        },
        "auth_string": "invalid_hash_string",
    }
    response = await client.post("/api/submit_survey", json=payload)
    # Теперь мы ожидаем 403, так как валидация payload пройдет, а валидация auth_string - нет
    assert response.status_code == 403
