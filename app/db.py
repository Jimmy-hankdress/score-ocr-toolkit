"""SQLite 資料層（規劃書 4.2：以 SQLite 檔案取代遠端 MySQL）。

只保存 metadata、任務狀態與檔案索引；樂譜內容本體以 project.json 保存在
專案目錄，bytes 不進資料庫（ProjectFile 設計）。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .config import PATHS
from .models import now_iso

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    lyricist    TEXT DEFAULT '',
    composer    TEXT DEFAULT '',
    key_sig     TEXT DEFAULT 'C',
    time_sig    TEXT DEFAULT '4/4',
    tempo       INTEGER DEFAULT 90,
    engine_mode TEXT DEFAULT 'manual',
    source_name TEXT DEFAULT '',
    directory   TEXT NOT NULL,
    measures    INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    source_name  TEXT NOT NULL,
    source_path  TEXT NOT NULL,
    status       TEXT NOT NULL,
    stage        TEXT NOT NULL,
    progress     INTEGER DEFAULT 0,
    message      TEXT DEFAULT '',
    error        TEXT DEFAULT '',
    engine_mode  TEXT DEFAULT '',
    pages        INTEGER DEFAULT 0,
    current_page INTEGER DEFAULT 0,
    result_path  TEXT DEFAULT '',
    project_id   TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    kind          TEXT NOT NULL,
    size          INTEGER DEFAULT 0,
    checksum      TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    UNIQUE(project_id, relative_path, kind)
);

CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
"""


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        PATHS.ensure()
        conn = sqlite3.connect(str(PATHS.db_file), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        conn.commit()
        _local.conn = conn
    return conn


def init_db() -> Path:
    connect()
    return PATHS.db_file


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def query_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(r) for r in connect().execute(sql, tuple(params)).fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    row = connect().execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


# ---------------- projects ----------------


def upsert_project(doc, directory: Path) -> None:
    execute(
        """
        INSERT INTO projects (id,title,lyricist,composer,key_sig,time_sig,tempo,
                              engine_mode,source_name,directory,measures,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, lyricist=excluded.lyricist, composer=excluded.composer,
            key_sig=excluded.key_sig, time_sig=excluded.time_sig, tempo=excluded.tempo,
            engine_mode=excluded.engine_mode, source_name=excluded.source_name,
            directory=excluded.directory, measures=excluded.measures,
            updated_at=excluded.updated_at
        """,
        (
            doc.id,
            doc.title,
            doc.lyricist,
            doc.composer,
            doc.key,
            doc.timeSignature,
            doc.tempo,
            doc.engineMode,
            doc.sourceName,
            str(directory),
            len(doc.measures),
            doc.createdAt,
            doc.updatedAt,
        ),
    )


def list_projects(limit: int = 100) -> list[dict]:
    return query_all(
        "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,)
    )


def get_project(project_id: str) -> dict | None:
    return query_one("SELECT * FROM projects WHERE id=?", (project_id,))


def delete_project(project_id: str) -> None:
    execute("DELETE FROM project_files WHERE project_id=?", (project_id,))
    execute("DELETE FROM projects WHERE id=?", (project_id,))


# ---------------- tasks ----------------


def create_task(task_id: str, source_name: str, source_path: str) -> dict:
    ts = now_iso()
    execute(
        """INSERT INTO tasks (id,source_name,source_path,status,stage,progress,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (task_id, source_name, source_path, "queued", "upload", 0, ts, ts),
    )
    return get_task(task_id)  # type: ignore[return-value]


def update_task(task_id: str, **fields) -> dict | None:
    if not fields:
        return get_task(task_id)
    allowed = {
        "status",
        "stage",
        "progress",
        "message",
        "error",
        "engine_mode",
        "pages",
        "current_page",
        "result_path",
        "project_id",
    }
    sets, values = [], []
    for k, v in fields.items():
        if k in allowed:
            if k == "project_id" and not v:
                # 若傳入空的 project_id，保留原值（失敗任務重試可能需要）
                continue
            sets.append(f"{k}=?")
            values.append(v)
    sets.append("updated_at=?")
    values.append(now_iso())
    values.append(task_id)
    execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", values)
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    return query_one("SELECT * FROM tasks WHERE id=?", (task_id,))


def list_tasks(limit: int = 30) -> list[dict]:
    return query_all("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))


def reset_orphan_tasks() -> int:
    """啟動時把上次未完成的任務標為可重試（規劃書 3. 可靠性）。"""
    cur = execute(
        """UPDATE tasks SET status='interrupted',
               error=CASE WHEN error='' THEN '上次執行被中斷，可重新開始此任務。' ELSE error END
           WHERE status IN ('queued','running')"""
    )
    return cur.rowcount or 0


# ---------------- project files ----------------


def record_file(project_id: str, relative_path: str, kind: str, size: int, checksum: str) -> None:
    execute(
        """INSERT INTO project_files (project_id,relative_path,kind,size,checksum,created_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(project_id,relative_path,kind) DO UPDATE SET
             size=excluded.size, checksum=excluded.checksum, created_at=excluded.created_at""",
        (project_id, relative_path, kind, size, checksum, now_iso()),
    )


def list_files(project_id: str) -> list[dict]:
    return query_all(
        "SELECT * FROM project_files WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    )
