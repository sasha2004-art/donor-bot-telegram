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