import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import analytics_requests 
from bot.filters.role import RoleFilter
from bot.keyboards import inline
from bot.utils import analytics_service 
from bot.states.states import AdminAnalytics

router = Router(name="admin_analytics")

@router.callback_query(F.data == "admin_analytics", RoleFilter('admin'))
async def show_analytics_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📊 <b>Аналитический дашборд</b>\n\nВыберите интересующий раздел:",
        reply_markup=inline.get_analytics_main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "analytics_kpi", RoleFilter('admin'))
async def show_main_kpi(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Собираю данные...")
    kpi_data = await analytics_requests.get_main_kpi(session)

    text_parts = ["📈 <b>Ключевые показатели (KPI)</b>\n"]
    text_parts.append(f"<b>Новые пользователи (30д):</b> {kpi_data['new_users_30d']}")
    text_parts.append(f"<b>Активные доноры (90д):</b> {kpi_data['active_donors_90d']}")
    text_parts.append(f"<b>Сейчас на медотводе:</b> {kpi_data['on_waiver_now']}")

    if kpi_data['next_event']:
        event = kpi_data['next_event']
        days_left = (event['date'] - datetime.datetime.now()).days
        text_parts.append(f"\n🔜 <b>Ближайшее мероприятие:</b> «{event['name']}»")
        text_parts.append(f"   - <b>Записано:</b> {event['registered']}/{event['limit']}")
        text_parts.append(f"   - <b>Осталось дней:</b> {days_left}")
    else:
        text_parts.append("\n❌ Нет запланированных мероприятий.")
        
    # Запрашиваем данные для графика
    plot_data = await analytics_requests.get_donations_by_month(session)
    plot_image = analytics_service.plot_donations_by_month(plot_data)

    # Отправляем текстовую часть
    await callback.message.edit_text(
        "\n".join(text_parts), 
        reply_markup=inline.get_analytics_main_menu_keyboard(),
        parse_mode="HTML"
    )
    # Если график создался, отправляем его отдельным сообщением
    if plot_image:
        await callback.message.answer_photo(
            photo=types.BufferedInputFile(plot_image.read(), filename="donations_plot.png")
        )

@router.callback_query(F.data == "analytics_events_select", RoleFilter('admin'))
async def select_event_for_analysis(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    past_events = await analytics_requests.get_past_events_for_analysis(session)
    if not past_events:
        await callback.answer("Еще не было ни одного прошедшего мероприятия.", show_alert=True)
        return

    await callback.message.edit_text(
        "📅 <b>Анализ мероприятий</b>\n\nВыберите мероприятие из списка:",
        reply_markup=inline.get_events_for_analysis_keyboard(past_events)
    )
    await state.set_state(AdminAnalytics.choosing_event_for_analysis)
    await callback.answer()

@router.callback_query(AdminAnalytics.choosing_event_for_analysis, F.data.startswith("analyze_event_"))
async def show_event_analysis(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    event_id = int(callback.data.split("_")[-1])
    
    await callback.answer("⏳ Собираю аналитику по мероприятию...")
    data = await analytics_requests.get_event_analysis_data(session, event_id)

    if not data:
        await callback.message.edit_text("Не удалось найти данные по этому мероприятию.")
        return

    text = [
        f"📊 <b>Аналитика по мероприятию «{data['event_name']}»</b>\n",
        "<b>Воронка привлечения:</b>",
        f"  - Записалось: {data['registered_count']}",
        f"  - Пришло: {data['attended_count']}",
        f"  - Конверсия в явку: {data['conversion_rate']:.1f}%\n",
        "<b>Портрет аудитории:</b>",
        f"  - Новички: {data['newcomers_count']}",
        f"  - 'Ветераны': {data['veterans_count']}\n",
        "<b>Распределение по факультетам (пришедшие):</b>"
    ]
    
    # Сортируем факультеты по количеству участников
    sorted_faculties = sorted(data['faculties_distribution'].items(), key=lambda item: item[1], reverse=True)
    for faculty, count in sorted_faculties:
        text.append(f"  - {faculty}: {count} чел.")

    await callback.message.edit_text(
        "\n".join(text),
        parse_mode="HTML",
        reply_markup=inline.get_analytics_main_menu_keyboard()
    )

@router.callback_query(F.data == "analytics_reports", RoleFilter('admin'))
async def show_reports_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📄 <b>Отчеты</b>\n\nВыберите категорию отчета:",
        reply_markup=inline.get_reports_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("report_"), RoleFilter('admin'))
async def generate_report(callback: types.CallbackQuery, session: AsyncSession, bot: Bot):
    report_type = callback.data.split("_", 1)[1]
    report_titles = {
        "churn_donors": "Доноры-однодневки",
        "lapsed_donors": "Угасающие доноры",
        "top_donors": "Доноры-чемпионы",
        "rare_blood_donors": "Доноры редкой крови",
        "top_faculties": "Самые активные факультеты",
        "dkm_candidates": "Кандидаты в регистр ДКМ",
        "survey_dropoff": "Потерянные после опросника"
    }
    report_title = report_titles.get(report_type, "Отчет")

    await callback.answer("⏳ Генерирую отчет...")

    report_data = await analytics_service.create_report(session, report_type)

    if not report_data:
        await callback.message.answer("Нет данных для этого отчета.")
        return

    # Формирование отчета в виде таблицы
    headers = list(report_data[0].keys())
    # Заголовки для красоты
    header_map = {
        "full_name": "ФИО", "username": "Username", "donation_date": "Дата донации",
        "donation_count": "Донаций", "last_donation_date": "Последняя донация", "rank": "Ранг",
        "blood_group": "Группа крови", "faculty_name": "Факультет", "survey_date": "Дата опросника"
    }
    pretty_headers = [header_map.get(h, h) for h in headers]

    # Определяем ширину колонок
    col_widths = {h: len(pretty_headers[i]) for i, h in enumerate(headers)}
    for row in report_data:
        for key, value in row.items():
            col_widths[key] = max(col_widths[key], len(str(value)))

    # Собираем текстовый файл
    report_lines = []
    report_lines.append(f"Отчет: {report_title}")
    report_lines.append("=" * (sum(col_widths.values()) + len(col_widths) * 3 -1))

    header_line = "  ".join(h.ljust(col_widths[headers[i]]) for i, h in enumerate(pretty_headers))
    report_lines.append(header_line)
    report_lines.append("-" * len(header_line))

    for row in report_data:
        row_list = []
        for header in headers:
            value = row.get(header, "")
            if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
                value = value.strftime('%Y-%m-%d')
            row_list.append(str(value).ljust(col_widths[header]))
        report_lines.append("  ".join(row_list))

    report_text = "\n".join(report_lines)

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=types.BufferedInputFile(
            report_text.encode("utf-8"),
            filename=f"report_{report_type}.txt"
        ),
        caption=f"Отчет: {report_title}"
    )