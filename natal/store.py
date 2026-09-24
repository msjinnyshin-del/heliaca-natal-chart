"""Admin-only SQLite store of chart submissions (spec §12: opt-in raw input, retention, delete paths).

Raw birth input (with the name, place and positions derived from it) is stored only when the user opts in,
and is cleared after RAW_RETENTION_DAYS. Statistics columns stay. Nothing in this module logs row data.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

from .rules import SIGNS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "admin.sqlite3"
SCHEMA_VERSION = 5
RAW_RETENTION_DAYS = 180
# Columns that identify a person or reproduce their birth data; cleared on expiry, never stored without consent.
RAW_COLUMNS = ("raw_input", "display_name", "place", "summary", "fingerprint")
# `consent`: 0 = no opt-in (raw columns empty); 1 = stored under the pre-2026-09-24 notice-only policy
# (that app wrote 1 for every row, so 1 always means legacy, even if an old deploy keeps writing it);
# 2 = opted in via `client.store_consent`. Legacy rows follow the same 180-day expiry.
CONSENT_NONE, CONSENT_LEGACY, CONSENT_OPT_IN = 0, 1, 2
# Must match the partial index predicate so the per-request purge only visits rows still holding raw data.
RAW_HELD = "(raw_input IS NOT NULL OR display_name IS NOT NULL OR place IS NOT NULL OR summary IS NOT NULL OR fingerprint IS NOT NULL)"
_INIT_LOCK = threading.Lock()
_INITIALIZED = set()

VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
UTM_RE = re.compile(r"^[\w.~+\- ]{1,100}$")
SHORT_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")
NAME_MAX = 80
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩]")

MIGRATIONS = {
    1: """
    CREATE TABLE submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        visitor_id TEXT,
        display_name TEXT,
        raw_input TEXT NOT NULL,
        status TEXT NOT NULL,
        error_code TEXT,
        summary TEXT,
        place TEXT,
        sun_sign TEXT,
        moon_sign TEXT,
        asc_sign TEXT,
        fingerprint TEXT,
        consent INTEGER NOT NULL DEFAULT 0,
        utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, utm_term TEXT,
        short_code TEXT
    );
    CREATE INDEX submissions_created_at ON submissions(created_at);
    CREATE INDEX submissions_visitor ON submissions(visitor_id, created_at);
    CREATE INDEX submissions_status ON submissions(status);
    """,
    # UTM builder (admin). Clicks keep no IP and no raw User-Agent, only a coarse ua_family label.
    2: """
    CREATE TABLE utm_channels (
        key TEXT PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 64),
        label_ko TEXT NOT NULL,
        utm_source TEXT NOT NULL,
        utm_medium TEXT NOT NULL,
        note TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        sort_order INTEGER NOT NULL DEFAULT 100,
        created_at TEXT NOT NULL
    );
    CREATE TABLE utm_campaigns (
        key TEXT PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 64),
        label_ko TEXT NOT NULL,
        note TEXT,
        starts_on TEXT,
        ends_on TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL
    );
    CREATE TABLE utm_links (
        code TEXT PRIMARY KEY CHECK (length(code) = 6),
        target_path TEXT NOT NULL CHECK (
            substr(target_path, 1, 1) = '/' AND substr(target_path, 1, 2) != '//'
            AND instr(target_path, '\\') = 0 AND instr(target_path, ':') = 0 AND length(target_path) <= 200),
        channel_key TEXT REFERENCES utm_channels(key),
        campaign_key TEXT REFERENCES utm_campaigns(key),
        utm_source TEXT NOT NULL,
        utm_medium TEXT NOT NULL,
        utm_campaign TEXT NOT NULL,
        utm_content TEXT,
        memo TEXT,
        created_by TEXT,
        archived_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX utm_links_active_combo ON utm_links(target_path, utm_source, utm_medium, utm_campaign, COALESCE(utm_content, ''))
        WHERE archived_at IS NULL;
    CREATE TABLE utm_clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        clicked_at TEXT NOT NULL,
        counted INTEGER NOT NULL CHECK (counted IN (0, 1)),
        exclude_note TEXT CHECK (exclude_note IN ('head', 'preview-bot')),
        ua_family TEXT
    );
    CREATE INDEX utm_clicks_code ON utm_clicks(code, clicked_at);
    CREATE INDEX utm_clicks_at ON utm_clicks(clicked_at);
    CREATE INDEX submissions_short_code ON submissions(short_code);
    INSERT INTO utm_channels (key, label_ko, utm_source, utm_medium, sort_order, created_at)
    SELECT * FROM (VALUES
        ('instagram', '인스타그램', 'instagram', 'social', 10, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('threads', '스레드', 'threads', 'social', 20, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('kakao', '카카오톡', 'kakao', 'messenger', 30, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('naver_blog', '네이버 블로그', 'naver_blog', 'blog', 40, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('youtube', '유튜브', 'youtube', 'video', 50, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('x', 'X(트위터)', 'x', 'social', 60, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('email', '이메일', 'newsletter', 'email', 70, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        ('offline_qr', '오프라인 QR', 'offline', 'qr', 80, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')))
    WHERE NOT EXISTS (SELECT 1 FROM utm_channels);
    """,
    # Login throttling shared by every process/instance (serverless has no shared memory).
    3: """
    CREATE TABLE login_attempts (
        key_hash TEXT NOT NULL,
        attempted_at REAL NOT NULL
    );
    CREATE INDEX login_attempts_key ON login_attempts(key_hash, attempted_at);
    """,
    # User-created private share links; the token is unguessable and the delete key is stored hashed.
    4: """
    CREATE TABLE shares (
        token TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        title TEXT,
        payload TEXT NOT NULL,
        delete_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # raw_input becomes optional: without consent (or after expiry) only statistics columns are kept.
    # One explicit transaction: executescript() autocommits otherwise, and a crash after DROP would lose the table.
    # Existing consent=1 rows keep meaning legacy; AUTOINCREMENT's high-water mark is carried over.
    5: """
    BEGIN;
    CREATE TABLE submissions_v5 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        visitor_id TEXT,
        display_name TEXT,
        raw_input TEXT,
        status TEXT NOT NULL,
        error_code TEXT,
        summary TEXT,
        place TEXT,
        sun_sign TEXT,
        moon_sign TEXT,
        asc_sign TEXT,
        fingerprint TEXT,
        consent INTEGER NOT NULL DEFAULT 0,
        utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, utm_content TEXT, utm_term TEXT,
        short_code TEXT
    );
    INSERT INTO submissions_v5 SELECT id, created_at, visitor_id, display_name, raw_input, status, error_code, summary,
        place, sun_sign, moon_sign, asc_sign, fingerprint, consent,
        utm_source, utm_medium, utm_campaign, utm_content, utm_term, short_code FROM submissions;
    INSERT INTO sqlite_sequence (name, seq)
        SELECT 'submissions_v5', 0 WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'submissions_v5');
    UPDATE sqlite_sequence SET seq = max(seq, COALESCE((SELECT seq FROM sqlite_sequence WHERE name = 'submissions'), 0))
        WHERE name = 'submissions_v5';
    DROP TABLE submissions;
    ALTER TABLE submissions_v5 RENAME TO submissions;
    CREATE INDEX submissions_created_at ON submissions(created_at);
    CREATE INDEX submissions_visitor ON submissions(visitor_id, created_at);
    CREATE INDEX submissions_status ON submissions(status);
    CREATE INDEX submissions_short_code ON submissions(short_code);
    CREATE INDEX submissions_raw_held ON submissions(created_at) WHERE raw_input IS NOT NULL OR display_name IS NOT NULL OR place IS NOT NULL OR summary IS NOT NULL OR fingerprint IS NOT NULL;
    PRAGMA user_version = 5;
    COMMIT;
    """,
}


class StoreError(ValueError):
    pass


def database_url():
    """Postgres when DATABASE_URL (Neon pooled URL on Vercel) or POSTGRES_URL is set; otherwise local SQLite.

    The URL is passed through untouched, so Neon's `sslmode=require` stays in effect.
    """
    return os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or None


def is_postgres():
    return database_url() is not None


def integrity_errors():
    errors = (sqlite3.IntegrityError,)
    if is_postgres():
        import psycopg
        errors += (psycopg.IntegrityError,)
    return errors


def _to_pyformat(sql):
    """`?` placeholders -> `%s` outside string literals; literal `%` is doubled for psycopg."""
    out, quoted = [], False
    for char in sql:
        if char == "'":
            quoted = not quoted
        if char == "%":
            out.append("%%")
        elif char == "?" and not quoted:
            out.append("%s")
        else:
            out.append(char)
    # SQLite LIKE is ASCII case-insensitive; keep that behaviour on Postgres.
    return "".join(out).replace(" LIKE ", " ILIKE ")


class PostgresConnection:
    """Tiny adapter giving psycopg the subset of the sqlite3 connection API this app uses.

    Autocommit is on; `with connection:` wraps the block in one transaction (commit / rollback),
    matching sqlite3's context-manager semantics. Rows are dicts, so `row["col"]` and `dict(row)` work.
    """

    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        # Neon's pooled URL is PgBouncer in transaction mode: no server-side prepared statements.
        self._conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, prepare_threshold=None,
                                     connect_timeout=5)
        self._tx = []

    def execute(self, sql, params=()):
        return self._conn.execute(_to_pyformat(sql), list(params))

    def __enter__(self):
        tx = self._conn.transaction()
        tx.__enter__()
        self._tx.append(tx)
        return self

    def __exit__(self, *exc):
        return self._tx.pop().__exit__(*exc)

    def close(self):
        self._conn.close()


def dialect(sqlite_sql, postgres_sql):
    return postgres_sql if is_postgres() else sqlite_sql


def db_path():
    return Path(os.environ.get("NATAL_DB_PATH") or DEFAULT_DB_PATH)


def connect():
    """SQLite connection (local/dev/tests) or a PostgresConnection when DATABASE_URL / POSTGRES_URL is set.

    Postgres schema is applied manually from db/schema.sql — never migrated at request time.
    """
    if is_postgres():
        return PostgresConnection(database_url())
    path = db_path()
    connection = sqlite3.connect(str(path), timeout=5)
    connection.row_factory = sqlite3.Row
    # Deleted rows are overwritten on disk so the delete path really removes birth data.
    connection.execute("PRAGMA secure_delete = ON")
    key = str(path.resolve())
    if key not in _INITIALIZED:
        with _INIT_LOCK:
            if key not in _INITIALIZED:
                migrate(connection)
                _INITIALIZED.add(key)
    return connection


def migrate(connection):
    connection.execute("PRAGMA journal_mode=WAL")
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    for version in sorted(MIGRATIONS):
        if version > current:
            try:
                with connection:
                    connection.executescript(MIGRATIONS[version])
                    connection.execute(f"PRAGMA user_version = {int(version)}")
            except Exception:
                if connection.in_transaction:  # a self-managed BEGIN ... COMMIT script that failed midway
                    connection.rollback()
                raise


# ---- validation -----------------------------------------------------------

def clean_visitor_id(value):
    return value if isinstance(value, str) and VISITOR_RE.fullmatch(value) else None


def clean_name(value):
    if not isinstance(value, str):
        return None
    text = CONTROL_RE.sub("", value).strip()[:NAME_MAX].strip()
    return text or None


def clean_utm(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if UTM_RE.fullmatch(text) else None


def clean_client(client):
    """Normalize the optional `client` object; invalid parts are dropped, never fatal."""
    client = client if isinstance(client, dict) else {}
    utm = client.get("utm") if isinstance(client.get("utm"), dict) else {}
    short_code = client.get("short_code")
    return {
        "visitor_id": clean_visitor_id(client.get("visitor_id")),
        "display_name": clean_name(client.get("name")),
        # Only the opt-in checkbox field counts; the old always-true `consent` field is ignored.
        "consent": client.get("store_consent") is True,
        **{key: clean_utm(utm.get(key)) for key in UTM_KEYS},
        "short_code": short_code if isinstance(short_code, str) and SHORT_CODE_RE.fullmatch(short_code) else None,
    }


def summarize(result):
    bodies = {item["id"]: item for item in result.get("bodies", [])}
    angles = {item["id"]: item for item in result.get("angles", [])}
    accuracy = (result.get("normalized") or {}).get("time_accuracy", "reported")
    unknown = accuracy == "unknown"

    def certain(item):
        # Unknown birth time: a sign that changes during the day is not a fact about this person.
        return item and (not unknown or (item.get("time_sensitivity") or {}).get("sign_stable") is True)

    def sign(item):
        return SIGNS[item["sign_index"]] if certain(item) and isinstance(item.get("sign_index"), int) else None

    return {
        "sun": sign(bodies.get("Sun")), "moon": sign(bodies.get("Moon")), "asc": sign(angles.get("ASC")),
        "sun_position": None if unknown else (bodies.get("Sun") or {}).get("position"),
        "moon_position": None if unknown else (bodies.get("Moon") or {}).get("position"),
        "asc_position": (angles.get("ASC") or {}).get("position"),
        "sect": result.get("sect"), "calculation_status": result.get("calculation_status"),
        "time_accuracy": accuracy,
        "utc": None if unknown else (result.get("normalized") or {}).get("utc"),
        "fingerprint": (result.get("metadata") or {}).get("input_fingerprint"),
    }


def utc_now():
    return datetime.now(timezone.utc)


def now_iso():
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def retention_cutoff():
    return (utc_now() - timedelta(days=RAW_RETENTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _purge(connection):
    cleared = ", ".join(f"{column} = NULL" for column in RAW_COLUMNS)
    with connection:
        return connection.execute(f"UPDATE submissions SET {cleared} WHERE created_at < ? AND {RAW_HELD}",
                                  (retention_cutoff(),)).rowcount


def purge_expired():
    """Clear raw columns of rows older than the retention period; statistics columns remain."""
    connection = connect()
    try:
        return _purge(connection)
    finally:
        connection.close()


def record_submission(raw_input, client, result=None, error_code=None):
    info = clean_client(client)
    summary = summarize(result) if result is not None else None
    place = raw_input.get("place") if isinstance(raw_input.get("place"), str) else None
    row = {
        "created_at": now_iso(), "visitor_id": info["visitor_id"], "display_name": info["display_name"],
        "raw_input": json.dumps(raw_input, ensure_ascii=False, sort_keys=True),
        "status": "success" if result is not None else (error_code or "UNKNOWN_ERROR"),
        "error_code": None if result is not None else (error_code or "UNKNOWN_ERROR"),
        "summary": json.dumps(summary, ensure_ascii=False) if summary else None,
        "place": clean_name(place) if place else None,
        "sun_sign": summary and summary["sun"], "moon_sign": summary and summary["moon"], "asc_sign": summary and summary["asc"],
        "fingerprint": summary and summary["fingerprint"], "consent": CONSENT_OPT_IN if info["consent"] else CONSENT_NONE,
        **{key: info[key] for key in UTM_KEYS}, "short_code": info["short_code"],
    }
    if not info["consent"]:
        row.update(dict.fromkeys(RAW_COLUMNS))
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    connection = connect()
    try:
        # Serverless has no scheduler, so each write also enforces retention (indexed on created_at).
        _purge(connection)
        with connection:
            if is_postgres():
                return connection.execute(f"INSERT INTO submissions ({columns}) VALUES ({marks}) RETURNING id",
                                          list(row.values())).fetchone()["id"]
            cursor = connection.execute(f"INSERT INTO submissions ({columns}) VALUES ({marks})", list(row.values()))
        return cursor.lastrowid
    finally:
        connection.close()


# ---- queries --------------------------------------------------------------

def parse_range(date_from=None, date_to=None):
    """Inclusive UTC day range -> [start, end) ISO strings. Invalid dates raise StoreError."""
    clauses, params = [], []
    for value, op in ((date_from, ">="), (date_to, "<")):
        if value in (None, ""):
            continue
        if not isinstance(value, str) or not DATE_RE.fullmatch(value):
            raise StoreError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
        try:
            day = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise StoreError("존재하지 않는 날짜입니다.") from None
        if op == "<":
            day += timedelta(days=1)
        clauses.append(f"created_at {op} ?")
        params.append(day.strftime("%Y-%m-%dT00:00:00Z"))
    return clauses, params


def like(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def where(clauses):
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


def stats(date_from=None, date_to=None):
    clauses, params = parse_range(date_from, date_to)
    base = where(clauses)
    ok = where(clauses + ["status = 'success'"])
    connection = connect()
    try:
        _purge(connection)
        q = lambda sql, extra=(): [dict(r) for r in connection.execute(sql, [*params, *extra]).fetchall()]
        totals = q(f"""SELECT COUNT(*) AS submissions,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                        SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failed,
                        COUNT(DISTINCT visitor_id) AS unique_visitors,
                        COUNT(DISTINCT display_name) AS unique_names
                       FROM submissions{base}""")[0]
        totals = {k: int(v or 0) for k, v in totals.items()}

        def group(column, source=base, limit=None):
            sql = (f"SELECT {column} AS key, COUNT(*) AS count FROM submissions{source} "
                   f"GROUP BY {column} ORDER BY count DESC, key")
            return q(sql + (f" LIMIT {int(limit)}" if limit else ""))

        return {
            "range": {"from": date_from or None, "to": date_to or None},
            "totals": totals,
            "daily": q(f"""SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total,
                           SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success, SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS failed
                           FROM submissions{base} GROUP BY day ORDER BY day"""),
            "by_status": group("status"),
            "top_places": group("place", where(clauses + ["place IS NOT NULL"]), 10),
            "signs": {"sun": group("sun_sign", ok), "moon": group("moon_sign", ok), "asc": group("asc_sign", ok)},
            "utm": {"source": group("utm_source"), "campaign": group("utm_campaign")},
        }
    finally:
        connection.close()


def users(date_from=None, date_to=None, q=None, limit=200):
    clauses, params = parse_range(date_from, date_to)
    clauses.append("visitor_id IS NOT NULL")
    if q:
        clauses.append("(visitor_id LIKE ? ESCAPE '\\' OR display_name LIKE ? ESCAPE '\\')")
        params += [like(q), like(q)]
    connection = connect()
    try:
        _purge(connection)
        rows = connection.execute(f"""
            SELECT s.visitor_id, COUNT(*) AS count, MIN(s.created_at) AS first_seen, MAX(s.created_at) AS last_seen,
                   SUM(CASE WHEN s.status = 'success' THEN 1 ELSE 0 END) AS success,
                   {dialect("json_group_array(DISTINCT s.display_name)", "json_agg(DISTINCT s.display_name)::text")} AS names,
                   (SELECT display_name FROM submissions t WHERE t.visitor_id = s.visitor_id AND t.display_name IS NOT NULL
                    ORDER BY t.created_at DESC, t.id DESC LIMIT 1) AS latest_name
            FROM submissions s{where(clauses)}
            GROUP BY s.visitor_id ORDER BY last_seen DESC LIMIT ?""", [*params, int(limit)]).fetchall()
        anonymous = connection.execute(
            f"SELECT COUNT(*) AS n FROM submissions{where(parse_range(date_from, date_to)[0] + ['visitor_id IS NULL'])}",
            parse_range(date_from, date_to)[1]).fetchone()["n"]
        result = []
        for row in rows:
            item = dict(row)
            item["names"] = sorted(name for name in json.loads(item["names"]) if name)
            result.append(item)
        return {"users": result, "anonymous_submissions": anonymous}
    finally:
        connection.close()


LIST_COLUMNS = ("id, created_at, visitor_id, display_name, status, error_code, place, sun_sign, moon_sign, asc_sign, "
                "consent, utm_source, utm_medium, utm_campaign, utm_content, utm_term, short_code")


def list_submissions(visitor_id=None, q=None, status=None, date_from=None, date_to=None, limit=50, offset=0):
    clauses, params = parse_range(date_from, date_to)
    if visitor_id:
        if not clean_visitor_id(visitor_id):
            raise StoreError("visitor_id 형식이 올바르지 않습니다.")
        clauses.append("visitor_id = ?")
        params.append(visitor_id)
    if q:
        clauses.append("(display_name LIKE ? ESCAPE '\\' OR place LIKE ? ESCAPE '\\')")
        params += [like(q), like(q)]
    if status == "failed":
        clauses.append("status != 'success'")
    elif status:
        if not re.fullmatch(r"[A-Za-z_]{1,64}", status):
            raise StoreError("status 형식이 올바르지 않습니다.")
        clauses.append("status = ?")
        params.append(status)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    connection = connect()
    try:
        _purge(connection)
        total = connection.execute(f"SELECT COUNT(*) AS n FROM submissions{where(clauses)}", params).fetchone()["n"]
        rows = connection.execute(f"SELECT {LIST_COLUMNS} FROM submissions{where(clauses)} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                                  [*params, limit, offset]).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "submissions": [dict(r) for r in rows]}
    finally:
        connection.close()


def get_submission(submission_id):
    connection = connect()
    try:
        _purge(connection)
        row = connection.execute(f"SELECT {LIST_COLUMNS}, raw_input, summary, fingerprint FROM submissions WHERE id = ?",
                                 (int(submission_id),)).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    item = dict(row)
    item["raw_input"] = json.loads(item["raw_input"]) if item["raw_input"] else None
    item["summary"] = json.loads(item["summary"]) if item["summary"] else None
    return item


def delete_submission(submission_id):
    connection = connect()
    try:
        with connection:
            return connection.execute("DELETE FROM submissions WHERE id = ?", (int(submission_id),)).rowcount
    finally:
        connection.close()


def delete_visitor(visitor_id):
    if not clean_visitor_id(visitor_id):
        raise StoreError("visitor_id 형식이 올바르지 않습니다.")
    connection = connect()
    try:
        with connection:
            return connection.execute("DELETE FROM submissions WHERE visitor_id = ?", (visitor_id,)).rowcount
    finally:
        connection.close()
