import datetime
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Event, EventRegistration, Donation, MedicalWaiver
from sqlalchemy.orm import joinedload
from bot.utils.text_messages import Text

async def get_active_events(session: AsyncSession) -> list[Event]:
    """Получает активные мероприятия, которые еще не начались."""
    stmt = (
        select(Event)
        .where(
            Event.is_active == True,
            Event.event_datetime >= datetime.datetime.now()
        )
        .order_by(Event.event_datetime)
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_active_events_for_user(session: AsyncSession, user_id: int) -> list[Event]:
    """
    Получает активные мероприятия для пользователя, включая те, на которые он уже записан,
    даже если регистрация на них закрыта.
    """
    user_registrations_subquery = select(EventRegistration.event_id).where(EventRegistration.user_id == user_id)
    stmt = (
        select(Event)
        .where(
            Event.is_active == True,
            Event.event_datetime >= datetime.datetime.now(),
            or_(
                Event.registration_is_open == True,
                Event.id.in_(user_registrations_subquery)
            )
        )
        .order_by(Event.event_datetime)
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_upcoming_events(session: AsyncSession) -> list[Event]:
    """Получает все будущие активные мероприятия (для админки)."""
    stmt = (
        select(Event)
        .where(
            Event.is_active == True,
            Event.event_datetime >= datetime.datetime.now()
        )
        .order_by(Event.event_datetime)
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_event_by_id(session: AsyncSession, event_id: int) -> Event | None:
    """Получает мероприятие по его ID."""
    return await session.get(Event, event_id)

async def get_today_event(session: AsyncSession) -> Event | None:
    """Получает мероприятие, которое проходит сегодня."""
    today = datetime.date.today()
    stmt = (
        select(Event)
        .where(
            Event.is_active == True,
            func.date(Event.event_datetime) == today
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def check_registration_eligibility(session: AsyncSession, user: User, event: Event) -> tuple[bool, str]:
    """Проверяет, может ли пользователь зарегистрироваться на мероприятие."""
    # Получаем только дату мероприятия для сравнения с медотводами
    event_date = event.event_datetime.date()

    # Проверка 1: Базовые условия мероприятия
    if not event.registration_is_open:
        return False, "Регистрация на это мероприятие закрыта."

    existing_registration = await find_specific_registration(session, user.id, event.id)
    if existing_registration:
        return False, f"Вы уже зарегистрированы на это мероприятие ({event.name})."

    reg_count = await session.scalar(select(func.count(EventRegistration.id)).where(EventRegistration.event_id == event.id))
    if reg_count >= event.participant_limit:
        return False, f"Достигнут лимит участников ({event.participant_limit})."

    # Проверка 2: Существующие медотводы из таблицы MedicalWaiver
    active_waiver_stmt = select(MedicalWaiver).where(
        MedicalWaiver.user_id == user.id,
        MedicalWaiver.end_date >= event_date
    ).order_by(MedicalWaiver.end_date.desc()).limit(1)
    active_waiver = (await session.execute(active_waiver_stmt)).scalar_one_or_none()
    if active_waiver:
        return False, f"У вас действует отвод до {active_waiver.end_date.strftime('%d.%m.%Y')}. Причина: {active_waiver.reason}."

    # Проверка 3: Потенциальные медотводы от ДРУГИХ будущих регистраций
    future_registrations_stmt = (
        select(EventRegistration)
        .join(EventRegistration.event)
        .where(
            EventRegistration.user_id == user.id,
            EventRegistration.status == 'registered',
            Event.event_datetime < event.event_datetime
        )
        .options(joinedload(EventRegistration.event))
        .order_by(Event.event_datetime)
    )
    future_registrations = (await session.execute(future_registrations_stmt)).scalars().all()

    for reg in future_registrations:
        registered_event = reg.event
        if registered_event.donation_type == 'whole_blood':
            interval = 90 if user.gender == 'female' else 60
        else:
            interval = 14

        potential_waiver_end_date = registered_event.event_datetime.date() + datetime.timedelta(days=interval)

        if event_date <= potential_waiver_end_date:
            return False, (f"Запись невозможна. У вас запланирована донация "
                           f"«{registered_event.name}» на {registered_event.event_datetime.strftime('%d.%m.%Y')}, "
                           f"после которой будет действовать медотвод.")

    # Проверка 4: Годовой лимит донаций (с учетом будущих регистраций)
    donation_type = event.donation_type
    
    # Считаем ПРОШЕДШИЕ донации
    past_donations_stmt = select(func.count(Donation.id)).where(
        Donation.user_id == user.id,
        Donation.donation_type == donation_type
    )
    past_donations_count = (await session.execute(past_donations_stmt)).scalar_one()

    # Считаем БУДУЩИЕ запланированные донации такого же типа
    future_registrations_stmt = (
        select(func.count(EventRegistration.id))
        .join(Event)
        .where(
            EventRegistration.user_id == user.id,
            EventRegistration.status == 'registered',
            Event.donation_type == donation_type
        )
    )
    future_registrations_count = (await session.execute(future_registrations_stmt)).scalar_one()

    total_committed_donations = past_donations_count + future_registrations_count
    limit = 0
    limit_reason = ""

    if donation_type == 'whole_blood':
        limit = 4 if user.gender == 'female' else 5
        limit_reason = (f"Вы достигли годового лимита ({limit}) на сдачу цельной крови, "
                        f"учитывая прошлые и запланированные донации.")
    elif donation_type in ['plasma', 'platelets', 'erythrocytes']:
        limit = 12
        limit_reason = (f"Вы достигли годового лимита ({limit}) на сдачу компонентов, "
                        f"учитывая прошлые и запланированные донации.")

    if limit > 0 and total_committed_donations >= limit:
        return False, limit_reason

    return True, "Все проверки пройдены."


async def add_event_registration(session: AsyncSession, user_id: int, event_id: int) -> EventRegistration:
    """Добавляет регистрацию пользователя на мероприятие."""
    registration = EventRegistration(user_id=user_id, event_id=event_id)
    session.add(registration)
    await session.flush()

    event = await session.get(Event, event_id)
    if event:
        reg_count_stmt = select(func.count(EventRegistration.id)).where(EventRegistration.event_id == event_id)
        reg_count = (await session.execute(reg_count_stmt)).scalar_one()
        if reg_count >= event.participant_limit:
            event.registration_is_open = False
            
    await session.commit()
    return registration

async def find_specific_registration(session: AsyncSession, user_id: int, event_id: int) -> EventRegistration | None:
    """Находит конкретную регистрацию пользователя на мероприятие."""
    stmt = select(EventRegistration).options(
        joinedload(EventRegistration.event)
    ).where(
        EventRegistration.user_id == user_id,
        EventRegistration.event_id == event_id,
        EventRegistration.status == 'registered'
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def confirm_donation_transaction(session: AsyncSession, user: User, registration: EventRegistration) -> tuple[int, datetime.date]:
    """Проводит транзакцию подтверждения донации: начисляет баллы, создает медотвод."""
    event = await session.get(Event, registration.event_id)
    event_date = event.event_datetime.date() # Получаем только дату для донации и медотвода

    # Проверка на редкую кровь
    is_rare_blood = False
    if event.rare_blood_types and user.blood_type and user.rh_factor:
        user_blood_full = f"{user.blood_type} Rh{user.rh_factor}"
        if user_blood_full in event.rare_blood_types:
            is_rare_blood = True
            
    points_to_award = event.points_per_donation + (event.rare_blood_bonus_points if is_rare_blood else 0)

    # Создаем запись о донации
    donation = Donation(
        user_id=user.id,
        event_id=event.id,
        donation_date=event_date,
        donation_type=event.donation_type,
        points_awarded=points_to_award
    )
    
    # Создаем системный медотвод
    days_waiver = (90 if user.gender == 'female' else 60) if event.donation_type == 'whole_blood' else 14
    end_date = event_date + datetime.timedelta(days=days_waiver)
    russian_donation_type = Text.DONATION_TYPE_RU.get(event.donation_type, event.donation_type)
    waiver = MedicalWaiver(
        user_id=user.id,
        start_date=event_date,
        end_date=end_date,
        reason=f"Сдача «{russian_donation_type}»",
        created_by='system'
    )

    # Обновляем пользователя и регистрацию
    user.points += points_to_award
    registration.status = 'attended'

    session.add_all([donation, waiver])
    await session.commit()
    return points_to_award, end_date

async def cancel_registration(session: AsyncSession, user_id: int, event_id: int) -> bool:
    """Отменяет регистрацию пользователя на мероприятие."""
    stmt = delete(EventRegistration).where(
        EventRegistration.user_id == user_id,
        EventRegistration.event_id == event_id
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0