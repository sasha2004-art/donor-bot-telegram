import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, Donation
from bot.db import user_requests
import datetime
import pandas as pd


async def import_data_from_file(session: AsyncSession, file_bytes: bytes) -> tuple[int, int]:
    """
    Imports data from an .xlsx file with the old format into the database.
    Returns a tuple of (created_count, updated_count).
    """
    df = pd.read_excel(file_bytes)

    column_mapping = {
        'ФИО': 'full_name',
        'Телефон': 'phone_number',
        'Группа': 'study_group',
        'Кол-во Гаврилова': 'donations_gavrilov',
        'Кол-во ФМБА': 'donations_fmba',
    }

    df = df.rename(columns=column_mapping)

    required_cols = ['full_name', 'phone_number']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Ошибка: в файле отсутствуют обязательные колонки ({', '.join(required_cols)}).")

    created_count = 0
    updated_count = 0

    for index, row in df.iterrows():
        phone = str(row['phone_number'])
        if not phone.startswith('+'):
            phone = '+' + phone
        user = await user_requests.get_user_by_phone(session, phone)

        study_group = row.get('study_group')
        university = "НИЯУ МИФИ" if 'сотрудник' in str(study_group).lower() or (study_group and study_group != '-') else "Внешний донор"
        faculty = "Сотрудник" if 'сотрудник' in str(study_group).lower() else None

        user_data = {
            'full_name': row.get('full_name'),
            'university': university,
            'faculty': faculty,
            'study_group': study_group if university == "НИЯУ МИФИ" and faculty != "Сотрудник" else None,
            'role': 'student',
        }
        user_data = {k: v for k, v in user_data.items() if pd.notna(v)}

        if user:
            await user_requests.update_user_profile(session, user.id, user_data)
            updated_count += 1
        else:
            full_data = user_data.copy()
            full_data['phone_number'] = phone
            full_data['telegram_id'] = -index  # Use negative index for unique tg_id
            full_data['telegram_username'] = f"import_{phone}"
            user = await user_requests.add_user(session, full_data)
            await session.flush()  # Flush to get the user ID
            created_count += 1

        donations_gavrilov = row.get('donations_gavrilov', 0)
        donations_fmba = row.get('donations_fmba', 0)
        total_donations = (donations_gavrilov if pd.notna(donations_gavrilov) else 0) + \
                          (donations_fmba if pd.notna(donations_fmba) else 0)

        if total_donations > 0:
            for _ in range(int(total_donations)):
                donation = Donation(
                    user_id=user.id,
                    donation_date=datetime.date(2023, 1, 1),
                    donation_type='whole_blood',
                    points_awarded=0,
                    event_id=None
                )
                session.add(donation)

    await session.commit()
    return created_count, updated_count
