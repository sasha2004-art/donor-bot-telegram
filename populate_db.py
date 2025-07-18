import asyncio
import datetime
import random
import logging
from faker import Faker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import delete, select

# Загружаем переменные окружения, чтобы получить доступ к БД
import os
from dotenv import load_dotenv

load_dotenv()

# Импортируем модели и конфигурацию из вашего проекта
try:
    # ФИНАЛЬНАЯ ВЕРСИЯ ИМПОРТОВ
    from bot.db.models import (
        Base, User, Event, EventRegistration, Donation, MedicalWaiver,
        UserBlock, MerchItem, MerchOrder, Survey, Feedback
    )
    from bot.config_reader import config
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что скрипт 'populate_db.py' находится в корневой папке вашего проекта.")
    exit()

# ПЕРЕОПРЕДЕЛЯЕМ ХОСТ БД СПЕЦИАЛЬНО ДЛЯ ЭТОГО СКРИПТА
config.db_host = "localhost"


# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Константы для генерации данных ---
USER_COUNT = 1000
VOLUNTEER_COUNT = 5
ADMIN_COUNT = 1
PAST_EVENTS_COUNT = 5
FUTURE_EVENTS_COUNT = 3
REGISTRATION_CHANCE = 0.4
DONATION_CHANCE = 0.7
MANUAL_WAIVER_CHANCE = 0.05

# Создаем экземпляр Faker для генерации русскоязычных данных
faker = Faker('ru_RU')

# --- Настройка соединения с БД (аналогично вашему engine.py) ---
engine = create_async_engine(
    url=config.database_url,
    echo=False
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# --- Вспомогательные данные ---
UNIVERSITIES = ["НИЯУ МИФИ"] * 8 + ["Другой ВУЗ"] * 2
FACULTIES_MIFI = ["ИИКС", "ФИБС", "ИФТЭБ", "ИФИБ", "а", "ИнЯз", "ИПТИС"]
BLOOD_TYPES = ["O(I)", "A(II)", "B(III)", "AB(IV)"]
RH_FACTORS = ["+", "-"]
GENDERS = ["male", "female"]
DONATION_TYPES = ['whole_blood', 'plasma', 'platelets']

async def clear_database(session: AsyncSession):
    """Очищает все данные из таблиц в правильном порядке, чтобы избежать ошибок внешних ключей."""
    logger.info("Очистка базы данных...")
    # ФИНАЛЬНЫЙ ПОРЯДОК ОЧИСТКИ
    tables_to_clear = [
        Survey, Feedback, Donation, EventRegistration, MedicalWaiver, UserBlock, MerchOrder,
        Event, MerchItem, User
    ]
    for table in tables_to_clear:
        stmt = delete(table)
        await session.execute(stmt)
    await session.commit()
    logger.info("База данных очищена.")


async def create_users(session: AsyncSession) -> list[User]:
    """Создает пачку пользователей, включая волонтеров и админов."""
    logger.info(f"Создание {USER_COUNT} пользователей...")
    users_to_create = []

    for i in range(USER_COUNT):
        role = 'student'
        if i < ADMIN_COUNT:
            role = 'admin'
        elif i < ADMIN_COUNT + VOLUNTEER_COUNT:
            role = 'volunteer'

        university = random.choice(UNIVERSITIES)
        faculty = random.choice(FACULTIES_MIFI) if university == "НИЯУ МИФИ" else "Не указан"
        gender = random.choice(GENDERS)

        user = User(
            phone_number=f"+79{random.randint(100000000, 999999999)}",
            telegram_id=1000000000 + i,
            telegram_username=faker.user_name(),
            full_name=faker.name_male() if gender == 'male' else faker.name_female(),
            university=university,
            faculty=faculty,
            study_group=f"{random.choice(['Б', 'М', 'С'])}{random.randint(20, 23)}-{random.randint(101, 515)}",
            blood_type=random.choice(BLOOD_TYPES),
            rh_factor=random.choice(RH_FACTORS),
            gender=gender,
            points=random.randint(0, 500),
            role=role,
            is_blocked=False,
            created_at=faker.date_time_between(start_date='-2y', end_date='now')
        )
        users_to_create.append(user)

    session.add_all(users_to_create)
    await session.commit()
    logger.info("Пользователи успешно созданы.")
    
    result = await session.execute(select(User))
    return result.scalars().all()


async def create_events(session: AsyncSession) -> tuple[list[Event], list[Event]]:
    """Создает прошедшие и будущие мероприятия."""
    logger.info(f"Создание {PAST_EVENTS_COUNT} прошедших и {FUTURE_EVENTS_COUNT} будущих мероприятий...")
    past_events = []
    future_events = []
    today = datetime.datetime.now()

    for i in range(PAST_EVENTS_COUNT):
        event_date = today - datetime.timedelta(days=random.randint(15, 365))
        event = Event(
            name=f"Прошедшая акция №{i+1}",
            event_datetime=event_date,
            location="г. Москва, ул. Щукинская, д. 6, корп. 2",
            latitude=55.807920,
            longitude=37.491633,
            donation_type=random.choice(DONATION_TYPES),
            points_per_donation=random.randint(100, 250),
            rare_blood_bonus_points=50,
            rare_blood_types=[f"{random.choice(BLOOD_TYPES)} Rh-"],
            participant_limit=random.randint(50, 100),
            is_active=False,
            registration_is_open=False
        )
        past_events.append(event)

    for i in range(FUTURE_EVENTS_COUNT):
        event_date = today + datetime.timedelta(days=random.randint(10, 60))
        event = Event(
            name=f"Будущая акция №{i+1}",
            event_datetime=event_date,
            location="г. Москва, Каширское шоссе, 31",
            latitude=55.649917,
            longitude=37.662128,
            donation_type=random.choice(DONATION_TYPES),
            points_per_donation=random.randint(100, 250),
            rare_blood_bonus_points=50,
            rare_blood_types=["AB(IV) Rh-", "O(I) Rh-"],
            participant_limit=random.randint(60, 120),
            is_active=True,
            registration_is_open=True
        )
        future_events.append(event)

    session.add_all(past_events + future_events)
    await session.commit()
    logger.info("Мероприятия успешно созданы.")
    return past_events, future_events


async def create_registrations_and_donations(session: AsyncSession, users: list[User], events: list[Event]):
    """Создает регистрации на мероприятия, а для прошедших - донации и медотводы."""
    logger.info("Создание регистраций, донаций и системных медотводов...")
    regs_to_create = []
    donations_to_create = []
    waivers_to_create = []
    user_updates = {}

    for event in events:
        for user in users:
            if random.random() < REGISTRATION_CHANCE:
                regs_to_create.append(EventRegistration(user_id=user.id, event_id=event.id))
                if not event.is_active and random.random() < DONATION_CHANCE:
                    donation_date = event.event_datetime.date()
                    points_awarded = event.points_per_donation
                    donations_to_create.append(Donation(
                        user_id=user.id,
                        event_id=event.id,
                        donation_date=donation_date,
                        donation_type=event.donation_type,
                        points_awarded=points_awarded
                    ))
                    user_updates[user.id] = user_updates.get(user.id, 0) + points_awarded
                    days_waiver = (90 if user.gender == 'female' else 60) if event.donation_type == 'whole_blood' else 14
                    end_date = donation_date + datetime.timedelta(days=days_waiver)
                    waivers_to_create.append(MedicalWaiver(
                        user_id=user.id,
                        start_date=donation_date,
                        end_date=end_date,
                        reason=f"Сдача «{event.donation_type}»",
                        created_by='system'
                    ))

    session.add_all(regs_to_create)
    session.add_all(donations_to_create)
    session.add_all(waivers_to_create)
    await session.commit()

    logger.info(f"Обновление баллов для {len(user_updates)} пользователей...")
    for user_id, points in user_updates.items():
        user = await session.get(User, user_id)
        if user:
            user.points += points
    await session.commit()
    logger.info("Регистрации и донации успешно созданы.")


async def create_manual_waivers(session: AsyncSession, users: list[User]):
    """Создает случайные медотводы, установленные 'пользователем'."""
    logger.info("Создание случайных пользовательских медотводов...")
    waivers_to_create = []
    users_with_waiver = random.sample(users, int(len(users) * MANUAL_WAIVER_CHANCE))
    today = datetime.date.today()

    for user in users_with_waiver:
        start_date = today - datetime.timedelta(days=random.randint(0, 10))
        end_date = today + datetime.timedelta(days=random.randint(5, 30))
        waiver = MedicalWaiver(
            user_id=user.id,
            start_date=start_date,
            end_date=end_date,
            reason=random.choice(["Простуда", "Плохое самочувствие", "Прием лекарств"]),
            created_by='user'
        )
        waivers_to_create.append(waiver)

    session.add_all(waivers_to_create)
    await session.commit()
    logger.info(f"Создано {len(waivers_to_create)} пользовательских медотводов.")


async def main():
    """Главная функция для запуска всех этапов заполнения БД."""
    async with async_session_maker() as session:
        await clear_database(session)
        users = await create_users(session)
        past_events, future_events = await create_events(session)
        all_events = past_events + future_events
        await create_registrations_and_donations(session, users, all_events)
        await create_manual_waivers(session, users)

    logger.info("🎉 Готово! База данных успешно заполнена тестовыми данными.")


if __name__ == "__main__":
    asyncio.run(main())