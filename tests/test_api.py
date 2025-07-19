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

from main import async_session_maker as main_session_maker


pytestmark = pytest.mark.asyncio

from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import TEST_DATABASE_URL

@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[main_session_maker] = override_get_session
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides = {}

# --- Тесты ---

async def test_health_check(client: AsyncClient):
    """Тестирует эндпоинт /health."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

async def test_submit_survey_success_ok(client: AsyncClient, session: AsyncSession):
    """Тест: Успешная отправка опросника без противопоказаний."""
    # 1. Подготовка
    user = User(phone_number="+1", telegram_id=12345, full_name="API User", university="Test")
    session.add(user)
    await session.commit()
    
    answers = {
        "feeling": "good", "weight": "no", "symptoms": "no", "tattoo": "no",
        "tooth": "no", "vaccine": "no", "vaccine_type": None, "antibiotics": "no",
        "aspirin": "no", "contact_hepatitis": "no", "diseases_absolute": "no",
        "diseases_chronic": "no", "travel": "no", "alcohol": "no"
    }
    
    user_data_for_auth = {"id": user.telegram_id, "username": "api_user"}
    auth_string = generate_test_auth_data(user_data_for_auth, config.bot_token.get_secret_value())
    
    payload = {"survey_data": answers, "auth_string": auth_string}

    # Мокаем отправку сообщения ботом, чтобы не было реальных сетевых вызовов
    mock_bot = AsyncMock()
    app.state.bot = mock_bot
    
    # 2. Выполнение
    response = await client.post("/api/submit_survey", json=payload)
    
    # 3. Проверка
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    
    # Проверяем, что в БД создалась запись опроса
    survey_record = (await session.execute(select(Survey))).scalar_one()
    assert survey_record.passed is True
    
    # Проверяем, что медотвод не создался
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one_or_none()
    assert waiver is None

    # Проверяем, что бот попытался отправить сообщение
    app.state.bot.send_message.assert_called_once()
    del app.state.bot # Очищаем мок

async def test_submit_survey_failure_bad_payload(client: AsyncClient):
    """Тест: Отправка некорректного JSON."""
    response = await client.post("/api/submit_survey", content="this is not json")
    assert response.status_code == 400

async def test_submit_survey_failure_invalid_auth(client: AsyncClient):
    """Тест: Отправка данных с неверным хешем."""
    payload = {
        "survey_data": {"feeling": "good", "weight": "no", "symptoms": "no", "tattoo": "no",
                        "tooth": "no", "vaccine": "no", "vaccine_type": None, "antibiotics": "no",
                        "aspirin": "no", "contact_hepatitis": "no", "diseases_absolute": "no",
                        "diseases_chronic": "no", "travel": "no", "alcohol": "no"},
        "auth_string": "invalid_hash_string"
    }
    response = await client.post("/api/submit_survey", json=payload)
    assert response.status_code == 403

async def test_submit_survey_failure_user_not_found(client: AsyncClient, session: AsyncSession):
    """Тест: Отправка данных для пользователя, которого нет в БД."""
    user_data_for_auth = {"id": 99999, "username": "ghost"}
    auth_string = generate_test_auth_data(user_data_for_auth, config.bot_token.get_secret_value())
    
    payload = {"survey_data": {"feeling": "good", "weight": "no", "symptoms": "no", "tattoo": "no",
                        "tooth": "no", "vaccine": "no", "vaccine_type": None, "antibiotics": "no",
                        "aspirin": "no", "contact_hepatitis": "no", "diseases_absolute": "no",
                        "diseases_chronic": "no", "travel": "no", "alcohol": "no"},
               "auth_string": auth_string}

    app.state.bot = AsyncMock()
    response = await client.post("/api/submit_survey", json=payload)
    del app.state.bot
    # Ожидаем 404, так как пользователь не найден
    assert response.status_code == 404