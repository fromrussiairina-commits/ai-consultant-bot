import re
import logging

logger = logging.getLogger(__name__)

# Опасные фразы для prompt injection
INJECTION_KEYWORDS = [
    "забудь", "ignore", "system prompt", "systemp", "sytem",
    "инструкция", "instruction", "приказ", "command",
    "игнорируй", "пропусти", "скрой", "hide",
    "скажи", "ответь", "tell me", "reveal", "show",
    "администратор", "админ", "admin", "root",
    "база данных", "database", "пароль", "password",
]

# Подозрительные паттерны
SUSPICIOUS_PATTERNS = [
    r"(?:забудь|ignore).*(?:промпт|prompt|инструкция|instruction)",
    r"(?:system|системн).*(?:prompt|инструкция)",
    r"(?:ты\s+)?(?:теперь|now)\s+(?:не|не)\s+(?:консультант|consultant)",
    r"(?:act\s+as|делай\s+вид).*(?:admin|админ|hacker)",
]

# Максимальная длина сообщения (защита от очень длинных запросов)
MAX_MESSAGE_LENGTH = 5000

# Минимальная длина сообщения (защита от пустых)
MIN_MESSAGE_LENGTH = 1


def validate_message(user_text: str) -> tuple[bool, str]:
    """
    Валидирует входное сообщение пользователя.
    Возвращает (валидно: bool, сообщение_об_ошибке: str)
    """
    if not user_text or not user_text.strip():
        return False, "Сообщение пустое."
    
    user_text = user_text.strip()
    
    if len(user_text) < MIN_MESSAGE_LENGTH:
        return False, "Сообщение слишком короткое."
    
    if len(user_text) > MAX_MESSAGE_LENGTH:
        return False, f"Сообщение слишком длинное (макс. {MAX_MESSAGE_LENGTH} символов)."
    
    return True, ""


def detect_prompt_injection(user_text: str) -> tuple[bool, str]:
    """
    Проверяет текст на попытки prompt injection.
    Возвращает (опасен ли, тип_угрозы)
    """
    text_lower = user_text.lower()
    
    # Проверка на опасные ключевые слова
    for keyword in INJECTION_KEYWORDS:
        if keyword in text_lower:
            # Дополнительная проверка контекста
            if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
                return True, f"suspicious_keyword:{keyword}"
    
    # Проверка на подозрительные паттерны
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text_lower):
            return True, "suspicious_pattern"
    
    # Проверка на множество спецсимволов (иногда используется для obfuscation)
    special_char_ratio = len(re.findall(r"[!@#$%^&*()_\-+=\[\]{};:'\"<>?,./]", user_text)) / len(user_text)
    if special_char_ratio > 0.3:  # Больше 30% спецсимволов
        return True, "high_special_chars"
    
    return False, ""


def sanitize_message(user_text: str) -> str:
    """
    Очищает сообщение от потенциально опасного контента.
    """
    # Убираем лишние пробелы
    user_text = " ".join(user_text.split())
    
    # Убираем управляющие символы (кроме переносов строк)
    user_text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", user_text)
    
    return user_text


def is_spam_pattern(user_text: str) -> bool:
    """
    Проверяет похож ли текст на спам (повторы, одинаковые символы и т.д.)
    """
    # Проверка на много одинаковых символов подряд
    if re.search(r"(.)\1{10,}", user_text):
        return True
    
    # Проверка на много повторяющихся слов
    words = user_text.split()
    if len(words) > 0 and len(set(words)) / len(words) < 0.3:  # Менее 30% уникальных слов
        return True
    
    return False
