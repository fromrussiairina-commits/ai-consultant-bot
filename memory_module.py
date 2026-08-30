import logging
from database import get_last_messages, get_user_summary

logger = logging.getLogger(__name__)


def build_conversation_context(user_id: str, platform: str = "telegram", limit: int = 10) -> str:
    """ Собирает историю сообщений и сводку по пользователю в единый контекст. """
    try:
        history = get_last_messages(user_id, platform=platform, limit=limit)
        summary = get_user_summary(user_id, platform=platform)

        context_parts = []

        if summary:
            context_parts.append(f"=== СВОДКА О ПОЛЬЗОВАТЕЛЕ ===\n{summary}\n")

        if history:
            context_parts.append("=== ПОСЛЕДНИЕ СООБЩЕНИЯ ДИАЛОГА ===")
            for user_msg, bot_resp in history:
                context_parts.append(f"Пользователь: {user_msg}")
                context_parts.append(f"Консультант: {bot_resp}")

        return "\n".join(context_parts)
    except Exception as e:
        logger.error(f"Ошибка при сборе контекста памяти: {e}")
        return ""