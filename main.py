import asyncio
import logging
import threading

from telegram_bot import bot, dp
import database as db
from dashboard_app import app as dashboard_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_dashboard():
    # Отключаем лишние логи Flask в консоли
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    logger.info("📊 Дашборд доступен по адресу: http://localhost:8080")
    dashboard_app.run(host="0.0.0.0", port=8080, use_reloader=False)


async def main():
    # 1. Единая инициализация всех таблиц БД
    db.init_db()
    logger.info("✅ База данных и все таблицы успешно инициализированы.")

    # 2. Старт дашборда в фоновом потоке
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()

    # 3. Старт бота
    logger.info("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
