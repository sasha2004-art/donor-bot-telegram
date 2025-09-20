import pytest
import pytest_asyncio
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from bot.db.models import Base, User, Event, EventRegistration, Donation, MedicalWaiver
from bot.db.event_requests import check_registration_eligibility, add_event_registration
from bot.db.models import Event as DbEvent  # Чтобы избежать конфликта имен

# --- Настройка тестовой базы данных в памяти ---

TEST_DATABASE_URL = "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_async_session_maker = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with test_async_session_maker() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# --- Фикстуры для создания тестовых данных ---


@pytest_asyncio.fixture
async def male_user(db_session: AsyncSession) -> User:
    user = User(
        phone_number="+79991112233",
        telegram_id=1,
        full_name="Тестовый Пользователь Мужчина",
        gender="male",
        university="Тестовый ВУЗ",  # <-- ИСПРАВЛЕНО
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def female_user(db_session: AsyncSession) -> User:
    user = User(
        phone_number="+79994445566",
        telegram_id=2,
        full_name="Тестовый Пользователь Женщина",
        gender="female",
        university="Тестовый ВУЗ",  # <-- ИСПРАВЛЕНО
    )
    db_session.add(user)
    await db_session.commit()
    return user


# --- Тесты для новой логики ---


@pytest.mark.asyncio
async def test_successful_registration(db_session: AsyncSession, male_user: User):
    """Тест: Успешная регистрация при отсутствии конфликтов."""
    event_date = datetime.date.today() + datetime.timedelta(days=10)
    event = DbEvent(  # <-- ИСПРАВЛЕНО: Явное указание модели
        name="Тестовая донация",
        event_datetime=datetime.datetime.combine(
            event_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Тестовая локация",
        points_per_donation=100,
    )
    db_session.add(event)
    await db_session.commit()

    is_eligible, reason = await check_registration_eligibility(
        db_session, male_user, event
    )

    assert is_eligible is True
    assert reason == "Все проверки пройдены."


@pytest.mark.asyncio
async def test_blocked_by_potential_waiver(db_session: AsyncSession, male_user: User):
    """
    Тест: Блокировка из-за ПОТЕНЦИАЛЬНОГО медотвода от другой будущей регистрации.
    """
    event_A_date = datetime.date.today() + datetime.timedelta(days=10)
    event_B_date = datetime.date.today() + datetime.timedelta(days=15)

    event_A = DbEvent(
        name="Донация А",
        event_datetime=datetime.datetime.combine(
            event_A_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Локация А",
        points_per_donation=100,
    )
    event_B = DbEvent(
        name="Донация Б",
        event_datetime=datetime.datetime.combine(
            event_B_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="plasma",
        participant_limit=10,
        location="Локация Б",
        points_per_donation=50,
    )
    db_session.add_all([event_A, event_B])
    await db_session.commit()

    await add_event_registration(db_session, male_user.id, event_A.id)

    is_eligible, reason = await check_registration_eligibility(
        db_session, male_user, event_B
    )

    assert is_eligible is False
    assert "запланирована донация" in reason
    assert "Донация А" in reason


@pytest.mark.asyncio
async def test_not_blocked_if_waiver_ends(db_session: AsyncSession, male_user: User):
    """
    Тест: Регистрация разрешена, если потенциальный медотвод закончится.
    """
    event_A_date = datetime.date.today() + datetime.timedelta(days=10)
    event_C_date = datetime.date.today() + datetime.timedelta(days=80)

    event_A = DbEvent(
        name="Донация А",
        event_datetime=datetime.datetime.combine(
            event_A_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Локация А",
        points_per_donation=100,
    )
    event_C = DbEvent(
        name="Донация С",
        event_datetime=datetime.datetime.combine(
            event_C_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="plasma",
        participant_limit=10,
        location="Локация C",
        points_per_donation=50,
    )
    db_session.add_all([event_A, event_C])
    await db_session.commit()

    await add_event_registration(db_session, male_user.id, event_A.id)

    is_eligible, reason = await check_registration_eligibility(
        db_session, male_user, event_C
    )

    assert is_eligible is True


@pytest.mark.asyncio
async def test_blocked_by_yearly_limit_combined(
    db_session: AsyncSession, female_user: User
):
    """
    Тест: Блокировка из-за годового лимита, учитывая прошлые и будущие донации.
    """
    # 2 прошлые донации
    db_session.add_all(
        [
            Donation(
                user_id=female_user.id,
                donation_date=datetime.date.today() - datetime.timedelta(days=200),
                donation_type="whole_blood",
                points_awarded=10,
            ),
            Donation(
                user_id=female_user.id,
                donation_date=datetime.date.today() - datetime.timedelta(days=300),
                donation_type="whole_blood",
                points_awarded=10,
            ),
        ]
    )

    # 1 будущая регистрация (донация №3)
    future_event_1_date = datetime.date.today() + datetime.timedelta(days=20)
    future_event_1 = DbEvent(
        name="Будущая 1",
        event_datetime=datetime.datetime.combine(
            future_event_1_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Локация 1",
        points_per_donation=100,
    )
    db_session.add(future_event_1)
    await db_session.commit()
    await add_event_registration(db_session, female_user.id, future_event_1.id)

    # Записываемся на 4-ю донацию. Должно быть успешно.
    event_ok_date = datetime.date.today() + datetime.timedelta(days=120)
    event_to_register_ok = DbEvent(
        name="Будущая 2 (OK)",
        event_datetime=datetime.datetime.combine(
            event_ok_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Локация 2",
        points_per_donation=100,
    )
    db_session.add(event_to_register_ok)
    await db_session.commit()

    is_eligible, reason = await check_registration_eligibility(
        db_session, female_user, event_to_register_ok
    )
    assert (
        is_eligible is True
    ), f"Регистрация на 4-ю донацию должна была пройти. Причина отказа: {reason}"

    await add_event_registration(db_session, female_user.id, event_to_register_ok.id)

    # Пытаемся записаться на 5-ю. Должны получить отказ именно по причине лимита.
    event_fail_date = datetime.date.today() + datetime.timedelta(days=220)
    event_to_register_fail = DbEvent(
        name="Будущая 3 (FAIL)",
        event_datetime=datetime.datetime.combine(
            event_fail_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Локация 3",
        points_per_donation=100,
    )
    db_session.add(event_to_register_fail)
    await db_session.commit()

    is_eligible_fail, reason_fail = await check_registration_eligibility(
        db_session, female_user, event_to_register_fail
    )

    assert is_eligible_fail is False
    assert (
        "годового лимита" in reason_fail
    ), f"Ожидалась ошибка лимита, но получено: '{reason_fail}'"


@pytest.mark.asyncio
async def test_yearly_limit_not_blocked_by_other_type(
    db_session: AsyncSession, male_user: User
):
    """
    Тест: Годовой лимит не должен блокировать запись, если типы донаций разные.
    """
    for i in range(5):
        db_session.add(
            Donation(
                user_id=male_user.id,
                donation_date=datetime.date.today()
                - datetime.timedelta(days=30 * (i + 1)),
                donation_type="plasma",
                points_awarded=10,
            )
        )
    await db_session.commit()

    blood_event_date = datetime.date.today() + datetime.timedelta(days=10)
    blood_event = DbEvent(
        name="Донация крови",
        event_datetime=datetime.datetime.combine(
            blood_event_date, datetime.time(10, 0)
        ),  # <-- ИСПРАВЛЕНО
        donation_type="whole_blood",
        participant_limit=10,
        location="Тестовая локация",
        points_per_donation=100,
    )
    db_session.add(blood_event)
    await db_session.commit()

    is_eligible, reason = await check_registration_eligibility(
        db_session, male_user, blood_event
    )

    assert is_eligible is True
