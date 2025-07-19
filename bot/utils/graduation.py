import datetime
from bot.db import user_requests

def calculate_graduation_year(group: str) -> int | None:
    """
    Calculates the graduation year based on the group name.
    Returns None if the group format is not recognized.
    """
    if not group or not isinstance(group, str):
        return None

    group_upper = group.upper()

    try:
        if group_upper.startswith('Б') or group_upper.startswith('B'):
            # Бакалавриат - 4 года
            year_prefix = int(group_upper[1:3])
            return 2000 + year_prefix + 4
        elif group_upper.startswith('С') or group_upper.startswith('C'):
            # Специалитет - 5 лет
            year_prefix = int(group_upper[1:3])
            return 2000 + year_prefix + 5
        elif group_upper.startswith('М') or group_upper.startswith('M'):
            # Магистратура - 2 года
            year_prefix = int(group_upper[1:3])
            return 2000 + year_prefix + 2
    except (ValueError, IndexError):
        return None

    return None

async def check_graduation_status(bot, session):
    """
    Checks the graduation status of all users and sends a notification
    to those who have graduated.
    """
    today = datetime.date.today()
    if today.month == 9:
        users = await user_requests.get_all_users(session)
        for user in users:
            if user.graduation_year and user.graduation_year <= today.year:
                await bot.send_message(
                    user.telegram_id,
                    "Здравствуйте! По нашим данным, вы уже выпустились. "
                    "Пожалуйста, обновите свои данные, чтобы продолжать "
                    "пользоваться ботом."
                )
