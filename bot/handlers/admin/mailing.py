import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.db.engine import async_session_maker
from bot.db import user_requests, admin_requests
from bot.filters.role import RoleFilter
from bot.states.states import Mailing
from bot.keyboards import inline
from bot.utils.text_messages import Text

router = Router(name="admin_mailing")
logger = logging.getLogger(__name__)


async def show_audience_choice_menu(message: types.Message, state: FSMContext):
    """Отображает меню выбора аудитории с текущими фильтрами."""
    data = await state.get_data()
    current_filters = data.get("filters", {})
    
    text_parts = [Text.MAILING_STEP_3_AUDIENCE_PROMPT]
    if current_filters:
        text_parts.append("\n<b>Выбранные фильтры:</b>")
        for key, value in current_filters.items():
            text_parts.append(f"  - {key.replace('_', ' ').capitalize()}: <code>{value}</code>")
    
    prompt_text = "\n".join(text_parts)

    await message.answer(
        text=prompt_text,
        reply_markup=inline.get_mailing_audience_keyboard(current_filters),
        parse_mode="HTML"
    )

# =============================================================================
# --- 📣 РАССЫЛКИ (FSM) ---
# =============================================================================

@router.callback_query(F.data == "admin_mailing", RoleFilter('admin'))
async def start_mailing(callback: types.CallbackQuery, state: FSMContext):
    """Шаг 1: Запрашивает текст для рассылки."""
    await state.clear()
    await state.set_state(Mailing.awaiting_message_text)
    await callback.message.edit_text(Text.MAILING_STEP_1_TEXT_PROMPT, parse_mode="HTML")
    await callback.answer()


@router.message(Mailing.awaiting_message_text)
async def get_mailing_text(message: types.Message, state: FSMContext):
    """Шаг 2: Получает текст и запрашивает медиа."""
    await state.update_data(
        message_text=message.html_text,
        photo_id=None,
        video_id=None,
        filters={}
    )
    await state.set_state(Mailing.awaiting_media)
    await message.answer(Text.MAILING_STEP_2_MEDIA_PROMPT, reply_markup=inline.get_skip_media_keyboard(), parse_mode="HTML")


@router.message(Mailing.awaiting_media, F.photo)
async def get_mailing_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(Mailing.awaiting_audience_choice)
    await show_audience_choice_menu(message, state)


@router.message(Mailing.awaiting_media, F.video)
async def get_mailing_video(message: types.Message, state: FSMContext):
    await state.update_data(video_id=message.video.file_id)
    await state.set_state(Mailing.awaiting_audience_choice)
    await show_audience_choice_menu(message, state)


@router.callback_query(Mailing.awaiting_media, F.data == "skip_media")
async def skip_media_step(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.awaiting_audience_choice)
    await callback.message.delete()
    await show_audience_choice_menu(callback.message, state)
    await callback.answer()


@router.callback_query(Mailing.awaiting_audience_choice, F.data.startswith("mail_audience_type_"))
async def choose_audience_filter_type(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Шаг 3.1: Админ выбрал тип фильтра (ВУЗ, факультет, группа крови)."""
    filter_type = callback.data.split('_')[-1]
    
    items = []
    prompt_text = "Неизвестный тип фильтра"
    
    if filter_type == "university":
        items = await admin_requests.get_distinct_universities(session)
        prompt_text = "Выберите ВУЗ для фильтрации:"
    elif filter_type == "faculty":
        items = await admin_requests.get_distinct_faculties(session)
        prompt_text = "Выберите факультет для фильтрации:"
    elif filter_type == "blood_type":
        items = ["O(I)", "A(II)", "B(III)", "AB(IV)"]
        prompt_text = "Выберите группу крови для фильтрации:"

    if not items:
        await callback.answer("Нет доступных значений для этого фильтра.", show_alert=True)
        return

    keyboard = inline.get_dynamic_mailing_filter_keyboard(items, filter_type, "mail_audience_back")
    await callback.message.edit_text(prompt_text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(Mailing.awaiting_audience_choice, F.data.startswith("mail_filter_"))
async def set_audience_filter(callback: types.CallbackQuery, state: FSMContext):
    """Шаг 3.2: Админ выбрал конкретное значение. Добавляем фильтр и возвращаемся в меню."""
    parts = callback.data.split('_')
    filter_key = parts[2]
    filter_value = '_'.join(parts[3:])

    data = await state.get_data()
    current_filters = data.get("filters", {})
    current_filters[filter_key] = filter_value
    await state.update_data(filters=current_filters)
    
    await callback.message.delete()
    await show_audience_choice_menu(callback.message, state)
    await callback.answer(f"Фильтр '{filter_value}' добавлен!")


@router.callback_query(Mailing.awaiting_audience_choice, F.data == "mail_audience_back")
async def back_to_audience_choice_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к основному меню выбора аудитории из меню выбора значения."""
    await callback.message.delete()
    await show_audience_choice_menu(callback.message, state)
    await callback.answer()


@router.callback_query(Mailing.awaiting_audience_choice, F.data == "mail_audience_reset")
async def reset_audience_filters(callback: types.CallbackQuery, state: FSMContext):
    """Сбрасывает все выбранные фильтры."""
    await state.update_data(filters={})
    await callback.message.delete()
    await show_audience_choice_menu(callback.message, state)
    await callback.answer("Все фильтры сброшены.", show_alert=True)


@router.callback_query(Mailing.awaiting_audience_choice, F.data == "mail_audience_finish")
async def finish_audience_selection(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    """Шаг 4: Админ нажал 'Готово'. Переход к подтверждению."""
    data = await state.get_data()
    filters = data.get("filters", {})
    
    if not filters:
        await callback.answer("Вы не выбрали ни одного фильтра!", show_alert=True)
        return

    audience_text_parts = []
    for key, value in filters.items():
        audience_text_parts.append(f"{key.replace('_', ' ').capitalize()}: {value}")
    audience_text = " и ".join(audience_text_parts)

    users_to_notify = await user_requests.get_users_for_mailing(session, filters)
    recipient_count = len(users_to_notify)

    message_text = data.get("message_text")
    photo_id = data.get("photo_id")
    video_id = data.get("video_id")
    
    preview_text = Text.MAILING_PREVIEW_HEADER.format(audience=audience_text, count=recipient_count)
    if photo_id: preview_text += Text.MAILING_PREVIEW_WITH_PHOTO
    if video_id: preview_text += Text.MAILING_PREVIEW_WITH_VIDEO
    preview_text += Text.MAILING_PREVIEW_TEXT_HEADER.format(text=message_text)
            
    await state.set_state(Mailing.awaiting_confirmation)
    
    await callback.message.delete()
    await callback.message.answer(preview_text, reply_markup=inline.get_mailing_confirmation_keyboard(), parse_mode="HTML")
    await callback.answer()


# --- Подтверждение и запуск ---

@router.callback_query(Mailing.awaiting_confirmation, F.data == "confirm_mailing")
async def confirm_and_start_mailing(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Запускает рассылку в фоновом режиме."""
    data = await state.get_data()
    await state.clear()
    
    await callback.message.edit_text(
        Text.MAILING_CONFIRMED_AND_RUNNING,
        reply_markup=inline.get_back_to_admin_panel_keyboard()
    )
    
    asyncio.create_task(do_mailing(
        filters=data.get("filters", {}),
        message_text=data.get("message_text"),
        photo_id=data.get("photo_id"),
        video_id=data.get("video_id"),
        bot=bot
    ))
    await callback.answer()


async def _send_broadcast_safe(bot: Bot, user_id: int, text: str, photo_id: str | None, video_id: str | None):
    """Безопасно отправляет широковещательное сообщение."""
    try:
        if photo_id:
            await bot.send_photo(user_id, photo_id, caption=text, parse_mode="HTML")
        elif video_id:
            await bot.send_video(user_id, video_id, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(user_id, text, parse_mode="HTML")
        return True
    except TelegramForbiddenError:
        logger.warning(f"Failed to send broadcast to user {user_id}. Bot was blocked or user deactivated.")
    except TelegramBadRequest as e:
         if "chat not found" in str(e):
             logger.warning(f"Failed to send broadcast to user {user_id}. Chat not found.")
         else:
             logger.error(f"Failed to send broadcast to user {user_id}. Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending broadcast to user {user_id}: {e}")
    return False


async def do_mailing(filters: dict, message_text: str, photo_id: str | None, video_id: str | None, bot: Bot):
    """Асинхронная задача для выполнения рассылки с использованием asyncio.gather."""
    logger.info(f"Starting mailing for filters: {filters}")
    async with async_session_maker() as session:
        try:
            users = await user_requests.get_users_for_mailing(session, filters)
            if not users:
                logger.warning("No users found for this mailing criteria.")
                return

            total_users = len(users)
            logger.info(f"Found {total_users} users for mailing.")

            tasks = [
                _send_broadcast_safe(bot, user.telegram_id, message_text, photo_id, video_id)
                for user in users
            ]

            results = await asyncio.gather(*tasks)

            success_count = sum(1 for r in results if r)
            fail_count = total_users - success_count

            logger.info(f"Mailing finished. Sent: {success_count}, Failed: {fail_count}.")

        except Exception as e:
            logger.error(f"Critical error during mailing: {e}", exc_info=True)