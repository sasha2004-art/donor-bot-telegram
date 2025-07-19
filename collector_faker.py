import asyncio
import datetime
import random
import logging
from faker import Faker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func

# Загружаем переменные окружения, чтобы получить доступ к БД
import os
from dotenv import load_dotenv

load_dotenv()

# Импортируем модели и конфигурацию из вашего проекта
try:
    from bot.db.models import (
        Base, User, Event, EventRegistration, Donation, MedicalWaiver,
        Survey, BloodCenter
    )
    from bot.config_reader import config
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что скрипт 'collector_faker.py' находится в корневой папке вашего проекта.")
    exit()

# ПЕРЕОПРЕДЕЛЯЕМ ХОСТ БД СПЕЦИАЛЬНО ДЛЯ ЭТОГО СКРИПТА
config.db_host = "localhost"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Константы для генерации данных ---
NEW_USER_COUNT = 300
# Распределение по сегментам для аналитики
CHURN_DONOR_COUNT = 30
LAPSED_DONOR_COUNT = 40
DKM_CANDIDATE_COUNT = 50
ACTIVE_DONOR_COUNT = 100
SURVEY_DROPOFF_COUNT = 20
# Оставшиеся 60 пользователей будут неактивными

PAST_EVENTS_TO_CREATE = 10

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
GENDERS = ["male", "female"]
DONATION_TYPES = ['whole_blood', 'plasma', 'platelets']


async def get_max_ids(session: AsyncSession) -> tuple[int, int]:
    """Получает максимальные существующие telegram_id и общее количество пользователей для избежания коллизий."""
    max_tg_id_res = await session.execute(select(func.max(User.telegram_id)))
    max_tg_id = max_tg_id_res.scalar_one_or_none() or 1000000000

    count_users_res = await session.execute(select(func.count(User.id)))
    count_users = count_users_res.scalar_one() or 0
    
    return max_tg_id, count_users


async def create_new_users(session: AsyncSession) -> list[User]:
    """Создает 300 новых пользователей, не затрагивая существующих."""
    logger.info(f"Создание {NEW_USER_COUNT} новых пользователей...")
    users_to_create = []

    max_tg_id, user_count_base = await get_max_ids(session)
    
    for i in range(NEW_USER_COUNT):
        gender = random.choice(GENDERS)
        university = random.choice(UNIVERSITIES)
        faculty = random.choice(FACULTIES_MIFI) if university == "НИЯУ МИФИ" else "Не указан"
        
        user = User(
            phone_number=f"+79{random.randint(100, 999):03d}{user_count_base + i:07d}",
            telegram_id=max_tg_id + i + 1,
            telegram_username=faker.user_name() + str(i),
            full_name=faker.name_male() if gender == 'male' else faker.name_female(),
            university=university,
            faculty=faculty,
            study_group=f"{random.choice(['Б', 'М'])}{random.randint(20, 24)}-{random.randint(101, 515)}",
            gender=gender,
            points=0,
            role='student',
            is_blocked=False,
            created_at=faker.date_time_between(start_date='-1y', end_date='now'),
            is_dkm_donor=False,
            consent_given=True,
            graduation_year=datetime.date.today().year + random.randint(0, 4)
        )
        users_to_create.append(user)
        
    session.add_all(users_to_create)
    await session.commit()
    
    logger.info(f"{len(users_to_create)} новых пользователей успешно создано.")
    return users_to_create


async def create_past_events(session: AsyncSession, blood_centers: list[BloodCenter]) -> list[Event]:
    """Создает новые прошедшие мероприятия, к которым будут привязаны донации новых пользователей."""
    logger.info(f"Создание {PAST_EVENTS_TO_CREATE} новых прошедших мероприятий...")
    if not blood_centers:
        raise ValueError("Нет центров крови для привязки мероприятий.")

    events_to_create = []
    today = datetime.datetime.now()

    for i in range(PAST_EVENTS_TO_CREATE):
        event_date = today - datetime.timedelta(days=random.randint(30, 500))
        center = random.choice(blood_centers)
        
        event = Event(
            name=f"Архивная акция (faker) №{i+1}",
            event_datetime=event_date,
            location=f"Место проведения архивной акции №{i+1}",
            blood_center_id=center.id,
            donation_type=random.choice(DONATION_TYPES),
            points_per_donation=random.randint(100, 200),
            participant_limit=random.randint(40, 80),
            is_active=False,
            registration_is_open=False
        )
        events_to_create.append(event)
    
    session.add_all(events_to_create)
    await session.commit()
    logger.info(f"{len(events_to_create)} новых прошедших мероприятий создано.")
    return events_to_create


async def create_history_for_new_users(session: AsyncSession, new_users: list[User], past_events: list[Event]):
    """Создает историю донаций, медотводов и опросников для разных сегментов новых пользователей."""
    logger.info("Генерация истории донаций для сегментов новых пользователей...")
    
    if not new_users or not past_events:
        logger.warning("Нет новых пользователей или мероприятий для создания истории.")
        return

    random.shuffle(new_users)
    
    # Распределяем пользователей по сегментам
    segments = {
        "churn": new_users[:CHURN_DONOR_COUNT],
        "lapsed": new_users[CHURN_DONOR_COUNT : CHURN_DONOR_COUNT + LAPSED_DONOR_COUNT],
        "dkm_candidates": new_users[CHURN_DONOR_COUNT + LAPSED_DONOR_COUNT : - (ACTIVE_DONOR_COUNT + SURVEY_DROPOFF_COUNT)],
        "active": new_users[-(ACTIVE_DONOR_COUNT + SURVEY_DROPOFF_COUNT) : -SURVEY_DROPOFF_COUNT],
        "survey_dropoff": new_users[-SURVEY_DROPOFF_COUNT:]
    }

    donations_to_add, waivers_to_add, surveys_to_add = [], [], []
    user_updates = {}
    
    def create_donation_entry(user, event, donation_date):
        points = event.points_per_donation
        donations_to_add.append(Donation(
            user_id=user.id, event_id=event.id, donation_date=donation_date,
            donation_type=event.donation_type, points_awarded=points
        ))
        
        days_waiver = (90 if user.gender == 'female' else 60) if event.donation_type == 'whole_blood' else 14
        end_date = donation_date + datetime.timedelta(days=days_waiver)
        waivers_to_add.append(MedicalWaiver(
            user_id=user.id, start_date=donation_date, end_date=end_date,
            reason=f"Сдача «{event.donation_type}»", created_by='system'
        ))
        user_updates[user.id] = user_updates.get(user.id, 0) + points

    # 1. "Однодневки": 1 донация > 6 месяцев назад
    logger.info(f"Обработка {len(segments['churn'])} доноров-однодневок...")
    for user in segments['churn']:
        event = random.choice(past_events)
        donation_date = datetime.date.today() - datetime.timedelta(days=random.randint(185, 300))
        create_donation_entry(user, event, donation_date)

    # 2. "Угасающие": 2+ донации, последняя > 9 месяцев назад
    logger.info(f"Обработка {len(segments['lapsed'])} угасающих доноров...")
    for user in segments['lapsed']:
        num_donations = random.randint(2, 4)
        last_date = datetime.date.today() - datetime.timedelta(days=random.randint(275, 400))
        for i in range(num_donations):
            create_donation_entry(user, random.choice(past_events), last_date - datetime.timedelta(days=i*90))

    # 3. "Кандидаты в ДКМ": 2+ донации, is_dkm_donor=False
    logger.info(f"Обработка {len(segments['dkm_candidates'])} кандидатов в ДКМ...")
    for user in segments['dkm_candidates']:
        for _ in range(random.randint(2, 5)):
            create_donation_entry(user, random.choice(past_events), datetime.date.today() - datetime.timedelta(days=random.randint(30, 365)))

    # 4. "Активные": 1+ донаций, последняя < 3 месяцев назад
    logger.info(f"Обработка {len(segments['active'])} активных доноров...")
    for user in segments['active']:
        for i in range(random.randint(1, 6)):
            create_donation_entry(user, random.choice(past_events), datetime.date.today() - datetime.timedelta(days=random.randint(15, 90) * (i + 1)))
        if random.random() < 0.3:
            user.is_dkm_donor = True

    # 5. "Потерянные после опросника": Прошли опрос, но не записались
    logger.info(f"Обработка {len(segments['survey_dropoff'])} 'потерянных' пользователей...")
    for user in segments['survey_dropoff']:
        surveys_to_add.append(Survey(
            user_id=user.id, passed=True, verdict_text="Противопоказаний не выявлено.",
            created_at=datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 20))
        ))

    session.add_all(donations_to_add + waivers_to_add + surveys_to_add)
    
    logger.info(f"Обновление баллов для {len(user_updates)} пользователей...")
    for user_id, points in user_updates.items():
        user = await session.get(User, user_id)
        if user:
            user.points += points
            
    await session.commit()
    logger.info("История донаций успешно сгенерирована.")


async def main():
    """Главная функция для запуска всех этапов генерации данных."""
    logger.info("Запуск скрипта для добавления фейковых данных...")
    async with async_session_maker() as session:
        
        logger.info("Проверка существующих данных...")
        
        existing_centers_res = await session.execute(select(BloodCenter))
        existing_centers = existing_centers_res.scalars().all()
        if not existing_centers:
            logger.warning("Центры крови не найдены. Создаю дефолтные.")
            centers = [BloodCenter(name="Центр крови ФМБА России"), BloodCenter(name="Центр крови им. О.К. Гаврилова")]
            session.add_all(centers)
            await session.commit()
            existing_centers = centers

        new_users = await create_new_users(session)
        past_events = await create_past_events(session, existing_centers)
        await create_history_for_new_users(session, new_users, past_events)

    logger.info("🎉 Готово! Фейковые данные были добавлены в базу данных.")


if __name__ == "__main__":
    asyncio.run(main())