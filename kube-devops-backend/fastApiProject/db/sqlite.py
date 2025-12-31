# db/sqlite.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path("data")
DB_PATH.mkdir(exist_ok=True)
DB_FILE = DB_PATH / "app.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL,
      admin_user TEXT NOT NULL,
      created_at TEXT NOT NULL,
      quota_cpu TEXT NOT NULL,
      quota_mem TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenant_namespaces (
      tenant_id TEXT NOT NULL,
      namespace TEXT NOT NULL,
      PRIMARY KEY (tenant_id, namespace),
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenant_labels (
      tenant_id TEXT NOT NULL,
      k TEXT NOT NULL,
      v TEXT NOT NULL,
      PRIMARY KEY (tenant_id, k),
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      username TEXT PRIMARY KEY,
      password_hash TEXT NOT NULL,
      must_change INTEGER NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenant_members (
      tenant_id TEXT NOT NULL,
      username TEXT NOT NULL,
      email TEXT,
      role TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (tenant_id, username),
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS namespaces_registry (
      name TEXT PRIMARY KEY,
      managed INTEGER NOT NULL DEFAULT 0,
      managed_by_tenant_id TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_ns_registry_tenant ON namespaces_registry(managed_by_tenant_id);")

    conn.commit()
    conn.close()

def q(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()):
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    return cur

def qmany(conn: sqlite3.Connection, sql: str, rows: list[tuple]):
    cur = conn.cursor()
    cur.executemany(sql, rows)
    return cur