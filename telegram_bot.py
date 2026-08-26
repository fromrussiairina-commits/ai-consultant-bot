import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from config import BOT_TOKEN, ADMIN_CHAT_ID, DEVELOPER_LINK, SPAM_INTERVAL_SECONDS
from database import init_db, check_and_save_lead, increment_normal_request, increment_attack_attempt, log_security_threat, get_remaining_requests, has_limit_warning_been_sent, mark_limit_warning_sent
from ai_service import get_ai_response
from security import validate_message, detect_prompt_injection, sanitize_message, is_spam_pattern

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

init_db()

# Отслеживание времени последнего сообщения (спам-защита)
user_last_message_time = {}

# Константы защиты
MAX_NORMAL_REQUESTS_PER_DAY = 10  # 10 обычных вопросов в день
MAX_ATTACK_ATTEMPTS = 3  # 3 попытки атак, потом блокировка на 24ч


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
        await message.answer("⚠️ Сообщение похоже на спам. Пожалуйста, напишите нормальный вопрос.")
        return

    # ========== ЗАЩИТА 4: Детекция prompt injection ==========
    is_injection, threat_type = detect_prompt_injection(user_text)
    if is_injection:
        log_security_threat(user_id, f"injection:{threat_type}", user_text, "telegram")
        
        # Увеличиваем счётчик попыток атак
        allowed, remaining, is_blocked = increment_attack_attempt(user_id, "telegram", MAX_ATTACK_ATTEMPTS)
        
        if is_blocked:
            # ЗАГЛУШКА НА 24 ЧАСА — БОТ МОЛЧИТ, НЕ ОТВЕЧАЕТ
            logger.warning(f"🚨 ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН ЗА АТАКИ: {full_name} (@{username}) ID:{user_id}")
            # Ничего не пишем, просто молчим!
            return
        
        # Если ещё не заблокирован, пишем предупреждение
        await message.answer(
            f"🛡️ Наша система обнаружила попытку манипуляции.\n\n"
            f"⚠️ Осталось попыток: {remaining}/{MAX_ATTACK_ATTEMPTS}\n"
            f"После {MAX_ATTACK_ATTEMPTS} попыток вы будете заблокированы на 24 часа.",
            reply_markup=get_contact_keyboard()
        )
        
        # Уведомляем админа об атаке
        if ADMIN_CHAT_ID:
            alert_text = (
                f"🚨 <b>ПОПЫТКА АТАКИ:</b>\n\n"
                f"👤 <b>Пользователь:</b> {full_name} (@{username})\n"
                f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                f"⚠️ <b>Тип угрозы:</b> {threat_type}\n"
                f"💬 <b>Текст:</b> {user_text[:100]}\n"
                f"📊 <b>Попыток атак:</b> {MAX_ATTACK_ATTEMPTS - remaining}/{MAX_ATTACK_ATTEMPTS}"
            )
            try:
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Не удалось отправить алерт админу: {e}")
        return

    # ========== ЗАЩИТА 5: Проверка лимита обычных вопросов ==========
    allowed, remaining = increment_normal_request(user_id, "telegram", MAX_NORMAL_REQUESTS_PER_DAY)
    
    if not allowed:
        # Лимит исчерпан - проверяем было ли уже сообщение об этом
        if not has_limit_warning_been_sent(user_id, "telegram"):
            # Первый раз после исчерпания лимита - отправляем информативное сообщение
            await message.answer(
                f"⏰ <b>Лимит 10 сообщений в сутки исчерпан.</b>\n\n"
                f"По всем вопросам пишите разработчику 👇",
                reply_markup=get_contact_keyboard()
            )
            # Отмечаем что сообщение уже отправлено
            mark_limit_warning_sent(user_id, "telegram")
            logger.info(f"⏰ ЛИМИТ ИСЧЕРПАН + СООБЩЕНИЕ ОТПРАВЛЕНО: {full_name} (@{username}) ID:{user_id}")
        else:
            # Уже отправляли сообщение - молчим 24ч
            logger.info(f"⏰ ЛИМИТ ИСЧЕРПАН + МОЛЧИМ: {full_name} (@{username}) ID:{user_id}")
        
        return

    # Фиксация нового лида
    is_new_lead = check_and_save_lead(user_id, username, full_name, user_text, platform="telegram")

    if is_new_lead and ADMIN_CHAT_ID:
        lead_text = (
            f"🔥 <b>НОВАЯ ЗАЯВКА / ЛИД:</b>\n\n"
            f"👤 <b>Клиент:</b> {full_name} (@{username})\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📝 <b>Первый запрос:</b> {user_text}"
        )
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=lead_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось отправить в группу админа: {e}")

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        ai_answer = await get_ai_response(user_text, full_name)
        
        # Добавляем информацию об оставшихся вопросах
        remaining_info = f"\n\n📊 <i>Осталось вопросов сегодня: {remaining}/{MAX_NORMAL_REQUESTS_PER_DAY}</i>"
        await message.reply(ai_answer + remaining_info, reply_markup=get_contact_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка при получении ответа от AI: {e}")
        await message.reply("Произошла ошибка. Попробуйте повторить вопрос чуть позже.", reply_markup=get_contact_keyboard())


async def main():
    logger.info("🚀 Telegram-бот запущен (ФАЗА 1: 10 вопросов + 3 атаки с блокировкой)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
