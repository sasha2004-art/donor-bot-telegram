from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться контактом", request_contact=True)]],
        resize_keyboard=True
    )


def get_home_keyboard():
    """Возвращает клавиатуру с кнопкой 'Домой'."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Домой")]
        ],
        resize_keyboard=True
    )
