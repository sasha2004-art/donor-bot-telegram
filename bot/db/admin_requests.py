# ФАЙЛ: bot/db/admin_requests.py

import datetime
import logging # <-- ДОБАВИТЬ ЭТУ СТРОКУ
from sqlalchemy import select, update, or_, func, String, delete, distinct, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from .models import (
    User, Event, EventRegistration, Donation, MedicalWaiver,
    UserBlock, BloodCenter
)
from .models import Feedback
from .event_requests import find_specific_registration, add_event_registration, confirm_donation_transaction
import math

logger = logging.getLogger(__name__) 

async def check_if_users_exist(session: AsyncSession) -> bool:
    user_count = await session.scalar(select(func.count(User.id)))
    return user_count > 0


# --- User Management ---
async def find_user_for_admin(session: AsyncSession, query: str) -> User | None:
    stmt = select(User).where(
        or_(
            User.full_name.ilike(f"%{query}%"),
            User.telegram_username.ilike(f"%{query}%"),
            User.telegram_id.cast(String).ilike(f"%{query}%"),
            User.phone_number.ilike(f"%{query}%")
        )
    ).order_by(User.full_name)
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_users_page(session: AsyncSession, page: int = 1, page_size: int = 10) -> tuple[list[User], int]:
    offset = (page - 1) * page_size
    total_count = (await session.execute(select(func.count(User.id)))).scalar_one()
    items_result = await session.execute(select(User).order_by(User.full_name).offset(offset).limit(page_size))
    items = items_result.scalars().all()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    return items, total_pages

async def update_user_field(session: AsyncSession, user_id: int, field_name: str, new_value: any):
    """
    Универсально обновляет поле для указанного пользователя.
    ВАЖНО: Эта функция больше не коммитит транзакцию.
    """
    if not hasattr(User, field_name):
        logger.error(f"Attempted to update a non-existent field '{field_name}' for User.")
        return

    stmt = update(User).where(User.id == user_id).values({field_name: new_value})
    await session.execute(stmt)


async def get_all_users(session: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.full_name)
    result = await session.execute(stmt)
    return result.scalars().all()

# НОВОЕ: Функция удаления пользователя
async def delete_user_by_id(session: AsyncSession, user_id: int) -> bool:
    """Полностью удаляет пользователя и связанные с ним данные."""
    user = await session.get(User, user_id)
    if not user:
        return False
    await session.delete(user)
    # SQLAlchemy благодаря `cascade` в моделях удалит связанные регистрации, заказы и т.д.
    await session.commit()
    return True

async def change_user_role(session: AsyncSession, user_id: int, new_role: str):
    stmt = update(User).where(User.id == user_id).values(role=new_role)
    await session.execute(stmt)
    await session.commit()

async def add_points_to_user(session: AsyncSession, user_id: int, points: int, reason: str):
    user = await session.get(User, user_id)
    user.points += points
    # log: # Здесь можно добавить логирование этой операции в отдельную таблицу
    await session.commit()

async def block_user(session: AsyncSession, user_id: int, admin_id: int, reason: str):
    user = await session.get(User, user_id)
    user.is_blocked = True
    block_record = UserBlock(user_id=user_id, admin_id=admin_id, reason=reason, is_active=True)
    session.add(block_record)
    # log: # Можно добавить логирование блокировки
    await session.commit()

async def unblock_user(session: AsyncSession, user_id: int):
    user = await session.get(User, user_id)
    user.is_blocked = False
    stmt = update(UserBlock).where(UserBlock.user_id == user_id, UserBlock.is_active == True).values(is_active=False)
    await session.execute(stmt)
    # log: # Можно добавить логирование разблокировки
    await session.commit()

# --- (Остальной код файла без изменений) ---

# --- Event Management ---
async def create_event(session: AsyncSession, data: dict) -> Event:
    event = Event(**data)
    session.add(event)
    await session.commit()
    return event

async def update_event_field(session: AsyncSession, event_id: int, field_name: str, new_value: any):
    if not hasattr(Event, field_name):
        return
    stmt = update(Event).where(Event.id == event_id).values({field_name: new_value})
    await session.execute(stmt)
    await session.commit()


async def get_all_blood_centers(session: AsyncSession) -> list[BloodCenter]:
    stmt = select(BloodCenter).order_by(BloodCenter.name)
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_blood_center(session: AsyncSession, name: str) -> BloodCenter:
    blood_center = BloodCenter(name=name)
    session.add(blood_center)
    await session.commit()
    return blood_center


async def get_blood_center_by_id(session: AsyncSession, blood_center_id: int) -> BloodCenter | None:
    return await session.get(BloodCenter, blood_center_id)

# --- Merch Management ---
# async def create_merch_item(session: AsyncSession, data: dict) -> MerchItem:
#     item = MerchItem(**data)
#     session.add(item)
#     await session.commit()
#     return item

# --- Order Processing ---
# async def get_pending_orders(session: AsyncSession) -> list[MerchOrder]:
#     stmt = select(MerchOrder).options(joinedload(MerchOrder.user), joinedload(MerchOrder.item)).where(MerchOrder.status == 'pending_pickup').order_by(MerchOrder.order_date)
#     result = await session.execute(stmt)
#     return result.scalars().all()
#
# async def complete_order(session: AsyncSession, order_id: int, admin_id: int):
#     order = await session.get(MerchOrder, order_id)
#     if order:
#         order.status = 'completed'
#         order.completed_by_admin_id = admin_id
#         order.completion_date = datetime.datetime.now()
#         # log: # Можно добавить логирование подтверждения заказа
#         await session.commit()

# --- Manual Waiver ---
async def create_manual_waiver(session: AsyncSession, user_id: int, end_date: datetime.date, reason: str, admin_id: int):
    waiver = MedicalWaiver(
        user_id=user_id,
        start_date=datetime.date.today(),
        end_date=end_date,
        reason=reason,
        created_by=str(admin_id)
    )
    session.add(waiver)
    # log: # Можно добавить логирование создания медотвода
    await session.commit()

# --- Export Functions ---
async def get_all_donations(session: AsyncSession) -> list:
    stmt = select(Donation).options(
        joinedload(Donation.user),
        joinedload(Donation.event)
    ).order_by(Donation.donation_date.desc())
    result = await session.execute(stmt)
    return result.scalars().all()

# --- Main Admin Setup ---
async def create_main_admin(session: AsyncSession, tg_id: int, tg_username: str, full_name: str):
    new_admin = User(
        phone_number=f"admin_{tg_id}",
        telegram_id=tg_id,
        telegram_username=tg_username,
        full_name=full_name,
        role='main_admin',
        university="Администрация"  # <-- ИСПРАВЛЕНО
    )
    session.add(new_admin)

async def update_main_admin_data(session: AsyncSession, tg_id: int, tg_username: str, full_name: str):
    stmt = (
        update(User)
        .where(User.telegram_id == tg_id)
        .values(
            role='main_admin',
            telegram_username=tg_username,
            full_name=full_name
        )
    )
    await session.execute(stmt)
    await session.commit()

async def get_event_registrations_count(session: AsyncSession, event_id: int) -> int:
    stmt = select(func.count(EventRegistration.id)).where(EventRegistration.event_id == event_id)
    result = await session.execute(stmt)
    return result.scalar_one()

async def get_event_with_participants(session: AsyncSession, event_id: int):
    stmt = select(Event).options(selectinload(Event.registrations).joinedload(EventRegistration.user)).where(Event.id == event_id)
    result = await session.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        return None, []
    return event, event.registrations

async def deactivate_event(session: AsyncSession, event_id: int):
    stmt = update(Event).where(Event.id == event_id).values(is_active=False)
    await session.execute(stmt)
    await session.commit()

# async def get_all_merch_items(session: AsyncSession) -> list[MerchItem]:
#     stmt = select(MerchItem).order_by(MerchItem.id)
#     result = await session.execute(stmt)
#     return result.scalars().all()
#
# async def get_merch_item_by_id(session: AsyncSession, item_id: int) -> MerchItem | None:
#     return await session.get(MerchItem, item_id)
#
# async def update_merch_item_field(session: AsyncSession, item_id: int, field_name: str, new_value: any):
#     if not hasattr(MerchItem, field_name):
#         return
#     stmt = update(MerchItem).where(MerchItem.id == item_id).values({field_name: new_value})
#     await session.execute(stmt)
#     await session.commit()
#
# async def toggle_merch_item_availability(session: AsyncSession, item_id: int) -> bool:
#     item = await session.get(MerchItem, item_id)
#     if not item:
#         return False
#     item.is_available = not item.is_available
#     await session.commit()
#     return item.is_available
#
# async def delete_merch_item_by_id(session: AsyncSession, item_id: int):
#     item = await session.get(MerchItem, item_id)
#     if item:
#         await session.delete(item)
#         await session.commit()

# --- Export Functions ---
async def get_all_data_for_export(session: AsyncSession) -> dict:
    data_to_export = {
        "users": (await session.execute(select(User))).scalars().all(),
        "events": (await session.execute(select(Event))).scalars().all(),
        "event_registrations": (await session.execute(select(EventRegistration))).scalars().all(),
        "donations": (await session.execute(select(Donation))).scalars().all(),
        "medical_waivers": (await session.execute(select(MedicalWaiver))).scalars().all(),
        # "merch_items": (await session.execute(select(MerchItem))).scalars().all(),
        # "merch_orders": (await session.execute(select(MerchOrder))).scalars().all(),
        "user_blocks": (await session.execute(select(UserBlock))).scalars().all(),
    }
    return data_to_export



async def toggle_event_registration_status(session: AsyncSession, event_id: int) -> bool:
    """Переключает статус регистрации на мероприятие (открыта/закрыта)."""
    event = await session.get(Event, event_id)
    if not event:
        return False
    event.registration_is_open = not event.registration_is_open
    await session.commit()
    return event.registration_is_open



async def get_user_registrations(session: AsyncSession, user_id: int) -> list[EventRegistration]:
    """Получает все активные регистрации пользователя на будущие мероприятия."""
    stmt = (
        select(EventRegistration)
        .join(EventRegistration.event)
        .where(
            EventRegistration.user_id == user_id,
            Event.event_date >= datetime.date.today(),
            EventRegistration.status == 'registered'
        )
        .options(joinedload(EventRegistration.event))
        .order_by(Event.event_date)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def manually_register_user(session: AsyncSession, user: User, event: Event) -> tuple[bool, str]:
    """
    Регистрирует пользователя на мероприятие вручную от имени администратора.
    Проверяет все условия, кроме статуса открытой регистрации.
    """
    # 1. Проверка на блокировку
    if user.is_blocked:
        return False, "Пользователь заблокирован."

    # 2. Проверка на существующую регистрацию
    existing_reg = await find_specific_registration(session, user.id, event.id)
    if existing_reg:
        return False, "Пользователь уже зарегистрирован на это мероприятие."

    # 3. Проверка на медотводы (частично используем логику из check_registration_eligibility)
    waiver_stmt = select(MedicalWaiver).where(MedicalWaiver.user_id == user.id, MedicalWaiver.end_date >= event.event_date)
    active_waiver = (await session.execute(waiver_stmt)).scalar_one_or_none()
    if active_waiver:
        return False, f"У пользователя действует отвод до {active_waiver.end_date.strftime('%d.%m.%Y')}."

    # Если все проверки пройдены, регистрируем
    await add_event_registration(session, user.id, event.id)
    return True, f"Пользователь {user.full_name} успешно записан на {event.name}."


async def get_all_user_active_waivers(session: AsyncSession, user_id: int) -> list[MedicalWaiver]:
    """Получает ВСЕ активные медотводы пользователя (и системные, и личные)."""
    stmt = select(MedicalWaiver).where(
        MedicalWaiver.user_id == user_id,
        MedicalWaiver.end_date >= datetime.date.today()
    ).order_by(MedicalWaiver.end_date)
    result = await session.execute(stmt)
    return result.scalars().all()


async def force_delete_waiver(session: AsyncSession, waiver_id: int) -> bool:
    """Принудительно удаляет медотвод по его ID. Возвращает True в случае успеха."""
    stmt = delete(MedicalWaiver).where(MedicalWaiver.id == waiver_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def get_feedback_for_event(session: AsyncSession, event_id: int) -> list[Feedback]:
    stmt = (
        select(Feedback)
        .options(joinedload(Feedback.user))
        .where(Feedback.event_id == event_id)
        .order_by(Feedback.created_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_distinct_universities(session: AsyncSession) -> list[str]:
    """Возвращает список уникальных названий университетов из таблицы users."""
    stmt = select(distinct(User.university)).order_by(User.university)
    result = await session.execute(stmt)
    return result.scalars().all()

async def get_distinct_faculties(session: AsyncSession) -> list[str]:
    """Возвращает список уникальных названий факультетов из таблицы users, исключая NULL."""
    stmt = (
        select(distinct(User.faculty))
        .where(User.faculty.is_not(None)) 
        .order_by(User.faculty)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def manually_confirm_donation(session: AsyncSession, user_id: int, event_id: int, became_dkm_donor: bool) -> tuple[bool, str]:
    """
    Вручную подтверждает донацию для пользователя на мероприятии.
    Возвращает (успех, сообщение).
    """
    user = await session.get(User, user_id)
    event = await session.get(Event, event_id)
    if not user or not event:
        return False, "Пользователь или мероприятие не найдены."

    registration = await find_specific_registration(session, user_id, event_id)
    if not registration:    
        registration = EventRegistration(user_id=user_id, event_id=event_id)
        session.add(registration)
        await session.flush()

    if registration.status == 'attended':
        return False, f"Донация для {user.full_name} уже была подтверждена."

    try:
        await confirm_donation_transaction(session, user, registration)
        if became_dkm_donor and not user.is_dkm_donor:
            user.is_dkm_donor = True
            
        await session.commit()
        return True, f"Донация для {user.full_name} подтверждена."
    except Exception as e:
        await session.rollback()
        logger.error(f"Error in manually_confirm_donation for user {user_id}: {e}")
        return False, f"Ошибка при подтверждении для {user.full_name}: {e}"


async def get_min_user_id(session: AsyncSession) -> int:
    """
    Gets the minimum user ID from the database.
    """
    result = await session.execute(select(func.min(User.telegram_id)))
    min_id = result.scalar_one_or_none()
    return min_id if min_id is not None else 0