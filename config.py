import os
from dotenv import load_dotenv

load_dotenv()

# ========== МОДУЛИ И ФИЧИ ==========
ENABLE_MEMORY = True  # Включить модуль памяти? (платная фича)
ENABLE_DASHBOARD = True  # Включить дашборд? (платная фича)

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # дешёвая модель, хватит для консультанта

# Ссылка на разработчика (используется на всех платформах)
DEVELOPER_LINK = "https://t.me/Irisha078"

# Спам-защита (секунды между сообщениями от одного пользователя)
SPAM_INTERVAL_SECONDS = 2

# База данных лидов
DB_PATH = "leads.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в .env")
