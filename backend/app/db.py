"""SQLite access, schema creation and first-run seeding."""
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager

from . import config
from .security import hash_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('ultimate', 'standard')),
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS intakes (
    number INTEGER PRIMARY KEY,
    year   INTEGER NOT NULL,
    type   TEXT NOT NULL CHECK (type IN ('ECD', 'Junior'))
);

CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    registered    INTEGER NOT NULL DEFAULT 0,       -- 0 = still on the temporary password
    intake_number INTEGER NOT NULL REFERENCES intakes(number) ON DELETE CASCADE,
    type          TEXT NOT NULL CHECK (type IN ('ECD', 'Junior')),
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_students_intake ON students(intake_number, type);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    admin_id   INTEGER REFERENCES admins(id)   ON DELETE CASCADE,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    CHECK ((admin_id IS NULL) <> (student_id IS NULL))
);

CREATE TABLE IF NOT EXISTS papers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    module_title TEXT NOT NULL,
    module_code  TEXT NOT NULL,
    level        TEXT NOT NULL,
    semester     TEXT NOT NULL,
    programme    TEXT NOT NULL CHECK (programme IN ('Both', 'Junior', 'ECD')),
    department   TEXT NOT NULL,
    subject      TEXT NOT NULL,
    exam_year    INTEGER NOT NULL,
    filename     TEXT NOT NULL,         -- original name shown to users
    stored_name  TEXT NOT NULL UNIQUE,  -- random name on disk
    size_bytes   INTEGER NOT NULL,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_department ON papers(department);

CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    pdf_name    TEXT,
    pdf_stored  TEXT,
    created_at  INTEGER NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """One connection per unit of work: commit on success, roll back on error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _env_or_random(name: str) -> tuple[str, bool]:
    value = os.getenv(name)
    if value:
        return value, False
    return secrets.token_urlsafe(12), True


def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        _seed_admins(db)
        _seed_intakes(db)


def _seed_admins(db: sqlite3.Connection) -> None:
    if db.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
        return
    ultimate_user = os.getenv("NYADIRE_ULTIMATE_USER", "superadmin")
    standard_user = os.getenv("NYADIRE_ADMIN_USER", "admin")
    ultimate_pw, u_generated = _env_or_random("NYADIRE_ULTIMATE_PASSWORD")
    standard_pw, s_generated = _env_or_random("NYADIRE_ADMIN_PASSWORD")
    now = int(time.time())
    db.execute("INSERT INTO admins(username, password_hash, role, created_at) VALUES (?,?,?,?)",
               (ultimate_user, hash_password(ultimate_pw), "ultimate", now))
    db.execute("INSERT INTO admins(username, password_hash, role, created_at) VALUES (?,?,?,?)",
               (standard_user, hash_password(standard_pw), "standard", now))

    if u_generated or s_generated:
        lines = ["Nyadire portal - initial administrator accounts",
                 "Change these passwords after your first login, then delete this file.", ""]
        lines.append(f"ultimate admin : {ultimate_user} / {ultimate_pw}" if u_generated
                     else f"ultimate admin : {ultimate_user} (password from environment)")
        lines.append(f"standard admin : {standard_user} / {standard_pw}" if s_generated
                     else f"standard admin : {standard_user} (password from environment)")
        path = config.DATA_DIR / "initial_admin_credentials.txt"
        path.write_text("\n".join(lines) + "\n")
        os.chmod(path, 0o600)
        print("\n".join(["", "=" * 60, *lines, f"(also saved to {path})", "=" * 60, ""]))


def _seed_intakes(db: sqlite3.Connection) -> None:
    """Seed the two default 2026 intakes once (an admin may delete them afterwards)."""
    if db.execute("SELECT 1 FROM meta WHERE key = 'intakes_seeded'").fetchone():
        return
    db.execute("INSERT OR IGNORE INTO intakes(number, year, type) VALUES (20, 2026, 'ECD')")
    db.execute("INSERT OR IGNORE INTO intakes(number, year, type) VALUES (31, 2026, 'Junior')")
    db.execute("INSERT INTO meta(key, value) VALUES ('intakes_seeded', '1')")
