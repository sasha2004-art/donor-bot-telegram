# tests/test_security.py

import pytest
import hmac
import hashlib
import json
from urllib.parse import urlencode
from fastapi import HTTPException

# Импортируем тестируемую функцию и конфиг
from main import validate_telegram_data
from bot.config_reader import config

# --- Вспомогательная функция для генерации корректной строки авторизации ---
def generate_test_auth_data(user_data_dict: dict, bot_token: str) -> str:
    """Генерирует валидную строку initData для тестов."""
    
    # ИСПРАВЛЕНИЕ: Используем json.dumps для корректной сериализации Python-словаря в JSON-строку.
    # separators убирает лишние пробелы, sort_keys обеспечивает одинаковый порядок ключей.
    user_data_str = json.dumps(user_data_dict, separators=(',', ':'), sort_keys=True)
    
    # Собираем данные для хеширования (кроме самого хеша)
    data_to_sign = {
        'auth_date': '1700000000',
        'query_id': 'AAg123456789',
        'user': user_data_str
    }
    
    # Сортируем и формируем строку для проверки (data_check_string)
    sorted_items = sorted(data_to_sign.items())
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted_items])
    
    # Вычисляем хеш точно так же, как это делает Telegram
    secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    # Добавляем хеш к данным и формируем финальную строку
    data_to_sign['hash'] = calculated_hash
    
    return urlencode(data_to_sign)


# --- Тесты ---

def test_validate_telegram_data_success():
    """Тест успешной валидации с корректными данными."""
    bot_token = config.bot_token.get_secret_value()
    user_data = {
        "id": 12345678,
        "first_name": "John",
        "last_name": "Doe",
        "username": "johndoe",
        "language_code": "en",
        "is_premium": True
    }
    
    auth_string = generate_test_auth_data(user_data, bot_token)
    
    # Выполняем валидацию
    validated_user_data = validate_telegram_data(auth_string)
    
    # Проверяем, что результат совпадает с исходными данными
    assert validated_user_data['id'] == user_data['id']
    assert validated_user_data['username'] == user_data['username']
    assert validated_user_data['is_premium'] is True


def test_validate_telegram_data_invalid_hash():
    """Тест провала валидации из-за неверного хеша."""
    bot_token = config.bot_token.get_secret_value()
    user_data = {"id": 123, "username": "test"}
    
    auth_string = generate_test_auth_data(user_data, bot_token)
    
    # Искажаем хеш
    tampered_auth_string = auth_string[:-10] + "abcdefghij"
    
    with pytest.raises(HTTPException) as excinfo:
        validate_telegram_data(tampered_auth_string)
        
    assert excinfo.value.status_code == 403
    # ИСПРАВЛЕНИЕ: Проверяем конкретное сообщение об ошибке, а не общее
    assert "Invalid hash" in str(excinfo.value.detail)


def test_validate_telegram_data_missing_hash():
    """Тест провала валидации из-за отсутствия хеша."""
    auth_string = "user=%7B%22id%22%3A+123%7D&auth_date=1700000000"
    
    with pytest.raises(HTTPException) as excinfo:
        validate_telegram_data(auth_string)
        
    assert excinfo.value.status_code == 403
    assert "Hash not found" in str(excinfo.value.detail)


def test_validate_telegram_data_tampered_data():
    """Тест провала валидации, если данные были изменены без пересчета хеша."""
    bot_token = config.bot_token.get_secret_value()
    user_data = {"id": 123}
    
    auth_string = generate_test_auth_data(user_data, bot_token)
    
    # Добавляем в строку новый параметр, который не участвовал в хешировании
    tampered_auth_string = auth_string + "&new_param=hacker"
    
    with pytest.raises(HTTPException) as excinfo:
        validate_telegram_data(tampered_auth_string)
        
    assert excinfo.value.status_code == 403
    assert "Invalid hash" in str(excinfo.value.detail)