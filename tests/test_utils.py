import pytest
import datetime
from unittest.mock import AsyncMock, Mock, patch

import datetime
from sqlalchemy import select 
from aiogram import Bot

from bot.utils.qr_service import create_secure_payload, verify_secure_payload
from bot.utils.scheduler import check_waiver_expirations
from bot.db.models import User, Event, EventRegistration, MedicalWaiver


# --- Тесты QR-кодов (без изменений) ---
def test_qr_payload_creation_and_verification():
    original_data = {"user_id": 12345, "event_id": 678}
    payload = create_secure_payload(original_data)
    verified_data = verify_secure_payload(payload)
    assert isinstance(payload, str)
    assert verified_data is not None
    assert verified_data == original_data

def test_qr_verification_failure_with_bad_hash():
    original_data = {"user_id": 999}
    payload = create_secure_payload(original_data)
    tampered_payload = payload[:-5] + "abcde"
    verified_data = verify_secure_payload(tampered_payload)
    assert verified_data is None

def test_qr_verification_failure_with_bad_format():
    bad_payload = "this_is_not_a_valid_payload"
    verified_data = verify_secure_payload(bad_payload)
    assert verified_data is None


@pytest.mark.asyncio
async def test_check_waiver_expirations(mocker, session_pool): # <-- Убираем фикстуру session
    """Тестирует отправку уведомлений об истечении медотводов."""
    
    fixed_today = datetime.date(2024, 5, 20)
    
    # Мокируем `datetime.date` как и раньше
    with patch('bot.utils.scheduler.datetime.date') as mock_date:
        
        mock_date.today.return_value = fixed_today
        yesterday_in_test = fixed_today - datetime.timedelta(days=1)
    
        # --- Создаем данные внутри новой сессии, как это сделала бы реальная функция ---
        async with session_pool() as session:
            user_expired = User(phone_number="+7771", telegram_id=7771, full_name="Expired", university="TestUni")
            user_active = User(phone_number="+7772", telegram_id=7772, full_name="Active", university="TestUni")
            session.add_all([user_expired, user_active])
            await session.flush()
    
            waiver_expired = MedicalWaiver(
                user_id=user_expired.id, 
                start_date=yesterday_in_test - datetime.timedelta(days=30),
                end_date=yesterday_in_test,
                reason="test", created_by="system"
            )
            waiver_active = MedicalWaiver(
                user_id=user_active.id,
                start_date=fixed_today - datetime.timedelta(days=10),
                end_date=fixed_today,
                reason="test", created_by="system"
            )
            session.add_all([waiver_expired, waiver_active])
            await session.commit() # Здесь коммит необходим, чтобы данные сохранились для следующей сессии

        # Настраиваем моки для вызова
        mock_send_message = mocker.patch('aiogram.Bot.send_message', new_callable=AsyncMock)
        mock_bot = Mock(spec=Bot)
        mock_bot.send_message = mock_send_message

        # Вызываем тестируемую функцию
        await check_waiver_expirations(mock_bot, session_pool)
    
        # Проверяем результат
        mock_send_message.assert_called_once()
        call_args = mock_send_message.call_args
        assert call_args.kwargs['chat_id'] == 7771
        
        expected_phrase = "срок вашего медицинского отвода истек"
        actual_text = call_args.kwargs['text']
        assert expected_phrase.lower() in actual_text.lower()

        # Дополнительная проверка, что в БД все чисто для следующего теста
        async with session_pool() as session:
            res = await session.execute(select(User))
            assert len(res.scalars().all()) > 0 # Данные есть
    # После выхода из async with фикстура session в conftest.py очистит данные