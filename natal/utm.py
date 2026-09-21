"""UTM builder: short codes, path-only targets, preview-bot detection and the admin ledger.

Clicks never store an IP address or a raw User-Agent — only a coarse `ua_family` label.
"""
import re
import secrets
from urllib.parse import urlencode

from . import store
from .store import StoreError, now_iso, where

# l, o, 0 and 1 are excluded so a code copied by hand cannot be misread.
ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
CODE_LENGTH = 6
CODE_RE = re.compile(f"^[{ALPHABET}]{{{CODE_LENGTH}}}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PATH_RE = re.compile(r"^/[A-Za-z0-9\-._~/]*$")
RESERVED_PREFIXES = ("/admin", "/api", "/l/")
TARGET_MAX = 200
UNKNOWN_TARGET = "/?" + urlencode({"utm_source": "short-link", "utm_medium": "unknown"})
MAX_CODE_ATTEMPTS = 8


def make_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def is_code_shaped(code):
    return isinstance(code, str) and bool(CODE_RE.fullmatch(code))


def normalize_target_path(value):
    """Path-only destination or None. Absolute, protocol-relative and scheme URLs can never be built."""
    if not isinstance(value, str):
        return None
    path = value.strip()
    if not path or len(path) > TARGET_MAX or not path.startswith("/") or path.startswith("//"):
        return None
    if not PATH_RE.fullmatch(path) or ".." in path:
        return None
    if any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/") for prefix in RESERVED_PREFIXES):
        return None
    return path


def build_target(path, utm_source, utm_medium, utm_campaign, utm_content=None, code=None):
    params = {"utm_source": utm_source, "utm_medium": utm_medium, "utm_campaign": utm_campaign}
    if utm_content:
        params["utm_content"] = utm_content
    if code:
        params["sc"] = code
    return f"{path}?{urlencode(params)}"


# ---- user agent -------------------------------------------------------------

PREVIEW_BOTS = [
    (r"facebookexternalhit|facebookcatalog|facebot", "facebook"),
    (r"kakaotalk-scrap|kakaostory-og-reader", "kakao-scrap"),
    (r"slackbot|slack-imgproxy", "slack"),
    (r"twitterbot", "twitter"),
    (r"discordbot", "discord"),
    (r"telegrambot", "telegram"),
    (r"whatsapp", "whatsapp"),
    (r"skypeuripreview|bingpreview", "microsoft"),
    (r"redditbot|pinterest|embedly|vkshare", "social-scrap"),
    (r"googlebot|bingbot|yeti|daum|naverbot|duckduckbot|applebot|petalbot", "crawler"),
    (r"\bbot\b|crawler|spider|curl/|wget/|python-requests|python-urllib|axios/|node-fetch|headlesschrome", "generic-bot"),
]
IN_APP = [
    (r"kakaotalk", "kakaotalk-inapp"),
    (r"naver\(inapp|naver ?whale", "naver-inapp"),
    (r"instagram", "instagram-inapp"),
    (r"threads|barcelona", "threads-inapp"),
    (r"fbav|fban|fb_iab", "facebook-inapp"),
]


def read_ua(ua):
    """(is_bot, family). The raw UA string is used only here and never stored."""
    if not ua:
        return True, "no-ua"
    for pattern, family in PREVIEW_BOTS:
        if re.search(pattern, ua, re.I):
            return True, family
    for pattern, family in IN_APP:
        if re.search(pattern, ua, re.I):
            return False, family
    return False, None


# ---- validation ---------------------------------------------------------------

def slug(value, field, required=True):
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value.strip()):
        raise StoreError(f"{field}: 영문 소문자·숫자·-·_ 만 사용할 수 있습니다 (최대 64자).")
    return value.strip()


def text(value, limit, field=None, required=False):
    cleaned = None
    if value not in (None, ""):
        if not isinstance(value, str):
            raise StoreError(f"{field or '값'}은(는) 문자열이어야 합니다.")
        cleaned = store.CONTROL_RE.sub("", value).strip()[:limit].strip() or None
    if required and not cleaned:
        raise StoreError(f"{field}을(를) 입력해 주세요.")
    return cleaned


def day(value, field):
    if value in (None, ""):
        return None
    store.parse_range(value, None)  # validates YYYY-MM-DD
    return value


# ---- channels & campaigns ------------------------------------------------------

def list_channels():
    connection = store.connect()
    try:
        rows = connection.execute("SELECT * FROM utm_channels ORDER BY is_active DESC, sort_order, key").fetchall()
        return {"channels": [dict(r) for r in rows]}
    finally:
        connection.close()


def list_campaigns():
    connection = store.connect()
    try:
        rows = connection.execute("SELECT * FROM utm_campaigns ORDER BY is_active DESC, created_at DESC, key").fetchall()
        return {"campaigns": [dict(r) for r in rows]}
    finally:
        connection.close()


def _channel_fields(payload, partial):
    fields = {}
    if not partial or "label_ko" in payload:
        fields["label_ko"] = text(payload.get("label_ko"), 40, "채널 이름", required=True)
    for key in ("utm_source", "utm_medium"):
        if not partial or key in payload:
            fields[key] = slug(payload.get(key), key)
    if "note" in payload:
        fields["note"] = text(payload.get("note"), 200)
    if "sort_order" in payload:
        order = payload.get("sort_order")
        if not isinstance(order, int) or isinstance(order, bool) or not -10_000 <= order <= 10_000:
            raise StoreError("sort_order는 정수여야 합니다.")
        fields["sort_order"] = order
    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise StoreError("is_active는 true/false여야 합니다.")
        fields["is_active"] = int(payload["is_active"])
    return fields


def _campaign_fields(payload, partial):
    fields = {}
    if not partial or "label_ko" in payload:
        fields["label_ko"] = text(payload.get("label_ko"), 60, "캠페인 이름", required=True)
    if "note" in payload:
        fields["note"] = text(payload.get("note"), 200)
    for key in ("starts_on", "ends_on"):
        if key in payload:
            fields[key] = day(payload.get(key), key)
    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise StoreError("is_active는 true/false여야 합니다.")
        fields["is_active"] = int(payload["is_active"])
    return fields


def _insert(table, row, duplicate_message):
    connection = store.connect()
    try:
        with connection:
            connection.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    except store.integrity_errors():
        raise StoreError(duplicate_message) from None
    finally:
        connection.close()


def _update(table, key, fields):
    if not fields:
        raise StoreError("변경할 항목이 없습니다.")
    connection = store.connect()
    try:
        with connection:
            return connection.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in fields)} WHERE key = ?",
                                      [*fields.values(), key]).rowcount
    finally:
        connection.close()


def create_channel(payload):
    row = {"key": slug(payload.get("key"), "key"), **_channel_fields(payload, partial=False), "created_at": now_iso()}
    row.setdefault("is_active", 1)
    _insert("utm_channels", row, "같은 key의 채널이 이미 있습니다.")
    return row


def update_channel(key, payload):
    return _update("utm_channels", slug(key, "key"), _channel_fields(payload, partial=True))


def create_campaign(payload):
    row = {"key": slug(payload.get("key"), "key"), **_campaign_fields(payload, partial=False), "created_at": now_iso()}
    row.setdefault("is_active", 1)
    if row.get("starts_on") and row.get("ends_on") and row["ends_on"] < row["starts_on"]:
        raise StoreError("종료일이 시작일보다 빠릅니다.")
    _insert("utm_campaigns", row, "같은 key의 캠페인이 이미 있습니다.")
    return row


def update_campaign(key, payload):
    return _update("utm_campaigns", slug(key, "key"), _campaign_fields(payload, partial=True))


# ---- links -------------------------------------------------------------------------

LINK_COLUMNS = ("code, target_path, channel_key, campaign_key, utm_source, utm_medium, utm_campaign, utm_content, "
                "memo, created_by, archived_at, created_at")


def _link_view(row):
    item = dict(row)
    item["short_path"] = f"/l/{item['code']}"
    item["full_path"] = build_target(item["target_path"], item["utm_source"], item["utm_medium"], item["utm_campaign"],
                                     item["utm_content"])
    return item


def create_links(payload):
    """One link per selected channel. An existing active identical combo returns its code (`existed`)."""
    target = normalize_target_path(payload.get("target_path"))
    if not target:
        raise StoreError("목적지는 /로 시작하는 사이트 내부 경로만 가능합니다 (외부 URL·//·\\·:·.. 불가, /admin·/api·/l 제외).")
    channel_keys = payload.get("channel_keys")
    if not isinstance(channel_keys, list) or not channel_keys or len(channel_keys) > 30:
        raise StoreError("채널을 1개 이상 선택해 주세요.")
    channel_keys = list(dict.fromkeys(slug(k, "channel") for k in channel_keys))
    campaign_key = slug(payload.get("campaign_key"), "campaign")
    content = slug(payload.get("utm_content"), "utm_content", required=False)
    source_override = slug(payload.get("utm_source_override"), "utm_source", required=False)
    medium_override = slug(payload.get("utm_medium_override"), "utm_medium", required=False)
    if (source_override or medium_override) and len(channel_keys) != 1:
        raise StoreError("source/medium 직접 지정은 채널을 하나만 선택했을 때만 쓸 수 있습니다.")
    memo = text(payload.get("memo"), 200)
    created_by = text(payload.get("created_by"), 40)

    connection = store.connect()
    try:
        campaign = connection.execute("SELECT key FROM utm_campaigns WHERE key = ? AND is_active = 1", (campaign_key,)).fetchone()
        if not campaign:
            raise StoreError("활성 캠페인을 선택해 주세요.")
        results = []
        for channel_key in channel_keys:
            channel = connection.execute("SELECT * FROM utm_channels WHERE key = ? AND is_active = 1", (channel_key,)).fetchone()
            if not channel:
                raise StoreError(f"활성 채널이 아닙니다: {channel_key}")
            combo = (target, source_override or channel["utm_source"], medium_override or channel["utm_medium"], campaign_key, content or "")
            find = ("SELECT " + LINK_COLUMNS + " FROM utm_links WHERE archived_at IS NULL AND target_path = ? AND utm_source = ? "
                    "AND utm_medium = ? AND utm_campaign = ? AND COALESCE(utm_content, '') = ?")
            existing = connection.execute(find, combo).fetchone()
            if existing:
                results.append({**_link_view(existing), "existed": True})
                continue
            for _ in range(MAX_CODE_ATTEMPTS):
                code = make_code()
                try:
                    with connection:
                        connection.execute(
                            "INSERT INTO utm_links (code, target_path, channel_key, campaign_key, utm_source, utm_medium, utm_campaign, "
                            "utm_content, memo, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (code, target, channel_key, campaign_key, combo[1], combo[2], campaign_key, content, memo, created_by, now_iso()))
                    break
                except store.integrity_errors():
                    raced = connection.execute(find, combo).fetchone()
                    if raced:  # a concurrent request created the same combo
                        code = raced["code"]
                        break
            else:
                raise StoreError("단축코드를 만들지 못했습니다. 다시 시도해 주세요.")
            row = connection.execute(f"SELECT {LINK_COLUMNS} FROM utm_links WHERE code = ?", (code,)).fetchone()
            results.append({**_link_view(row), "existed": False})
        return {"links": results}
    finally:
        connection.close()


def set_archived(code, archived):
    if not is_code_shaped(code):
        raise StoreError("단축코드 형식이 올바르지 않습니다.")
    connection = store.connect()
    try:
        with connection:
            if archived:
                return connection.execute("UPDATE utm_links SET archived_at = ? WHERE code = ? AND archived_at IS NULL",
                                          (now_iso(), code)).rowcount
            row = connection.execute("SELECT * FROM utm_links WHERE code = ?", (code,)).fetchone()
            if row is None:
                return 0
            clash = connection.execute(
                "SELECT code FROM utm_links WHERE archived_at IS NULL AND code != ? AND target_path = ? AND utm_source = ? "
                "AND utm_medium = ? AND utm_campaign = ? AND COALESCE(utm_content, '') = COALESCE(?, '')",
                (code, row["target_path"], row["utm_source"], row["utm_medium"], row["utm_campaign"], row["utm_content"])).fetchone()
            if clash:
                raise StoreError(f"같은 조합의 활성 링크({clash['code']})가 있어 복원할 수 없습니다.")
            return connection.execute("UPDATE utm_links SET archived_at = NULL WHERE code = ?", (code,)).rowcount
    finally:
        connection.close()


def resolve_link(code):
    """Active link for a public redirect, or None."""
    connection = store.connect()
    try:
        row = connection.execute(f"SELECT {LINK_COLUMNS} FROM utm_links WHERE code = ? AND archived_at IS NULL", (code,)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def record_click(code, counted, exclude_note, ua_family):
    connection = store.connect()
    try:
        with connection:
            connection.execute("INSERT INTO utm_clicks (code, clicked_at, counted, exclude_note, ua_family) VALUES (?, ?, ?, ?, ?)",
                               (code, now_iso(), int(counted), exclude_note, ua_family))
    finally:
        connection.close()


# ---- metrics ----------------------------------------------------------------------

def _range(date_from, date_to, column):
    clauses, params = store.parse_range(date_from, date_to)
    return [clause.replace("created_at", column) for clause in clauses], params


def _rate(submissions, clicks):
    return round(submissions / clicks, 4) if clicks else None


def _link_metrics(connection, date_from=None, date_to=None):
    click_where, click_params = _range(date_from, date_to, "clicked_at")
    sub_where, sub_params = _range(date_from, date_to, "created_at")
    clicks = {r["code"]: dict(r) for r in connection.execute(
        f"SELECT code, SUM(CASE WHEN counted = 1 THEN 1 ELSE 0 END) AS clicks, SUM(CASE WHEN counted = 0 THEN 1 ELSE 0 END) AS bot_clicks FROM utm_clicks{where(click_where)} GROUP BY code",
        click_params)}
    subs = {r["code"]: dict(r) for r in connection.execute(
        f"SELECT short_code AS code, COUNT(*) AS submissions, SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success FROM submissions"
        f"{where(sub_where + ['short_code IS NOT NULL'])} GROUP BY short_code", sub_params)}
    return clicks, subs


def _metrics(clicks, submissions, success, bot_clicks):
    return {"clicks": int(clicks or 0), "bot_clicks": int(bot_clicks or 0), "submissions": int(submissions or 0),
            "success": int(success or 0), "conversion": _rate(int(submissions or 0), int(clicks or 0))}


def list_links(q=None, channel=None, campaign=None, archived=None, limit=500):
    clauses, params = [], []
    if archived == "only":
        clauses.append("archived_at IS NOT NULL")
    elif archived != "all":
        clauses.append("archived_at IS NULL")
    if channel:
        clauses.append("channel_key = ?")
        params.append(slug(channel, "channel"))
    if campaign:
        clauses.append("campaign_key = ?")
        params.append(slug(campaign, "campaign"))
    if q:
        clauses.append("(code LIKE ? ESCAPE '\\' OR memo LIKE ? ESCAPE '\\' OR utm_content LIKE ? ESCAPE '\\' "
                       "OR target_path LIKE ? ESCAPE '\\' OR created_by LIKE ? ESCAPE '\\')")
        params += [store.like(q)] * 5
    connection = store.connect()
    try:
        rows = connection.execute(f"SELECT {LINK_COLUMNS} FROM utm_links{where(clauses)} ORDER BY created_at DESC, code LIMIT ?",
                                  [*params, int(limit)]).fetchall()
        clicks, subs = _link_metrics(connection)
        links = []
        for row in rows:
            c, s = clicks.get(row["code"], {}), subs.get(row["code"], {})
            links.append({**_link_view(row), **_metrics(c.get("clicks"), s.get("submissions"), s.get("success"), c.get("bot_clicks"))})
        return {"links": links}
    finally:
        connection.close()


def utm_stats(date_from=None, date_to=None):
    """Short-link attribution by submissions.short_code; UTM without a short code is reported as '직접 유입'."""
    connection = store.connect()
    try:
        clicks, subs = _link_metrics(connection, date_from, date_to)
        links = [dict(r) for r in connection.execute(f"SELECT {LINK_COLUMNS} FROM utm_links ORDER BY created_at DESC")]
        channels = {r["key"]: dict(r) for r in connection.execute("SELECT * FROM utm_channels")}
        campaigns = {r["key"]: dict(r) for r in connection.execute("SELECT * FROM utm_campaigns")}
        known_codes = {link["code"] for link in links}

        sub_where, sub_params = _range(date_from, date_to, "created_at")
        # UTM direct: tagged submissions without a known short code (a hand-built UTM URL, or a stale code).
        direct_rows = [dict(r) for r in connection.execute(
            f"SELECT utm_source, utm_medium, utm_campaign, short_code, COUNT(*) AS submissions, SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success "
            f"FROM submissions{where(sub_where + ['utm_source IS NOT NULL'])} "
            "GROUP BY utm_source, utm_medium, utm_campaign, short_code", sub_params)]
        direct_rows = [r for r in direct_rows if r["short_code"] not in known_codes]
        direct = {}
        for r in direct_rows:
            key = (r["utm_source"], r["utm_medium"], r["utm_campaign"])
            item = direct.setdefault(key, {"utm_source": key[0], "utm_medium": key[1], "utm_campaign": key[2], "submissions": 0, "success": 0})
            item["submissions"] += r["submissions"]
            item["success"] += int(r["success"] or 0)
        direct = sorted(direct.values(), key=lambda d: (-d["submissions"], d["utm_source"] or ""))

        def bucket(label):
            return {"label": label, "clicks": 0, "bot_clicks": 0, "submissions": 0, "success": 0,
                    "direct_submissions": 0, "direct_success": 0}

        by_channel = {key: {"key": key, **bucket(ch["label_ko"])} for key, ch in channels.items()}
        by_campaign = {key: {"key": key, **bucket(cp["label_ko"])} for key, cp in campaigns.items()}
        link_rows = []
        for link in links:
            c, s = clicks.get(link["code"], {}), subs.get(link["code"], {})
            metrics = _metrics(c.get("clicks"), s.get("submissions"), s.get("success"), c.get("bot_clicks"))
            if not any(metrics[k] for k in ("clicks", "bot_clicks", "submissions")) and link["archived_at"]:
                continue
            link_rows.append({**_link_view(link), **metrics})
            for groups, key in ((by_channel, link["channel_key"]), (by_campaign, link["campaign_key"])):
                target = groups.setdefault(key, {"key": key, **bucket(key)})
                for name in ("clicks", "bot_clicks", "submissions", "success"):
                    target[name] += metrics[name]
        source_medium = {(ch["utm_source"], ch["utm_medium"]): key for key, ch in channels.items()}
        for d in direct:
            channel_key = source_medium.get((d["utm_source"], d["utm_medium"]))
            for groups, key in ((by_channel, channel_key), (by_campaign, d["utm_campaign"] if d["utm_campaign"] in campaigns else None)):
                if key:
                    groups[key]["direct_submissions"] += d["submissions"]
                    groups[key]["direct_success"] += d["success"]

        def finish(groups):
            rows = [g for g in groups.values() if any(g[k] for k in ("clicks", "bot_clicks", "submissions", "direct_submissions"))]
            for g in rows:
                g["conversion"] = _rate(g["submissions"], g["clicks"])
            return sorted(rows, key=lambda g: (-g["clicks"], -g["submissions"], g["key"]))

        click_where, click_params = _range(date_from, date_to, "clicked_at")
        daily = {}
        for r in connection.execute(f"SELECT substr(clicked_at, 1, 10) AS day, SUM(CASE WHEN counted = 1 THEN 1 ELSE 0 END) AS clicks, SUM(CASE WHEN counted = 0 THEN 1 ELSE 0 END) AS bot_clicks "
                                    f"FROM utm_clicks{where(click_where)} GROUP BY day", click_params):
            daily.setdefault(r["day"], {"day": r["day"], "clicks": 0, "bot_clicks": 0, "submissions": 0, "direct_submissions": 0})
            daily[r["day"]].update(clicks=int(r["clicks"] or 0), bot_clicks=int(r["bot_clicks"] or 0))
        for r in connection.execute(f"SELECT substr(created_at, 1, 10) AS day, short_code, utm_source FROM submissions"
                                    f"{where(sub_where + ['(short_code IS NOT NULL OR utm_source IS NOT NULL)'])}", sub_params):
            entry = daily.setdefault(r["day"], {"day": r["day"], "clicks": 0, "bot_clicks": 0, "submissions": 0, "direct_submissions": 0})
            if r["short_code"] in known_codes:
                entry["submissions"] += 1
            elif r["utm_source"]:
                entry["direct_submissions"] += 1

        totals = {name: sum(row[name] for row in link_rows) for name in ("clicks", "bot_clicks", "submissions", "success")}
        totals["conversion"] = _rate(totals["submissions"], totals["clicks"])
        totals["direct_submissions"] = sum(d["submissions"] for d in direct)
        totals["direct_success"] = sum(d["success"] for d in direct)
        return {
            "range": {"from": date_from or None, "to": date_to or None},
            "totals": totals,
            "links": sorted(link_rows, key=lambda r: (-r["clicks"], -r["submissions"], r["code"])),
            "by_channel": finish(by_channel),
            "by_campaign": finish(by_campaign),
            "direct": direct,
            "daily": [daily[k] for k in sorted(daily)],
        }
    finally:
        connection.close()
