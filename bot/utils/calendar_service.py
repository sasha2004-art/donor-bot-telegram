import datetime
import pytz
from ics import Calendar, Event as IcsEvent
from ics.alarm import DisplayAlarm
from bot.db.models import Event as DbEvent
from bot.utils.text_messages import Text

def generate_ics_file(event: DbEvent) -> str:
    """
    Генерирует содержимое .ics файла для указанного мероприятия,
    оптимизированное для лучшей совместимости, в т.ч. с Google Calendar.

    :param event: Объект мероприятия из базы данных.
    :return: Строка с содержимым .ics файла.
    """
    cal = Calendar()
    e = IcsEvent()

    timezone = pytz.timezone("Europe/Moscow")

    if event.event_datetime.tzinfo is None:
        start_time = timezone.localize(event.event_datetime)
    else:
        start_time = event.event_datetime.astimezone(timezone)

    end_time = start_time + datetime.timedelta(hours=2)

    e.name = f"Донация: {event.name}"
    e.begin = start_time
    e.end = end_time
    donation_type_ru = Text.DONATION_TYPE_RU.get(event.donation_type, event.donation_type)
    e.description = (
        f"Тип донации: {donation_type_ru}.\n" # <-- ИЗМЕНЕНО
        f"Не забудьте взять с собой паспорт и хорошо себя чувствовать. "
        f"Спасибо за вашу помощь!"
    )
    e.location = event.location
    e.created = datetime.datetime.now(tz=timezone)
    
    e.uid = f"{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}-{event.id}@donor.mifi.ru"
    

    alarm = DisplayAlarm(trigger=datetime.timedelta(hours=-1))
    
    e.alarms.append(alarm)
    
    cal.events.add(e)
    
    return cal.serialize()