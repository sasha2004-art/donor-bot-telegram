import pytest
from bot.keyboards import inline

def get_button_texts(keyboard):
    """Вспомогательная функция для извлечения текста со всех кнопок."""
    return [button.text for row in keyboard.inline_keyboard for button in row]

def test_get_student_main_menu():
    """Тестирует, что в меню студента есть правильные кнопки, в т.ч. для админа."""
    # Сценарий 1: Обычный студент
    student_keyboard = inline.get_student_main_menu(viewer_role='student')
    student_buttons = get_button_texts(student_keyboard)
    
    assert "📅 Записаться на донацию" in student_buttons
    assert "🎁 Магазин мерча" in student_buttons
    assert "⚙️ Вернуться в админ-панель" not in student_buttons

    # Сценарий 2: Админ просматривает меню как студент
    admin_keyboard = inline.get_student_main_menu(viewer_role='admin')
    admin_buttons = get_button_texts(admin_keyboard)

    assert "📅 Записаться на донацию" in admin_buttons
    assert "⭐ Перейти в режим волонтера" in admin_buttons
    assert "⚙️ Вернуться в админ-панель" in admin_buttons

def test_get_admin_panel_keyboard():
    """Тестирует, что у главного админа есть кнопка экспорта, а у обычного - нет."""
    # Сценарий 1: Обычный админ
    admin_keyboard = inline.get_admin_panel_keyboard(viewer_role='admin')
    admin_buttons = get_button_texts(admin_keyboard)
    
    assert "👥 Упр. пользователями" in admin_buttons
    assert "💾 Экспорт данных" not in admin_buttons

    # Сценарий 2: Главный админ
    main_admin_keyboard = inline.get_admin_panel_keyboard(viewer_role='main_admin')
    main_admin_buttons = get_button_texts(main_admin_keyboard)

    assert "👥 Упр. пользователями" in main_admin_buttons
    assert "💾 Экспорт данных" in main_admin_buttons

def test_get_user_management_keyboard_permissions():
    """
    Тестирует логику отображения кнопок управления пользователем
    в зависимости от ролей смотрящего и цели.
    """
    # Сценарий 1: Главный админ смотрит на обычного студента
    kbd1 = inline.get_user_management_keyboard(
        target_user_id=1, target_user_role='student', viewer_role='main_admin', is_blocked=False
    )
    btn1 = get_button_texts(kbd1)
    assert "👑➕ Назначить админом" in btn1
    assert "🚫 Заблокировать" in btn1
    assert "👑➖ Разжаловать админа" not in btn1

    # Сценарий 2: Главный админ смотрит на обычного админа
    kbd2 = inline.get_user_management_keyboard(
        target_user_id=1, target_user_role='admin', viewer_role='main_admin', is_blocked=False
    )
    btn2 = get_button_texts(kbd2)
    assert "👑➖ Разжаловать админа" in btn2
    assert "👑➕ Назначить админом" not in btn2

    # Сценарий 3: Обычный админ смотрит на волонтера (не может управлять админами/блокировками)
    kbd3 = inline.get_user_management_keyboard(
        target_user_id=1, target_user_role='volunteer', viewer_role='admin', is_blocked=False
    )
    btn3 = get_button_texts(kbd3)
    assert "🧑‍🎓 Снять с должности волонтера" in btn3
    assert "👑➕ Назначить админом" not in btn3
    assert "🚫 Заблокировать" not in btn3
    
    
def test_admin_panel_keyboard_for_admin():
    """
    Тестирует, что обычный админ видит свою клавиатуру БЕЗ кнопки экспорта.
    """
    keyboard = inline.get_admin_panel_keyboard(viewer_role='admin')
    
    # Преобразуем клавиатуру в простой список callback_data для удобства проверки
    callbacks = []
    for row in keyboard.inline_keyboard:
        for button in row:
            callbacks.append(button.callback_data)

    assert "admin_manage_users" in callbacks
    assert "ma_export_data" not in callbacks # Главная проверка

def test_admin_panel_keyboard_for_main_admin():
    """
    Тестирует, что главный админ видит свою клавиатуру С кнопкой экспорта.
    """
    keyboard = inline.get_admin_panel_keyboard(viewer_role='main_admin')
    
    callbacks = []
    for row in keyboard.inline_keyboard:
        for button in row:
            callbacks.append(button.callback_data)

    assert "admin_manage_users" in callbacks
    assert "ma_export_data" in callbacks # Главная проверка

def test_user_management_keyboard_roles():
    """
    Тестирует, что кнопки управления ролями и блокировки появляются/исчезают правильно.
    """
    # Сценарий 1: Главный админ смотрит на обычного админа
    kb1 = inline.get_user_management_keyboard(
        target_user_id=1, target_user_role='admin', viewer_role='main_admin', is_blocked=False
    )
    cb1 = {b.callback_data for r in kb1.inline_keyboard for b in r}
    assert "ma_demote_admin_1" in cb1
    assert "ma_promote_admin_1" not in cb1
    assert "ma_block_user_1" in cb1

    # Сценарий 2: Главный админ смотрит на волонтера
    kb2 = inline.get_user_management_keyboard(
        target_user_id=2, target_user_role='volunteer', viewer_role='main_admin', is_blocked=False
    )
    cb2 = {b.callback_data for r in kb2.inline_keyboard for b in r}
    assert "ma_promote_admin_2" in cb2
    assert "admin_demote_volunteer_2" in cb2

    # Сценарий 3: Обычный админ смотрит на волонтера (не должен видеть кнопки гл. админа)
    kb3 = inline.get_user_management_keyboard(
        target_user_id=3, target_user_role='volunteer', viewer_role='admin', is_blocked=False
    )
    cb3 = {b.callback_data for r in kb3.inline_keyboard for b in r}
    assert "ma_promote_admin_3" not in cb3
    assert "ma_block_user_3" not in cb3
    assert "admin_demote_volunteer_3" in cb3