'''
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.markdown import hbold, hlink
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.db import admin_requests, user_requests
from bot.filters.role import RoleFilter
from bot.states.states import MerchCreation, MerchEditing
from bot.keyboards import inline
from bot.db.models import MerchOrder
from bot.utils.text_messages import Text

router = Router(name="admin_merch_management")
logger = logging.getLogger(__name__)


# =============================================================================
# --- 🛍️ УПРАВЛЕНИЕ МАГАЗИНОМ ---
# =============================================================================
@router.callback_query(F.data == "admin_manage_merch", RoleFilter('admin'))
async def manage_merch_panel(callback: types.CallbackQuery):
    # ИСПРАВЛЕНО: parse_mode="HTML"
    await callback.message.edit_text(Text.ADMIN_MERCH_HEADER, reply_markup=inline.get_merch_management_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- Создание товара ---
@router.callback_query(F.data == "admin_create_merch", RoleFilter('admin'))
async def start_merch_creation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MerchCreation.awaiting_photo)
    await callback.message.edit_text(Text.MERCH_CREATE_STEP_1_PHOTO)
    await callback.answer()

@router.message(MerchCreation.awaiting_photo, F.photo)
async def process_merch_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(MerchCreation.awaiting_name)
    await message.answer(Text.MERCH_PHOTO_RECEIVED)

@router.message(MerchCreation.awaiting_name)
async def process_merch_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(MerchCreation.awaiting_description)
    await message.answer(Text.MERCH_NAME_RECEIVED)

@router.message(MerchCreation.awaiting_description)
async def process_merch_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(MerchCreation.awaiting_price)
    await message.answer(Text.MERCH_DESC_RECEIVED)

@router.message(MerchCreation.awaiting_price)
async def process_merch_price(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        price = int(message.text)
        await state.update_data(price=price)
        item_data = await state.get_data()

        if 'photo_file_id' not in item_data or not item_data['photo_file_id']:
            logger.error("photo_file_id is missing from FSM data during merch creation!")
            await message.answer(Text.MERCH_CREATE_PHOTO_ID_ERROR)
            await state.clear()
            return

        await admin_requests.create_merch_item(session, item_data)
        await session.commit()
        await state.clear()

        await message.answer(Text.MERCH_CREATE_SUCCESS, reply_markup=inline.get_back_to_admin_panel_keyboard())
    except ValueError:
        await message.answer(Text.MERCH_PRICE_NAN_ERROR)

# --- Просмотр и редактирование товаров ---
@router.callback_query(F.data == "admin_view_merch", RoleFilter('admin'))
async def view_merch_items(callback: types.CallbackQuery, session: AsyncSession):
    items = await admin_requests.get_all_merch_items(session)
    if not items:
        await callback.message.edit_text(Text.ADMIN_NO_MERCH_ITEMS, reply_markup=inline.get_merch_management_keyboard())
        return

    builder = InlineKeyboardBuilder()
    for item in items:
        status = "✅" if item.is_available else "❌"
        builder.row(types.InlineKeyboardButton(text=f"{status} {item.name} ({item.price}Б)", callback_data=f"admin_show_merch_{item.id}"))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_manage_merch"))

    try:
        await callback.message.edit_text(Text.ADMIN_CHOOSE_MERCH_TO_MANAGE, reply_markup=builder.as_markup())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(Text.ADMIN_CHOOSE_MERCH_TO_MANAGE, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("admin_show_merch_"), RoleFilter('admin'))
async def show_single_merch_card(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    item = await admin_requests.get_merch_item_by_id(session, item_id)
    if not item: return await callback.answer(Text.MERCH_ITEM_NOT_FOUND, show_alert=True)

    status_text = '✅ Доступен' if item.is_available else '❌ Недоступен'
    caption = Text.MERCH_CARD_CAPTION.format(
        name=item.name,
        description=item.description,
        price=item.price,
        status=status_text
    )
    # ИСПРАВЛЕНО: parse_mode="HTML"
    await callback.message.edit_media(media=types.InputMediaPhoto(media=item.photo_file_id, caption=caption, parse_mode="HTML"),
        reply_markup=inline.get_single_merch_management_keyboard(item.id, item.is_available))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_edit_merch_"), RoleFilter('admin'))
async def start_merch_editing(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    item_id = int(callback.data.split('_')[-1])
    item = await admin_requests.get_merch_item_by_id(session, item_id)
    if not item: return

    await state.update_data(item_id=item_id)
    await state.set_state(MerchEditing.choosing_field)

    fields = {"name": "Название", "description": "Описание", "price": "Цена"}
    builder = InlineKeyboardBuilder()
    for key, name in fields.items():
        builder.row(types.InlineKeyboardButton(text=f"Изменить: {name}", callback_data=f"edit_merch_field_{key}"))
    builder.row(types.InlineKeyboardButton(text="✅ Завершить", callback_data=f"admin_show_merch_{item_id}"))

    # ИСПРАВЛЕНО: parse_mode="HTML"
    await callback.message.edit_caption(caption=Text.MERCH_EDIT_PROMPT.format(name=item.name), reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(MerchEditing.choosing_field, F.data.startswith("edit_merch_field_"))
async def choose_merch_field_to_edit(callback: types.CallbackQuery, state: FSMContext):
    field_to_edit = callback.data.split('_', 3)[-1]
    await state.update_data(field_to_edit=field_to_edit)
    await state.set_state(MerchEditing.awaiting_new_value)

    prompt = Text.MERCH_EDIT_FIELD_PROMPTS.get(field_to_edit, Text.MERCH_EDIT_NEW_VALUE_PROMPT)
    await callback.message.delete()
    await callback.message.answer(prompt)
    await callback.answer()

@router.message(MerchEditing.awaiting_new_value)
async def process_new_value_for_merch(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    field, item_id, new_value_str = data.get("field_to_edit"), data.get("item_id"), message.text
    try:
        update_value = int(new_value_str) if field == "price" else new_value_str
    except ValueError:
        return await message.answer(Text.MERCH_PRICE_NAN_ERROR)

    await admin_requests.update_merch_item_field(session, item_id, field, update_value)
    await session.commit()
    await message.answer(Text.MERCH_EDIT_SUCCESS)
    await state.clear()

    item = await admin_requests.get_merch_item_by_id(session, item_id)
    status_text = '✅ Доступен' if item.is_available else '❌ Недоступен'
    caption = Text.MERCH_CARD_CAPTION.format(
        name=item.name,
        description=item.description,
        price=item.price,
        status=status_text
    )
    # ИСПРАВЛЕНО: parse_mode="HTML"
    await message.answer_photo(photo=item.photo_file_id, caption=caption,
        reply_markup=inline.get_single_merch_management_keyboard(item.id, item.is_available), parse_mode="HTML")

@router.callback_query(F.data.startswith("admin_toggle_merch_"), RoleFilter('admin'))
async def toggle_merch_availability(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    new_status = await admin_requests.toggle_merch_item_availability(session, item_id)
    await session.commit()
    status_text = 'доступен' if new_status else 'недоступен'
    await callback.answer(Text.MERCH_TOGGLE_AVAILABILITY.format(status=status_text), show_alert=True)
    await show_single_merch_card(callback, session)

@router.callback_query(F.data.startswith("admin_delete_merch_"), RoleFilter('admin'))
async def ask_for_merch_deletion_confirmation(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    item = await admin_requests.get_merch_item_by_id(session, item_id)
    if not item: return await callback.answer(Text.MERCH_ITEM_NOT_FOUND, show_alert=True)

    try: await callback.message.delete()
    except TelegramBadRequest: pass

    # ИСПРАВЛЕНО: parse_mode="HTML"
    await callback.message.answer(
        Text.MERCH_DELETE_CONFIRMATION.format(name=item.name),
        reply_markup=inline.get_merch_deletion_confirmation_keyboard(item_id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_confirm_delete_merch_"), RoleFilter('admin'))
async def confirm_and_delete_merch(callback: types.CallbackQuery, session: AsyncSession):
    item_id = int(callback.data.split('_')[-1])
    item = await admin_requests.get_merch_item_by_id(session, item_id)
    if not item: return await callback.answer(Text.MERCH_ITEM_ALREADY_DELETED, show_alert=True)

    item_name = item.name
    await admin_requests.delete_merch_item_by_id(session, item_id)
    await session.commit()
    # ИСПРАВЛЕНО: parse_mode="HTML"
    await callback.message.edit_text(Text.MERCH_DELETE_SUCCESS.format(name=item_name), reply_markup=inline.get_back_to_merch_menu_keyboard(), parse_mode="HTML")
    await callback.answer()

# =============================================================================
# --- 📦 ОБРАБОТКА ЗАКАЗОВ ---
# =============================================================================
@router.callback_query(F.data == "admin_process_orders", RoleFilter('admin'))
async def process_orders_list(callback: types.CallbackQuery, session: AsyncSession):
    orders = await admin_requests.get_pending_orders(session)
    if not orders:
        await callback.answer(Text.ADMIN_NO_PENDING_ORDERS, show_alert=True)
        return

    text_parts = [Text.ADMIN_PENDING_ORDERS_HEADER]
    builder = InlineKeyboardBuilder()
    for order in orders:
        user_link = hlink(order.user.full_name, f"tg://user?id={order.user.telegram_id}")

        if order.user.telegram_username:
            order_info = Text.ADMIN_ORDER_ITEM_TEXT.format(
                order_id=order.id,
                date=order.order_date.strftime('%d.%m %H:%M'),
                item_name=order.item.name,
                user_link=user_link,
                username=order.user.telegram_username,
                phone=order.user.phone_number
            )
        else:
            order_info = Text.ADMIN_ORDER_ITEM_TEXT_NO_USERNAME.format(
                order_id=order.id,
                date=order.order_date.strftime('%d.%m %H:%M'),
                item_name=order.item.name,
                user_link=user_link,
                phone=order.user.phone_number
            )

        text_parts.append(order_info)
        text_parts.append("")
        builder.row(types.InlineKeyboardButton(text=f"✅ Выдать заказ №{order.id}", callback_data=f"complete_order_{order.id}"))

    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_panel"))

    await callback.message.edit_text(
        text="\n".join(text_parts),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("complete_order_"), RoleFilter('admin'))
async def complete_order(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    order_id = int(callback.data.split('_')[-1])

    admin_user = await user_requests.get_user_by_tg_id(session, callback.from_user.id)
    if not admin_user:
        await callback.answer(Text.ADMIN_COMPLETE_ORDER_ADMIN_ID_ERROR, show_alert=True)
        return

    order = await session.get(MerchOrder, order_id, options=[joinedload(MerchOrder.item), joinedload(MerchOrder.user)])
    if not order or order.status != 'pending_pickup':
        await callback.answer(Text.ADMIN_ORDER_NOT_FOUND_OR_PROCESSED, show_alert=True)
        return

    await admin_requests.complete_order(session, order_id, admin_user.id)
    await session.commit()
    await callback.answer(Text.ADMIN_ORDER_COMPLETED_SUCCESS.format(order_id=order_id), show_alert=True)

    try:
        await bot.send_message(
            chat_id=order.user.telegram_id,
            text=Text.USER_ORDER_COMPLETED_NOTIFICATION.format(item_name=order.item.name)
        )
    except Exception as e:
        logger.error(f"Failed to notify user {order.user.id} about order completion: {e}")

    await process_orders_list(callback, session)
'''
