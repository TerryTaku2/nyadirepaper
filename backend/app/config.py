"""Runtime configuration, read from environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # .../backend
STATIC_DIR = BASE_DIR.parent / "static"                    # front-end files

DATA_DIR = Path(os.getenv("NYADIRE_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "nyadire.db"
UPLOAD_DIR = DATA_DIR / "uploads"


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# Set to true when the site is served over HTTPS (strongly recommended in production).
COOKIE_SECURE = _bool("NYADIRE_COOKIE_SECURE", False)
COOKIE_NAME = "nyadire_session"

ADMIN_SESSION_HOURS = int(os.getenv("NYADIRE_ADMIN_SESSION_HOURS", "8"))
STUDENT_SESSION_HOURS = int(os.getenv("NYADIRE_STUDENT_SESSION_HOURS", "24"))

# The temporary password students use for first-time registration after an
# administrator "unregisters" them. Admins can also set an individual one per student.
REGISTRATION_PASSWORD = os.getenv("NYADIRE_REGISTRATION_PASSWORD", "1947")

MAX_PAPER_BYTES = int(os.getenv("NYADIRE_MAX_PAPER_MB", "25")) * 1024 * 1024
MAX_ANNOUNCEMENT_BYTES = int(os.getenv("NYADIRE_MAX_ANNOUNCEMENT_MB", "10")) * 1024 * 1024

# Brute-force protection: this many failed logins per (IP, username) in the window.
LOGIN_MAX_FAILURES = int(os.getenv("NYADIRE_LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("NYADIRE_LOGIN_WINDOW_SECONDS", "900"))

DEPARTMENTS = ("Natural Science", "Humanities", "P.E and Arts", "Educational Foundation")
PROGRAMMES = ("Both", "Junior", "ECD")
LEVELS = ("Level 1", "Level 2")
SEMESTERS = ("Semester 1", "Semester 2")
STUDENT_TYPES = ("Junior", "ECD")
