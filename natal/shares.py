"""Private share links. Only the unguessable token travels in the URL; inputs stay in the store.

The creator receives a delete key once (stored here only as a SHA-256 hash) so sharing has a delete path.
"""
import hashlib
import hmac
import json
import re
import secrets

from . import store

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")
KINDS = {"synastry", "composite"}


def _hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_share(kind, title, payload):
    if kind not in KINDS:
        raise store.StoreError("지원하지 않는 공유 종류입니다.")
    token, delete_key = secrets.token_urlsafe(16), secrets.token_urlsafe(24)
    connection = store.connect()
    try:
        with connection:
            connection.execute("INSERT INTO shares (token, kind, title, payload, delete_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                               (token, kind, store.clean_name(title), json.dumps(payload, ensure_ascii=False, sort_keys=True),
                                _hash(delete_key), store.now_iso()))
    finally:
        connection.close()
    return token, delete_key


def get_share(token):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return None
    connection = store.connect()
    try:
        row = connection.execute("SELECT kind, title, payload, created_at FROM shares WHERE token = ?", (token,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {"kind": row["kind"], "title": row["title"], "payload": json.loads(row["payload"]), "created_at": row["created_at"]}


def delete_share(token, delete_key):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token) or not isinstance(delete_key, str) or len(delete_key) > 100:
        return False
    connection = store.connect()
    try:
        row = connection.execute("SELECT delete_hash FROM shares WHERE token = ?", (token,)).fetchone()
        if row is None or not hmac.compare_digest(row["delete_hash"], _hash(delete_key)):
            return False
        with connection:
            connection.execute("DELETE FROM shares WHERE token = ?", (token,))
        return True
    finally:
        connection.close()
