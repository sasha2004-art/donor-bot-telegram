import io
import matplotlib.pyplot as plt
import datetime

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

    ax.bar(months, counts, color='#E53935') # Фирменный красный цвет

    ax.set_title('Динамика донаций по месяцам', fontsize=16, pad=20)
    ax.set_ylabel('Количество донаций')
    ax.tick_params(axis='x', rotation=45)
    
    # Добавляем цифры над столбцами
    for i, v in enumerate(counts):
        ax.text(i, v + 0.5, str(v), ha='center', fontweight='bold')

    plt.tight_layout()

    # Сохраняем график в буфер в памяти
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig) # Закрываем фигуру, чтобы освободить память

    return buf