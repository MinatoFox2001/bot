import sqlite3
import os
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from config import ROOT_ADMIN_ID

DATABASE_NAME = "users.db"

def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def init_db():
    """Инициализирует базу данных и создает все необходимые таблицы"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        
        # Проверяем существование таблицы users
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='users'
        """)
        users_table_exists = cursor.fetchone() is not None
        
        # Создаем таблицу users со всеми необходимыми колонками
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance INTEGER DEFAULT 0,
                referral_balance INTEGER DEFAULT 0,
                mode TEXT DEFAULT 'chat',
                subscription_type TEXT DEFAULT 'free',
                subscription_expires DATETIME,
                tokens_used_today INTEGER DEFAULT 0,
                last_token_reset DATE DEFAULT CURRENT_DATE
            )
        """)
        
        # Если таблица уже существовала, проверяем наличие колонок
        if users_table_exists:
            # Проверяем наличие колонки referral_balance
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'referral_balance' not in columns:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN referral_balance INTEGER DEFAULT 0")
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
        
        # Создаем остальные таблицы
        tables = {
            'message_logs': """
                CREATE TABLE IF NOT EXISTS message_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    message TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'admins': """
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'discount_codes': """
                CREATE TABLE IF NOT EXISTS discount_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    max_uses INTEGER NOT NULL,
                    used_count INTEGER DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """,
            'user_discounts': """
                CREATE TABLE IF NOT EXISTS user_discounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    discount_code TEXT NOT NULL,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    used BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """,
            'referrals': """
                CREATE TABLE IF NOT EXISTS referrals (
                    user_id INTEGER PRIMARY KEY,
                    referrer_id INTEGER,
                    registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (referrer_id) REFERENCES users (user_id)
                )
            """,
            'referral_payments': """
                CREATE TABLE IF NOT EXISTS referral_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    referrer_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    level INTEGER NOT NULL,
                    payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    subscription_type TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (referrer_id) REFERENCES users (user_id)
                )
            """
        }
        
        for table_name, create_sql in tables.items():
            cursor.execute(create_sql)
        
        # Добавляем root админа, если база только что создана
        if not users_table_exists and ROOT_ADMIN_ID:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
                    (ROOT_ADMIN_ID, ROOT_ADMIN_ID)
                )
            except Exception as e:
                print(f"Ошибка при добавлении root админа: {e}")
        
        conn.commit()

def log_message(user_id: int, role: str, message: str):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO message_logs (user_id, role, message)
            VALUES (?, ?, ?)
        """, (user_id, role, message))
        conn.commit()

def get_last_messages(user_id: int, limit: int = 10) -> List[Dict]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, message FROM message_logs
            WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
        """, (user_id, limit))
        return list(reversed(cursor.fetchall()))

def get_user(user_id: int) -> Optional[Dict]:
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def create_user(user_id: int, username: str, full_name: str):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""INSERT OR IGNORE INTO users (
            user_id, username, full_name, subscription_type
        ) VALUES (?, ?, ?, ?)""", (user_id, username, full_name, 'free'))
        conn.commit()


def update_balance(user_id: int, amount: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()

def update_user_mode(user_id: int, mode: str):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET mode = ? WHERE user_id = ?",
            (mode, user_id)
        )
        conn.commit()

def update_subscription(user_id: int, sub_type: str, duration_days: int):
    expires = datetime.now() + timedelta(days=duration_days)
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET subscription_type = ?, subscription_expires = ? WHERE user_id = ?",
            (sub_type, expires.isoformat(), user_id)
        )
        conn.commit()

def get_subscription_info(user_id: int) -> dict:
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subscription_type, subscription_expires, 
                   tokens_used_today, last_token_reset
            FROM users WHERE user_id = ?
        """, (user_id,))
        return cursor.fetchone()

def reset_daily_tokens_if_needed(user_id: int):
    today = datetime.now().date()
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET tokens_used_today = 0, last_token_reset = ?
            WHERE user_id = ? AND last_token_reset < ?
        """, (today.isoformat(), user_id, today.isoformat()))
        conn.commit()

def increment_token_usage(user_id: int, tokens_used: int):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET tokens_used_today = tokens_used_today + ?
            WHERE user_id = ?
        """, (tokens_used, user_id))
        conn.commit()

def get_active_subscription(user_id: int) -> dict:
    """Возвращает активную подписку пользователя"""
    # Если user_id не определен, 0 или None - возвращаем None
    if not user_id:
        return None
        
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            conn.row_factory = dict_factory
            cursor = conn.cursor()
            cursor.execute("SELECT subscription_type, subscription_expires FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return {
                'type': result[0] if result else 'free',
                'expires': result[1] if result else None
            } if result else None
    except Exception:
        return None

def is_subscription_active(user_id: int) -> bool:
    """Проверяет, активна ли подписка"""
    # Если user_id не определен, 0 или None - сразу возвращаем False без ошибок
    if not user_id:
        return False
        
    try:
        subscription = get_active_subscription(user_id)
        if not subscription or not subscription.get('type') or subscription['type'] == 'free':
            return False
        
        expires = subscription.get('expires')
        if not expires:
            return False
            
        # Обработка строки даты
        if isinstance(expires, str):
            # Удаляем информацию о часовом поясе если есть
            expires = expires.split('+')[0]
            expires_dt = datetime.fromisoformat(expires)
            
        return expires_dt > datetime.now()
    except Exception:
        return False

def is_user_admin(user_id: int) -> bool:
    # Root админ всегда имеет доступ
    if user_id == ROOT_ADMIN_ID:
        return True
    
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None
    except Exception:
        return False

def add_admin(user_id: int, added_by: int) -> bool:
    """Добавляет администратора"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by)
            )
            conn.commit()
            return True
    except Exception:
        return False

def remove_admin(user_id: int) -> bool:
    """Удаляет администратора"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()
            return True
    except Exception:
        return False

def get_all_admins() -> List[Dict]:
    """Возвращает список всех администраторов"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            conn.row_factory = dict_factory
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM admins")
            return cursor.fetchall()
    except Exception:
        return []

def get_user_info(user_id: int) -> Optional[Dict]:
    """Получает информацию о пользователе по ID"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, full_name, balance, referral_balance, subscription_type FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

# Добавьте эти функции в конец файла database.py:

def init_discounts_table():
    """Создает таблицу для скидочных кодов"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_percent INTEGER NOT NULL,
                max_uses INTEGER NOT NULL,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        conn.commit()

def init_user_discounts_table():
    """Создает таблицу для хранения примененных скидок пользователей"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_discounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                discount_code TEXT NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                used BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        conn.commit()

def apply_discount_to_user(user_id: int, code: str) -> bool:
    """Применяет скидку к пользователю (сохраняет для последующего использования)"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_discounts (user_id, discount_code, used)
                VALUES (?, ?, 0)
            """, (user_id, code))
            conn.commit()
            return True
    except Exception as e:
        print(f"Ошибка при применении скидки к пользователю: {e}")
        return False

def get_user_active_discount(user_id: int) -> Optional[Dict]:
    """Получает активную (неиспользованную) скидку пользователя"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ud.*, dc.discount_percent 
            FROM user_discounts ud
            JOIN discount_codes dc ON ud.discount_code = dc.code
            WHERE ud.user_id = ? AND ud.used = 0 AND dc.is_active = 1
        """, (user_id,))
        return cursor.fetchone()

def mark_discount_as_used(user_id: int, code: str) -> bool:
    """Отмечает скидку как использованную"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_discounts 
                SET used = 1 
                WHERE user_id = ? AND discount_code = ?
            """, (user_id, code))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при отметке скидки как использованной: {e}")
        return False

def create_discount_code(code: str, discount_percent: int, max_uses: int, created_by: int) -> bool:
    """Создает новый скидочный код"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO discount_codes (code, discount_percent, max_uses, created_by)
                VALUES (?, ?, ?, ?)
            """, (code, discount_percent, max_uses, created_by))
            conn.commit()
            return True
    except Exception as e:
        print(f"Ошибка при создании скидочного кода: {e}")
        return False

def get_discount_code(code: str) -> Optional[Dict]:
    """Получает информацию о скидочном коде"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM discount_codes WHERE code = ? AND is_active = 1
        """, (code,))
        return cursor.fetchone()

def use_discount_code(code: str) -> bool:
    """Увеличивает счетчик использований скидочного кода"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE discount_codes 
                SET used_count = used_count + 1 
                WHERE code = ? AND is_active = 1 AND used_count < max_uses
            """, (code,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при использовании скидочного кода: {e}")
        return False

def get_all_discount_codes() -> List[Dict]:
    """Получает все скидочные коды"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM discount_codes ORDER BY created_at DESC
        """)
        return cursor.fetchall()

def delete_discount_code(code: str) -> bool:
    """Удаляет скидочный код"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM discount_codes WHERE code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при удалении скидочного кода: {e}")
        return False

def deactivate_discount_code(code: str) -> bool:
    """Деактивирует скидочный код"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE discount_codes SET is_active = 0 WHERE code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Ошибка при деактивации скидочного кода: {e}")
        return False

def get_user_id_by_username(username: str) -> Optional[int]:
    """Получает ID пользователя по username"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ? COLLATE NOCASE", (username,))
        result = cursor.fetchone()
        return result[0] if result else None

def init_referral_tables():
    """Создает таблицы для реферальной системы"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                user_id INTEGER PRIMARY KEY,
                referrer_id INTEGER,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (referrer_id) REFERENCES users (user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referral_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                referrer_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                level INTEGER NOT NULL,
                payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                subscription_type TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (referrer_id) REFERENCES users (user_id)
            )
        """)
        conn.commit()

def add_referral(user_id: int, referrer_id: int) -> bool:
    """Добавляет реферальную связь"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO referrals (user_id, referrer_id)
                VALUES (?, ?)
            """, (user_id, referrer_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"Ошибка при добавлении реферала: {e}")
        return False

def get_referrer_id(user_id: int) -> Optional[int]:
    """Получает ID реферера пользователя"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT referrer_id FROM referrals WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def get_referrals(user_id: int) -> List[Dict]:
    """Получает список рефералов пользователя"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.full_name, r.registration_date
            FROM referrals r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.referrer_id = ?
            ORDER BY r.registration_date DESC
        """, (user_id,))
        return cursor.fetchall()

def add_referral_payment(user_id: int, referrer_id: int, amount: float, level: int, sub_type: str) -> bool:
    """Добавляет запись о реферальном платеже"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO referral_payments (user_id, referrer_id, amount, level, subscription_type)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, referrer_id, amount, level, sub_type))
            conn.commit()
            return True
    except Exception as e:
        print(f"Ошибка при добавлении реферального платежа: {e}")
        return False

def get_referral_stats(user_id: int) -> Dict:
    """Получает статистику по реферальной программе"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        # Общее количество рефералов
        cursor.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?", (user_id,))
        total_referrals = cursor.fetchone()['count']
        
        # Количество активных рефералов (с подпиской)
        cursor.execute("""
            SELECT COUNT(DISTINCT r.user_id) as count
            FROM referrals r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.referrer_id = ? AND u.subscription_type != 'free'
        """, (user_id,))
        active_referrals = cursor.fetchone()['count']
        
        # Общий заработок
        cursor.execute("SELECT SUM(amount) as total FROM referral_payments WHERE referrer_id = ?", (user_id,))
        total_earned = cursor.fetchone()['total'] or 0
        
        # Последние платежи
        cursor.execute("""
            SELECT rp.*, u.username, u.full_name
            FROM referral_payments rp
            JOIN users u ON rp.user_id = u.user_id
            WHERE rp.referrer_id = ?
            ORDER BY rp.payment_date DESC
            LIMIT 5
        """, (user_id,))
        recent_payments = cursor.fetchall()
        
        return {
            'total_referrals': total_referrals,
            'active_referrals': active_referrals,
            'total_earned': total_earned,
            'recent_payments': recent_payments
        }

def update_purchase_balance(user_id: int, amount: int):
    """Обновляет баланс для покупок"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()

def update_referral_balance(user_id: int, amount: int):
    """Обновляет реферальный баланс"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET referral_balance = referral_balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        conn.commit()

def transfer_referral_to_purchase_balance(user_id: int, amount: int) -> bool:
    """Переводит средства с реферального баланса на баланс покупок"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # Проверяем, достаточно ли средств на реферальном балансе
        cursor.execute("SELECT referral_balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if not result or result[0] < amount or amount <= 0:
            return False
        
        # Выполняем перевод
        cursor.execute(
            "UPDATE users SET referral_balance = referral_balance - ?, balance = balance + ? WHERE user_id = ?",
            (amount, amount, user_id)
        )
        conn.commit()
        return True