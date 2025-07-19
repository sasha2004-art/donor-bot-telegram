import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, Donation
from bot.db import user_requests
import datetime
import pandas as pd


async def import_data_from_file(session: AsyncSession, file_bytes: bytes) -> tuple[int, int]:
    """
    Imports data from an .xlsx file into the database.
    Returns a tuple of (created_count, updated_count).
    """
    df = pd.read_excel(file_bytes)

    required_cols = ['phone_number', 'full_name', 'university']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Ошибка: в файле отсутствуют обязательные колонки ({', '.join(required_cols)}).")

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
            user = await user_requests.add_user(session, full_data)
            created_count += 1

        donations_count = row.get('Кол-во донаций')
        if pd.notna(donations_count):
            for _ in range(int(donations_count)):
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
