import asyncio
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
import json
import hmac
import hashlib
from urllib.parse import unquote, parse_qs
import datetime
import aiohttp
import time

import redis.asyncio as redis
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from bot.middlewares.block import BlockUserMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.config_reader import config
from bot.db.engine import create_db_and_tables, async_session_maker
from bot.db import admin_requests, user_requests, event_requests
from bot.db.models import Survey, UserBlock, InfoText   
from bot.utils.scheduler import setup_scheduler
from bot.handlers import common, student, volunteer, other
from bot.handlers.admin import admin_router
from bot.handlers.student import feedback_router
from bot.utils.text_messages import Text




logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


redis_client = redis.Redis(host='redis', port=6379, db=0) # host='redis' - имя сервиса из docker-compose
storage = RedisStorage(redis=redis_client)
bot = Bot(token=config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=storage)



class SurveyAnswers(BaseModel):
    # Общие вопросы
    age: str
    weight: str
    health_issues_last_month: str

    # Новые вопросы из требований
    symptoms: str # ОРВИ, ангина, грипп
    pressure: str
    hemoglobin_level: str

    # Подготовка к донации
    diet_followed: str
    alcohol_last_48h: str
    medication_last_72h: str
    sleep_last_night: str
    smoking_last_hour: str

    # Противопоказания
    tattoo_or_piercing: str
    tooth_removal_last_10_days: str
    menstruation_last_5_days: str
    antibiotics_last_2_weeks: str
    analgesics_last_3_days: str

    # Абсолютные противопоказания
    has_hiv_or_hepatitis: str
    has_cancer_or_blood_disease: str
    has_chronic_disease: str

class SurveyPayload(BaseModel):
    survey_data: SurveyAnswers
    auth_string: str

def validate_telegram_data(auth_data: str) -> dict:
    """
    Проверяет строку initData, полученную от Telegram Web App.
    """
    bot_token = config.bot_token.get_secret_value()
    if not auth_data:
        raise HTTPException(status_code=403, detail="auth_data is empty.")
    try:
        parsed_data = parse_qs(auth_data)
        received_hash = parsed_data.pop('hash', [None])[0]
        if not received_hash:
            raise ValueError("Hash not found in auth data")
        data_check_string = "\n".join(
            f"{key}={value[0]}" for key, value in sorted(parsed_data.items())
        )
        secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash != received_hash:
            raise ValueError("Invalid hash")
        user_data_str = parsed_data.get('user', [None])[0]
        if not user_data_str:
            raise ValueError("User data not found")
        return json.loads(user_data_str)
    except Exception as e:
        logger.error(f"Telegram WebApp data validation failed: {e}. Raw auth_data: '{auth_data}'")
        raise HTTPException(status_code=403, detail=str(e))

async def process_survey_rules(answers: SurveyAnswers, user_gender: str) -> tuple[str, int | None, str]:
    # Абсолютные противопоказания
    if answers.age == 'no':
        return ('temp_waiver', 365000, "Возраст менее 18 лет.")
    if answers.has_hiv_or_hepatitis == 'yes' or answers.has_cancer_or_blood_disease == 'yes' or answers.has_chronic_disease == 'yes':
        return ('temp_waiver', 365000, "Абсолютное противопоказание (ВИЧ, гепатит, онкология, болезни крови, астма).")

    # Временные противопоказания
    if answers.weight == 'no':
        return ('temp_waiver', 365000, "Вес менее 50 кг.")
    if answers.health_issues_last_month == 'yes' or answers.symptoms == 'yes':
        return ('temp_waiver', 30, "ОРВИ, грипп или ангина в течение последнего месяца.")
    if answers.tooth_removal_last_10_days == 'yes':
        return ('temp_waiver', 10, "Удаление зуба в последние 10 дней.")
    if user_gender == 'female' and answers.menstruation_last_5_days == 'no':
        return ('temp_waiver', 5, "Менструация (включая 5 дней после).")
    if answers.tattoo_or_piercing == 'yes':
        return ('temp_waiver', 120, "Наличие свежей татуировки/пирсинга (отвод на 4 месяца).")
    if answers.antibiotics_last_2_weeks == 'yes':
        return ('temp_waiver', 14, "Прием антибиотиков в последние 2 недели.")
    if answers.analgesics_last_3_days == 'yes' or answers.medication_last_72h == 'yes':
        return ('temp_waiver', 3, "Прием анальгетиков или других лекарств в последние 3 дня.")

    # Подготовка к донации
    if answers.alcohol_last_48h == 'yes':
        return ('temp_waiver', 2, "Употребление алкоголя за последние 48 часов.")
    if answers.diet_followed == 'no':
        return ('ok', 0, "Несоблюдение диеты. Рекомендуется перенести донацию.") # Нестрогое правило
    if answers.sleep_last_night == 'no':
        return ('ok', 0, "Недостаточный сон. Рекомендуется перенести донацию.") # Нестрогое правило
    if answers.smoking_last_hour == 'yes':
        return ('ok', 0, "Курение в течение последнего часа. Рекомендуется воздержаться.") # Нестрогое правило

    # Если все проверки пройдены
    return ('ok', 0, "Противопоказаний не выявлено.")

async def get_ngrok_url():
    for _ in range(10):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://ngrok:4040/api/tunnels") as response:
                    if response.status == 200:
                        data = await response.json()
                        for tunnel in data['tunnels']:
                            if tunnel['proto'] == 'https':
                                return tunnel['public_url']
        except aiohttp.ClientConnectorError:
            logger.warning("Ngrok is not ready yet, retrying in 3 seconds...")
        await asyncio.sleep(3)
    return None

async def initial_admin_and_texts_setup(): 
    logger.info("Checking for initial admin and texts setup...")
    async with async_session_maker() as session:
        users_exist = await admin_requests.check_if_users_exist(session)
        if not users_exist:
            super_admin_id = config.super_admin_id
            logger.warning(f"Users table is empty. Creating main admin with ID: {super_admin_id}")
            try:
                await admin_requests.create_main_admin(session=session, tg_id=super_admin_id, tg_username="main_admin", full_name="Главный Администратор")
                await session.commit()
                logger.info(f"Main admin user created successfully for TG ID {super_admin_id}.")
            except Exception as e:
                logger.error(f"Failed to create main admin: {e}", exc_info=True)
        else:
            logger.info("Users table is not empty. Skipping admin creation.")
        
        info_texts_in_db = (await session.execute(select(func.count(InfoText.section_key)))).scalar()
        if info_texts_in_db == 0:
            logger.warning("InfoTexts table is empty. Populating from Text class.")
            texts_to_add = [
                InfoText(section_key="prepare", section_title="Как подготовиться?", section_text=Text.INFO_PREPARE),
                InfoText(section_key="contraindications", section_title="Противопоказания", section_text=Text.INFO_CONTRAINDICATIONS),
                InfoText(section_key="after", section_title="Что делать после?", section_text=Text.INFO_AFTER),
                InfoText(section_key="dkm", section_title="О донорстве костного мозга (ДКМ)", section_text=Text.INFO_DKM),
                InfoText(section_key="mifi_process", section_title="О донациях в МИФИ", section_text=Text.INFO_MIFI_PROCESS),
                InfoText(section_key="contacts", section_title="Связаться с организаторами", section_text=Text.INFO_CONTACTS)
            ]
            session.add_all(texts_to_add)
            await session.commit()
            logger.info("InfoTexts table populated successfully.")
        else:
            logger.info("InfoTexts table already populated. Skipping.")
            
def setup_aiogram_routers():
    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker)) 
    dp.update.middleware(BlockUserMiddleware())
    dp.include_router(common.router)
    dp.include_router(student.router)
    dp.include_router(feedback_router)
    dp.include_router(volunteer.router)
    dp.include_router(admin_router)
    dp.include_router(other.router)

async def submit_survey_logic(session: AsyncSession, payload: SurveyPayload) -> tuple[int, str, types.InlineKeyboardMarkup | None]:
    """
    Основная логика обработки опросника.
    Теперь возвращает данные для отправки сообщения.
    """
    logger.info("submit_survey_logic: Starting survey processing.")
    try:
        user_data = validate_telegram_data(payload.auth_string)
        user_tg_id = user_data['id']
        user_username = user_data.get('username')
        logger.info(f"submit_survey_logic: Validation successful for user_tg_id: {user_tg_id}, username: {user_username}")
    except HTTPException as e:
        logger.error(f"Survey validation failed: {e.detail}")
        raise

    answers = payload.survey_data
    
    user = await user_requests.get_user_by_tg_id(session, user_tg_id)
    if not user and user_username:
        logger.warning(f"User with tg_id {user_tg_id} not found. Trying to find by username '{user_username}'.")
        found_users = await admin_requests.find_user_for_admin(session, user_username)
        if found_users:
            user = found_users[0]
            logger.info(f"Found user by username: '{user.full_name}'. Updating their tg_id from {user.telegram_id} to {user_tg_id}.")
            user.telegram_id = user_tg_id
            session.add(user)

    if not user:
        logger.error(f"submit_survey_logic: User with tg_id {user_tg_id} or username {user_username} not found in DB.")
        raise HTTPException(status_code=404, detail="User not found in DB")

    status, days, reason = await process_survey_rules(answers, user.gender)
    logger.info(f"submit_survey_logic: Survey rules processed. Status: {status}, Reason: {reason}")

    logger.info(f"submit_survey_logic: Found user '{user.full_name}' (ID: {user.id}) in DB.")
    survey_record = Survey(user_id=user.id, passed=(status == 'ok'), verdict_text=reason, **answers.model_dump())
    session.add(survey_record)

    chat_id_to_send = user_tg_id 
    message_text = ""
    reply_markup = None

    if status == 'ok':
        logger.info(f"submit_survey_logic: Status is OK. Preparing 'success' message.")
        events = await event_requests.get_active_events_for_user(session, user.id)
        message_text = "✅ Спасибо за ответы! Противопоказаний не найдено.\n\n"
        if not events:
            message_text += "К сожалению, активных мероприятий для записи сейчас нет."
        else:
            message_text += "Вот список доступных мероприятий:"
            builder = InlineKeyboardBuilder() 
            for event in events:
                builder.row(types.InlineKeyboardButton(
                    text=f"{event.event_datetime.strftime('%d.%m.%Y')} - {event.name}",
                    callback_data=f"reg_event_{event.id}"
                ))
            reply_markup = builder.as_markup()
            
    elif status == 'temp_waiver':
        logger.info(f"submit_survey_logic: Status is TEMP_WAIVER. Creating waiver for {days} days.")
        end_date = datetime.date.today() + datetime.timedelta(days=days)
        await admin_requests.create_manual_waiver(session, user.id, end_date, reason, admin_id=0)
        message_text = f"Спасибо за честность. У вас выявлено противопоказание: <b>{reason}</b>\n\nМы автоматически установили вам медотвод до <b>{end_date.strftime('%d.%m.%Y')}</b>. Если вы считаете, что произошла ошибка, свяжитесь с организаторами."
    
    return chat_id_to_send, message_text, reply_markup

from typing import AsyncGenerator

# Создай эту функцию
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

async def submit_survey_endpoint(request: Request, session: AsyncSession = Depends(get_session)):
    """
    API эндпоинт, который вызывает логику и затем отправляет сообщение.
    """
    try:
        body = await request.json()
        payload = SurveyPayload.model_validate(body)
    except Exception as e:
        logger.error(f"Error processing survey submission: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    chat_id, text, markup = await submit_survey_logic(session, payload)
    await session.commit()
    
    if chat_id and text:
        try:
            logger.info(f"Endpoint: Attempting to send message to chat_id: {chat_id}")
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            logger.info(f"Endpoint: Successfully sent message to chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Endpoint: FAILED to send message to chat_id {chat_id}. Error: {e}", exc_info=True)
    else:
        logger.warning("Endpoint: No chat_id or text returned from logic, nothing to send.")
            
    return {"ok": True}

app = FastAPI()
app.mount("/webapp", StaticFiles(directory="webapp"), name="webapp")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    app.state.ngrok_url = await get_ngrok_url()

    if app.state.ngrok_url:
        logger.info(f"Successfully fetched ngrok URL: {app.state.ngrok_url}")
        dp["ngrok_url"] = app.state.ngrok_url
    else:
        logger.error("Could not get ngrok URL after several attempts. WebApp will not work.")
        dp["ngrok_url"] = None
    
    await create_db_and_tables()
    await initial_admin_and_texts_setup()
    scheduler = setup_scheduler(bot, async_session_maker, storage)
    scheduler.start()
    asyncio.create_task(dp.start_polling(bot, dp=dp))
    yield
    logger.info("Shutting down...")
    scheduler.shutdown()
    await dp.storage.close()
    await bot.session.close()

app.router.lifespan_context = lifespan
app.add_api_route("/api/submit_survey", submit_survey_endpoint, methods=["POST"])

if __name__ == "__main__":
    setup_aiogram_routers()
    uvicorn.run(app, host="0.0.0.0", port=8000)