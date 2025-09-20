import io
import matplotlib.pyplot as plt
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db import analytics_requests


async def create_report(session: AsyncSession, report_type: str) -> dict:
    """
    Создает отчет на основе указанного типа.
    """
    report_data = {}
    if report_type == "one_time_donors":
        report_data = await analytics_requests.get_one_time_donors(session)
    elif report_type == "no_show_donors":
        report_data = await analytics_requests.get_no_show_donors(session)
    elif report_type == "dkm_donors":
        report_data = await analytics_requests.get_dkm_donors(session)
    elif report_type == "students":
        report_data = await analytics_requests.get_students(session)
    elif report_type == "employees":
        report_data = await analytics_requests.get_employees(session)
    elif report_type == "external_donors":
        report_data = await analytics_requests.get_external_donors(session)
    elif report_type == "graduated_donors":
        report_data = await analytics_requests.get_graduated_donors(session)
    elif report_type == "churn_donors":
        report_data = await analytics_requests.get_churn_donors(session)
    elif report_type == "lapsed_donors":
        report_data = await analytics_requests.get_lapsed_donors(session)
    elif report_type == "top_donors":
        report_data = await analytics_requests.get_top_donors(session)
    elif report_type == "rare_blood_donors":
        report_data = await analytics_requests.get_rare_blood_donors(session)
    elif report_type == "top_faculties":
        report_data = await analytics_requests.get_top_faculties(session)
    elif report_type == "dkm_candidates":
        report_data = await analytics_requests.get_dkm_candidates(session)
    elif report_type == "survey_dropoff":
        report_data = await analytics_requests.get_survey_dropoff(session)
    return report_data


def plot_donations_by_month(data: list[tuple]) -> io.BytesIO:
    """
    Создает график в виде столбчатой диаграммы по данным о донациях.
    :param data: Список кортежей (datetime.date, int), где date - первый день месяца.
    :return: BytesIO объект с изображением PNG.
    """
    if not data:
        return None

    # plt.style.use('ggplot') # Можете выбрать стиль по вкусу
    fig, ax = plt.subplots(figsize=(10, 6))

    months = [item[0].strftime("%b %Y") for item in data]
    counts = [item[1] for item in data]

    ax.bar(months, counts, color="#E53935")  # Фирменный красный цвет

    ax.set_title("Динамика донаций по месяцам", fontsize=16, pad=20)
    ax.set_ylabel("Количество донаций")
    ax.tick_params(axis="x", rotation=45)

    # Добавляем цифры над столбцами
    for i, v in enumerate(counts):
        ax.text(i, v + 0.5, str(v), ha="center", fontweight="bold")

    plt.tight_layout()

    # Сохраняем график в буфер в памяти
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)  # Закрываем фигуру, чтобы освободить память

    return buf
