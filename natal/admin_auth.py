"""Admin password + stateless signed session cookie (`exp.hmac`), modeled on usadongne lib/admin/session.ts."""
import hashlib
import hmac
import os
import secrets
import threading
import time

COOKIE_NAME = "natal_admin"
SESSION_SECONDS = 12 * 3600
FAILURE_DELAY = 1.0
RATE_WINDOW = 15 * 60
RATE_MAX_FAILURES = 5
_PROCESS_SECRET = secrets.token_bytes(32)
_FAILURES = {}
_FAILURE_LOCK = threading.Lock()


def admin_password():
    return os.environ.get("NATAL_ADMIN_PASSWORD") or None


def is_serverless():
    """True on Vercel (the platform sets VERCEL=1 at build and run time)."""
    return bool(os.environ.get("VERCEL"))


def secret_configured():
    return bool(os.environ.get("NATAL_ADMIN_SECRET"))


def _secret():
    configured = os.environ.get("NATAL_ADMIN_SECRET")
    # Without a configured secret, sessions are valid only for this process lifetime.
    return configured.encode("utf-8") if configured else _PROCESS_SECRET


def sign(exp):
    return hmac.new(_secret(), str(exp).encode("ascii"), hashlib.sha256).hexdigest()


def issue_token(now=None):
    exp = int((now if now is not None else time.time()) + SESSION_SECONDS)
    return f"{exp}.{sign(exp)}"


def verify_token(token, now=None):
    if not token or not isinstance(token, str) or "." not in token:
        return False
    exp, signature = token.split(".", 1)
    if not exp.isdigit() or len(exp) > 12:
        return False
    if int(exp) < (now if now is not None else time.time()):
        return False
    return hmac.compare_digest(signature.encode("ascii", "replace"), sign(exp).encode("ascii"))


def check_password(candidate):
    real = admin_password()
    if not real or not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), real.encode("utf-8"))


def _key_hash(client_key):
    # Client IPs are never stored in clear; the keyed hash only groups attempts per client.
    return hmac.new(_secret(), f"login:{client_key}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _memory_rate_limited(client_key, now):
    with _FAILURE_LOCK:
        recent = [t for t in _FAILURES.get(client_key, []) if now - t < RATE_WINDOW]
        _FAILURES[client_key] = recent
        return len(recent) >= RATE_MAX_FAILURES


def rate_limited(client_key, now=None):
    """Failures in the last RATE_WINDOW, counted in the shared database (login_attempts).

    The database is shared across serverless instances; if it is unavailable the per-process
    memory counter still applies so a broken store never disables throttling.
    """
    now = now if now is not None else time.time()
    from . import store
    try:
        connection = store.connect()
        try:
            row = connection.execute("SELECT COUNT(*) AS n FROM login_attempts WHERE key_hash = ? AND attempted_at > ?",
                                     (_key_hash(client_key), now - RATE_WINDOW)).fetchone()
            return int(row["n"]) >= RATE_MAX_FAILURES or _memory_rate_limited(client_key, now)
        finally:
            connection.close()
    except Exception:
        return _memory_rate_limited(client_key, now)


def note_failure(client_key, now=None):
    now = now if now is not None else time.time()
    with _FAILURE_LOCK:
        _FAILURES.setdefault(client_key, []).append(now)
    from . import store
    try:
        connection = store.connect()
        try:
            with connection:
                connection.execute("DELETE FROM login_attempts WHERE attempted_at <= ?", (now - RATE_WINDOW,))
                connection.execute("INSERT INTO login_attempts (key_hash, attempted_at) VALUES (?, ?)", (_key_hash(client_key), now))
        finally:
            connection.close()
    except Exception:
        pass


def reset_failures(client_key=None):
    with _FAILURE_LOCK:
        if client_key is None:
            _FAILURES.clear()
        else:
            _FAILURES.pop(client_key, None)
    from . import store
    try:
        connection = store.connect()
        try:
            with connection:
                if client_key is None:
                    connection.execute("DELETE FROM login_attempts")
                else:
                    connection.execute("DELETE FROM login_attempts WHERE key_hash = ?", (_key_hash(client_key),))
        finally:
            connection.close()
    except Exception:
        pass


def session_cookie(token, secure=False):
    return f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}" + ("; Secure" if secure else "")


def clear_cookie(secure=False):
    return f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" + ("; Secure" if secure else "")


def cookie_token(cookie_header):
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value
    return None
