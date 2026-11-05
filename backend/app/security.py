"""Password hashing, login throttling and session tokens (standard library only)."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

from . import config

# ---------------------------------------------------------------- passwords
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=_N, r=_R, p=_P, dklen=32)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("dummy-password-for-timing")


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check, so unknown usernames can't be detected by timing."""
    verify_password(password, _DUMMY_HASH)


# ------------------------------------------------------------- login throttle
class LoginThrottle:
    """Blocks a (client, username) pair after too many failed attempts in a time window."""

    def __init__(self) -> None:
        self._fails: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > config.LOGIN_WINDOW_SECONDS:
            q.popleft()

    def retry_after(self, key: tuple[str, str]) -> int:
        """Seconds the caller must wait (0 = allowed)."""
        now = time.monotonic()
        with self._lock:
            q = self._fails[key]
            self._prune(q, now)
            if len(q) >= config.LOGIN_MAX_FAILURES:
                return int(config.LOGIN_WINDOW_SECONDS - (now - q[0])) + 1
            return 0

    def record_failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._fails[key].append(time.monotonic())

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._fails.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._fails.clear()


throttle = LoginThrottle()


# ------------------------------------------------------------------ sessions
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    # Only the hash is stored, so a leaked database can't be used to hijack sessions.
    return hashlib.sha256(token.encode()).hexdigest()
