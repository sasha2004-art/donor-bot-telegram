import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import datetime

from bot.db.models import User, Donation, MedicalWaiver, Survey, EventRegistration, Event
from bot.db.analytics_requests import (
    get_churn_donors,
    get_lapsed_donors,
    get_top_donors,
    get_rare_blood_donors,
    get_top_faculties,
    get_dkm_candidates,
    get_survey_dropoff
)

@pytest.mark.asyncio
async def test_get_churn_donors(session: AsyncSession):
    # Arrange
    user1 = User(id=1, full_name="Churn Donor", telegram_id=111, phone_number="111")
    donation1 = Donation(id=1, user_id=1, donation_date=datetime.datetime.now() - datetime.timedelta(days=200))
    user2 = User(id=2, full_name="Active Donor", telegram_id=222, phone_number="222")
    donation2 = Donation(id=2, user_id=2, donation_date=datetime.datetime.now() - datetime.timedelta(days=30))
    user3 = User(id=3, full_name="Multiple Donor", telegram_id=333, phone_number="333")
    donation3_1 = Donation(id=3, user_id=3, donation_date=datetime.datetime.now() - datetime.timedelta(days=200))
    donation3_2 = Donation(id=4, user_id=3, donation_date=datetime.datetime.now() - datetime.timedelta(days=30))

    session.add_all([user1, donation1, user2, donation2, user3, donation3_1, donation3_2])
    await session.commit()

    # Act
    churn_donors = await get_churn_donors(session)

    # Assert
    assert len(churn_donors) == 1
    assert churn_donors[0]["full_name"] == "Churn Donor"

@pytest.mark.asyncio
async def test_get_lapsed_donors(session: AsyncSession):
    # Arrange
    user1 = User(id=4, full_name="Lapsed Donor", telegram_id=444, phone_number="444")
    donation1_1 = Donation(id=5, user_id=4, donation_date=datetime.datetime.now() - datetime.timedelta(days=300))
    donation1_2 = Donation(id=6, user_id=4, donation_date=datetime.datetime.now() - datetime.timedelta(days=400))
    
    user2 = User(id=5, full_name="Active Donor", telegram_id=555, phone_number="555")
    donation2_1 = Donation(id=7, user_id=5, donation_date=datetime.datetime.now() - datetime.timedelta(days=30))
    donation2_2 = Donation(id=8, user_id=5, donation_date=datetime.datetime.now() - datetime.timedelta(days=60))

    user3 = User(id=6, full_name="Lapsed With Waiver", telegram_id=666, phone_number="666")
    donation3_1 = Donation(id=9, user_id=6, donation_date=datetime.datetime.now() - datetime.timedelta(days=300))
    donation3_2 = Donation(id=10, user_id=6, donation_date=datetime.datetime.now() - datetime.timedelta(days=400))
    waiver = MedicalWaiver(id=1, user_id=6, end_date=datetime.date.today() + datetime.timedelta(days=30))


    session.add_all([user1, donation1_1, donation1_2, user2, donation2_1, donation2_2, user3, donation3_1, donation3_2, waiver])
    await session.commit()

    # Act
    lapsed_donors = await get_lapsed_donors(session)

    # Assert
    assert len(lapsed_donors) == 1
    assert lapsed_donors[0]["full_name"] == "Lapsed Donor"

@pytest.mark.asyncio
async def test_get_top_donors(session: AsyncSession):
    # Arrange
    users_donations = []
    for i in range(7, 28): # 21 users
        user = User(id=i, full_name=f"User {i}", telegram_id=i*100, phone_number=str(i*100))
        users_donations.append(user)
        for j in range(i-6): # User 7 has 1 donation, User 8 has 2, etc.
            donation = Donation(user_id=i, donation_date=datetime.datetime.now())
            users_donations.append(donation)
    
    session.add_all(users_donations)
    await session.commit()
    
    # Act
    top_donors = await get_top_donors(session)
    
    # Assert
    assert len(top_donors) == 20
    assert top_donors[0]['full_name'] == 'User 27'
    assert top_donors[0]['donation_count'] == 21
    assert top_donors[19]['full_name'] == 'User 8'
    assert top_donors[19]['donation_count'] == 2

@pytest.mark.asyncio
async def test_get_rare_blood_donors(session: AsyncSession):
    # Arrange
    user1 = User(id=28, full_name="Rare AB", telegram_id=280, phone_number="280", blood_type="AB(IV)", rh_factor="+")
    user2 = User(id=29, full_name="Rare Rh-", telegram_id=290, phone_number="290", blood_type="A(II)", rh_factor="-")
    user3 = User(id=30, full_name="Common", telegram_id=300, phone_number="300", blood_type="O(I)", rh_factor="+")

    session.add_all([user1, user2, user3])
    await session.commit()

    # Act
    rare_donors = await get_rare_blood_donors(session)

    # Assert
    assert len(rare_donors) == 2
    names = {d['full_name'] for d in rare_donors}
    assert "Rare AB" in names
    assert "Rare Rh-" in names

@pytest.mark.asyncio
async def test_get_top_faculties(session: AsyncSession):
    # Arrange
    user1 = User(id=31, full_name="F1 Donor 1", telegram_id=310, phone_number="310", university="НИЯУ МИФИ", faculty="F1")
    user2 = User(id=32, full_name="F1 Donor 2", telegram_id=320, phone_number="320", university="НИЯУ МИФИ", faculty="F1")
    user3 = User(id=33, full_name="F2 Donor 1", telegram_id=330, phone_number="330", university="НИЯУ МИФИ", faculty="F2")
    user4 = User(id=34, full_name="Other Uni Donor", telegram_id=340, phone_number="340", university="Другой", faculty="F3")

    donations = [
        Donation(user_id=31, donation_date=datetime.datetime.now()),
        Donation(user_id=31, donation_date=datetime.datetime.now()),
        Donation(user_id=32, donation_date=datetime.datetime.now()),
        Donation(user_id=33, donation_date=datetime.datetime.now()),
        Donation(user_id=34, donation_date=datetime.datetime.now()),
    ]
    
    session.add_all([user1, user2, user3, user4] + donations)
    await session.commit()

    # Act
    top_faculties = await get_top_faculties(session)

    # Assert
    assert len(top_faculties) == 2
    assert top_faculties[0]['faculty_name'] == 'F1'
    assert top_faculties[0]['donation_count'] == 3
    assert top_faculties[1]['faculty_name'] == 'F2'
    assert top_faculties[1]['donation_count'] == 1

@pytest.mark.asyncio
async def test_get_dkm_candidates(session: AsyncSession):
    # Arrange
    user1 = User(id=35, full_name="DKM Candidate", telegram_id=350, phone_number="350", is_dkm_donor=False)
    d1 = Donation(user_id=35, donation_date=datetime.datetime.now())
    d2 = Donation(user_id=35, donation_date=datetime.datetime.now())
    
    user2 = User(id=36, full_name="Already DKM", telegram_id=360, phone_number="360", is_dkm_donor=True)
    d3 = Donation(user_id=36, donation_date=datetime.datetime.now())
    d4 = Donation(user_id=36, donation_date=datetime.datetime.now())

    user3 = User(id=37, full_name="Not enough donations", telegram_id=370, phone_number="370", is_dkm_donor=False)
    d5 = Donation(user_id=37, donation_date=datetime.datetime.now())
    
    session.add_all([user1, user2, user3, d1, d2, d3, d4, d5])
    await session.commit()
    
    # Act
    dkm_candidates = await get_dkm_candidates(session)
    
    # Assert
    assert len(dkm_candidates) == 1
    assert dkm_candidates[0]['full_name'] == 'DKM Candidate'

@pytest.mark.asyncio
async def test_get_survey_dropoff(session: AsyncSession):
    # Arrange
    user1 = User(id=38, full_name="Dropoff User", telegram_id=380, phone_number="380")
    survey1 = Survey(id=1, user_id=38, passed=True, created_at=datetime.datetime.now() - datetime.timedelta(days=10))
    
    user2 = User(id=39, full_name="Registered User", telegram_id=390, phone_number="390")
    survey2 = Survey(id=2, user_id=39, passed=True, created_at=datetime.datetime.now() - datetime.timedelta(days=10))
    event1 = Event(id=1, name="event 1", event_datetime=datetime.datetime.now())
    reg2 = EventRegistration(id=1, user_id=39, event_id=1, registration_date=datetime.datetime.now() - datetime.timedelta(days=5))

    user3 = User(id=40, full_name="Failed Survey User", telegram_id=400, phone_number="400")
    survey3 = Survey(id=3, user_id=40, passed=False, created_at=datetime.datetime.now() - datetime.timedelta(days=10))
    
    session.add_all([user1, survey1, user2, survey2, event1, reg2, user3, survey3])
    await session.commit()
    
    # Act
    survey_dropoff = await get_survey_dropoff(session)
    
    # Assert
    assert len(survey_dropoff) == 1
    assert survey_dropoff[0]['full_name'] == 'Dropoff User'