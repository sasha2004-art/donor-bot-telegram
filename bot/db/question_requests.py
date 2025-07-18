import datetime
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Question, User

async def create_question(session: AsyncSession, user_id: int, question_text: str):
    """Сохраняет новый вопрос от пользователя."""
    new_question = Question(user_id=user_id, question_text=question_text)
    session.add(new_question)
    await session.commit()

async def get_unanswered_questions(session: AsyncSession) -> list[Question]:
    """Получает список неотвеченных вопросов с информацией о пользователе."""
    stmt = (
        select(Question)
        .options(joinedload(Question.user))
        .where(Question.status == 'unanswered')
        .order_by(Question.created_at)
    )
    result = await session.execute(stmt)
    return result.scalars().all()

async def answer_question(session: AsyncSession, question_id: int, answer_text: str, admin_id: int):
    """Сохраняет ответ на вопрос и обновляет его статус."""
    stmt = (
        update(Question)
        .where(Question.id == question_id)
        .values(
            answer_text=answer_text,
            status='answered',
            answered_at=datetime.datetime.now(),
            answered_by_admin_id=admin_id
        )
    )
    await session.execute(stmt)
    await session.commit()