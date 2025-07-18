import pytest
import datetime
from bot.utils.calendar_service import generate_ics_file
from bot.db.models import Event

def test_generate_ics_file():
    """
    Тестирует корректность генерации содержимого .ics файла.
    Адаптирован для ics==0.7.2, который конвертирует время в UTC.
    """
    # 1. Подготовка "фейкового" мероприятия.
    # Используем английский ключ, как в БД.
    mock_event = Event(
        id=123,
        name="Тестовое мероприятие",
        event_datetime=datetime.datetime(2025, 10, 26, 14, 0, 0), 
        location="НИЯУ МИФИ, Каширское ш. 31",
        donation_type="plasma" 
    )

    # 2. Генерация контента
    ics_string = generate_ics_file(mock_event)

    # 3. Проверки
    assert "BEGIN:VCALENDAR" in ics_string
    assert "SUMMARY:Донация: Тестовое мероприятие" in ics_string
    assert "LOCATION:НИЯУ МИФИ\\, Каширское ш. 31" in ics_string
    assert "DESCRIPTION:Тип донации: Плазма" in ics_string
    assert "DTSTART:20251026T110000Z" in ics_string
    assert "DTEND:20251026T130000Z" in ics_string

    # Проверяем наличие будильника
    assert "ACTION:DISPLAY" in ics_string
    assert "TRIGGER:-PT1H" in ics_string