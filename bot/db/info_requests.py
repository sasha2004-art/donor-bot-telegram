from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from .models import InfoText

async def get_info_text(session: AsyncSession, section_key: str) -> str | None:
    """Получает текст инфо-раздела по ключу."""
    text_obj = await session.get(InfoText, section_key)
    return text_obj.section_text if text_obj else "Раздел не найден."

async def get_all_info_sections(session: AsyncSession) -> list[InfoText]:
    """Получает все инфо-разделы для меню редактирования."""
    result = await session.execute(select(InfoText).order_by(InfoText.section_key))
    return result.scalars().all()

async def update_info_text(session: AsyncSession, section_key: str, new_text: str):
    """Обновляет текст инфо-раздела."""
    stmt = (
        update(InfoText)
        .where(InfoText.section_key == section_key)
        .values(section_text=new_text)
    )
    await session.execute(stmt)
    await session.commit()