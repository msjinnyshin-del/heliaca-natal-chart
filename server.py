"""Natal chart HTTP handler.

Locally it runs as a loopback-only development server (`python server.py`). On Vercel the same
ChartHandler is served by the Python runtime through api/index.py; public hosts must then be listed
in NATAL_ALLOWED_HOSTS (see README "Vercel + Neon 배포").
"""
import argparse
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


WEB_ROOT = Path(__file__).resolve().parent / "web"
ADMIN_ROOT = WEB_ROOT / "admin"
MAX_REQUEST_BYTES = 16_384
# Admin static files reachable before login; everything else under /admin needs a session.
ADMIN_PUBLIC_FILES = {"login.html", "login.js", "admin.css"}
ADMIN_PRIVATE_FILES = {"index.html", "admin.js"}
# Hostnames Vercel assigns to a deployment; readable at runtime as system environment variables.
VERCEL_HOST_VARS = ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")


def serverless():
    return bool(os.environ.get("VERCEL"))


def configured_hosts():
    """Extra public hosts (`host[:port]`, lowercase) from NATAL_ALLOWED_HOSTS, plus Vercel's own on Vercel."""
    hosts = {h.strip().lower() for h in os.environ.get("NATAL_ALLOWED_HOSTS", "").split(",") if h.strip()}
    if serverless():
        hosts |= {os.environ[name].strip().lower() for name in VERCEL_HOST_VARS if os.environ.get(name, "").strip()}
    return hosts


class ChartHandler(BaseHTTPRequestHandler):
    server_version = "NatalLocal/1"

    def log_message(self, format, *args):
        # HTTP access logs can contain personally identifying query strings.
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def send_content(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if self.is_admin_route():
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, value, headers=None):
        self.send_content(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), headers=headers)

    def route(self):
        return unquote(urlsplit(self.path).path)

    def is_admin_route(self):
        route = self.route()
        return route == "/admin" or route.startswith("/admin/") or route.startswith("/api/admin")

    def redirect(self, location, headers=None):
        self.send_content(303, b"", "text/plain; charset=utf-8", {"Location": location, **(headers or {})})

    def error_json(self, status, code, message, details=None):
        self.send_json(status, {"error": {"code": code, "message": message, "details": details}})

    def forwarded(self, name):
        """First value of a proxy header, trusted only on Vercel where the edge overwrites it."""
        if not serverless():
            return None
        value = (self.headers.get(name) or "").split(",", 1)[0].strip()
        return value or None

    def request_host(self):
        return (self.forwarded("X-Forwarded-Host") or self.headers.get("Host") or "").strip().lower()

    def request_scheme(self):
        return "https" if (self.forwarded("X-Forwarded-Proto") or "").lower() == "https" else "http"

    def client_key(self):
        return self.forwarded("X-Real-IP") or self.forwarded("X-Forwarded-For") or self.client_address[0]

    def allowed_hosts(self):
        hosts = configured_hosts()
        if not serverless():
            port = self.server.server_port
            hosts |= {f"127.0.0.1:{port}", f"localhost:{port}"}
        return hosts

    def allowed_origins(self):
        scheme = self.request_scheme()
        return {f"{scheme}://{host}" for host in self.allowed_hosts()}

    def permitted_origin(self):
        if self.request_host() not in self.allowed_hosts():
            self.error_json(403, "HOST_NOT_ALLOWED", "허용된 주소에서만 이용할 수 있습니다.")
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in self.allowed_origins():
            self.error_json(403, "ORIGIN_REJECTED", "외부 사이트의 계산 요청은 허용하지 않습니다.")
            return False
        return True

    def do_GET(self):
        if not self.permitted_origin():
            return
        route = self.route()
        if self.is_admin_route():
            self.admin_get(route)
            return
        if route.startswith("/l/"):
            self.short_link(route, head=False)
            return
        if route == "/api/health":
            self.send_json(200, {"status": "local_server_running"})
            return
        if route.startswith("/api/share/"):
            self.share_get(route[len("/api/share/"):])
            return
        if route == "/api/places":
            from natal.places import PlaceSearchError, search_places
            try:
                query = urlsplit(self.path).query
                if len(query) > 2048:
                    raise ValueError("Query too long")
                parameters = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=2, errors="strict")
                # Reject personal or arbitrary extra fields instead of forwarding
                # the chart form. Only the explicit city search string can leave.
                if set(parameters) != {"q"} or len(parameters["q"]) != 1:
                    raise ValueError("Exactly one city query required")
            except ValueError:
                self.error_json(422, "INVALID_PLACE_QUERY", "도시명 검색어 q만 한 번 전달해 주세요.")
                return
            try:
                self.send_json(200, search_places(parameters["q"][0]))
            except PlaceSearchError as error:
                self.error_json(error.status, error.code, str(error))
            except Exception:
                self.error_json(502, "PLACE_SEARCH_UNAVAILABLE", "장소 검색에 실패했습니다. 다시 검색하거나 직접 입력하세요.")
            return
        relative = "index.html" if route == "/" else route.lstrip("/")
        target = (WEB_ROOT / relative).resolve()
        try:
            target.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self.error_json(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")
            return
        if target.suffix not in {".html", ".css", ".js", ".mjs", ".svg", ".woff2"} or not target.is_file():
            self.error_json(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".mjs", ".js"}:
            content_type = "text/javascript"
        self.send_content(200, target.read_bytes(), content_type + "; charset=utf-8")

    def do_HEAD(self):
        if not self.permitted_origin():
            return
        route = self.route()
        if route.startswith("/l/"):
            self.short_link(route, head=True)
        else:
            self.send_content(405, b"", "text/plain; charset=utf-8", {"Allow": "GET, POST"})

    def short_link(self, route, head):
        """Public short link: 302 to a path-only target with utm_* + sc. Recording never blocks the redirect."""
        from natal import utm
        code = route[len("/l/"):].lower()
        link = None
        if utm.is_code_shaped(code):
            try:
                link = utm.resolve_link(code)
            except Exception:
                link = None
        path = utm.normalize_target_path(link["target_path"]) if link else None
        if not path:
            self.go(utm.UNKNOWN_TARGET)
            return
        target = utm.build_target(path, link["utm_source"], link["utm_medium"], link["utm_campaign"], link["utm_content"], code)
        is_bot, family = utm.read_ua(self.headers.get("User-Agent"))
        try:
            utm.record_click(code, counted=not head and not is_bot,
                             exclude_note="head" if head else ("preview-bot" if is_bot else None), ua_family=family)
        except Exception:
            pass
        self.go(target)

    def go(self, location):
        # 302 (not 301) + no-store so every click reaches the server and is counted.
        self.send_content(302, b"", "text/plain; charset=utf-8",
                          {"Location": location, "X-Robots-Tag": "noindex, nofollow"})

    def read_body(self, allow_form=False):
        """Return (kind, bytes) or None after sending an error response."""
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        allowed = {"application/json"} | ({"application/x-www-form-urlencoded"} if allow_form else set())
        if content_type not in allowed:
            self.error_json(415, "JSON_REQUIRED", "JSON 형식의 입력이 필요합니다.")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 1:
            self.error_json(400, "INVALID_LENGTH", "입력 본문이 올바르지 않습니다.")
            return None
        if length > MAX_REQUEST_BYTES:
            self.error_json(413, "PAYLOAD_TOO_LARGE", "입력 데이터가 너무 큽니다.")
            return None
        return content_type, self.rfile.read(length)

    @staticmethod
    def parse_json_object(raw):
        def reject_nonfinite(value):
            raise ValueError("Non-finite JSON number")
        payload = json.loads(raw, parse_constant=reject_nonfinite)
        if not isinstance(payload, dict):
            raise ValueError("Expected an object")
        return payload

    def do_POST(self):
        if not self.permitted_origin():
            return
        route = self.route()
        if self.is_admin_route():
            self.admin_post(route)
            return
        if route == "/api/synastry":
            self.synastry()
            return
        if route == "/api/share":
            self.share_create()
            return
        if route.startswith("/api/share/") and route.endswith("/delete"):
            self.share_delete(route[len("/api/share/"):-len("/delete")])
            return
        if route != "/api/chart":
            self.error_json(404, "NOT_FOUND", "요청 경로를 찾을 수 없습니다.")
            return
        body = self.read_body()
        if body is None:
            return
        try:
            payload = self.parse_json_object(body[1])
        except (ValueError, UnicodeError):
            self.error_json(400, "INVALID_JSON", "올바른 JSON 객체를 입력해 주세요.")
            return
        # `client` (visitor id, name, UTM) is operational data: never passed to the engine
        # and never part of the deterministic chart result.
        client = payload.pop("client", None)
        # Import on request so private engine/data cannot become static routes.
        from natal.engine import calculate_chart
        from natal.errors import ChartError
        try:
            result = calculate_chart(payload)
        except ChartError as error:
            self.record(payload, client, error_code=error.code)
            self.error_json(422, error.code, str(error), getattr(error, "details", None))
            return
        except Exception:
            self.record(payload, client, error_code="CALCULATION_FAILED")
            # Never return a traceback, input payload or filesystem paths.
            self.error_json(500, "CALCULATION_FAILED", "계산에 실패했습니다. 엔진과 데이터 설치 상태를 확인해 주세요.")
            return
        self.record(payload, client, result=result)
        self.send_json(200, result)

    def synastry(self):
        body = self.read_body()
        if body is None:
            return
        try:
            payload = self.parse_json_object(body[1])
        except (ValueError, UnicodeError):
            self.error_json(400, "INVALID_JSON", "올바른 JSON 객체를 입력해 주세요.")
            return
        # Synastry inputs are not stored; the client context is accepted and dropped.
        payload.pop("client", None)
        from natal.errors import ChartError
        from natal.synastry import calculate_synastry
        try:
            result = calculate_synastry(payload)
        except ChartError as error:
            self.error_json(422, error.code, str(error), getattr(error, "details", None))
            return
        except Exception:
            self.error_json(500, "CALCULATION_FAILED", "계산에 실패했습니다. 엔진과 데이터 설치 상태를 확인해 주세요.")
            return
        self.send_json(200, result)

    def json_body(self):
        body = self.read_body()
        if body is None:
            return None
        try:
            return self.parse_json_object(body[1])
        except (ValueError, UnicodeError):
            self.error_json(400, "INVALID_JSON", "올바른 JSON 객체를 입력해 주세요.")
            return None

    def share_create(self):
        payload = self.json_body()
        if payload is None:
            return
        from natal import shares, store
        from natal.errors import ChartError
        from natal.synastry import calculate_synastry
        names = payload.get("names") if isinstance(payload.get("names"), dict) else {}
        if payload.get("kind") != "synastry" or not isinstance(payload.get("input"), dict):
            self.error_json(422, "INVALID_INPUT", "kind=synastry와 input 객체가 필요합니다.")
            return
        try:
            calculate_synastry(payload["input"])  # only shareable if it calculates cleanly
        except ChartError as error:
            self.error_json(422, error.code, str(error), getattr(error, "details", None))
            return
        stored = {"names": {key: store.clean_name(names.get(key)) for key in ("a", "b")}, "input": payload["input"]}
        try:
            token, delete_key = shares.create_share("synastry", payload.get("title"), stored)
        except Exception:
            self.error_json(503, "SHARE_UNAVAILABLE", "공유 링크 저장소를 사용할 수 없습니다.")
            return
        self.send_json(201, {"token": token, "path": f"/synastry.html?s={token}", "delete_key": delete_key})

    def share_get(self, token):
        from natal import shares
        from natal.errors import ChartError
        from natal.synastry import calculate_synastry
        try:
            share = shares.get_share(token)
        except Exception:
            self.error_json(503, "SHARE_UNAVAILABLE", "공유 링크 저장소를 사용할 수 없습니다.")
            return
        if share is None:
            self.error_json(404, "SHARE_NOT_FOUND", "공유 링크가 없거나 삭제되었습니다.")
            return
        try:
            result = calculate_synastry(share["payload"]["input"])
        except ChartError as error:
            self.error_json(422, error.code, str(error), getattr(error, "details", None))
            return
        self.send_json(200, {"kind": share["kind"], "title": share["title"], "names": share["payload"]["names"],
                             "created_at": share["created_at"], "result": result})

    def share_delete(self, token):
        payload = self.json_body()
        if payload is None:
            return
        from natal import shares
        try:
            deleted = shares.delete_share(token, payload.get("delete_key"))
        except Exception:
            self.error_json(503, "SHARE_UNAVAILABLE", "공유 링크 저장소를 사용할 수 없습니다.")
            return
        if not deleted:
            self.error_json(404, "SHARE_NOT_FOUND", "삭제할 링크가 없거나 삭제 키가 맞지 않습니다.")
            return
        self.send_json(200, {"deleted": True})

    @staticmethod
    def record(payload, client, result=None, error_code=None):
        # Storage is best-effort: a broken database must never break the chart response,
        # and failures are swallowed silently so raw input never reaches a log.
        try:
            from natal import store
            store.record_submission(payload, client, result=result, error_code=error_code)
        except Exception:
            pass

    # ---- admin --------------------------------------------------------------

    def admin_available(self, api):
        from natal import admin_auth, store
        if serverless() and not admin_auth.secret_configured():
            # A per-process random key breaks sessions across serverless instances.
            message = "운영 환경에서는 NATAL_ADMIN_SECRET이 필요합니다."
            if api:
                self.error_json(503, "ADMIN_SECRET_REQUIRED", message)
            else:
                self.send_content(503, message.encode("utf-8"), "text/plain; charset=utf-8")
            return False
        if serverless() and not store.is_postgres():
            message = "운영 환경에서는 DATABASE_URL(또는 POSTGRES_URL)이 필요합니다."
            if api:
                self.error_json(503, "DATABASE_REQUIRED", message)
            else:
                self.send_content(503, message.encode("utf-8"), "text/plain; charset=utf-8")
            return False
        if admin_auth.admin_password():
            return True
        if api:
            self.error_json(503, "ADMIN_DISABLED", "관리자 비밀번호(NATAL_ADMIN_PASSWORD)가 설정되지 않았습니다.")
        else:
            self.send_content(503, "관리자 기능이 비활성 상태입니다. NATAL_ADMIN_PASSWORD를 설정하세요.".encode("utf-8"), "text/plain; charset=utf-8")
        return False

    def admin_authenticated(self):
        from natal import admin_auth
        return admin_auth.verify_token(admin_auth.cookie_token(self.headers.get("Cookie")))

    def same_origin_required(self):
        """CSRF guard for state-changing admin requests: Origin must be present and ours."""
        if self.headers.get("Origin") not in self.allowed_origins():
            self.error_json(403, "CSRF_REJECTED", "같은 출처의 요청만 허용합니다.")
            return False
        return True

    def serve_admin_file(self, name):
        target = ADMIN_ROOT / name
        if not target.is_file():
            self.error_json(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")
            return
        content_type = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[target.suffix.lstrip(".")]
        self.send_content(200, target.read_bytes(), content_type + "; charset=utf-8")

    def admin_get(self, route):
        api = route.startswith("/api/admin")
        if not self.admin_available(api):
            return
        if route == "/admin/login":
            self.serve_admin_file("login.html")
            return
        name = route[len("/admin/"):] if route.startswith("/admin/") else ""
        if name in ADMIN_PUBLIC_FILES:
            self.serve_admin_file(name)
            return
        if not self.admin_authenticated():
            if api:
                self.error_json(401, "ADMIN_AUTH_REQUIRED", "관리자 로그인이 필요합니다.")
            else:
                self.redirect("/admin/login")
            return
        if api:
            self.admin_api_get(route)
        elif route in {"/admin", "/admin/"}:
            self.serve_admin_file("index.html")
        elif name in ADMIN_PRIVATE_FILES:
            self.serve_admin_file(name)
        else:
            self.error_json(404, "NOT_FOUND", "파일을 찾을 수 없습니다.")

    def query_params(self, allowed):
        query = urlsplit(self.path).query
        if len(query) > 2048:
            raise ValueError("Query too long")
        parameters = parse_qs(query, keep_blank_values=False, strict_parsing=False, max_num_fields=20)
        if set(parameters) - allowed or any(len(values) != 1 for values in parameters.values()):
            raise ValueError("Unexpected query parameter")
        return {key: values[0] for key, values in parameters.items()}

    def admin_api_get(self, route):
        from natal import store
        from natal.engine import calculate_chart
        from natal.errors import ChartError
        parts = route.strip("/").split("/")  # api, admin, ...
        try:
            if parts[2:] == ["utm-stats"]:
                params = self.query_params({"from", "to"})
                from natal import utm
                self.send_json(200, utm.utm_stats(params.get("from"), params.get("to")))
            elif parts[2:] == ["utm", "channels"]:
                self.query_params(set())
                from natal import utm
                self.send_json(200, utm.list_channels())
            elif parts[2:] == ["utm", "campaigns"]:
                self.query_params(set())
                from natal import utm
                self.send_json(200, utm.list_campaigns())
            elif parts[2:] == ["utm", "links"]:
                params = self.query_params({"q", "channel", "campaign", "archived"})
                from natal import utm
                self.send_json(200, utm.list_links(params.get("q"), params.get("channel"), params.get("campaign"), params.get("archived")))
            elif parts[2:] == ["stats"]:
                params = self.query_params({"from", "to"})
                self.send_json(200, store.stats(params.get("from"), params.get("to")))
            elif parts[2:] == ["users"]:
                params = self.query_params({"from", "to", "q"})
                self.send_json(200, store.users(params.get("from"), params.get("to"), params.get("q")))
            elif parts[2:] == ["submissions"]:
                params = self.query_params({"visitor_id", "q", "status", "from", "to", "limit", "offset"})
                self.send_json(200, store.list_submissions(
                    params.get("visitor_id"), params.get("q"), params.get("status"), params.get("from"), params.get("to"),
                    int(params.get("limit", 50)), int(params.get("offset", 0))))
            elif len(parts) in (4, 5) and parts[2] == "submissions" and parts[3].isdigit() and (len(parts) == 4 or parts[4] == "chart"):
                item = store.get_submission(int(parts[3]))
                if item is None:
                    self.error_json(404, "NOT_FOUND", "입력 기록을 찾을 수 없습니다.")
                elif len(parts) == 4:
                    self.send_json(200, item)
                else:
                    try:
                        # Recomputed on demand from the stored raw input; never cached.
                        self.send_json(200, calculate_chart(dict(item["raw_input"])))
                    except ChartError as error:
                        self.error_json(422, error.code, str(error), getattr(error, "details", None))
            else:
                self.error_json(404, "NOT_FOUND", "요청 경로를 찾을 수 없습니다.")
        except (ValueError, store.StoreError) as error:
            message = str(error) if isinstance(error, store.StoreError) else "조회 조건이 올바르지 않습니다."
            self.error_json(422, "INVALID_QUERY", message)

    def admin_post(self, route):
        if not self.admin_available(route.startswith("/api/admin")):
            return
        if not self.same_origin_required():
            return
        if route == "/admin/login":
            self.admin_login()
        elif route == "/admin/logout":
            from natal import admin_auth
            self.redirect("/admin/login", {"Set-Cookie": admin_auth.clear_cookie(self.request_scheme() == "https")})
        elif route.startswith("/api/admin/"):
            if not self.admin_authenticated():
                self.error_json(401, "ADMIN_AUTH_REQUIRED", "관리자 로그인이 필요합니다.")
                return
            self.admin_api_post(route)
        else:
            self.error_json(404, "NOT_FOUND", "요청 경로를 찾을 수 없습니다.")

    def admin_api_post(self, route):
        from natal import store, utm
        parts = route.strip("/").split("/")[2:]  # after api/admin
        handlers = {
            ("utm", "channels"): lambda body: (201, utm.create_channel(body)),
            ("utm", "campaigns"): lambda body: (201, utm.create_campaign(body)),
            ("utm", "links"): lambda body: (200, utm.create_links(body)),
        }
        handler = handlers.get(tuple(parts))
        if handler is None and len(parts) == 3 and parts[:2] in (["utm", "channels"], ["utm", "campaigns"]):
            update = utm.update_channel if parts[1] == "channels" else utm.update_campaign
            handler = lambda body: (200, {"updated": update(parts[2], body)})
        if handler is None and len(parts) == 4 and parts[:2] == ["utm", "links"] and parts[3] in ("archive", "unarchive"):
            handler = lambda body: (200, {"updated": utm.set_archived(parts[2], parts[3] == "archive")})
        if handler is None:
            self.error_json(404, "NOT_FOUND", "요청 경로를 찾을 수 없습니다.")
            return
        body = {}
        if parts[-1] not in ("archive", "unarchive"):
            raw = self.read_body()
            if raw is None:
                return
            try:
                body = self.parse_json_object(raw[1])
            except (ValueError, UnicodeError):
                self.error_json(400, "INVALID_JSON", "올바른 JSON 객체를 입력해 주세요.")
                return
        try:
            status, value = handler(body)
        except store.StoreError as error:
            self.error_json(422, "INVALID_INPUT", str(error))
            return
        if value.get("updated") == 0:
            self.error_json(404, "NOT_FOUND", "대상을 찾을 수 없거나 이미 그 상태입니다.")
            return
        self.send_json(status, value)

    def admin_login(self):
        from natal import admin_auth
        client_key = self.client_key()
        if admin_auth.rate_limited(client_key):
            self.error_json(429, "TOO_MANY_ATTEMPTS", "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
            return
        body = self.read_body(allow_form=True)
        if body is None:
            return
        kind, raw = body
        try:
            if kind == "application/json":
                password = self.parse_json_object(raw).get("password")
            else:
                form = parse_qs(raw.decode("utf-8"), max_num_fields=5)
                password = form.get("password", [None])[0]
        except (ValueError, UnicodeError):
            password = None
        if not admin_auth.check_password(password):
            admin_auth.note_failure(client_key)
            time.sleep(admin_auth.FAILURE_DELAY)
            if kind == "application/json":
                self.error_json(401, "INVALID_PASSWORD", "비밀번호가 올바르지 않습니다.")
            else:
                self.redirect("/admin/login?error=1")
            return
        admin_auth.reset_failures(client_key)
        cookie = {"Set-Cookie": admin_auth.session_cookie(admin_auth.issue_token(), secure=self.request_scheme() == "https")}
        if kind == "application/json":
            self.send_json(200, {"ok": True}, cookie)
        else:
            self.redirect("/admin/", cookie)

    def do_DELETE(self):
        if not self.permitted_origin():
            return
        route = self.route()
        if not route.startswith("/api/admin/"):
            self.error_json(405, "METHOD_NOT_ALLOWED", "허용되지 않는 요청입니다.")
            return
        if not self.admin_available(True):
            return
        if not self.admin_authenticated():
            self.error_json(401, "ADMIN_AUTH_REQUIRED", "관리자 로그인이 필요합니다.")
            return
        if not self.same_origin_required():
            return
        from natal import store
        parts = route.strip("/").split("/")
        try:
            if len(parts) == 4 and parts[2] == "submissions" and parts[3].isdigit():
                deleted = store.delete_submission(int(parts[3]))
            elif len(parts) == 4 and parts[2] == "users":
                deleted = store.delete_visitor(parts[3])
            else:
                self.error_json(404, "NOT_FOUND", "요청 경로를 찾을 수 없습니다.")
                return
        except store.StoreError as error:
            self.error_json(422, "INVALID_QUERY", str(error))
            return
        if not deleted:
            self.error_json(404, "NOT_FOUND", "삭제할 기록이 없습니다.")
            return
        self.send_json(200, {"deleted": deleted})


def make_server(port=8765):
    return ThreadingHTTPServer(("127.0.0.1", port), ChartHandler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start a private local natal chart workbench")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"네이털 차트: http://127.0.0.1:{server.server_port} (로컬 전용)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
