"""SQLite database for user management and usage tracking."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from scrape_hub.commercial.config import DB_PATH

_local = threading.local()


def _get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _init_schema(_local.conn)
    return _local.conn


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            tier TEXT NOT NULL DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            platform TEXT,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_usage_user_action_date
            ON usage_log(user_id, action, created_at);
    """)


@contextmanager
def get_db():
    """Context manager for database transactions."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
