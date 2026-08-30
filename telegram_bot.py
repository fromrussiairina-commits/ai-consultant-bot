import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart

from config import TELEGRAM_TOKEN
import database as db
import memory_module as memory
import ai_service as ai

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Фразы-сигналы, что клиент реально готов покупать —
# по ним поднимаем классификацию и снимаем лимит сообщений.
TARGET_SIGNALS = [
    "посчитай", "расчёт", "расчет", "сколько будет стоить", "сколько стоит",
    "хочу купить", "хочу заказать", "оформить", "готов оплатить",
    "давайте созвон", "давайте обсудим детали", "когда можно начать",
    "как оплатить", "выставите счет", "выставите счёт", "договор",
]


def _looks_like_target_client(user_text: str) -> bool:
    text = user_text.lower()
    return any(signal in text for signal in TARGET_SIGNALS)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    db.check_and_save_lead(user_id, username, full_name, "/start")

    # Приветствие больше НЕ зашито в код — его генерирует сам ИИ
    # по правилам из system_prompt.txt (раздел "КАК ВСТРЕЧАТЬ ПЕРВОЕ СООБЩЕНИЕ").
    # Поменяли текст в промпте — поменялось и приветствие, без правки кода.
    start_trigger = (
        f"[Пользователь {full_name or 'клиент'} только что запустил бота командой /start. "
        f"Поприветствуй его по правилам для первого сообщения.]"
    )

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception as e:
        logger.warning(f"Не удалось отправить chat action: {e}")

    greeting = await ai.get_ai_response(start_trigger, history_context="")
    await message.answer(greeting)


@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = str(message.from_user.id)
    user_text = message.text.strip()

    # 1. ДИНАМИЧЕСКИЙ лимит — целевой клиент не упирается в потолок
    #    на самом интересном месте разговора.
    max_requests = db.get_dynamic_limit(user_id)
    allowed, remaining = db.increment_normal_request(user_id, max_requests=max_requests)

    if not allowed:
        # Предупреждаем один раз, дальше молчим — не долбим одним и тем же
        if not db.has_limit_warning_been_sent(user_id):
            await message.answer(
                "Ваш лимит сообщений на сегодня исчерпан. "
                "Возвращайтесь завтра, либо напишите нашему специалисту напрямую."
            )
            db.mark_limit_warning_sent(user_id)
        return

    # 2. Сохраняем/обновляем лида
    db.check_and_save_lead(
        user_id,
        message.from_user.username or "",
        message.from_user.full_name or "",
        user_text
    )

    # 3. Клиент показал явный сигнал готовности купить — поднимаем классификацию.
    #    С этого момента у него уже не 15 сообщений, а фактически без лимита.
    if _looks_like_target_client(user_text):
        db.classify_user(user_id, "Целевой")

    # 4. Контекст из памяти
    history_context = memory.build_conversation_context(user_id)

    # 5. «печатает…»
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception as e:
        logger.warning(f"Не удалось отправить chat action: {e}")

    # 6. Ответ от ИИ
    bot_response = await ai.get_ai_response(user_text, history_context=history_context)

    # 7. Сохраняем в историю диалога
    db.save_message_to_history(user_id, user_text, bot_response)

    # 8. Отправляем с защитой от разрывов сети
    for attempt in range(3):
        try:
            await message.answer(bot_response)
            break
        except Exception as e:
            logger.error(f"Попытка {attempt + 1} отправки не удалась: {e}")
            await asyncio.sleep(1)
