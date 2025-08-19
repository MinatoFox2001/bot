import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional

DATABASE_NAME = "users.db"

def init_error_log_table():
    """Создает таблицу для логирования ошибок"""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                traceback TEXT,
                user_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def log_error(error_type: str, error_message: str, traceback: str = None, user_id: int = None):
    """Логирует ошибку в базу данных"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO error_logs (error_type, error_message, traceback, user_id)
                VALUES (?, ?, ?, ?)
            """, (error_type, error_message, traceback, user_id))
            conn.commit()
    except Exception as e:
        # В случае ошибки логирования, просто выводим в консоль
        print(f"Ошибка логирования: {e}")

def get_recent_errors(limit: int = 50) -> List[Dict]:
    """Получает последние ошибки из базы данных"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            conn.row_factory = lambda cursor, row: {
                'id': row[0],
                'error_type': row[1],
                'error_message': row[2],
                'traceback': row[3],
                'user_id': row[4],
                'timestamp': row[5]
            }
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, error_type, error_message, traceback, user_id, timestamp
                FROM error_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
    except Exception:
        return []

def clear_error_logs():
    """Очищает все записи об ошибках"""
    try:
        with sqlite3.connect(DATABASE_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM error_logs")
            conn.commit()
            return True
    except Exception:
        return False

# Инициализируем таблицу при запуске
init_error_log_table()