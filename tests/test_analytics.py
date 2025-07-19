# tests/test_analytics.py

import pytest
import datetime
from sqlalchemy.ext.asyncio import AsyncSession

# Правильный импорт из существующего модуля
from bot.db import analytics_requests
from bot.db.models import User, Donation, MedicalWaiver, Survey, Event, EventRegistration

pytestmark = pytest.mark.asyncio

# --- Тесты для функций из analytics_requests.py ---

async def test_get_churn_donors(session: AsyncSession):
    """
    Тест: Находит доноров-однодневок (1 донация, >6 мес. назад).
    """
    # Пользователь 1: подходит под условия
    user1 = User(id=1, full_name="Churn Donor", telegram_id=111, phone_number="111", university="Test")
    donation1 = Donation(user_id=1, donation_date=datetime.date.today() - datetime.timedelta(days=200), donation_type='whole_blood', points_awarded=10)
    
    # Пользователь 2: донация была недавно
    user2 = User(id=2, full_name="Active Donor", telegram_id=222, phone_number="222", university="Test")
    donation2 = Donation(user_id=2, donation_date=datetime.date.today() - datetime.timedelta(days=30), donation_type='whole_blood', points_awarded=10)
    
    # Пользователь 3: имеет несколько донаций
    user3 = User(id=3, full_name="Multiple Donor", telegram_id=333, phone_number="333", university="Test")
    donation3_1 = Donation(user_id=3, donation_date=datetime.date.today() - datetime.timedelta(days=200), donation_type='whole_blood', points_awarded=10)
    donation3_2 = Donation(user_id=3, donation_date=datetime.date.today() - datetime.timedelta(days=30), donation_type='plasma', points_awarded=10)

    session.add_all([user1, donation1, user2, donation2, user3, donation3_1, donation3_2])
    await session.commit()

    churn_donors = await analytics_requests.get_churn_donors(session)

    assert len(churn_donors) == 1
    assert churn_donors[0]['full_name'] == "Churn Donor"


async def test_get_lapsed_donors(session: AsyncSession):
    """
    Тест: Находит угасающих доноров (2+ донации, последняя >9 мес. назад, без медотвода).
    """
    # Пользователь 1: подходит под условия
    user1 = User(id=4, full_name="Lapsed Donor", telegram_id=444, phone_number="444", university="Test")
    d1_1 = Donation(user_id=4, donation_date=datetime.date.today() - datetime.timedelta(days=300), donation_type='whole_blood', points_awarded=10)
    d1_2 = Donation(user_id=4, donation_date=datetime.date.today() - datetime.timedelta(days=400), donation_type='whole_blood', points_awarded=10)

    # Пользователь 2: последняя донация была недавно
    user2 = User(id=5, full_name="Active Donor", telegram_id=555, phone_number="555", university="Test")
    d2_1 = Donation(user_id=5, donation_date=datetime.date.today() - datetime.timedelta(days=30), donation_type='whole_blood', points_awarded=10)
    d2_2 = Donation(user_id=5, donation_date=datetime.date.today() - datetime.timedelta(days=60), donation_type='plasma', points_awarded=10)

    # Пользователь 3: подходит по датам, но имеет активный медотвод
    user3 = User(id=6, full_name="Lapsed With Waiver", telegram_id=666, phone_number="666", university="Test")
    d3_1 = Donation(user_id=6, donation_date=datetime.date.today() - datetime.timedelta(days=300), donation_type='whole_blood', points_awarded=10)
    d3_2 = Donation(user_id=6, donation_date=datetime.date.today() - datetime.timedelta(days=400), donation_type='whole_blood', points_awarded=10)
    waiver = MedicalWaiver(user_id=6, start_date=datetime.date.today(), end_date=datetime.date.today() + datetime.timedelta(days=30), reason="test", created_by="system")

    session.add_all([user1, d1_1, d1_2, user2, d2_1, d2_2, user3, d3_1, d3_2, waiver])
    await session.commit()

    lapsed_donors = await analytics_requests.get_lapsed_donors(session)

    assert len(lapsed_donors) == 1
    assert lapsed_donors[0]['full_name'] == "Lapsed Donor"

async def test_get_survey_dropoff(session: AsyncSession):
    """
    Тест: Находит пользователей, прошедших опрос, но не записавшихся на мероприятие после этого.
    """
    # Пользователь 1: прошел опрос, не записался -> должен быть в списке
    user1 = User(id=38, full_name="Dropoff User", telegram_id=380, phone_number="380", university="Test")
    survey1 = Survey(user_id=38, passed=True, answers_json={}, created_at=datetime.datetime.now() - datetime.timedelta(days=10))

    # Пользователь 2: прошел опрос и записался ПОСЛЕ
    user2 = User(id=39, full_name="Registered User", telegram_id=390, phone_number="390", university="Test")
    survey2 = Survey(user_id=39, passed=True, answers_json={}, created_at=datetime.datetime.now() - datetime.timedelta(days=10))
    event1 = Event(name="event 1", event_datetime=datetime.datetime.now(), location="Центр крови", donation_type="d", points_per_donation=1, participant_limit=1)
    session.add(event1)
    await session.commit()
    reg2 = EventRegistration(user_id=39, event_id=event1.id, registration_date=datetime.datetime.now() - datetime.timedelta(days=5))

    # Пользователь 3: опрос не пройден
    user3 = User(id=40, full_name="Failed Survey User", telegram_id=400, phone_number="400", university="Test")
    survey3 = Survey(user_id=40, passed=False, answers_json={}, created_at=datetime.datetime.now() - datetime.timedelta(days=10))

    session.add_all([user1, survey1, user2, survey2, reg2, user3, survey3])
    await session.commit()
    
    dropoff_users = await analytics_requests.get_survey_dropoff(session)

    assert len(dropoff_users) == 1
    assert dropoff_users[0]['full_name'] == "Dropoff User"