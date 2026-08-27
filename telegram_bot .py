import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from config import (
    BOT_TOKEN, ADMIN_CHAT_ID, DEVELOPER_LINK, SPAM_INTERVAL_SECONDS,
    ENABLE_MEMORY, ENABLE_DASHBOARD
)

# Безопасный импорт из database.py (с защиты от отсутствующих функций)
import database

init_db = getattr(database, 'init_db', lambda: None)
check_and_save_lead = getattr(database, 'check_and_save_lead', lambda *a, **k: False)
increment_normal_request = getattr(database, 'increment_normal_request', lambda u, p, l: (True, l))
increment_attack_attempt = getattr(database, 'increment_attack_attempt', lambda u, p, m: (True, m, False))
log_security_threat = getattr(database, 'log_security_threat', lambda *a, **k: None)
has_limit_warning_been_sent = getattr(database, 'has_limit_warning_been_sent', lambda *a, **k: False)
mark_limit_warning_sent = getattr(database, 'mark_limit_warning_sent', lambda *a, **k: None)
mark_user_as_spam = getattr(database, 'mark_user_as_spam', lambda *a, **k: None)
save_message_to_history = getattr(database, 'save_message_to_history', lambda *a, **k: None)

# Заглушка для функции, из-за которой вылетала ошибка
def get_user_classification(user_id, platform="telegram"):
    if hasattr(database, 'get_user_classification'):
        try:
            return database.get_user_classification(user_id, platform)
        except Exception:
            pass
    return "Целевой"

from ai_service import get_ai_response
from security import validate_message, detect_prompt_injection, sanitize_message, is_spam_pattern

# Условный импорт памяти (ТОЛЬКО если ENABLE_MEMORY = True)
if ENABLE_MEMORY:
    from memory_module import (
        build_conversation_context, compress_conversation, 
        detect_user_type, get_user_limit
    )
else:
    # Пустышки - ничего не делают
    def build_conversation_context(*args, **kwargs):
        return ""
    async def compress_conversation(*args, **kwargs):
        pass
    def detect_user_type(*args, **kwargs):
        return "неизвестный"
    def get_user_limit(classification):
        return 10  # Базовый лимит для всех если память отключена

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

init_db()

# Отслеживание времени последнего сообщения (спам-защита)
user_last_message_time = {}

# Константы защиты
MAX_ATTACK_ATTEMPTS = 3
BASE_MAX_REQUESTS = 10


def get_contact_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать разработчику", url=DEVELOPER_LINK)]
        ]
    )


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if ADMIN_CHAT_ID and str(message.chat.id) == str(ADMIN_CHAT_ID):
        return

    await message.answer(
        "Здравствуйте! Я ИИ-консультант Лаборатории ИИ-решений. Готов ответить на любые вопросы "
        "по разработке ботов, рассчитать примерную стоимость или подобрать решение под ваш бизнес.",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer("Чем могу помочь вам сегодня?", reply_markup=get_contact_keyboard())


@dp.message()
async def ai_dialog_handler(message: types.Message):
    if ADMIN_CHAT_ID and str(message.chat.id) == str(ADMIN_CHAT_ID):
        return

    user_id = message.from_user.id
    username = message.from_user.username or "Без_юзернейма"
    full_name = message.from_user.full_name or "Пользователь"
    user_text = message.text or message.caption or "[Медиафайл]"
    current_time = time.time()

    # ========== ЗАЩИТА 1: Спам-защита (2 сек между сообщениями) ==========
    if current_time - user_last_message_time.get(user_id, 0) < SPAM_INTERVAL_SECONDS:
        await message.answer("⚠️ Пожалуйста, подождите пару секунд перед следующим вопросом.")
        return
    user_last_message_time[user_id] = current_time

    # ========== ЗАЩИТА 2: Валидация входных данных ==========
    is_valid, error_msg = validate_message(user_text)
    if not is_valid:
        await message.answer(f"❌ {error_msg}")
        return

    # ========== ЗАЩИТА 3: Проверка на спам-паттерны ==========
    if is_spam_pattern(user_text):
        log_security_threat(user_id, "spam_pattern", user_text, "telegram")
        mark_user_as_spam(user_id, "telegram")
        await message.answer("⚠️ Сообщение похоже на спам. Пожалуйста, напишите нормальный вопрос.")
        return

    # ========== ЗАЩИТА 4: Детекция prompt injection ==========
    is_injection, threat_type = detect_prompt_injection(user_text)
    if is_injection:
        log_security_threat(user_id, f"injection:{threat_type}", user_text, "telegram")
        
        allowed, remaining, is_blocked = increment_attack_attempt(user_id, "telegram", MAX_ATTACK_ATTEMPTS)
        
        if is_blocked:
            logger.warning(f"🚨 ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН: {full_name} (@{username})")
            return
        
        await message.answer(
            f"🛡️ Наша система обнаружила попытку манипуляции.\n\n"
            f"⚠️ Осталось попыток: {remaining}/{MAX_ATTACK_ATTEMPTS}",
            reply_markup=get_contact_keyboard()
        )
        
        if ADMIN_CHAT_ID:
            try:
                await bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🚨 АТАКА: {full_name} (@{username}) | Тип: {threat_type}",
                    parse_mode="HTML"
                )
            except:
                pass
        return

    # ========== ДИНАМИЧЕСКИЙ ЛИМИТ (если память включена) ==========
    if ENABLE_MEMORY:
        current_classification = get_user_classification(user_id, "telegram")
        dynamic_limit = get_user_limit(current_classification)
    else:
        dynamic_limit = BASE_MAX_REQUESTS

    # Проверяем лимит
    allowed, remaining = increment_normal_request(user_id, "telegram", dynamic_limit)
    
    if not allowed:
        if not has_limit_warning_been_sent(user_id, "telegram"):
            await message.answer(
                f"⏰ <b>Лимит сообщений в сутки исчерпан.</b>\n\n"
                f"По всем вопросам пишите разработчику 👇",
                reply_markup=get_contact_keyboard()
            )
            mark_limit_warning_sent(user_id, "telegram")
        return

    # Фиксация нового лида
    is_new_lead = check_and_save_lead(user_id, username, full_name, user_text, platform="telegram")

    if is_new_lead and ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🔥 ЛИД: {full_name} (@{username})\n💬 {user_text[:80]}...",
                parse_mode="HTML"
            )
        except:
            pass

    # ========== ПАМЯТЬ (если включена) ==========
    conversation_context = ""
    if ENABLE_MEMORY:
        conversation_context = build_conversation_context(user_id, "telegram", max_messages=10)
        asyncio.create_task(compress_conversation(user_id, "telegram"))

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        # Получаем ответ с контекстом (если память включена, иначе пустой контекст)
        ai_answer = await get_ai_response(user_text, full_name, conversation_context)
        
        # Сохраняем в историю (если память включена)
        if ENABLE_MEMORY:
            save_message_to_history(user_id, user_text, ai_answer, "telegram")
        
        # Информация об оставшихся вопросах (только если есть лимит)
        remaining_info = ""
        if dynamic_limit < 100:
            remaining_info = f"\n\n📊 <i>Осталось вопросов: {remaining}/{dynamic_limit}</i>"
        
        await message.reply(ai_answer + remaining_info, reply_markup=get_contact_keyboard())
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.reply("Произошла ошибка. Попробуйте повторить вопрос.", reply_markup=get_contact_keyboard())


async def main():
    mode = "ПАМЯТЬ+ДАШБОРД" if ENABLE_MEMORY else "БАЗОВЫЙ"
    logger.info(f"🚀 Бот запущен ({mode})")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())