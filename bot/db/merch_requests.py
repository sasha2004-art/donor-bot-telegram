# import math
# from sqlalchemy import select, func
# from sqlalchemy.orm import joinedload
# from sqlalchemy.ext.asyncio import AsyncSession
# from .models import User, MerchItem, MerchOrder
#
# async def get_merch_page(session: AsyncSession, page: int = 1) -> tuple[MerchItem | None, int]:
#     page_size = 1
#     offset = (page - 1) * page_size
#     total_count_stmt = select(func.count(MerchItem.id)).where(MerchItem.is_available == True)
#     total_items = (await session.execute(total_count_stmt)).scalar_one()
#
#     if total_items == 0:
#         return None, 0
#     item_stmt = select(MerchItem).where(MerchItem.is_available == True).order_by(MerchItem.id).offset(offset).limit(page_size)
#     item_result = await session.execute(item_stmt)
#     item = item_result.scalar_one_or_none()
#
#     return item, total_items
#
# async def get_merch_item_by_id(session: AsyncSession, item_id: int) -> MerchItem | None:
#     return await session.get(MerchItem, item_id)
#
# async def create_merch_order(session: AsyncSession, user: User, item: MerchItem) -> tuple[bool, str]:
#     if user.points < item.price:
#         return False, "Недостаточно баллов."
#
#     user.points -= item.price
#     order = MerchOrder(user_id=user.id, item_id=item.id)
#     session.add(order)
#     return True, f"Покупка совершена! Ваш баланс: {user.points} баллов."
#
# async def get_user_orders(session: AsyncSession, user_id: int) -> list[MerchOrder]:
#     stmt = select(MerchOrder).options(joinedload(MerchOrder.item)).where(MerchOrder.user_id == user_id).order_by(MerchOrder.order_date.desc())
#     result = await session.execute(stmt)
#     return result.scalars().all()
