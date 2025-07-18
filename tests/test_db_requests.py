import pytest
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.db import user_requests, admin_requests, event_requests, merch_requests
from bot.db.models import User, Event, EventRegistration, MedicalWaiver, Donation, MerchItem, UserBlock, MerchOrder

# Маркируем все тесты в этом файле для pytest-asyncio
pytestmark = pytest.mark.asyncio

async def test_add_user_with_custom_university(session: AsyncSession):
    """
    Тестирует добавление пользователя с кастомным ВУЗом и его корректное сохранение.
    """
    # 1. Подготовка данных
    user_data = {
        "phone_number": "+79991112233",
        "telegram_id": 987654321,
        "telegram_username": "msu_student",
        "full_name": "Студент Другого ВУЗа",
        "university": "МГУ им. Ломоносова", # Кастомный ВУЗ
        "faculty": "ВМК",
        "study_group": "101",
        "gender": "male"
    }

    # 2. Выполнение
    new_user = await user_requests.add_user(session, user_data)
    await session.commit()
    
    retrieved_user = await user_requests.get_user_by_tg_id(session, 987654321)

    # 3. Проверка
    assert new_user.id is not None
    assert retrieved_user is not None
    assert retrieved_user.full_name == "Студент Другого ВУЗа"
    assert retrieved_user.university == "МГУ им. Ломоносова" # Главная проверка
    assert retrieved_user.role == "student"


# --- НОВЫЙ ТЕСТ ДЛЯ ПРОВЕРКИ СОХРАНЕНИЯ КООРДИНАТ ---
async def test_create_event_with_location(session: AsyncSession):
    """
    Тестирует создание мероприятия с координатами и их корректное сохранение в БД.
    """
    # 1. Подготовка данных
    event_data = {
        "name": "Event with Location",
        "event_datetime": datetime.datetime(2030, 5, 20, 10, 0),
        "location": "НИЯУ МИФИ, Каширское ш. 31",
        "latitude": 55.649917,
        "longitude": 37.662128,
        "donation_type": "whole_blood",
        "points_per_donation": 100,
        "participant_limit": 50,
    }

    # 2. Выполнение
    new_event = await admin_requests.create_event(session, event_data)
    await session.commit()

    # 3. Проверка
    retrieved_event = await session.get(Event, new_event.id)
    assert retrieved_event is not None
    assert retrieved_event.name == "Event with Location"
    assert retrieved_event.latitude == 55.649917
    assert retrieved_event.longitude == 37.662128
# --- КОНЕЦ НОВОГО ТЕСТА ---


async def test_add_and_get_user(session: AsyncSession):
    """
    Тестирует добавление пользователя в БД и его последующее получение.
    """
    # 1. Подготовка данных
    user_data = {
        "phone_number": "+79991234567",
        "telegram_id": 123456789,
        "telegram_username": "testuser",
        "full_name": "Тестовый Пользователь",
        "university": "НИЯУ МИФИ",
    }

    # 2. Выполнение
    new_user = await user_requests.add_user(session, user_data)
    await session.commit()
    
    retrieved_user = await user_requests.get_user_by_tg_id(session, 123456789)

    # 3. Проверка
    assert new_user.id is not None
    assert retrieved_user is not None
    assert retrieved_user.full_name == "Тестовый Пользователь"
    assert retrieved_user.telegram_id == 123456789

async def test_find_user_for_admin(session: AsyncSession):
    """
    Тестирует поиск пользователя по разным критериям.
    """
    # 1. Подготовка (создаем несколько пользователей)
    users_to_add = [
        User(phone_number="+7001", telegram_id=1, telegram_username="john_doe", full_name="John Doe", university="A"),
        User(phone_number="+7002", telegram_id=2, telegram_username="jane_smith", full_name="Jane Smith", university="B"),
        User(phone_number="+7003", telegram_id=3, telegram_username="tester", full_name="Another Tester", university="C"),
    ]
    session.add_all(users_to_add)
    await session.commit()

    # 2. Выполнение и Проверка
    # Поиск по части ФИО
    found_by_name = await admin_requests.find_user_for_admin(session, "Smith")
    assert len(found_by_name) == 1
    assert found_by_name[0].full_name == "Jane Smith"

    # Поиск по username
    found_by_username = await admin_requests.find_user_for_admin(session, "john_doe")
    assert len(found_by_username) == 1
    assert found_by_username[0].telegram_id == 1

    # Поиск по ID
    found_by_id = await admin_requests.find_user_for_admin(session, "3")
    assert len(found_by_id) == 1
    assert found_by_id[0].full_name == "Another Tester"

    # Поиск по части телефона
    found_by_phone = await admin_requests.find_user_for_admin(session, "001")
    assert len(found_by_phone) == 1
    assert found_by_phone[0].telegram_id == 1

async def test_check_registration_eligibility(session: AsyncSession):
    """
    Тестирует логику проверки возможности регистрации на мероприятие.
    """
    # 1. Подготовка
    user = User(
        phone_number="+7111", telegram_id=111, full_name="Eligible User", gender="male",
        is_blocked=False, university="TestUni"
    )
    event = Event(
        name="Test Event",
        event_datetime=datetime.datetime.now() + datetime.timedelta(days=10),
        location="Тестовая локация, г. Москва",
        donation_type="whole_blood",
        participant_limit=5,
        registration_is_open=True,
        points_per_donation=10
    )
    session.add_all([user, event])
    await session.commit()

    # 2. Выполнение и Проверка
    # Сценарий 1: Успешная регистрация
    is_eligible, reason = await event_requests.check_registration_eligibility(session, user, event)
    assert is_eligible is True
    assert "пройдены" in reason

    # Сценарий 2: Регистрация закрыта
    event.registration_is_open = False
    await session.commit()
    is_eligible, reason = await event_requests.check_registration_eligibility(session, user, event)
    assert is_eligible is False
    assert "закрыта" in reason
    event.registration_is_open = True 
    await session.commit()

    # Сценарий 3: Пользователь уже зарегистрирован
    reg = EventRegistration(user_id=user.id, event_id=event.id)
    session.add(reg)
    await session.commit()
    is_eligible, reason = await event_requests.check_registration_eligibility(session, user, event)
    assert is_eligible is False
    assert "уже зарегистрированы" in reason
    await session.delete(reg) 
    await session.commit()

    # Сценарий 4: У пользователя есть медотвод
    waiver = MedicalWaiver(
        user_id=user.id,
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=30), 
        reason="Test Waiver",
        created_by="system"
    )
    session.add(waiver)
    await session.commit()
    is_eligible, reason = await event_requests.check_registration_eligibility(session, user, event)
    assert is_eligible is False
    assert "действует отвод" in reason


# --- НОВЫЕ ТЕСТЫ ---

async def test_change_user_role(session: AsyncSession):
    """Тестирует повышение и понижение роли пользователя."""
    # 1. Подготовка
    user = User(phone_number="+7111", telegram_id=111, full_name="Test User", role="student", university="TestUni")
    session.add(user)
    await session.commit()

    # 2. Повышаем до волонтера
    await admin_requests.change_user_role(session, user.id, "volunteer")
    
    # 3. Проверяем
    updated_user_1 = await session.get(User, user.id)
    assert updated_user_1.role == "volunteer"

    # 4. Понижаем до студента
    await admin_requests.change_user_role(session, user.id, "student")

    # 5. Проверяем
    updated_user_2 = await session.get(User, user.id)
    assert updated_user_2.role == "student"


async def test_block_and_unblock_user(session: AsyncSession):
    """Тестирует блокировку и разблокировку пользователя."""
    # 1. Подготовка
    admin = User(phone_number="+7_admin", telegram_id=999, full_name="Admin", university="TestUni")
    target_user = User(phone_number="+7_target", telegram_id=123, full_name="Target", university="TestUni")
    session.add_all([admin, target_user])
    await session.commit()

    # 2. Блокируем пользователя
    await admin_requests.block_user(session, target_user.id, admin.id, "Test block reason")
    
    # 3. Проверяем
    blocked_user = await session.get(User, target_user.id)
    block_record = (await session.execute(select(UserBlock))).scalar_one_or_none()
    assert blocked_user.is_blocked is True
    assert block_record is not None
    assert block_record.reason == "Test block reason"
    assert block_record.is_active is True

    # 4. Разблокируем
    await admin_requests.unblock_user(session, target_user.id)
    
    # 5. Проверяем
    unblocked_user = await session.get(User, target_user.id)
    await session.refresh(block_record) # Обновляем запись о блокировке из БД
    assert unblocked_user.is_blocked is False
    assert block_record.is_active is False


async def test_confirm_donation_transaction(session: AsyncSession):
    """Тестирует полную транзакцию подтверждения донации."""
    # 1. Подготовка
    user = User(phone_number="+7", telegram_id=1, full_name="Donor", gender="male", points=0, university="TestUni")
    event_date = datetime.date.today()
    event_dt = datetime.datetime.combine(event_date, datetime.time.min)
    event = Event(
        name="Transaction Test Event",
        event_datetime=event_dt,
        location="Test",
        donation_type="whole_blood",
        points_per_donation=50,
        rare_blood_bonus_points=25,
        participant_limit=5
    )
    session.add_all([user, event])
    await session.commit()
    registration = EventRegistration(user_id=user.id, event_id=event.id)
    session.add(registration)
    await session.commit()

    # 2. Выполнение
    points, waiver_end_date = await event_requests.confirm_donation_transaction(session, user, registration)
    
    # 3. Проверка
    # Проверяем начисление баллов
    updated_user = await session.get(User, user.id)
    assert points == 50 # 50, т.к. кровь не редкая
    assert updated_user.points == 50
    
    # Проверяем запись о донации
    donation = (await session.execute(select(Donation))).scalar_one()
    assert donation.user_id == user.id
    assert donation.points_awarded == 50
    
    # Проверяем создание медотвода
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one()
    expected_end_date = event_date + datetime.timedelta(days=60) # 60 дней для мужчины
    assert waiver.end_date == expected_end_date
    assert waiver_end_date == expected_end_date
    assert waiver.created_by == "system"

    # Проверяем статус регистрации
    updated_reg = await session.get(EventRegistration, registration.id)
    assert updated_reg.status == "attended"


async def test_create_merch_order_success_and_fail(session: AsyncSession):
    """Тестирует успешное создание заказа и отказ при нехватке баллов."""
    # 1. Подготовка
    user_rich = User(phone_number="+1", telegram_id=1, full_name="Rich", points=100, university="TestUni")
    user_poor = User(phone_number="+2", telegram_id=2, full_name="Poor", points=10, university="TestUni")
    item = MerchItem(name="Test Mug", description="A mug", price=50, photo_file_id="123")
    session.add_all([user_rich, user_poor, item])
    await session.commit()

    # 2. Успешная покупка
    success, msg = await merch_requests.create_merch_order(session, user_rich, item)
    await session.commit()

    # 3. Проверка успешной покупки
    order = (await session.execute(select(MerchOrder).where(MerchOrder.user_id == user_rich.id))).scalar_one()
    assert success is True
    assert "Покупка совершена" in msg
    assert user_rich.points == 50
    assert order is not None

    # 4. Неуспешная покупка
    success_fail, msg_fail = await merch_requests.create_merch_order(session, user_poor, item)
    await session.commit()

    # 5. Проверка неуспешной покупки
    order_fail = (await session.execute(select(MerchOrder).where(MerchOrder.user_id == user_poor.id))).scalar_one_or_none()
    assert success_fail is False
    assert "Недостаточно баллов" in msg_fail
    assert user_poor.points == 10 # Баллы не должны были списаться
    assert order_fail is None


async def test_user_can_delete_own_waiver_but_not_system(session: AsyncSession):
    """
    Тестирует, что пользователь может удалить свой медотвод, но не системный.
    """
    # 1. Подготовка
    user = User(phone_number="+1", telegram_id=1, full_name="Waiver User", university="TestUni")
    session.add(user)
    await session.commit()

    # --- ИЗМЕНЕНИЕ: ДОБАВЛЯЕМ start_date ---
    today = datetime.date.today()
    waiver_by_user = MedicalWaiver(
        user_id=user.id,
        start_date=today, # <-- Добавлено
        end_date=datetime.date.max,
        reason="self",
        created_by="user"
    )
    waiver_by_system = MedicalWaiver(
        user_id=user.id,
        start_date=today, # <-- Добавлено
        end_date=datetime.date.max,
        reason="donation",
        created_by="system"
    )
    # ----------------------------------------
    
    session.add_all([waiver_by_user, waiver_by_system])
    await session.commit()
    
    # 2. Выполнение и проверка
    # Пытаемся удалить свой
    can_delete_own = await user_requests.delete_user_waiver(session, waiver_by_user.id, user.id)
    assert can_delete_own is True
    
    # Пытаемся удалить системный
    can_delete_system = await user_requests.delete_user_waiver(session, waiver_by_system.id, user.id)
    assert can_delete_system is False

    # Проверяем, что в БД остался только системный
    remaining_waivers = (await session.execute(select(MedicalWaiver))).scalars().all()
    assert len(remaining_waivers) == 1
    assert remaining_waivers[0].id == waiver_by_system.id
    
@pytest.mark.parametrize(
    "user_data, donations, waivers, expected_in_list",
    [
        # Сценарий 1: Чистый пользователь, должен попасть в рассылку
        ({"gender": "male", "id": 1, "tg_id": 1}, [], [], True),
        
        # Сценарий 2: Пользователь с активным медотводом, НЕ должен попасть
        ({"gender": "male", "id": 2, "tg_id": 2}, [], [{"days_ago": 10, "duration": 30}], False),
        
        # Сценарий 3: Мужчина, сдача крови < 60 дней назад, НЕ должен попасть
        ({"gender": "male", "id": 3, "tg_id": 3}, [{"type": "whole_blood", "days_ago": 45}], [], False),
        
        # Сценарий 4: Мужчина, сдача крови > 60 дней назад, должен попасть
        ({"gender": "male", "id": 4, "tg_id": 4}, [{"type": "whole_blood", "days_ago": 70}], [], True),
        
        # Сценарий 5: Женщина, сдача крови 80 дней назад. Интервал 90 дней. 80+15=95 > 90. ДОЛЖНА ПОПАСТЬ.
        ({"gender": "female", "id": 5, "tg_id": 5}, [{"type": "whole_blood", "days_ago": 80}], [], True), 

        # Сценарий 6: Женщина, сдача крови 100 дней назад. ДОЛЖНА ПОПАСТЬ.
        ({"gender": "female", "id": 6, "tg_id": 6}, [{"type": "whole_blood", "days_ago": 100}], [], True),

        # Сценарий 7: Сдача плазмы 10 дней назад. Интервал 14 дней. 10+15=25 > 14. ДОЛЖЕН ПОПАСТЬ.
        ({"gender": "male", "id": 7, "tg_id": 7}, [{"type": "plasma", "days_ago": 10}], [], True),
        
        # Сценарий 8: Сдача компонентов > 14 дней назад, должен попасть
        ({"gender": "male", "id": 8, "tg_id": 8}, [{"type": "plasma", "days_ago": 20}], [], True),

        # Сценарий 9: Мужчина, достиг лимита (5) по цельной крови, НЕ должен попасть
        ({"gender": "male", "id": 9, "tg_id": 9}, [{"type": "whole_blood", "days_ago": d} for d in [70, 140, 210, 280, 350]], [], False),

        # Сценарий 10: Пользователь со старым медотводом, должен попасть
        ({"gender": "male", "id": 10, "tg_id": 10}, [], [{"days_ago": 100, "duration": 30}], True),
    ]
)
async def test_get_users_for_event_notification(session: AsyncSession, user_data, donations, waivers, expected_in_list):
    """
    Тестирует сложную логику фильтрации пользователей для уведомления о новом мероприятии.
    Использует параметризацию для проверки множества сценариев.
    """
    # 1. Подготовка
    today = datetime.date.today()
    
    # Создаем тестовое мероприятие для сдачи цельной крови через 15 дней
    event = Event(
        name="Notification Test Event",
        event_datetime=datetime.datetime.now() + datetime.timedelta(days=15),
        location="Test",
        donation_type="whole_blood",
        points_per_donation=10,
        participant_limit=100
    )
    
    # Создаем пользователя
    user = User(
        id=user_data["id"],
        telegram_id=user_data["tg_id"],
        phone_number=f"+{user_data['id']}",
        full_name=f"User {user_data['id']}",
        gender=user_data["gender"],
        university="TestUni"
    )
    session.add(user)

    # Создаем его историю донаций
    for don in donations:
        donation = Donation(
            user_id=user.id,
            donation_type=don["type"],
            donation_date=today - datetime.timedelta(days=don["days_ago"]),
            points_awarded=10
        )
        session.add(donation)
    
    # Создаем его историю медотводов
    for wav in waivers:
        waiver = MedicalWaiver(
            user_id=user.id,
            start_date=today - datetime.timedelta(days=wav["days_ago"]),
            end_date=today - datetime.timedelta(days=wav["days_ago"]) + datetime.timedelta(days=wav["duration"]),
            reason="test",
            created_by="system"
        )
        session.add(waiver)
        
    await session.commit()

    # 2. Выполнение
    users_to_notify = await user_requests.get_users_for_event_notification(session, event)
    user_ids_to_notify = {u.id for u in users_to_notify}

    # 3. Проверка
    if expected_in_list:
        assert user.id in user_ids_to_notify, f"User {user.id} should be in the list but was NOT"
    else:
        assert user.id not in user_ids_to_notify, f"User {user.id} should NOT be in the list but was"
        
        
        
async def test_confirm_donation_transaction_with_rare_blood(session: AsyncSession):
    """
    Тестирует транзакцию подтверждения донации для пользователя с редкой группой крови.
    """
    # 1. Подготовка
    # Редкая кровь: IV группа или любой отрицательный резус
    user = User(phone_number="+7", telegram_id=1, full_name="Donor", gender="male", points=0, blood_type="AB(IV)", rh_factor="+", university="TestUni")
    event_date = datetime.date.today()
    event_dt = datetime.datetime.combine(event_date, datetime.time.min)
    event = Event(
        name="Transaction Test Event",
        event_datetime=event_dt,
        location="Test",
        donation_type="whole_blood",
        points_per_donation=50,
        rare_blood_bonus_points=25, # Бонус за редкую кровь
        participant_limit=5,
        # --- ИСПРАВЛЕНИЕ: Явно указываем, что считаем редкой кровью в этом ивенте ---
        rare_blood_types=["AB(IV) Rh+"] 
    )
    session.add_all([user, event])
    await session.commit()
    registration = EventRegistration(user_id=user.id, event_id=event.id)
    session.add(registration)
    await session.commit()

    # 2. Выполнение
    points, waiver_end_date = await event_requests.confirm_donation_transaction(session, user, registration)

    # 3. Проверка
    await session.refresh(user)
    expected_points = 50 + 25 # Основные + бонус
    assert points == expected_points
    assert user.points == expected_points


async def test_admin_create_manual_waiver(session: AsyncSession):
    """
    Тестирует создание медотвода администратором.
    """
    # 1. Подготовка
    admin = User(phone_number="+1", telegram_id=101, full_name="Admin", university="TestUni")
    user = User(phone_number="+2", telegram_id=102, full_name="User", university="TestUni")
    session.add_all([admin, user])
    await session.commit()
    
    end_date = datetime.date.today() + datetime.timedelta(days=30)
    
    # 2. Выполнение
    await admin_requests.create_manual_waiver(session, user_id=user.id, end_date=end_date, reason="Manual by admin", admin_id=admin.id)
    
    # 3. Проверка
    waiver = (await session.execute(select(MedicalWaiver))).scalar_one_or_none()
    
    assert waiver is not None
    assert waiver.user_id == user.id
    assert waiver.reason == "Manual by admin"
    # Проверяем, что ID админа записался как строка
    assert waiver.created_by == str(admin.id)
    
@pytest.mark.parametrize(
    "user_blood_type, user_rh, rare_types_in_event, should_get_bonus",
    [
        # Сценарий 1: Кровь пользователя в списке редких -> получает бонус
        ("AB(IV)", "-", ["O(I) Rh-", "AB(IV) Rh-"], True),
        # Сценарий 2: Кровь пользователя НЕ в списке редких -> не получает бонус
        ("A(II)", "+", ["O(I) Rh-", "AB(IV) Rh-"], False),
        # Сценарий 3: Список редких пуст -> не получает бонус
        ("O(I)", "-", [], False),
        # Сценарий 4: Список редких в БД None -> не получает бонус
        ("A(II)", "+", None, False),
    ]
)
async def test_confirm_donation_with_selective_rare_blood(
    session: AsyncSession, user_blood_type, user_rh, rare_types_in_event, should_get_bonus
):
    """
    Тестирует начисление бонусных баллов за выборочно указанные редкие группы крови.
    """
    # 1. Подготовка
    user = User(
        phone_number="+7", telegram_id=1, full_name="Donor", gender="male", points=0, 
        university="TestUni", blood_type=user_blood_type, rh_factor=user_rh
    )
    event = Event(
        name="Selective Bonus Event",
        event_datetime=datetime.datetime.now(),
        location="Test",
        donation_type="whole_blood",
        points_per_donation=50,
        rare_blood_bonus_points=25,
        participant_limit=5,
        rare_blood_types=rare_types_in_event  # <-- Используем параметризованный список
    )
    session.add_all([user, event])
    await session.commit()
    registration = EventRegistration(user_id=user.id, event_id=event.id)
    session.add(registration)
    await session.commit()

    # 2. Выполнение
    points_awarded, _ = await event_requests.confirm_donation_transaction(session, user, registration)
    
    # 3. Проверка
    await session.refresh(user)
    
    base_points = 50
    bonus_points = 25
    expected_points = base_points + (bonus_points if should_get_bonus else 0)
    
    assert points_awarded == expected_points
    assert user.points == expected_points
    
    
async def test_create_event_with_datetime(session: AsyncSession):
    """
    Тестирует создание мероприятия с датой и временем и их корректное сохранение.
    """
    event_dt = datetime.datetime(2030, 11, 25, 15, 30)
    event_data = {
        "name": "Event with Time",
        "event_datetime": event_dt,
        "location": "НИЯУ МИФИ",
        "donation_type": "platelets",
        "points_per_donation": 200,
        "participant_limit": 20,
    }

    new_event = await admin_requests.create_event(session, event_data)
    await session.commit()

    retrieved_event = await session.get(Event, new_event.id)
    assert retrieved_event is not None
    assert retrieved_event.name == "Event with Time"
    assert retrieved_event.event_datetime == event_dt