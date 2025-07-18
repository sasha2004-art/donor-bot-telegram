import io
import csv
import logging
import zipfile
import datetime
from aiogram import Router, F, types, Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import admin_requests
from bot.filters.role import RoleFilter
from bot.utils.text_messages import Text

router = Router(name="admin_system")
logger = logging.getLogger(__name__)


# =============================================================================
# --- 💾 ЭКСПОРТ ДАННЫХ (ТОЛЬКО ДЛЯ ГЛАВНОГО АДМИНА) ---
# =============================================================================

async def create_full_backup_zip(session: AsyncSession) -> io.BytesIO:
    """
    Собирает данные из всех таблиц, создает CSV-файлы и упаковывает их в ZIP-архив в памяти.
    """
    all_data = await admin_requests.get_all_data_for_export(session)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for table_name, records in all_data.items():
            if not records:
                continue

            csv_buffer = io.StringIO()
            headers = [c.name for c in records[0].__table__.columns]
            writer = csv.DictWriter(csv_buffer, fieldnames=headers, delimiter=';')
            writer.writeheader()
            
            for record in records:
                row_data = {}
                for h in headers:
                    # Преобразуем сложные типы в строки, чтобы избежать ошибок csv
                    value = getattr(record, h)
                    if isinstance(value, (datetime.datetime, datetime.date)):
                        row_data[h] = value.isoformat()
                    elif isinstance(value, list):
                         row_data[h] = str(value) # для relationship полей, хотя лучше их не выгружать так
                    else:
                        row_data[h] = value
                writer.writerow(row_data)
            
            # Добавляем CSV-строку в ZIP-архив как файл
            zip_file.writestr(f"{table_name}.csv", csv_buffer.getvalue().encode('utf-8-sig'))

    zip_buffer.seek(0)
    return zip_buffer


@router.callback_query(F.data == "ma_export_data", RoleFilter('main_admin'))
async def export_data_start(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    """
    Запускает процесс создания и отправки полного бэкапа.
    """
    msg = await callback.message.edit_text(Text.EXPORT_STARTED)
    await callback.answer()

    try:
        zip_archive_bytes = await create_full_backup_zip(session)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"donor_bot_backup_{timestamp}.zip"
        
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=types.BufferedInputFile(zip_archive_bytes.read(), filename=filename),
            caption=Text.EXPORT_SUCCESSFUL
        )
        
        await msg.delete()

    except Exception as e:
        logger.error(f"Failed to create data backup: {e}", exc_info=True)
        await msg.edit_text(Text.EXPORT_FAILED)
