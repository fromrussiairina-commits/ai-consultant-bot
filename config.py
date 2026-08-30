import os
from dotenv import load_dotenv

load_dotenv()

# Читаем TELEGRAM_TOKEN из файла .env (или BOT_TOKEN для подстраховки)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DB_PATH = "leads.db"

if not TELEGRAM_TOKEN:
    raise ValueError("Токен Telegram не найден в .env (проверьте наличие TELEGRAM_TOKEN или BOT_TOKEN)")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в .env")