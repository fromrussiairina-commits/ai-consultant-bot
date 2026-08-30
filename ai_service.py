import os
import logging
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")


def load_system_prompt() -> str:
    """Считывает системный промпт из внешнего текстового файла."""
    if os.path.exists(PROMPT_FILE_PATH):
        try:
            with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Ошибка чтения system_prompt.txt: {e}")
    return "Ты — вежливый ИИ-консультант. Помогай пользователям отвечать на вопросы."


async def get_ai_response(prompt: str, history_context: str = "", system_prompt: str = None) -> str:
    """ Отправляет запрос в OpenAI с учетом памяти и контекста. """
    try:
        base_prompt = system_prompt or load_system_prompt()

        messages = [{"role": "system", "content": base_prompt}]

        if history_context:
            messages.append({
                "role": "system",
                "content": f"Контекст прошлых сообщений пользователя:\n{history_context}"
            })

        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=450,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Ошибка OpenAI API: {e}")
        return "Произошла небольшая техническая заминка. Пожалуйста, повторите вопрос чуть позже."
