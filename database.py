import sqlite3
from config import DB_PATH


def _get_existing_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _migrate_table(cursor, table_name, expected_columns):
    existing = _get_existing_columns(cursor, table_name)
    for column_name, column_def in expected_columns:
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS message_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            platform TEXT DEFAULT 'telegram',
            user_message TEXT,
            bot_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_classifications (
            user_id TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'telegram',
            classification TEXT DEFAULT 'Заявка',
            summary TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_classification (
            user_id TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'telegram',
            username TEXT,
            first_name TEXT,
            first_message TEXT,
            summary TEXT,
            classification TEXT DEFAULT 'Заявка',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_summary (
            user_id TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'telegram',
            summary TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    _migrate_table(cursor, "leads", [("platform", "TEXT DEFAULT 'telegram'")])
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
    _migrate_table(cursor, "security_logs", [("platform", "TEXT DEFAULT 'telegram'")])
    _migrate_table(cursor, "user_classifications", [("summary", "TEXT"), ("platform", "TEXT DEFAULT 'telegram'")])
    _migrate_table(cursor, "user_classification", [
        ("platform", "TEXT DEFAULT 'telegram'"),
        ("username", "TEXT"),
        ("first_name", "TEXT"),
        ("first_message", "TEXT"),
        ("summary", "TEXT"),
        ("classification", "TEXT DEFAULT 'Заявка'"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ])
    _migrate_table(cursor, "user_summary", [("platform", "TEXT DEFAULT 'telegram'")])

    conn.commit()
    conn.close()


def check_and_save_lead(user_id, username, full_name, message, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM leads WHERE platform = ? AND user_id = ?", (platform, str(user_id)))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute(
            "INSERT INTO leads (platform, user_id, username, full_name, first_message) VALUES (?, ?, ?, ?, ?)",
            (platform, str(user_id), username, full_name, message or "[Медиа]")
        )

    cursor.execute("""
        INSERT INTO user_classification (user_id, platform, username, first_name, first_message)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            platform = excluded.platform
    """, (str(user_id), platform, username, full_name, message or "[Медиа]"))

    conn.commit()
    conn.close()
    return not existing


def increment_normal_request(user_id, platform="telegram", max_requests=15):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT normal_request_count, last_reset FROM daily_limits WHERE user_id = ? AND platform = ?", (str(user_id), platform))
    result = cursor.fetchone()

    if not result:
        cursor.execute("INSERT INTO daily_limits (user_id, platform, normal_request_count, limit_warning_sent) VALUES (?, ?, ?, ?)", (str(user_id), platform, 1, 0))
        conn.commit()
        conn.close()
        return True, max_requests - 1

    count, last_reset = result
    from datetime import datetime
    last_reset_dt = datetime.fromisoformat(last_reset)
    now = datetime.now()

    if (now - last_reset_dt).days >= 1:
        cursor.execute("UPDATE daily_limits SET normal_request_count = 1, limit_warning_sent = 0, last_reset = ? WHERE user_id = ? AND platform = ?", (now.isoformat(), str(user_id), platform))
        conn.commit()
        conn.close()
        return True, max_requests - 1

    if count >= max_requests:
        conn.close()
        return False, 0

    cursor.execute("UPDATE daily_limits SET normal_request_count = normal_request_count + 1 WHERE user_id = ? AND platform = ?", (str(user_id), platform))
    conn.commit()
    conn.close()
    return True, max_requests - (count + 1)


def increment_attack_attempt(user_id, platform="telegram", max_attempts=3):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT attack_attempt_count FROM daily_limits WHERE user_id = ? AND platform = ?", (str(user_id), platform))
    result = cursor.fetchone()

    if not result:
        cursor.execute("INSERT INTO daily_limits (user_id, platform, attack_attempt_count) VALUES (?, ?, ?)", (str(user_id), platform, 1))
        conn.commit()
        conn.close()
        return True, max_attempts - 1, False

    count = result[0]
    new_count = count + 1
    cursor.execute("UPDATE daily_limits SET attack_attempt_count = ? WHERE user_id = ? AND platform = ?", (new_count, str(user_id), platform))

    if new_count >= max_attempts:
        cursor.execute("INSERT OR REPLACE INTO user_blocks (user_id, platform, block_type, block_reason) VALUES (?, ?, ?, ?)", (str(user_id), platform, "attack", f"Обнаружено {max_attempts} попыток атак"))
        conn.commit()
        conn.close()
        return False, 0, True

    conn.commit()
    conn.close()
    return True, max_attempts - new_count, False


def log_security_threat(user_id, threat_type, message_text, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO security_logs (user_id, platform, threat_type, message_text) VALUES (?, ?, ?, ?)", (str(user_id), platform, threat_type, message_text[:200]))
    conn.commit()
    conn.close()


def has_limit_warning_been_sent(user_id, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT limit_warning_sent FROM daily_limits WHERE user_id = ? AND platform = ?", (str(user_id), platform))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1


def mark_limit_warning_sent(user_id, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE daily_limits SET limit_warning_sent = 1 WHERE user_id = ? AND platform = ?", (str(user_id), platform))
    conn.commit()
    conn.close()


def get_user_classification(user_id, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT classification FROM user_classifications WHERE user_id = ?", (str(user_id),))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Заявка"


def get_dynamic_limit(user_id, platform="telegram"):
    """
    Лимит сообщений в день в зависимости от того, кто перед нами.
    Целевой клиент (уже показал явный сигнал готовности купить) — практически
    без лимита, чтобы не обрывать разговор на моменте "посчитай мне цену".
    """
    classification = get_user_classification(user_id, platform)
    limits = {
        "Целевой": 999,
        "Заявка": 15,
        "Спам": 3,
    }
    return limits.get(classification, 15)


def classify_user(user_id, classification, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_classifications (user_id, platform, classification) VALUES (?, ?, ?)", (str(user_id), platform, classification))
    cursor.execute("UPDATE user_classification SET classification = ? WHERE user_id = ?", (classification, str(user_id)))
    conn.commit()
    conn.close()


def mark_user_as_spam(user_id, platform="telegram"):
    classify_user(user_id, "Спам", platform)


def save_message_to_history(user_id, user_message, bot_response, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO message_history (user_id, platform, user_message, bot_response) VALUES (?, ?, ?, ?)", (str(user_id), platform, user_message, bot_response))
    conn.commit()
    conn.close()


def get_last_messages(user_id, platform="telegram", limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_message, bot_response FROM message_history WHERE user_id = ? AND platform = ? ORDER BY id DESC LIMIT ?", (str(user_id), platform, limit))
    rows = cursor.fetchall()
    conn.close()
    return list(reversed(rows))


def save_user_summary(user_id, summary_text, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_classifications (user_id, platform, summary)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            summary = excluded.summary,
            platform = excluded.platform,
            updated_at = CURRENT_TIMESTAMP
    """, (str(user_id), platform, summary_text))
    cursor.execute("UPDATE user_classification SET summary = ? WHERE user_id = ?", (summary_text, str(user_id)))
    cursor.execute("""
        INSERT INTO user_summary (user_id, platform, summary)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            summary = excluded.summary,
            platform = excluded.platform,
            updated_at = CURRENT_TIMESTAMP
    """, (str(user_id), platform, summary_text))
    conn.commit()
    conn.close()


def get_user_summary(user_id, platform="telegram"):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT summary FROM user_classifications WHERE user_id = ?", (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    return row['summary'] if (row and row['summary']) else None
