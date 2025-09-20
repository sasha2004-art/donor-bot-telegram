import io
import hashlib
import qrcode
import json
import logging
from PIL import Image
from pyzbar.pyzbar import decode, ZBarSymbol

from bot.config_reader import config

logger = logging.getLogger(__name__)


def create_secure_payload(data: dict) -> str:
    # Формирует строку для QR-кода
    json_string = json.dumps(data, sort_keys=True, separators=(",", ":"))
    salt = config.qr_secret_key.get_secret_value()
    string_to_hash = json_string + salt
    # logger.info(f"[CREATE] String to be hashed: '{string_to_hash}'")
    h = hashlib.sha256(string_to_hash.encode()).hexdigest()
    # logger.info(f"[CREATE] Generated hash: {h}")
    return f"{json_string}|{h}"


def verify_secure_payload(payload: str) -> dict | None:
    # Проверяет строку и возвращает данные
    try:
        json_string, received_hash = payload.split("|", 1)
        salt = config.qr_secret_key.get_secret_value()
        string_to_hash = json_string + salt
        # logger.info(f"[VERIFY] String to be hashed: '{string_to_hash}'")
        expected_hash = hashlib.sha256(string_to_hash.encode()).hexdigest()
        # logger.info(f"[VERIFY] Received hash:  {received_hash}")
        # logger.info(f"[VERIFY] Expected hash:  {expected_hash}")
        if received_hash == expected_hash:
            # logger.info("[VERIFY] Hashes MATCH. Verification successful.")
            return json.loads(json_string)
        else:
            # logger.error("[VERIFY] Hashes DO NOT MATCH. Verification failed.")
            return None
    except (ValueError, IndexError, json.JSONDecodeError) as e:
        # logger.error(f"[VERIFY] An exception occurred during verification: {e}")
        return None


async def generate_qr(data: dict) -> bytes:
    # Генерирует QR-код
    # logger.info(f"--- Generating QR for data: {data} ---")
    payload = create_secure_payload(data)
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf.read()


async def read_qr(photo_bytes: bytes) -> dict | None:
    # Читает QR-код и возвращает данные
    try:
        image = Image.open(io.BytesIO(photo_bytes)).convert("L")
        decoded_objects = decode(image, symbols=[ZBarSymbol.QRCODE])
        if not decoded_objects:
            # logger.warning("pyzbar failed to find any QR codes on the image.")
            return None
        payload = decoded_objects[0].data.decode("utf-8")
        # logger.info(f"--- Verifying QR with payload: '{payload}' ---")
        verified_data = verify_secure_payload(payload)
        return verified_data
    except Exception as e:
        # logger.error(f"An exception occurred in read_qr: {e}", exc_info=True)
        return None
