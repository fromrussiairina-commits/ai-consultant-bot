"""
МОДУЛЬ ПАМЯТИ ДИАЛОГОВ
Отдельный опциональный модуль для сохранения истории и классификации клиентов.
Подключается условно через флаг ENABLE_MEMORY в config.py
"""

import asyncio
import logging
from database import (
    get_last_messages, save_user_summary, get_user_summary,
    classify_user, get_user_classification, mark_user_as_spam,
    save_message_to_history
)
from ai_service import client, OPENAI_MODEL

logger = logging.getLogger(__name__)


def build_conversation_context(user_id, platform="telegram", max_messages=10):
    """
    Собирает контекст разговора для передачи в GPT.
    Включает резюме + последние сообщения.
    """
    # Получаем резюме
    summary = get_user_summary(user_id, platform)
    
    # Получаем последние сообщения
    messages = get_last_messages(user_id, platform, max_messages)
    
    if not messages and not summary:
        return ""  # Нет контекста
    
    context = ""
    
    if summary:
        context += f"📌 РЕЗЮМЕ:\n{summary}\n\n"
    
    if messages:
        context += "💬 ПОСЛЕДНИЕ СООБЩЕНИЯ:\n"
        for user_msg, bot_resp, timestamp in messages:
            context += f"• Клиент: {user_msg[:100]}\n"
            context += f"  Я: {bot_resp[:100]}\n"
    
    return context


async def compress_conversation(user_id, platform="telegram"):
    """
    Сжимает диалог в резюме если сообщений больше 50.
    Использует GPT для умного резюме.
    """
    messages = get_last_messages(user_id, platform, limit=100)
    
    if len(messages) < 50:
        return  # Ещё мало, не сжимаем
    
    # Собираем весь диалог в текст
    dialogue_text = ""
    for user_msg, bot_resp, timestamp in messages:
        dialogue_text += f"Клиент: {user_msg}\nБот: {bot_resp}\n---\n"
    
    try:
        # Просим GPT сделать краткое резюме
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": 
                    "Ты помощник для суммаризации диалогов с клиентами. "
                    "Извлеки ГЛАВНОЕ: ниша клиента, его проблема, интересующие платформы, упомянутый бюджет. "
                    "Ответь в формате: Ниша: X, Проблема: Y, Платформы: Z, Бюджет: W. "
                    "Будь краток (одна строка)."},
                {"role": "user", "content": f"Сожми этот диалог:\n{dialogue_text[:2000]}"}
            ],
            max_tokens=200
        )
        
        summary = response.choices[0].message.content
        save_user_summary(user_id, summary, platform)
        logger.info(f"✅ Диалог юзера {user_id} сжат в резюме")
    except Exception as e:
        logger.error(f"❌ Ошибка при сжатии диалога: {e}")


def detect_user_type(user_message, messages_count, wrote_to_dev, passed_funnel):
    """
    Классифицирует пользователя на основе поведения.
    целевой: написал разработчику
    теплый: прошёл по воронке но не написал
    левый: спам или фигня не по делу
    неизвестный: новый пользователь
    """
    
    # Целевой: написал разработчику
    if wrote_to_dev:
        return "целевой"
    
    # Теплый: прошёл по воронке но не написал
    if passed_funnel and messages_count >= 3:
        return "теплый"
    
    # Левый: спам или фигня не по делу
    spam_keywords = [
        "забудь", "ignore", "погода", "анекдот", "мемас", "картинку", 
        "видео", "музыку", "фото", "шутка", "привет как дела"
    ]
    
    if any(keyword in user_message.lower() for keyword in spam_keywords):
        return "левый"
    
    # Если мало вопросов и нет контекста
    if messages_count < 2:
        return "неизвестный"
    
    return "неизвестный"


def get_user_limit(classification):
    """
    Возвращает динамический лимит сообщений в день.
    целевой: 999 (практически без ограничений)
    теплый: 20 сообщений (хороший контакт)
    левый: 3 сообщения (почти блокируем)
    неизвестный: 10 сообщений (стандарт)
    """
    limits = {
        "целевой": 999,
        "теплый": 20,
        "левый": 3,
        "неизвестный": 10
    }
    return limits.get(classification, 10)


async def save_to_history_wrapper(user_id, user_message, bot_response, platform="telegram"):
    """Оборачивает сохранение в историю"""
    try:
        save_message_to_history(user_id, user_message, bot_response, platform)
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении в историю: {e}")
