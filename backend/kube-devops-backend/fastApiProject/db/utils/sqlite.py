# db/sqlite.py
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Callable

DB_PATH = Path(__file__).parent.parent.parent / "data"
DB_PATH.mkdir(exist_ok=True)
DB_FILE = DB_PATH / "app.db"


def get_conn() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE.as_posix(), check_same_thread=False, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


def q(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()):
    """执行单条 SQL"""
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    return cur


def qmany(conn: sqlite3.Connection, sql: str, rows: Iterable[Iterable[Any]]):
    """批量执行 SQL"""
    cur = conn.cursor()
    cur.executemany(sql, [tuple(r) for r in rows])
    return cur


def write_with_retry(op: Callable[[], Any]) -> Any:
    """写入重试：最多 3 次，退避 50/100/200ms"""
    backoffs = [0.05, 0.1, 0.2]
    for i in range(len(backoffs) + 1):
        try:
            return op()
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            if i >= len(backoffs):
                raise
            time.sleep(backoffs[i])


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    cur = q(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = q(conn, f"PRAGMA table_info({table});", ())
    return {str(r["name"]) for r in cur.fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, ddl_fragment: str) -> None:
    if col in _cols(conn, table):
        return
    q(conn, f"ALTER TABLE {table} ADD COLUMN {ddl_fragment};", ())


def init_db() -> None:
    """
    初始化/升级数据库表结构
    - heal_events : 事件流（检测/动作/验收）
    - heal_state  : deployment_uid 维度状态
    - heal_pending: pending 验收窗口
    - ops_actions : 动作审计（apply_action）
    - ops_cooldown: 冷却节流
    - ops_config  : 运行时配置（DB override）
    - clusters    : 纳管集群（多集群）
    """
    conn = get_conn()
    try:
        print(f"DB_FILE={DB_FILE.resolve()}")
        # 1) heal_events
        if not _has_table(conn, "heal_events"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS heal_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    namespace TEXT NOT NULL,
                    pod TEXT NOT NULL,
                    pod_uid TEXT NOT NULL,
                    deployment_uid TEXT NOT NULL,
                    deployment_name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    fail_count INTEGER DEFAULT 0,
                    is_failing INTEGER DEFAULT 0,
                    dry_run INTEGER DEFAULT 0
                );
                """,
            )
        else:
            c = _cols(conn, "heal_events")
            if "is_failing" not in c:
                q(conn, "ALTER TABLE heal_events ADD COLUMN is_failing INTEGER DEFAULT 0;", ())
            if "dry_run" not in c:
                q(conn, "ALTER TABLE heal_events ADD COLUMN dry_run INTEGER DEFAULT 0;", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_heal_events_ts ON heal_events(ts);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_heal_events_ns ON heal_events(namespace);", ())

        # 2) heal_state
        if not _has_table(conn, "heal_state"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS heal_state(
                    namespace TEXT NOT NULL,
                    deployment_uid TEXT NOT NULL,
                    deployment_name TEXT NOT NULL,
                    fail_count INTEGER DEFAULT 0,
                    is_failing INTEGER DEFAULT 0,
                    reason TEXT DEFAULT '',
                    updated_ts INTEGER DEFAULT 0,
                    last_replicas INTEGER DEFAULT NULL,
                    PRIMARY KEY(namespace, deployment_uid)
                );
                """,
            )

        # 3) heal_pending
        if not _has_table(conn, "heal_pending"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS heal_pending(
                    namespace TEXT NOT NULL,
                    deployment_uid TEXT NOT NULL,
                    pending INTEGER DEFAULT 0,
                    pending_until_ts INTEGER DEFAULT 0,
                    deployment_name TEXT DEFAULT '',
                    last_action TEXT DEFAULT '',
                    last_action_ts INTEGER DEFAULT 0,
                    last_pod TEXT DEFAULT '',
                    last_pod_uid TEXT DEFAULT '',
                    last_reason TEXT DEFAULT '',
                    PRIMARY KEY(namespace, deployment_uid)
                );
                """,
            )

        # 4) ops_actions
        if not _has_table(conn, "ops_actions"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ops_actions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    params TEXT NOT NULL,
                    dry_run INTEGER DEFAULT 0,
                    result TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                """,
            )

        # 5) ops_cooldown
        if not _has_table(conn, "ops_cooldown"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ops_cooldown(
                    k TEXT PRIMARY KEY,
                    ts INTEGER NOT NULL
                );
                """,
            )

        # 6) ops_config
        if not _has_table(conn, "ops_config"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ops_config(
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    updated_ts INTEGER NOT NULL
                );
                """,
            )

        # 7) clusters（✅ 新增）
        if not _has_table(conn, "clusters"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS clusters(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,          -- self-hosted / managed
                    provider TEXT DEFAULT '',    -- aliyun / tencent / huawei / custom
                    kubeconfig TEXT NOT NULL,    -- 直接存内容（后面可升级为落盘+加密）
                    is_active INTEGER DEFAULT 0,
                    created_ts INTEGER NOT NULL,
                    updated_ts INTEGER NOT NULL
                );
                """,
            )
        else:
            c = _cols(conn, "clusters")
            # 兼容升级字段（如果你之前创建过）
            if "is_active" not in c:
                q(conn, "ALTER TABLE clusters ADD COLUMN is_active INTEGER DEFAULT 0;", ())
            if "provider" not in c:
                q(conn, "ALTER TABLE clusters ADD COLUMN provider TEXT DEFAULT '';", ())

        # 8) users (✅ 新增)
        if not _has_table(conn, "users"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS users(
                    username TEXT PRIMARY KEY,
                    hashed_password TEXT NOT NULL,
                    must_change INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """,
            )
        # Ensure older columns are also present for upgrades
        else:
            _ensure_column(conn, "users", "must_change", "must_change INTEGER NOT NULL DEFAULT 0")
            _ensure_column(conn, "users", "status", "status TEXT NOT NULL DEFAULT 'active'")

        # 9) ai_feedback
        if not _has_table(conn, "ai_feedback"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ai_feedback(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    key TEXT NOT NULL,
                    suggestion_id TEXT DEFAULT '',
                    action_kind TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    detail TEXT DEFAULT ''
                );
                """,
            )

        # 9) ai_evolution
        if not _has_table(conn, "ai_evolution"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ai_evolution(
                    target TEXT NOT NULL,
                    key TEXT NOT NULL,
                    observe_ratio REAL NOT NULL,
                    trigger_ratio REAL NOT NULL,
                    sustain_minutes INTEGER NOT NULL,
                    updated_ts INTEGER NOT NULL,
                    PRIMARY KEY(target, key)
                );
                """,
            )

        # 10) ai_suggestion_state
        if not _has_table(conn, "ai_suggestion_state"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS ai_suggestion_state(
                    user TEXT NOT NULL,
                    row_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_ts INTEGER NOT NULL,
                    PRIMARY KEY(user, row_key)
                );
                """,
            )

        # 11) alerts (platform alert center)
        if not _has_table(conn, "alerts"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS alerts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    labels_json TEXT NOT NULL,
                    annotations_json TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    last_seen INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_push_status TEXT NOT NULL DEFAULT '',
                    last_push_error TEXT NOT NULL DEFAULT '',
                    last_push_at INTEGER NOT NULL DEFAULT 0
                );
                """,
            )
        else:
            c = _cols(conn, "alerts")
            if "last_push_status" not in c:
                q(conn, "ALTER TABLE alerts ADD COLUMN last_push_status TEXT NOT NULL DEFAULT '';", ())
            if "last_push_error" not in c:
                q(conn, "ALTER TABLE alerts ADD COLUMN last_push_error TEXT NOT NULL DEFAULT '';", ())
            if "last_push_at" not in c:
                q(conn, "ALTER TABLE alerts ADD COLUMN last_push_at INTEGER NOT NULL DEFAULT 0;", ())
        q(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_fp ON alerts(fingerprint);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_alerts_last_seen ON alerts(last_seen);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);", ())

        # 12) tasks
        q(
            conn,
            """
            CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                input_json TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                started_at INTEGER NOT NULL DEFAULT 0,
                finished_at INTEGER NOT NULL DEFAULT 0,
                worker_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """,
        )
        # 确保所有列都存在，无论是新创建的表还是旧表升级
        _ensure_column(conn, "tasks", "priority", "priority INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "is_cancelled", "is_cancelled INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "is_paused", "is_paused INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "max_retries", "max_retries INTEGER NOT NULL DEFAULT 3")
        _ensure_column(conn, "tasks", "retry_count", "retry_count INTEGER NOT NULL DEFAULT 0")
        # Ensure older columns are also present for upgrades
        _ensure_column(conn, "tasks", "input_json", "input_json TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "tasks", "attempts", "attempts INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "started_at", "started_at INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "finished_at", "finished_at INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tasks", "worker_id", "worker_id TEXT NOT NULL DEFAULT ''")

        q(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC);", ())
        q(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_is_cancelled ON tasks(is_cancelled);", ())

        # 13) maintenance logs
        if not _has_table(conn, "maintenance_logs"):
            q(
                conn,
                """
                CREATE TABLE IF NOT EXISTS maintenance_logs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                """,
            )

        conn.commit()
    finally:
        conn.close()
