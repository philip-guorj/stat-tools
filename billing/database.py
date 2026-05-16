# billing/database.py - SQLite 数据库初始化与连接管理
"""
独立 SQLite 文件 billing.db，与现有系统完全分离。
线程安全：使用 threading.Lock 防止并发写入冲突。
"""

import sqlite3
import threading
import os

# 数据库文件路径（与主入口文件同目录）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "billing.db")

# 线程锁，防止并发写入
_db_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    """获取数据库连接，启用 WAL 模式提升并发性能"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构（幂等操作，可重复调用）"""
    with _db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    nickname TEXT DEFAULT '',
                    organization TEXT DEFAULT '',
                    free_quota INTEGER DEFAULT 100,
                    paid_quota INTEGER DEFAULT 0,
                    role TEXT DEFAULT 'user',
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    last_login TEXT
                );

                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS redeem_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    amount INTEGER NOT NULL,
                    status TEXT DEFAULT 'unused',
                    created_by INTEGER,
                    used_by INTEGER,
                    used_at TEXT,
                    batch_id TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS billing_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    analysis_type TEXT NOT NULL,
                    params_hash TEXT NOT NULL,
                    quota_used INTEGER DEFAULT 1,
                    quota_type TEXT DEFAULT 'free',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    last_active_at TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS recharge_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    quota_requested INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    remark TEXT DEFAULT '',
                    admin_note TEXT DEFAULT '',
                    processed_by INTEGER,
                    processed_at TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                -- 索引
                CREATE INDEX IF NOT EXISTS idx_billing_logs_user ON billing_logs(user_id);
                CREATE INDEX IF NOT EXISTS idx_billing_logs_hash ON billing_logs(params_hash, created_at);
                CREATE INDEX IF NOT EXISTS idx_billing_logs_created ON billing_logs(created_at);
                CREATE INDEX IF NOT EXISTS idx_redeem_codes_code ON redeem_codes(code);
                CREATE INDEX IF NOT EXISTS idx_redeem_codes_status ON redeem_codes(status);
                CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token);
                CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_recharge_requests_user ON recharge_requests(user_id);
                CREATE INDEX IF NOT EXISTS idx_recharge_requests_status ON recharge_requests(status);
            """)

            # 预置系统设置
            defaults = [
                ('new_user_free_quota', '100'),
                ('token_expire_hours', '72'),
                ('session_expire_hours', '72'),
            ]
            for key, value in defaults:
                cursor.execute(
                    "INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)",
                    (key, value)
                )

            conn.commit()
        finally:
            conn.close()

    # ---- 迁移：为旧数据库补充缺失字段 ----
    _migrate_add_columns('users', {
        'organization': "TEXT DEFAULT ''",
    })


def execute_query(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """执行写操作（带线程锁）"""
    with _db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor
        finally:
            conn.close()


def fetch_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    """查询单条记录"""
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """查询多条记录"""
    conn = get_connection()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _migrate_add_columns(table: str, columns: dict[str, str]):
    """安全迁移：为已有表添加缺失的列（幂等）"""
    with _db_lock:
        conn = get_connection()
        try:
            # 获取现有列名
            cursor = conn.execute(f"PRAGMA table_info({table})")
            existing = {row['name'] for row in cursor.fetchall()}
            for col_name, col_def in columns.items():
                if col_name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
            conn.commit()
        finally:
            conn.close()


# 模块加载时自动初始化数据库
init_db()
