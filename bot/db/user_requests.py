import datetime
from sqlalchemy import select, func, update, delete 
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User, Donation, MedicalWaiver
from sqlalchemy import and_, or_, not_
from sqlalchemy.orm import aliased, joinedload 
from .models import User, Donation, MedicalWaiver, Event, Survey
import logging
logger = logging.getLogger(__name__)


async def update_user_credentials(session: AsyncSession, user_id: int, new_tg_id: int, new_username: str | None):
    # Обновить Telegram ID и username
    stmt = update(User).where(User.id == user_id).values(
        telegram_id=new_tg_id,
        telegram_username=new_username
    )
    await session.execute(stmt)
    await session.commit()


async def get_user_by_phone(session: AsyncSession, phone: str) -> User | None:
    # Найти пользователя по телефону
    stmt = select(User).where(User.phone_number == phone)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> User | None:
    # Найти пользователя по Telegram ID
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

# --- ИЗМЕНЕНИЕ: Убираем commit из этой функции ---
async def add_user(session: AsyncSession, data: dict) -> User:
    # Добавить пользователя
    user = User(**data)
    session.add(user)
    # await session.commit()  # <-- УБИРАЕМ ЭТУ СТРОКУ
    return user
# --- КОНЕЦ ИЗМЕНЕНИЯ ---

async def update_user_tg_id(session: AsyncSession, user_id: int, new_tg_id: int):
    # Обновить Telegram ID
    stmt = update(User).where(User.id == user_id).values(telegram_id=new_tg_id)
    await session.execute(stmt)
    await session.commit()
    
async def update_user_profile(session: AsyncSession, user_id: int, data: dict):
    # Обновить профиль пользователя
    stmt = update(User).where(User.id == user_id).values(**data)
    await session.execute(stmt)
    await session.commit()

async def get_user_profile_info(session: AsyncSession, user_id: int) -> dict | None:
    user = await session.get(User, user_id)
    if not user:
        return None

    stmt_last_donation = (
        select(Donation)
        .options(joinedload(Donation.event))
        .where(Donation.user_id == user.id)
        .order_by(Donation.donation_date.desc())
        .limit(1)
    )
    last_donation_obj = (await session.execute(stmt_last_donation)).scalar_one_or_none()

    today = datetime.date.today()
    stmt_waiver = select(MedicalWaiver.end_date).where(MedicalWaiver.user_id == user.id, MedicalWaiver.end_date >= today).order_by(MedicalWaiver.end_date.desc()).limit(1)
    active_waiver_end_date = (await session.execute(stmt_waiver)).scalar_one_or_none()
    
    next_possible_donation = today
    if active_waiver_end_date:
        next_possible_donation = active_waiver_end_date + datetime.timedelta(days=1)
    
    if last_donation_obj:
        last_date = last_donation_obj.donation_date
        last_type = last_donation_obj.donation_type
        if last_type == 'whole_blood':
            interval = 90 if user.gender == 'female' else 60
            possible_date = last_date + datetime.timedelta(days=interval)
        else:
            interval = 14
            possible_date = last_date + datetime.timedelta(days=interval)
        next_possible_donation = max(next_possible_donation, possible_date)

    total_donations = await session.scalar(select(func.count(Donation.id)).where(Donation.user_id == user.id))

    return {
        "user": user,
        "total_donations": total_donations,
        "next_possible_donation": next_possible_donation,
        "last_donation": last_donation_obj 
    }

async def get_user_donation_history(session: AsyncSession, user_id: int) -> list[Donation]:
    # История донаций пользователя
    stmt = select(Donation).where(Donation.user_id == user_id).order_by(Donation.donation_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_user_active_waivers(session: AsyncSession, user_id: int) -> list[MedicalWaiver]:
    # Активные медотводы пользователя
    stmt = select(MedicalWaiver).where(
        MedicalWaiver.user_id == user_id,
        MedicalWaiver.end_date >= datetime.date.today()
    ).order_by(MedicalWaiver.end_date)
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    # Найти пользователя по ID
    return await session.get(User, user_id)

async def get_all_users(session: AsyncSession) -> list[User]:
    # Все пользователи
    stmt = select(User).order_by(User.full_name)
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_users_for_event_notification(session: AsyncSession, event: Event) -> list[User]:
    """
    Возвращает список пользователей, которые могут быть уведомлены о мероприятии.
    Фильтрует по активным медотводам, интервалам между донациями и годовым лимитам.
    """
    event_date_only = event.event_datetime.date()

    # 1. Получаем всех пользователей, у которых нет активных медотводов на дату мероприятия
    active_waiver_subquery = select(MedicalWaiver.user_id).where(MedicalWaiver.end_date >= event_date_only).distinct()
    query = select(User).where(not_(User.id.in_(active_waiver_subquery)))
    initial_users = (await session.execute(query)).scalars().all()
    
    final_users_to_notify = []
    one_year_ago = event_date_only - datetime.timedelta(days=365)
    
    for user in initial_users:
        # Получаем донации за год
        donations_stmt = select(Donation).where(
            Donation.user_id == user.id,
            Donation.donation_date >= one_year_ago
        ).order_by(Donation.donation_date.desc())
        user_donations = (await session.execute(donations_stmt)).scalars().all()

        # --- Проверка 1: Годовые лимиты ---
        donations_of_event_type = [d for d in user_donations if d.donation_type == event.donation_type]
        
        if event.donation_type == 'whole_blood':
            limit = 4 if user.gender == 'female' else 5
            if len(donations_of_event_type) >= limit:
                continue
        else: # для компонентов
            limit = 12
            if len(donations_of_event_type) >= limit:
                continue

        # --- Проверка 2: Интервалы ---
        if not user_donations:
            final_users_to_notify.append(user)
            continue
            
        # Правило 2.1: Проверяем отвод от последней донации ЛЮБОГО типа
        last_donation = user_donations[0]
        
        if last_donation.donation_type == 'whole_blood':
            interval = 90 if user.gender == 'female' else 60
        else:
            interval = 14
        
        # Дата, когда отвод от последней донации заканчивается.
        waiver_end_date_from_last = last_donation.donation_date + datetime.timedelta(days=interval)
        
        # Если дата мероприятия меньше или равна дате окончания отвода, то сдавать нельзя.
        if event_date_only <= waiver_end_date_from_last:
            continue

        # Правило 2.2: Если предстоит сдача ЦЕЛЬНОЙ КРОВИ, нужна доп. проверка
        if event.donation_type == 'whole_blood':
            donations_whole_blood = [d for d in user_donations if d.donation_type == 'whole_blood']
            if donations_whole_blood:
                last_whole_blood_donation = donations_whole_blood[0]
                interval_whole = 90 if user.gender == 'female' else 60
                
                waiver_end_date_from_last_whole = last_whole_blood_donation.donation_date + datetime.timedelta(days=interval_whole)
                
                if event_date_only <= waiver_end_date_from_last_whole:
                    continue
        
        final_users_to_notify.append(user)
            
    return final_users_to_notify

async def get_users_for_mailing(session: AsyncSession, filters: dict) -> list[User]:
    """
    Возвращает список пользователей для рассылки на основе набора фильтров.
    """
    stmt = select(User)
    
    # Копируем фильтры, чтобы безопасно изменять их
    filters_to_apply = filters.copy()
    
    # Сначала обрабатываем специальный фильтр по ролям
    if 'role' in filters_to_apply:
        role_filter = filters_to_apply.pop('role') # Извлекаем и удаляем, чтобы не попасть в цикл ниже
        if role_filter == 'volunteers':
            stmt = stmt.where(User.role.in_(['volunteer', 'admin', 'main_admin']))
        elif role_filter == 'admins':
            stmt = stmt.where(User.role.in_(['admin', 'main_admin']))
        # Если role_filter == 'all', то ничего не делаем, это фильтр по умолчанию

    # Применяем остальные фильтры по атрибутам
    for key, value in filters_to_apply.items():
        if hasattr(User, key):
            stmt = stmt.where(getattr(User, key) == value)

    result = await session.execute(stmt.order_by(User.id))
    return result.scalars().all()


async def add_user_waiver(session: AsyncSession, user_id: int, end_date: datetime.date, reason: str):
    """Создает медотвод от имени пользователя."""
    waiver = MedicalWaiver(
        user_id=user_id,
        start_date=datetime.date.today(),
        end_date=end_date,
        reason=reason,
        created_by='user' 
    )
    session.add(waiver)
    await session.commit()

async def delete_user_waiver(session: AsyncSession, waiver_id: int, user_id: int) -> bool:
    """
    Удаляет медотвод, если он был создан этим же пользователем.
    Возвращает True в случае успеха.
    """
    stmt = (
        delete(MedicalWaiver)
        .where(
            MedicalWaiver.id == waiver_id,
            MedicalWaiver.user_id == user_id,
            MedicalWaiver.created_by == 'user'
        )
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0

async def check_recent_survey(session: AsyncSession, user_id: int) -> bool:
    """
    Проверяет, проходил ли пользователь успешно опросник за последние 24 часа.
    Возвращает True, если да, иначе False.
    """
    twenty_four_hours_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    
    stmt = (
        select(Survey)
        .where(
            Survey.user_id == user_id,
            Survey.passed == True,
            Survey.created_at >= twenty_four_hours_ago
        )
        .order_by(Survey.created_at.desc())
        .limit(1)
    )
    
    result = await session.execute(stmt)
    recent_survey = result.scalar_one_or_none()
    
    return recent_survey is not None


async def get_unlinked_user_by_fio(session: AsyncSession, full_name: str) -> User | None:
    """
    Ищет пользователя по ФИО среди тех, у кого telegram_id = 0.
    """
    stmt = select(User).where(
        User.full_name == full_name,
        User.telegram_id == 0
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()