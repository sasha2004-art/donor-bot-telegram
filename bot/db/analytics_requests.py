import datetime
from sqlalchemy import select, func, and_, distinct, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from .models import User, Event, Donation, EventRegistration, Survey, MedicalWaiver

async def get_main_kpi(session: AsyncSession) -> dict:
    """Собирает ключевые показатели для главного дашборда."""
    
    thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
    new_users_stmt = select(func.count(User.id)).where(User.created_at >= thirty_days_ago)
    new_users_count = (await session.execute(new_users_stmt)).scalar_one()

    ninety_days_ago = datetime.date.today() - datetime.timedelta(days=90)
    active_donors_stmt = select(func.count(distinct(Donation.user_id))).where(Donation.donation_date >= ninety_days_ago)
    active_donors_count = (await session.execute(active_donors_stmt)).scalar_one()
    
    waiver_stmt = select(func.count(distinct(User.id))).join(User.waivers).where(MedicalWaiver.end_date >= datetime.date.today())
    on_waiver_count = (await session.execute(waiver_stmt)).scalar_one()

    next_event_stmt = select(Event).where(Event.is_active == True, Event.event_datetime >= datetime.datetime.now()).order_by(Event.event_datetime).limit(1)
    next_event = (await session.execute(next_event_stmt)).scalar_one_or_none()
    
    next_event_info = None
    if next_event:
        regs_count = (await session.execute(select(func.count(EventRegistration.id)).where(EventRegistration.event_id == next_event.id))).scalar_one()
        next_event_info = {
            "name": next_event.name,
            "registered": regs_count,
            "limit": next_event.participant_limit,
            "date": next_event.event_datetime
        }
        
    return {
        "new_users_30d": new_users_count,
        "active_donors_90d": active_donors_count,
        "on_waiver_now": on_waiver_count,
        "next_event": next_event_info
    }

async def get_donations_by_month(session: AsyncSession, months: int = 6) -> list[tuple]:
    """
    Возвращает количество донаций по месяцам за последние N месяцев.
    ИСПОЛЬЗУЕТ date_trunc для совместимости с PostgreSQL.
    """
    today = datetime.date.today()
    start_date = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    for _ in range(months - 1):
        start_date = (start_date - datetime.timedelta(days=1)).replace(day=1)

    stmt = text("""
        SELECT
            date_trunc('month', donation_date)::DATE as month_date,
            count(id) as count
        FROM donations
        WHERE donation_date >= :start_date
        GROUP BY month_date
        ORDER BY month_date
    """)
    
    result = await session.execute(stmt, {"start_date": start_date})
    
    return [(row.month_date, row.count) for row in result]

async def get_past_events_for_analysis(session: AsyncSession) -> list[Event]:
    """Получает список прошедших мероприятий для выбора."""
    stmt = select(Event).where(Event.event_datetime < datetime.datetime.now()).order_by(Event.event_datetime.desc()).limit(15)
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_event_analysis_data(session: AsyncSession, event_id: int) -> dict:
    """Собирает всю аналитику по конкретному прошедшему мероприятию."""
    event = await session.get(Event, event_id)
    if not event:
        return None

    stmt_registrations = select(func.count(EventRegistration.id)).where(EventRegistration.event_id == event_id)
    registered_count = (await session.execute(stmt_registrations)).scalar_one()
    
    stmt_donations = select(func.count(Donation.id)).where(Donation.event_id == event_id)
    attended_count = (await session.execute(stmt_donations)).scalar_one()
    
    stmt_attended_users = (
        select(User)
        .join(Donation)
        .where(Donation.event_id == event_id)
    )
    # ЗДЕСЬ БЫЛА ОШИБКА, ТЕПЕРЬ ОНА ИСПРАВЛЕНА БЛАГОДАРЯ ИМПОРТУ
    attended_users_result = await session.execute(stmt_attended_users.options(selectinload(User.donations)))
    attended_users = attended_users_result.scalars().unique().all()
    
    newcomers_count = sum(1 for user in attended_users if len(user.donations) == 1)
    
    faculties_dist = {}
    for user in attended_users:
        faculty = user.faculty or "Не указан"
        faculties_dist[faculty] = faculties_dist.get(faculty, 0) + 1

    return {
        "event_name": event.name,
        "registered_count": registered_count,
        "attended_count": attended_count,
        "conversion_rate": (attended_count / registered_count * 100) if registered_count > 0 else 0,
        "newcomers_count": newcomers_count,
        "veterans_count": attended_count - newcomers_count,
        "faculties_distribution": faculties_dist
    }

async def get_one_time_donors(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые сдали кровь только один раз."""
    stmt = (
        select(User, func.count(Donation.id).label("donation_count"))
        .join(Donation)
        .group_by(User)
        .having(func.count(Donation.id) == 1)
    )
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_no_show_donors(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые регистрировались, но не пришли."""
    stmt = (
        select(User)
        .join(EventRegistration)
        .where(EventRegistration.status == "no_show_survey_sent")
    )
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_dkm_donors(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые являются донорами костного мозга."""
    stmt = select(User).where(User.is_dkm_donor == True)
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_students(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые являются студентами."""
    stmt = select(User).where(User.category == "student")
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_employees(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые являются сотрудниками."""
    stmt = select(User).where(User.category == "employee")
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_external_donors(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые являются внешними донорами."""
    stmt = select(User).where(User.category == "external")
    result = await session.execute(stmt)
    return [{"full_name": row.User.full_name, "telegram_username": row.User.telegram_username} for row in result]

async def get_graduated_donors(session: AsyncSession) -> list[dict]:
    """Возвращает список доноров, которые выпустились из университета."""
    # This is a placeholder. The actual implementation will depend on how graduation is determined.
    return []

async def get_churn_donors(session: AsyncSession) -> list[dict]:
    """
    Возвращает доноров-однодневок.
    Логика: Пользователи, у которых ровно 1 донация, и она была более 6 месяцев назад.
    """
    six_months_ago = datetime.datetime.now() - datetime.timedelta(days=180)

    # Подзапрос для поиска пользователей с одной донацией
    subquery = (
        select(Donation.user_id)
        .group_by(Donation.user_id)
        .having(func.count(Donation.id) == 1)
    ).alias("one_donation_users")

    # Основной запрос
    stmt = (
        select(User.full_name, User.telegram_username, Donation.donation_date)
        .join(subquery, User.id == subquery.c.user_id)
        .join(Donation, User.id == Donation.user_id)
        .where(Donation.donation_date < six_months_ago)
    )

    result = await session.execute(stmt)
    return [
        {"full_name": row.full_name, "username": row.telegram_username, "donation_date": row.donation_date}
        for row in result
    ]

async def get_lapsed_donors(session: AsyncSession) -> list[dict]:
    """
    Возвращает угасающих доноров.
    Логика: 2+ донации, последняя > 9 мес. назад, нет активных медотводов.
    """
    nine_months_ago = datetime.datetime.now() - datetime.timedelta(days=270)
    today = datetime.date.today()

    # Подзапрос: пользователи с 2+ донациями и датой последней донации
    subquery = (
        select(
            Donation.user_id,
            func.count(Donation.id).label("donations_count"),
            func.max(Donation.donation_date).label("last_donation_date")
        )
        .group_by(Donation.user_id)
        .having(func.count(Donation.id) >= 2)
        .alias("lapsed_candidates")
    )

    # Подзапрос: пользователи с активными медотводами
    active_waiver_subquery = (
        select(MedicalWaiver.user_id)
        .where(MedicalWaiver.end_date >= today)
    ).alias("active_waivers")

    # Основной запрос
    stmt = (
        select(
            User.full_name,
            User.telegram_username,
            subquery.c.donations_count,
            subquery.c.last_donation_date
        )
        .join(subquery, User.id == subquery.c.user_id)
        .outerjoin(active_waiver_subquery, User.id == active_waiver_subquery.c.user_id)
        .where(
            subquery.c.last_donation_date < nine_months_ago,
            active_waiver_subquery.c.user_id == None # Условие отсутствия в подзапросе с медотводами
        )
    )

    result = await session.execute(stmt)
    return [
        {
            "full_name": row.full_name,
            "username": row.telegram_username,
            "donation_count": row.donations_count,
            "last_donation_date": row.last_donation_date
        }
        for row in result
    ]

async def get_top_donors(session: AsyncSession) -> list[dict]:
    """
    Возвращает топ-20 доноров по количеству донаций.
    """
    # Используем оконную функцию для ранжирования
    stmt = (
        select(
            User.full_name,
            User.telegram_username,
            func.count(Donation.id).label("donation_count"),
            func.rank().over(order_by=func.count(Donation.id).desc()).label("rank")
        )
        .join(Donation, User.id == Donation.user_id)
        .group_by(User.id)
        .order_by(text("rank")) # Сортируем по рангу
        .limit(20)
    )

    result = await session.execute(stmt)
    return [
        {
            "rank": row.rank,
            "full_name": row.full_name,
            "username": row.telegram_username,
            "donation_count": row.donation_count
        }
        for row in result
    ]

async def get_rare_blood_donors(session: AsyncSession) -> list[dict]:
    """
    Возвращает доноров с редкой группой крови.
    Логика: rh_factor = '-' ИЛИ blood_type = 'AB(IV)'.
    """
    stmt = (
        select(User.full_name, User.telegram_username, User.blood_type, User.rh_factor)
        .where(
            (User.rh_factor == '-') |
            (User.blood_type == 'AB(IV)')
        )
        .order_by(User.full_name)
    )

    result = await session.execute(stmt)
    return [
        {
            "full_name": row.full_name,
            "username": row.telegram_username,
            "blood_group": f"{row.blood_type}{row.rh_factor}"
        }
        for row in result
    ]

# async def get_top_faculties(session: AsyncSession) -> list[dict]:
#     """
#     Возвращает самые активные факультеты по количеству донаций.
#     Логика: Группировка донаций по факультетам пользователей из НИЯУ МИФИ.
#     """
#     stmt = (
#         select(User.faculty, func.count(Donation.id).label("donation_count"))
#         .join(Donation, User.id == Donation.user_id)
#         .where(User.university == "НИЯУ МИФИ", User.faculty != None)
#         .group_by(User.faculty)
#         .order_by(func.count(Donation.id).desc())
#     )
#
#     result = await session.execute(stmt)
#     return [
#         {"faculty_name": row.faculty, "donation_count": row.donation_count}
#         for row in result
#     ]

async def get_dkm_candidates(session: AsyncSession) -> list[dict]:
    """
    Возвращает кандидатов в регистр ДКМ.
    Логика: Пользователи с 2+ донациями, но is_dkm_donor = False.
    """
    subquery = (
        select(Donation.user_id, func.count(Donation.id).label("donation_count"))
        .group_by(Donation.user_id)
        .having(func.count(Donation.id) >= 2)
    ).alias("two_plus_donations")

    stmt = (
        select(User.full_name, User.telegram_username, two_plus_donations.c.donation_count)
        .join(two_plus_donations, User.id == two_plus_donations.c.user_id)
        .where(User.is_dkm_donor == False)
        .order_by(User.full_name)
    )

    result = await session.execute(stmt)
    return [
        {
            "full_name": row.full_name,
            "username": row.telegram_username,
            "donation_count": row.donation_count
        }
        for row in result
    ]

async def get_survey_dropoff(session: AsyncSession) -> list[dict]:
    """
    Возвращает пользователей, "потерянных" после опросника.
    Логика: Есть успешный опросник, но нет регистрации на мероприятие после него.
    """
    # Подзапрос: последняя регистрация для каждого пользователя
    last_reg_subquery = (
        select(
            EventRegistration.user_id,
            func.max(EventRegistration.registration_date).label("last_reg_date")
        )
        .group_by(EventRegistration.user_id)
    ).alias("last_regs")

    # Основной запрос
    stmt = (
        select(User.full_name, User.telegram_username, Survey.created_at)
        .join(Survey, User.id == Survey.user_id)
        .outerjoin(last_reg_subquery, User.id == last_reg_subquery.c.user_id)
        .where(
            (Survey.passed == True) &
            (
                (last_reg_subquery.c.last_reg_date == None) |
                (Survey.created_at > last_reg_subquery.c.last_reg_date)
            )
        )
        # Убедимся, что берем только последнюю запись о прохождении опросника для пользователя
        .distinct(User.id)
        .order_by(User.id, Survey.created_at.desc())
    )

    result = await session.execute(stmt)
    return [
        {
            "full_name": row.full_name,
            "username": row.telegram_username,
            "survey_date": row.created_at
        }
        for row in result
    ]