from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.db.models import MerchItem, InfoText
from aiogram.fsm.context import FSMContext

# --- КЛАВИАТУРЫ ---

def get_back_to_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_category_keyboard():
    """Клавиатура для выбора категории пользователя."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Студент", callback_data="category_student"))
    builder.row(InlineKeyboardButton(text="Сотрудник", callback_data="category_employee"))
    builder.row(InlineKeyboardButton(text="Внешний донор", callback_data="category_external"))
    return builder.as_markup()

def get_consent_keyboard():
    """Клавиатура для подтверждения согласия на обработку ПДн."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Принимаю условия", callback_data="consent_given"))
    return builder.as_markup()


def get_student_main_menu(viewer_role: str = 'student'):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Записаться на донацию", callback_data="register_donation"))
    builder.row(InlineKeyboardButton(text="👤 Мой профиль", callback_data="my_profile"))
    builder.row(InlineKeyboardButton(text="🎁 Магазин мерча", callback_data="merch_store"))
    builder.row(InlineKeyboardButton(text="ℹ️ Полезная информация", callback_data="info"))
    builder.row(InlineKeyboardButton(text="⚕️ Мои медотводы", callback_data="my_waivers"))
    builder.row(InlineKeyboardButton(text="❓ Задать вопрос организаторам", callback_data="ask_question"))
    
    if viewer_role == 'volunteer':
        builder.row(InlineKeyboardButton(
            text="⭐ Вернуться в меню волонтера",
            callback_data="volunteer_panel"
        ))
    elif viewer_role in ['admin', 'main_admin']:
        builder.row(InlineKeyboardButton(
            text="⭐ Перейти в режим волонтера",
            callback_data="switch_to_volunteer_view"
        ))
        builder.row(InlineKeyboardButton(
            text="⚙️ Вернуться в админ-панель",
            callback_data="admin_panel"
        ))
        
    return builder.as_markup()

def get_volunteer_main_menu(viewer_role: str = 'volunteer'):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Меню волонтёра", callback_data="volunteer_panel"))
    builder.row(InlineKeyboardButton(text="👤 Перейти в режим донора", callback_data="switch_to_donor_view"))
    return builder.as_markup()

def get_admin_main_menu(viewer_role: str = 'admin'):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚙️ Панель администратора", callback_data="admin_panel"))
    return builder.as_markup()  

def get_main_admin_main_menu(viewer_role: str = 'main_admin'):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚙️ Открыть панель администратора", callback_data="admin_panel"))
    return builder.as_markup()

def get_university_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="НИЯУ МИФИ", callback_data="university_mifi"))
    builder.row(InlineKeyboardButton(text="Другой вуз", callback_data="university_other"))
    return builder.as_markup()


def get_faculties_keyboard():
    faculties = ["ИИКС", "ФИБС", "ИнЯз", "ИФТЭБ", "БМТ", "ИФИБ"]
    builder = InlineKeyboardBuilder()
    for faculty in faculties:
        builder.row(InlineKeyboardButton(text=faculty, callback_data=f"faculty_{faculty}"))
    builder.row(InlineKeyboardButton(text="Другой/Не из списка", callback_data="faculty_Other"))
    return builder.as_markup()

def get_gender_inline_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Мужской", callback_data="gender_male"),
        InlineKeyboardButton(text="Женский", callback_data="gender_female")
    )
    return builder.as_markup()

def get_profile_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Мои данные", callback_data="profile_data"))
    builder.row(InlineKeyboardButton(text="🩸 История донаций", callback_data="profile_history"))
    builder.row(InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_back_to_profile_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад в профиль", callback_data="my_profile"))
    return builder.as_markup()

def get_info_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Как подготовиться?", callback_data="info_prepare"))
    builder.row(InlineKeyboardButton(text="Противопоказания", callback_data="info_contraindications"))
    builder.row(InlineKeyboardButton(text="Что делать после?", callback_data="info_after"))
    builder.row(InlineKeyboardButton(text="🩸 О донорстве костного мозга (ДКМ)", callback_data="info_dkm"))
    builder.row(InlineKeyboardButton(text="🏥 О донациях в МИФИ", callback_data="info_mifi_process"))
    builder.row(InlineKeyboardButton(text="Связаться с организаторами", callback_data="info_contacts"))
    builder.row(InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_back_to_info_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад к разделам", callback_data="info"))
    return builder.as_markup()

def get_merch_store_keyboard(item: MerchItem, page: int, total_pages: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f'Купить за {item.price}Б', callback_data=f"buy_merch_{item.id}"))
    nav_buttons = []
    prev_page = total_pages if page == 1 else page - 1
    nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"merch_page_{prev_page}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    next_page = 1 if page == total_pages else page + 1
    nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"merch_page_{next_page}"))
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="🛍️ Мои заказы", callback_data="my_orders"))
    builder.row(InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_purchase_confirmation_keyboard(item_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_buy_{item_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="merch_store")
    )
    return builder.as_markup()

def get_back_to_merch_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад в магазин", callback_data="merch_store"))
    return builder.as_markup()
    
def get_admin_panel_keyboard(viewer_role: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🗓️ Упр. мероприятиями", callback_data="admin_manage_events"))
    builder.row(types.InlineKeyboardButton(text="❓ Вопросы от пользователей", callback_data="admin_answer_questions"))
    builder.row(InlineKeyboardButton(text="👥 Упр. пользователями", callback_data="admin_manage_users"))
    builder.row(InlineKeyboardButton(text="🛍️ Упр. магазином", callback_data="admin_manage_merch"))
    builder.row(InlineKeyboardButton(text="📦 Обработка заказов", callback_data="admin_process_orders"))
    builder.row(InlineKeyboardButton(text="📣 Рассылки", callback_data="admin_mailing"))
    builder.row(InlineKeyboardButton(text="📊 Аналитика", callback_data="admin_analytics"))
    builder.row(InlineKeyboardButton(text="📝 Ред. инфо-разделы", callback_data="admin_edit_info"))
    if viewer_role == 'main_admin':
        builder.row(
        types.InlineKeyboardButton(text="💾 Экспорт данных", callback_data="ma_export_data"),
        types.InlineKeyboardButton(text="📥 Импорт данных", callback_data="ma_import_data")
        )
    builder.row(InlineKeyboardButton(text="👤 Перейти в режим донора", callback_data="switch_to_donor_view"))
    return builder.as_markup()



def get_info_sections_for_editing_keyboard(sections: list[InfoText]):
    builder = InlineKeyboardBuilder()
    for section in sections:
        builder.row(types.InlineKeyboardButton(
            text=section.section_title,
            callback_data=f"edit_info_{section.section_key}"
        ))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_panel"))
    return builder.as_markup()

def get_analytics_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📈 Общая статистика (KPI)", callback_data="analytics_kpi"))
    builder.row(InlineKeyboardButton(text="📅 Анализ мероприятий", callback_data="analytics_events_select"))
    builder.row(InlineKeyboardButton(text="📄 Отчеты", callback_data="analytics_reports"))
    # Можно добавить еще кнопки для других разделов
    builder.row(InlineKeyboardButton(text="↩️ В админ-панель", callback_data="admin_panel"))
    return builder.as_markup()

def get_reports_menu_keyboard():
    builder = InlineKeyboardBuilder()
    # I. Отчеты по активности и лояльности доноров
    builder.row(InlineKeyboardButton(text="Доноры-однодневки", callback_data="report_churn_donors"))
    builder.row(InlineKeyboardButton(text="Угасающие доноры", callback_data="report_lapsed_donors"))
    builder.row(InlineKeyboardButton(text="Топ-20 доноров", callback_data="report_top_donors"))
    # builder.row(InlineKeyboardButton(text="Доноры редкой крови", callback_data="report_rare_blood_donors"))
    # II. Отчеты по сегментации и демографии
    builder.row(InlineKeyboardButton(text="Самые активные факультеты", callback_data="report_top_faculties"))
    builder.row(InlineKeyboardButton(text="Кандидаты в регистр ДКМ", callback_data="report_dkm_candidates"))
    # III. Отчеты по конверсии и эффективности
    builder.row(InlineKeyboardButton(text="Потеря после опросника", callback_data="report_survey_dropoff"))

    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="admin_analytics"))
    return builder.as_markup()

def get_events_for_analysis_keyboard(events: list):
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.row(InlineKeyboardButton(
            text=f"{event.event_datetime.strftime('%d.%m.%y')} - {event.name}",
            callback_data=f"analyze_event_{event.id}"
        ))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="admin_analytics"))
    return builder.as_markup()

def get_events_management_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="admin_create_event"))
    builder.row(InlineKeyboardButton(text="📜 Просмотр/Редактирование активных", callback_data="admin_view_events"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="admin_panel"))
    return builder.as_markup()

def get_single_event_management_keyboard(event_id: int, registration_is_open: bool, has_feedback: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_event_{event_id}"))
    reg_status_text = "🔒 Закрыть регистрацию" if registration_is_open else "🔓 Открыть регистрацию"
    builder.row(InlineKeyboardButton(text=reg_status_text, callback_data=f"admin_toggle_reg_{event_id}"))
    builder.row(InlineKeyboardButton(text="👥 Список участников (.csv)", callback_data=f"admin_event_participants_{event_id}"))
    builder.row(InlineKeyboardButton(text="🚨 Отменить мероприятие", callback_data=f"admin_cancel_event_{event_id}"))
    if has_feedback:
        builder.row(InlineKeyboardButton(text="📊 Посмотреть отзывы", callback_data=f"admin_view_feedback_{event_id}"))
    builder.row(InlineKeyboardButton(text="↩️ К списку мероприятий", callback_data="admin_view_events"))
    return builder.as_markup()

def get_back_to_admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ В панель администратора", callback_data="admin_panel"))
    return builder.as_markup()

def get_user_management_keyboard(target_user_id: int, target_user_role: str, viewer_role: str, is_blocked: bool):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎟️ Упр. регистрациями", callback_data=f"admin_manage_user_regs_{target_user_id}"))
    builder.row(InlineKeyboardButton(text="⚕️ Упр. медотводами", callback_data=f"admin_manage_waivers_{target_user_id}"))

    builder.row(InlineKeyboardButton(text="+/- Баллы", callback_data=f"admin_points_{target_user_id}"))

    if target_user_role == 'student':
        builder.row(InlineKeyboardButton(text="⭐ Назначить волонтером", callback_data=f"admin_promote_volunteer_{target_user_id}"))
    elif target_user_role == 'volunteer':
        builder.row(InlineKeyboardButton(text="🧑‍🎓 Снять с должности волонтера", callback_data=f"admin_demote_volunteer_{target_user_id}"))
    
    if viewer_role == 'main_admin' and target_user_role != 'main_admin':
        if target_user_role == 'admin':
            builder.row(InlineKeyboardButton(text="👑➖ Разжаловать админа", callback_data=f"ma_demote_admin_{target_user_id}"))
        else:
            builder.row(InlineKeyboardButton(text="👑➕ Назначить админом", callback_data=f"ma_promote_admin_{target_user_id}"))
        if is_blocked:
            builder.row(InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"ma_unblock_user_{target_user_id}"))
        else:
            builder.row(InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"ma_block_user_{target_user_id}"))
            
    builder.row(InlineKeyboardButton(text="↩️ Назад к управлению", callback_data="admin_manage_users"))
    return builder.as_markup()

def get_donation_type_keyboard():
    builder = InlineKeyboardBuilder()
    types = {'whole_blood': 'Цельная кровь', 'plasma': 'Плазма', 'platelets': 'Тромбоциты', 'erythrocytes': 'Эритроциты'}
    for key, value in types.items():
        builder.row(InlineKeyboardButton(text=value, callback_data=f"settype_{key}"))
    return builder.as_markup()

def get_main_admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👮‍♂️ Управление администраторами", callback_data="ma_manage_admins"))
    builder.row(InlineKeyboardButton(text="🚫 Управление блокировками", callback_data="ma_manage_blocks"))
    builder.row(InlineKeyboardButton(text="💾 Экспорт данных", callback_data="ma_export_data"))
    builder.row(InlineKeyboardButton(text="↩️ В панель администратора", callback_data="admin_panel"))
    return builder.as_markup()
    
def get_back_to_ma_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ В панель гл. администратора", callback_data="main_admin_panel"))
    return builder.as_markup()

def get_admins_management_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Назначить администратора", callback_data="add_admin"))
    builder.row(InlineKeyboardButton(text="➖ Разжаловать администратора", callback_data="remove_admin"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="main_admin_panel"))
    return builder.as_markup()

def get_blocks_management_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔒 Заблокировать пользователя", callback_data="block_user_start"))
    builder.row(InlineKeyboardButton(text="🔓 Разблокировать пользователя", callback_data="unblock_user_start"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="main_admin_panel"))
    return builder.as_markup()
    
def get_export_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Выгрузить пользователей (.csv)", callback_data="export_users_csv"))
    builder.row(InlineKeyboardButton(text="Выгрузить донации (.csv)", callback_data="export_donations_csv"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="main_admin_panel"))
    return builder.as_markup()

def get_merch_management_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_create_merch"))
    builder.row(InlineKeyboardButton(text="📜 Просмотр/Редактирование", callback_data="admin_view_merch"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="admin_panel"))
    return builder.as_markup()

def get_event_cancellation_confirmation_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Да, отменить", callback_data=f"admin_confirm_cancel_{event_id}"),
        InlineKeyboardButton(text="↩️ Нет, назад", callback_data=f"admin_show_event_{event_id}")
    )
    return builder.as_markup()

def get_back_to_events_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ К управлению мероприятиями", callback_data="admin_manage_events"))
    return builder.as_markup()

def get_single_merch_management_keyboard(item_id: int, is_available: bool):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_merch_{item_id}"))
    availability_text = "✅ Сделать доступным" if not is_available else "❌ Сделать недоступным"
    builder.row(InlineKeyboardButton(text=availability_text, callback_data=f"admin_toggle_merch_{item_id}"))
    builder.row(InlineKeyboardButton(text="🗑️ Удалить товар", callback_data=f"admin_delete_merch_{item_id}"))
    builder.row(InlineKeyboardButton(text="↩️ К списку товаров", callback_data="admin_view_merch"))
    return builder.as_markup()

def get_merch_deletion_confirmation_keyboard(item_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑️ Да, удалить", callback_data=f"admin_confirm_delete_merch_{item_id}"),
        InlineKeyboardButton(text="↩️ Нет, назад", callback_data=f"admin_show_merch_{item_id}")
    )
    return builder.as_markup()

def get_back_to_merch_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ К управлению магазином", callback_data="admin_manage_merch"))
    return builder.as_markup()

def get_already_registered_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="❌ Отменить мою регистрацию",
        callback_data=f"cancel_reg_{event_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="↩️ К списку мероприятий",
        callback_data="register_donation"
    ))
    return builder.as_markup()

def get_event_creation_confirmation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Создать и разослать", callback_data="confirm_create_event"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_manage_events"))
    return builder.as_markup()

def get_mailing_audience_keyboard(current_filters: dict = None):
    """
    Создает клавиатуру для выбора аудитории рассылки.
    Динамически отображает уже выбранные фильтры и кнопки.
    """
    if current_filters is None:
        current_filters = {}

    builder = InlineKeyboardBuilder()


    builder.row(InlineKeyboardButton(text="📢 Всем пользователям", callback_data="mail_filter_role_all"))
    builder.row(InlineKeyboardButton(text="⭐ Волонтерам и админам", callback_data="mail_filter_role_volunteers"))
    builder.row(InlineKeyboardButton(text="⚙️ Только администраторам", callback_data="mail_filter_role_admins"))
    # builder.row(InlineKeyboardButton(text="-"*25, callback_data="ignore")) 

    # builder.row(InlineKeyboardButton(text="🎓 По ВУЗу", callback_data="mail_audience_type_university"))
    builder.row(InlineKeyboardButton(text="🏛️ По факультету", callback_data="mail_audience_type_faculty"))
    
    if current_filters:
        builder.row(InlineKeyboardButton(text="✅ Готово (перейти к подтверждению)", callback_data="mail_audience_finish"))

    # Кнопка "Сбросить фильтры"
    if current_filters:
        builder.row(InlineKeyboardButton(text="🔄 Сбросить все фильтры", callback_data="mail_audience_reset"))

    builder.row(InlineKeyboardButton(text="❌ Отмена рассылки", callback_data="admin_panel"))
    
    return builder.as_markup()



def get_dynamic_mailing_filter_keyboard(items: list[str], filter_key: str, back_callback: str):
    """
    Создает клавиатуру для выбора значения фильтра.
    :param items: Список значений для кнопок (напр., список ВУЗов).
    :param filter_key: Ключ фильтра (напр., 'university').
    :param back_callback: callback_data для кнопки "Назад".
    """
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.row(InlineKeyboardButton(text=item, callback_data=f"mail_filter_{filter_key}_{item}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=back_callback))
    return builder.as_markup()

def get_mailing_confirmation_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚀 Да, запустить рассылку", callback_data="confirm_mailing"),
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_mailing_text"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")
    )
    return builder.as_markup()

def get_skip_media_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_media"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    return builder.as_markup()

def get_user_management_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📜 Список всех пользователей", callback_data="admin_users_list_page_1"))
    builder.row(InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_search_user"))
    builder.row(InlineKeyboardButton(text="➕ Добавить пользователя вручную", callback_data="admin_add_user_start"))
    builder.row(InlineKeyboardButton(text="↩️ Назад в админ-панель", callback_data="admin_panel"))
    return builder.as_markup()

def get_users_list_pagination_keyboard(page: int, total_pages: int):
    builder = InlineKeyboardBuilder()
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_users_list_page_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_list_page_{page + 1}"))
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="admin_manage_users"))
    return builder.as_markup()

def get_successful_registration_keyboard(event_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🔲 Мой QR-код для этого мероприятия",
        callback_data=f"get_event_qr_{event_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="🗓️ Добавить в календарь",
        callback_data=f"add_to_calendar_{event_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="❌ Отменить мою регистрацию",
        callback_data=f"cancel_reg_{event_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="↩️ К списку мероприятий",
        callback_data="register_donation"
    ))
    return builder.as_markup()

def get_donation_confirmation_keyboard(user_id: int, event_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Подтвердить",
            callback_data=f"confirm_donation_{user_id}_{event_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="volunteer_panel"
        )
    )
    return builder.as_markup()

def get_volunteer_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📷 Подтвердить донацию (QR)", callback_data="confirm_donation_qr"))
    builder.row(InlineKeyboardButton(text="↩️ Назад в меню донора", callback_data="switch_to_donor_view"))
    return builder.as_markup()

def get_manual_registration_management_keyboard(user_id: int):
    """Клавиатура для выбора: записать или отменить запись."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Записать на мероприятие", callback_data=f"admin_reg_start_{user_id}"))
    builder.row(InlineKeyboardButton(text="➖ Отменить регистрацию", callback_data=f"admin_cancel_start_{user_id}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад к пользователю", callback_data=f"admin_show_user_{user_id}"))
    return builder.as_markup()

def get_events_for_manual_registration_keyboard(user_id: int, events: list):
    """Клавиатура со списком мероприятий для ручной записи."""
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.row(InlineKeyboardButton(
            text=f"{event.event_date.strftime('%d.%m')} - {event.name}",
            callback_data=f"adminReg_{user_id}_{event.id}" 
        ))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=f"admin_manage_user_regs_{user_id}"))
    return builder.as_markup()

def get_registrations_for_cancellation_keyboard(user_id: int, registrations: list):
    """Клавиатура со списком регистраций для отмены."""
    builder = InlineKeyboardBuilder()
    for reg in registrations:
        builder.row(InlineKeyboardButton(
            text=f"❌ {reg.event.event_date.strftime('%d.%m')} - {reg.event.name}",
            callback_data=f"adminCancel_{user_id}_{reg.event_id}"
        ))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=f"admin_manage_user_regs_{user_id}"))
    return builder.as_markup()



def get_my_waivers_keyboard(user_waivers_exist: bool):
    """
    Клавиатура для меню 'Мои медотводы'.
    Показывает кнопку удаления, только если у пользователя есть созданные им отводы.
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Установить временный отвод", callback_data="set_user_waiver"))
    if user_waivers_exist:
        builder.row(InlineKeyboardButton(text="➖ Отменить свой отвод", callback_data="cancel_user_waiver"))
    builder.row(InlineKeyboardButton(text="↩️ В главное меню", callback_data="back_to_main_menu"))
    return builder.as_markup()

def get_waiver_cancellation_keyboard(waivers: list):
    """Клавиатура со списком медотводов, созданных пользователем, для отмены."""
    builder = InlineKeyboardBuilder()
    for waiver in waivers:
        builder.row(InlineKeyboardButton(
            text=f"❌ До {waiver.end_date.strftime('%d.%m.%y')}: {waiver.reason[:25]}...",
            callback_data=f"delete_waiver_{waiver.id}"
        ))
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="my_waivers"))
    return builder.as_markup()

def get_admin_waiver_management_keyboard(user_id: int, waivers: list):
    """Клавиатура для админа со списком медотводов пользователя для удаления."""
    builder = InlineKeyboardBuilder()
    for waiver in waivers:
        creator_map = {'user': '👤', 'system': '⚙️', 'admin': '👑'}
        creator_icon = creator_map.get(str(waiver.created_by).lower(), '❓')
        
        if str(waiver.created_by).isdigit():
            creator_icon = '👑'

        reason_short = (waiver.reason[:20] + '...') if len(waiver.reason) > 20 else waiver.reason
        
        builder.row(InlineKeyboardButton(
            text=f"❌ {creator_icon} До {waiver.end_date.strftime('%d.%m')} - {reason_short}",
            callback_data=f"admin_del_waiver_{waiver.id}_{user_id}"
        ))
        
    builder.row(InlineKeyboardButton(text="➕ Установить новый медотвод", callback_data=f"admin_waiver_{user_id}"))
    builder.row(InlineKeyboardButton(text="↩️ Назад к пользователю", callback_data=f"admin_show_user_{user_id}"))
    return builder.as_markup()

def get_feedback_well_being_keyboard():
    builder = InlineKeyboardBuilder()
    buttons = [InlineKeyboardButton(text=str(i), callback_data=f"fb_wb_{i}") for i in range(1, 6)]
    builder.row(*buttons)
    return builder.as_markup()

def get_feedback_organization_keyboard():
    builder = InlineKeyboardBuilder()
    # Две строки по 5 кнопок
    builder.row(*[InlineKeyboardButton(text=str(i), callback_data=f"fb_org_{i}") for i in range(1, 6)])
    builder.row(*[InlineKeyboardButton(text=str(i), callback_data=f"fb_org_{i}") for i in range(6, 11)])
    return builder.as_markup()

def get_feedback_skip_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➡️ Пропустить", callback_data="fb_skip_step"))
    return builder.as_markup()



def get_events_for_post_processing_keyboard(events: list):
    """Клавиатура для выбора прошедшего мероприятия для обработки."""
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.row(types.InlineKeyboardButton(
            text=f"{event.event_datetime.strftime('%d.%m.%y')} - {event.name}",
            callback_data=f"post_process_event_{event.id}"
        ))
    builder.row(types.InlineKeyboardButton(text="↩️ Назад", callback_data="admin_manage_events"))
    return builder.as_markup()

def get_participant_marking_keyboard(event_id: int, participants: list, marked_donations: set, marked_dkm: set):
    """Динамическая клавиатура для отметки участников."""
    builder = InlineKeyboardBuilder()
    for reg in participants:
        user = reg.user
        
        donation_icon = "🟢" if user.id in marked_donations else "⚪️"
        dkm_icon = "🟢" if user.id in marked_dkm else "⚪️"

        builder.row(
            types.InlineKeyboardButton(text=user.full_name, callback_data="ignore"),
            types.InlineKeyboardButton(
                text=f"{donation_icon} Сдал кровь", 
                callback_data=f"mark_participant_{event_id}_{user.id}_donation"
            ),
            types.InlineKeyboardButton(
                text=f"{dkm_icon} Вступил в ДКМ", 
                callback_data=f"mark_participant_{event_id}_{user.id}_dkm"
            )
        )
    builder.row(types.InlineKeyboardButton(text="✅ Сохранить изменения и завершить", callback_data=f"finish_marking_{event_id}"))
    builder.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_manage_events"))
    return builder.as_markup()