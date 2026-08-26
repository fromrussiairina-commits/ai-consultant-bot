import sqlite3
from config import DB_PATH


def _get_existing_columns(cursor, table_name):
    """Возвращает список колонок, которые уже есть в таблице"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _migrate_table(cursor, table_name, expected_columns):
    """
    Проверяет структуру таблицы и добавляет недостающие колонки через ALTER TABLE.
    Никогда не удаляет данные и не пересоздаёт таблицу.
    expected_columns: список кортежей (имя_колонки, sql_тип_и_default)
    """
    existing = _get_existing_columns(cursor, table_name)
    for column_name, column_def in expected_columns:
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            print(f"🔧 Миграция: добавлена колонка '{column_name}' в таблицу '{table_name}'")


def init_db():
    """
    Создаёт таблицы лидов, лимитов и блокировок, если их нет.
    Если таблицы уже существуют со старой структурой — автоматически
    дополняет их недостающими колонками (миграция), не теряя данные.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица лидов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT DEFAULT 'telegram',
            user_id TEXT,
            username TEXT,
            full_name TEXT,
            first_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, user_id)
        )
    """)
    
    # Таблица для отслеживания дневных лимитов (обычные вопросы + атаки)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT DEFAULT 'telegram',
            normal_request_count INTEGER DEFAULT 0,
            attack_attempt_count INTEGER DEFAULT 0,
            limit_warning_sent INTEGER DEFAULT 0,
            last_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, platform)
        )
    """)
    
    # Таблица для блокировок (заглушка на 24ч)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT DEFAULT 'telegram',
            block_type TEXT,
            block_reason TEXT,
            blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, platform, block_type)
        )
    """)
    
    # Таблица для логирования попыток injection и аномалий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT DEFAULT 'telegram',
            threat_type TEXT,
            message_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    # ========== АВТОМАТИЧЕСКАЯ МИГРАЦИЯ ==========
    # Если таблицы существовали ДО этого запуска со старой структурой
    # (например, старый daily_limits с колонкой request_count вместо
    # normal_request_count/attack_attempt_count) — дополняем их,
    # не удаляя ни одной строки данных.
    
    _migrate_table(cursor, "leads", [
        ("platform", "TEXT DEFAULT 'telegram'"),
    ])
    
    _migrate_table(cursor, "daily_limits", [
        ("normal_request_count", "INTEGER DEFAULT 0"),
        ("attack_attempt_count", "INTEGER DEFAULT 0"),
        ("last_reset", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("limit_warning_sent", "INTEGER DEFAULT 0"),
    ])
    
    _migrate_table(cursor, "user_blocks", [
        ("block_type", "TEXT"),
        ("block_reason", "TEXT"),
        ("blocked_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ])
    
    _migrate_table(cursor, "security_logs", [
        ("platform", "TEXT DEFAULT 'telegram'"),
    ])
    
    conn.commit()
    conn.close()


def check_and_save_lead(user_id, username, full_name, message, platform="telegram"):
    """
    Сохраняет нового лида, если его ещё нет.
    Возвращает True, если лид новый (нужно уведомить админа).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM leads WHERE platform = ? AND user_id = ?",
        (platform, str(user_id))
    )
    existing = cursor.fetchone()

    if not existing:
        cursor.execute(
            "INSERT INTO leads (platform, user_id, username, full_name, first_message) VALUES (?, ?, ?, ?, ?)",
            (platform, str(user_id), username, full_name, message or "[Медиа]")
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def check_daily_limit(user_id, platform="telegram", max_normal_requests=10, max_attack_attempts=3):
    """
    Проверяет суточный лимит запросов пользователя.
    Отдельно считает обычные вопросы (10) и попытки атак (3).
    Возвращает (разрешено: bool, тип_лимита: str, оставшихся: int)
    
    Тип лимита: 'ok', 'normal_limit', 'attack_blocked'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем есть ли блокировка
    cursor.execute(
        "SELECT block_reason FROM user_blocks WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    block_result = cursor.fetchone()
    
    if block_result:
        # Пользователь заблокирован
        conn.close()
        return False, "blocked", 0
    
    # Получаем текущие счётчики
    cursor.execute(
        "SELECT normal_request_count, attack_attempt_count, last_reset FROM daily_limits WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    result = cursor.fetchone()
    
    if not result:
        # Новый пользователь
        cursor.execute(
            "INSERT INTO daily_limits (user_id, platform, normal_request_count, attack_attempt_count) VALUES (?, ?, ?, ?)",
            (str(user_id), platform, 0, 0)
        )
        conn.commit()
        conn.close()
        return True, "ok", max_normal_requests
    
    normal_count, attack_count, last_reset = result
    
    # Проверяем прошли ли сутки
    from datetime import datetime, timedelta
    last_reset_dt = datetime.fromisoformat(last_reset)
    now = datetime.now()
    
    if (now - last_reset_dt).days >= 1:
        # Сутки прошли, сбрасываем оба счётчика
        cursor.execute(
            "UPDATE daily_limits SET normal_request_count = ?, attack_attempt_count = ?, last_reset = ? WHERE user_id = ? AND platform = ?",
            (0, 0, now.isoformat(), str(user_id), platform)
        )
        # Удаляем блокировку если была
        cursor.execute(
            "DELETE FROM user_blocks WHERE user_id = ? AND platform = ?",
            (str(user_id), platform)
        )
        conn.commit()
        conn.close()
        return True, "ok", max_normal_requests
    
    conn.close()
    return True, "ok", max_normal_requests


def increment_normal_request(user_id, platform="telegram", max_requests=10):
    """
    Увеличивает счётчик обычных вопросов. 
    Если прошли сутки - сбрасывает счётчик и флаг предупреждения.
    Возвращает (разрешено, осталось)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT normal_request_count, last_reset FROM daily_limits WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    result = cursor.fetchone()
    
    if not result:
        cursor.execute(
            "INSERT INTO daily_limits (user_id, platform, normal_request_count, limit_warning_sent) VALUES (?, ?, ?, ?)",
            (str(user_id), platform, 1, 0)
        )
        conn.commit()
        conn.close()
        return True, max_requests - 1
    
    count, last_reset = result
    
    # Проверяем прошли ли сутки
    from datetime import datetime
    last_reset_dt = datetime.fromisoformat(last_reset)
    now = datetime.now()
    
    if (now - last_reset_dt).days >= 1:
        # Сутки прошли - сбрасываем счётчик И флаг предупреждения
        cursor.execute(
            "UPDATE daily_limits SET normal_request_count = 1, limit_warning_sent = 0, last_reset = ? WHERE user_id = ? AND platform = ?",
            (now.isoformat(), str(user_id), platform)
        )
        conn.commit()
        conn.close()
        return True, max_requests - 1
    
    if count >= max_requests:
        conn.close()
        return False, 0  # Лимит исчерпан
    
    # Увеличиваем счётчик
    cursor.execute(
        "UPDATE daily_limits SET normal_request_count = normal_request_count + 1 WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    conn.commit()
    conn.close()
    return True, max_requests - (count + 1)


def increment_attack_attempt(user_id, platform="telegram", max_attempts=3):
    """
    Увеличивает счётчик попыток атак.
    После 3 попыток — создаёт блокировку на 24 часа.
    Возвращает (разрешено_продолжить, осталось_попыток, заблокирован_ли_сейчас)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT attack_attempt_count FROM daily_limits WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    result = cursor.fetchone()
    
    if not result:
        cursor.execute(
            "INSERT INTO daily_limits (user_id, platform, attack_attempt_count) VALUES (?, ?, ?)",
            (str(user_id), platform, 1)
        )
        conn.commit()
        conn.close()
        return True, max_attempts - 1, False
    
    count = result[0]
    
    # Увеличиваем счётчик атак
    new_count = count + 1
    cursor.execute(
        "UPDATE daily_limits SET attack_attempt_count = ? WHERE user_id = ? AND platform = ?",
        (new_count, str(user_id), platform)
    )
    
    # Если достигли лимита атак — блокируем
    if new_count >= max_attempts:
        cursor.execute(
            "INSERT OR REPLACE INTO user_blocks (user_id, platform, block_type, block_reason) VALUES (?, ?, ?, ?)",
            (str(user_id), platform, "attack", f"Обнаружено {max_attempts} попыток атак")
        )
        conn.commit()
        conn.close()
        return False, 0, True  # Заблокирован
    
    conn.commit()
    conn.close()
    remaining = max_attempts - new_count
    return True, remaining, False  # Продолжить, осталось X попыток, не заблокирован


def log_security_threat(user_id, threat_type, message_text, platform="telegram"):
    """Логирует попытки атак (injection, спам и т.д.)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO security_logs (user_id, platform, threat_type, message_text) VALUES (?, ?, ?, ?)",
        (str(user_id), platform, threat_type, message_text[:200])  # Сохраняем первые 200 символов
    )
    conn.commit()
    conn.close()


def get_all_leads():
    """Возвращает всех лидов (для будущей CRM/выгрузки)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_remaining_requests(user_id, platform="telegram", max_requests=10):
    """Возвращает сколько осталось обычных вопросов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT normal_request_count FROM daily_limits WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return max_requests
    
    count = result[0]
    return max(0, max_requests - count)


def has_limit_warning_been_sent(user_id, platform="telegram"):
    """Проверяет было ли уже отправлено предупреждение об исчерпании лимита"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Сначала проверяем есть ли колонка
    existing_cols = _get_existing_columns(cursor, "daily_limits")
    if "limit_warning_sent" not in existing_cols:
        # Добавляем колонку если её нет
        cursor.execute("ALTER TABLE daily_limits ADD COLUMN limit_warning_sent INTEGER DEFAULT 0")
        conn.commit()
    
    cursor.execute(
        "SELECT limit_warning_sent FROM daily_limits WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    result = cursor.fetchone()
    conn.close()
    
    return result and result[0] == 1


def mark_limit_warning_sent(user_id, platform="telegram"):
    """Отмечает что предупреждение об исчерпании лимита уже отправлено"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE daily_limits SET limit_warning_sent = 1 WHERE user_id = ? AND platform = ?",
        (str(user_id), platform)
    )
    conn.commit()
    conn.close()
