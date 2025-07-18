import io
import logging
import zipfile
import datetime
import pandas as pd
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext  # <-- ВОТ НУЖНЫЙ ИМПОРТ
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import admin_requests, user_requests
from bot.db.models import User
from bot.filters.role import RoleFilter
from bot.states.states import DataImport
from bot.utils.text_messages import Text

router = Router(name="admin_system")
logger = logging.getLogger(__name__)


# =============================================================================
# --- 💾 ЭКСПОРТ ДАННЫХ (ТОЛЬКО ДЛЯ ГЛАВНОГО АДМИНА) ---
# =============================================================================

async def create_full_backup_xlsx(session: AsyncSession) -> io.BytesIO:
    """
    Собирает данные из всех таблиц, создает XLSX-файл с несколькими листами.
    """
    all_data_models = await admin_requests.get_all_data_for_export(session)
    
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        for table_name, records in all_data_models.items():
            if not records:
                continue

            data_list = [
                {c.name: getattr(record, c.name) for c in record.__table__.columns}
                for record in records
            ]
            
            df = pd.DataFrame(data_list)
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]) and df[col].dt.tz is not None:
                    df[col] = df[col].dt.tz_localize(None)
            for col in df.columns:
                if not df[col].dropna().empty:
                    if isinstance(df[col].dropna().iloc[0], (dict, list)):
                        df[col] = df[col].astype(str)
            
            df.to_excel(writer, sheet_name=table_name.capitalize(), index=False)

    output_buffer.seek(0)
    return output_buffer


@router.callback_query(F.data == "ma_export_data", RoleFilter('main_admin'))
async def export_data_start(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    """
    Запускает процесс создания и отправки полного бэкапа в XLSX.
    """
    msg = await callback.message.edit_text(Text.EXPORT_STARTED)
    await callback.answer()

    try:
        xlsx_archive_bytes = await create_full_backup_xlsx(session)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"donor_bot_backup_{timestamp}.xlsx"
        
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=types.BufferedInputFile(xlsx_archive_bytes.read(), filename=filename),
            caption=Text.EXPORT_SUCCESSFUL
        )
        
        await msg.delete()

    except Exception as e:
        logger.error(f"Failed to create data backup: {e}", exc_info=True)
        await msg.edit_text(Text.EXPORT_FAILED)


# =============================================================================
# --- 📥 ИМПОРТ ДАННЫХ (ТОЛЬКО ДЛЯ ГЛАВНОГО АДМИНА) ---
# =============================================================================

@router.callback_query(F.data == "ma_import_data", RoleFilter('main_admin'))
async def import_data_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DataImport.awaiting_file)
    await callback.message.edit_text("Отправьте .xlsx файл для импорта/обновления данных пользователей. Обязательные колонки: `phone_number` (для поиска), `full_name`, `university`.")
    await callback.answer()

@router.message(DataImport.awaiting_file, F.document)
async def process_import_file(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if not message.document.file_name.endswith('.xlsx'):
        await message.answer("Неверный формат файла. Пожалуйста, отправьте файл .xlsx")
        return

    await state.clear()
    status_msg = await message.answer("Файл получен. Начинаю обработку...")
    
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)

    try:
        df = pd.read_excel(file_bytes)
        
        required_cols = ['phone_number', 'full_name', 'university']
        if not all(col in df.columns for col in required_cols):
            await status_msg.edit_text(f"Ошибка: в файле отсутствуют обязательные колонки ({', '.join(required_cols)}).")
            return
            
        created_count = 0
        updated_count = 0

        for index, row in df.iterrows():
            phone = str(row['phone_number'])
            user = await user_requests.get_user_by_phone(session, phone)
            
            user_data = {
                'full_name': row.get('full_name'),
                'university': row.get('university'),
                'faculty': row.get('faculty'),
                'study_group': row.get('study_group'),
                'blood_type': row.get('blood_type'),
                'rh_factor': row.get('rh_factor'),
                'gender': row.get('gender'),
                'points': row.get('points', 0),
                'role': row.get('role', 'student'),
                'is_dkm_donor': bool(row.get('is_dkm_donor', False))
            }
            user_data = {k: v for k, v in user_data.items() if pd.notna(v)}

            if user:
                await user_requests.update_user_profile(session, user.id, user_data)
                updated_count += 1
            else:
                full_data = user_data.copy()
                full_data['phone_number'] = phone
                full_data['telegram_id'] = 0
                full_data['telegram_username'] = f"import_{phone}"
                await user_requests.add_user(session, full_data)
                created_count += 1
        
        await session.commit()
        await status_msg.edit_text(f"✅ Импорт завершен!\n\n- Создано новых пользователей: {created_count}\n- Обновлено существующих: {updated_count}")
        
    except Exception as e:
        logger.error(f"Error processing XLSX import: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Произошла ошибка при обработке файла: {e}")