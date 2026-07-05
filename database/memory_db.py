import json
import os
import time
from typing import List, Dict, Any, Optional

from config import settings
from core.logger import setup_logger

logger = setup_logger("Database")


class DatabaseBackend:
    def save_message(self, session_id: str, role: str, content: str) -> None: ...
    def get_history(self, session_id: str, limit: int = 15) -> List[Dict[str, str]]: ...
    def save_metadata(self, key: str, value: Any) -> None: ...
    def get_metadata(self, key: str) -> Optional[Any]: ...
    def cleanup_old_sessions(self, keep_days: int = 30) -> int: ...


class SQLiteBackend(DatabaseBackend):
    def __init__(self) -> None:
        import sqlite3
        from config import DB_PATH
        self.db_path = DB_PATH
        self._init_db()

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db_path), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS metadata_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_history_session ON history(session_id, id);
            """)

    def save_message(self, session_id: str, role: str, content: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO history (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()

    def get_history(self, session_id: str, limit: int = 15) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT role, content FROM history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def save_metadata(self, key: str, value: Any) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata_store (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
            conn.commit()

    def get_metadata(self, key: str) -> Optional[Any]:
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT value FROM metadata_store WHERE key = ?", (key,))
            row = cursor.fetchone()
            return json.loads(row["value"]) if row else None

    def cleanup_old_sessions(self, keep_days: int = 30) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM history WHERE timestamp < datetime('now', ?)",
                (f"-{keep_days} days",)
            )
            conn.commit()
            return cursor.rowcount


class PostgreSQLBackend(DatabaseBackend):
    def __init__(self, database_url: str) -> None:
        import psycopg2
        self.database_url = database_url
        self._conn = psycopg2.connect(database_url)
        self._conn.autocommit = True
        self._init_db()

    def _get_conn(self):
        import psycopg2
        try:
            if self._conn.closed:
                self._conn = psycopg2.connect(self.database_url)
                self._conn.autocommit = True
        except AttributeError:
            pass
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS metadata_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_session
                ON history(session_id, id)
            """)
        conn.commit()

    def save_message(self, session_id: str, role: str, content: str) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO history (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content)
            )
        conn.commit()

    def get_history(self, session_id: str, limit: int = 15) -> List[Dict[str, str]]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM history WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                (session_id, limit)
            )
            rows = cur.fetchall()
            result = []
            for row in reversed(rows):
                result.append({"role": row[0], "content": row[1]})
            return result

    def save_metadata(self, key: str, value: Any) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO metadata_store (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, json.dumps(value))
            )
        conn.commit()

    def get_metadata(self, key: str) -> Optional[Any]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM metadata_store WHERE key = %s", (key,))
            row = cur.fetchone()
            return json.loads(row[0]) if row else None

    def cleanup_old_sessions(self, keep_days: int = 30) -> int:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM history WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL %s",
                (f"{keep_days} days",)
            )
            count = cur.rowcount
        conn.commit()
        return count


def _create_backend() -> DatabaseBackend:
    database_url = settings.DATABASE_URL
    if database_url and database_url.startswith("postgres"):
        logger.info("Usando PostgreSQL como backend de banco de dados")
        return PostgreSQLBackend(database_url)
    logger.info("Usando SQLite como backend de banco de dados")
    return SQLiteBackend()


db = _create_backend()
