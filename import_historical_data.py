import asyncio
import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.engine import async_session_maker
from bot.db.models import User, Donation
from bot.db import user_requests
import datetime
from bot.config_reader import config
from dotenv import load_dotenv

load_dotenv()


async def main():
    """
    Imports historical data from an .xlsx file into the database.
    """
    workbook = openpyxl.load_workbook("historical_data.xlsx")
    sheet = workbook.active

    async with async_session_maker() as session:
        for row in sheet.iter_rows(min_row=2, values_only=True):
            full_name, phone_number, university, faculty, study_group, dkm, donations_count = row

            if not phone_number:
                continue

            phone_number = str(phone_number)
            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number

            user = await user_requests.get_user_by_phone(session, phone_number)

            if not user:
                user = await user_requests.add_user(session, {
                    "full_name": full_name,
                    "phone_number": phone_number,
                    "university": university,
                    "faculty": faculty,
                    "study_group": study_group,
                    "is_dkm_donor": str(dkm).lower() in ["да", "+"],
                    "telegram_id": 0,
                    "telegram_username": f"imported_{phone_number}",
                    "role": "student"
                })
                print(f"Created new user: {full_name}")
            else:
                # Update existing user if data is more complete
                if not user.university and university:
                    user.university = university
                if not user.faculty and faculty:
                    user.faculty = faculty
                if not user.study_group and study_group:
                    user.study_group = study_group
                if not user.is_dkm_donor and str(dkm).lower() in ["да", "+"]:
                    user.is_dkm_donor = True
                await session.commit()
                print(f"Updated user: {full_name}")

            if donations_count:
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
                print(f"Added {donations_count} donations for {full_name}")


if __name__ == "__main__":
    asyncio.run(main())
