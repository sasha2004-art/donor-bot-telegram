from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from bot.db import question_requests, user_requests
from bot.filters.role import RoleFilter
from bot.states.states import AnswerQuestion
from bot.keyboards import inline
from bot.utils.text_messages import Text

router = Router(name="admin_qa_management")

@router.callback_query(F.data == "admin_answer_questions", RoleFilter('admin'))
async def show_unanswered_questions(callback: types.CallbackQuery, session: AsyncSession):
    questions = await question_requests.get_unanswered_questions(session)
    if not questions:
        await callback.answer("Новых вопросов от пользователей нет.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for q in questions:
        builder.row(types.InlineKeyboardButton(
            text=f"От {q.user.full_name}: {q.question_text[:30]}...",
            callback_data=f"answer_q_{q.id}"
        ))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_panel"))
    
    await callback.message.edit_text(
        "<b>Неотвеченные вопросы:</b>\n\nВыберите вопрос, чтобы ответить:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("answer_q_"), RoleFilter('admin'))
async def start_answering_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    question_id = int(callback.data.split("_")[-1])
    question = await session.get(question_requests.Question, question_id, options=[joinedload(question_requests.Question.user)])
    if not question:
        await callback.answer("Вопрос не найден.", show_alert=True)
        return
        
    await state.set_state(AnswerQuestion.awaiting_answer)
    await state.update_data(question_id=question.id, user_to_answer_id=question.user.telegram_id)
    
    await callback.message.edit_text(
        f"<b>Вопрос от:</b> {question.user.full_name}\n"
        f"<b>Текст вопроса:</b>\n<i>{Text.escape_html(question.question_text)}</i>\n\n"
        f"<b>Введите ваш ответ:</b>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AnswerQuestion.awaiting_answer, F.text)
async def process_answer(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data()
    question_id = data.get("question_id")
    user_to_answer_id = data.get("user_to_answer_id")
    admin_user = await user_requests.get_user_by_tg_id(session, message.from_user.id)
    
    await question_requests.answer_question(session, question_id, message.text, admin_user.id)
    
    question = await session.get(question_requests.Question, question_id)

    # Уведомляем пользователя
    try:
        await bot.send_message(
            chat_id=user_to_answer_id,
            text=(
                f"📨 <b>Получен ответ на ваш вопрос!</b>\n\n"
                f"<b>Ваш вопрос:</b>\n<i>{Text.escape_html(question.question_text)}</i>\n\n"
                f"<b>Ответ организаторов:</b>\n{Text.escape_html(message.text)}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"Не удалось уведомить пользователя. Ошибка: {e}")

    await state.clear()
    await message.answer("✅ Ответ отправлен пользователю.", reply_markup=inline.get_back_to_admin_panel_keyboard())