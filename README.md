# 황도실 · 네이털 차트 워크벤치

Swiss Ephemeris로 계산하는 서양 점성술 차트 워크벤치. 핵심 천체·각도·하우스·어스펙트를 실제 계산하고 계산 근거를 공개하는 첫 구현이다. 앱 전체의 100% 동일 재현이나 상용 출시 검증 완료를 의미하지 않는다.

## 시작

현재 작업 폴더의 `.venv`에 고정 의존성이 설치되어 있다.

```sh
cd natal-chart   # 이 저장소 폴더
.venv/bin/python server.py --port 8765
```

브라우저: <http://127.0.0.1:8765>

새 환경에서는 Python 3.9 이상과 아래 설치가 필요하다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`data/ephe/`의 3개 파일은 [공식 Swiss Ephemeris의 고정 커밋](https://github.com/aloistr/swisseph/tree/9083a12d59e98034fb2337061481ac8800c16e64/ephe)에서 받았다. 파일 이름·해시는 `data/manifest.json`으로 고정한다. 파일 누락·변조 시 근사 엔진으로 대체하지 않고 계산을 거절한다.

## 이용 범위

- 양력 생년월일과 **알려진 현지 출생 시각**, 정밀 경위도, IANA 시간대를 입력한다. 기본 Tropical / geocentric / Placidus / True Node / Mean Black Moon Lilith.
- 초 단위 출력은 입력값보다 정밀한 출생기록을 보증하지 않는다. 기준 비교 프로필은 최근접 초 반올림이며 원시 좌표는 보존한다.
- 1970년부터 오늘까지가 초기 입력 범위. 이전 날짜는 역사 시간대 검토가 필요하다. 생시 미상·추정 구간, 음력은 이번 구현에서 지원하지 않는다.
- 장소 검색(Open-Meteo)으로 좌표·시간대 후보를 제공하고, 그 외 장소는 정밀 좌표와 IANA를 직접 입력한다. 도시명만 입력하면 전 세계 위치를 자동 판정하는 서비스가 아니다. 시간대와 좌표 조합의 정확성은 사용자가 확인해야 한다.
- DST 중복 시각은 회차 선택이 필요하고, 존재하지 않는 시각은 거절한다. 극지 Placidus 실패 시 다른 하우스로 몰래 대체하지 않는다.
- 실제 계산한 10행성, True/Mean Nodes, Mean Lilith, Chiron, ASC/MC/DSC/IC, Fortune/Spirit, 12하우스, 주요 어스펙트를 제공한다.
- Almuten Figuris, 전통 dignity 전체표, 차트 패턴, 항성, V%, Auriga/Doryphoros, 트랜짓·프로그레션 및 AI 해석은 이번 구현의 검증 범위 밖이다. 활성 기능처럼 표시하지 않는다.

## 비교 결과를 읽는 법

[참조 비교 방법](docs/REFERENCE_COMPARISON.md)에 입력·노드·시간척도 차이를 점검하는 절차를 정리했다. 개발 중 사용한 외부 참조 차트는 실존 인물 정보라 저장소에 포함하지 않으며, 테스트는 가상 인물(1985-07-14 21:45, New York) 기준의 엔진 회귀 스냅샷을 쓴다. 외부 앱의 버전·숨은 설정이 확인되지 않은 비교는 호환성 검사일 뿐이며, 원본에 맞추기 위한 상수 보정은 하지 않는다.

## 테스트

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.mjs
```

현재 자동 검증(2026-09-22): Python unittest 106건(Postgres 3건은 `TEST_DATABASE_URL` 미설정 시 skip) + node --test 27건 통과(UTM 15+1건 포함). Postgres 테스트는 빈 DB에 `TEST_DATABASE_URL=postgresql://... .venv/bin/python -m unittest tests/test_deploy.py`로 실행한다(테이블을 비운다). 실제 Chrome 검사는 별도 실행. 독립 코드 리뷰에서 발견한 시간 경계·DST 선택·SVG 스타일·오래된 결과 저장 오류도 수정 및 재검토했다.

브라우저 검증은 실행 중인 로컬 서버와 개발 의존성이 필요하다.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tests/browser_checks.py
```

macOS에서는 설치된 Chrome을 격리된 headless 프로필로 사용한다. 다른 환경에서는 `.venv/bin/python -m playwright install chromium`으로 테스트 브라우저를 준비한다. 브라우저 QA 산출물은 `artifacts/`에 있으며 개인정보를 포함하므로 공개하지 않는다.

HTTP 통합 검사는 로컬 포트 바인딩 권한이 필요하다. 실제 계산·시간대 오류·파일 무결성·하우스 실패·입력 변경·API/정적 파일 경계를 검증한다. 테스트 통과는 입력 정보 자체나 점성술 해석의 과학적 타당성을 인증하지 않는다.

## 관리자 (입력 기록·통계)

```sh
NATAL_ADMIN_PASSWORD='긴-비밀번호' NATAL_ADMIN_SECRET='임의의-긴-문자열' .venv/bin/python server.py --port 8765
```

- 관리자 화면: <http://127.0.0.1:8765/admin/> (로그인: `/admin/login`). 탭: 통계 · 사용자 · 입력 기록(상세에서 원문·재계산 차트·삭제).
- `NATAL_ADMIN_PASSWORD`가 없으면 모든 `/admin*`, `/api/admin/*`는 503이다. `NATAL_ADMIN_SECRET`이 없으면 프로세스별 임의 키를 써서 서버 재시작 시 세션이 만료된다.
- 세션: `exp.hmac` 쿠키(HttpOnly, SameSite=Strict, 12시간, https 요청이면 `Secure`). 로그인 실패 시 1초 지연, IP별 15분 5회 제한 — 실패 기록은 DB `login_attempts`(IP는 HMAC 해시로만 저장)에 두어 서버리스 인스턴스 간에 공유하고, DB 장애 시 프로세스 메모리로 대체한다. 관리자 POST/DELETE는 같은 Origin만 허용.
- 저장소: 기본 `data/admin.sqlite3`(WAL, `PRAGMA user_version` 마이그레이션, `NATAL_DB_PATH`로 변경 가능, git 제외). `DATABASE_URL`(없으면 `POSTGRES_URL`)이 있으면 Postgres(Neon 등)를 쓰며, 스키마는 요청 중 마이그레이션하지 않고 `db/schema.sql`로 수동 적용한다. 백업·보관 기간은 운영자가 정한다.
- UTM 빌더: 관리자 탭 `UTM 빌더`(채널 여러 개 동시 생성·단축/UTM URL 복사) · `링크 장부`(누적 클릭·봇·입력·성공·전환율, 보관/복원) · `채널 · 캠페인`(추가·편집·활성 전환). 통계 탭 하단에 채널/캠페인/링크별 성과, 일별 클릭 대 입력, “UTM 직접 유입”(단축코드 없이 utm만 있는 입력)을 표시한다.
- 단축 링크 `/l/{6자 코드}`(l·o·0·1 제외): 사이트 내부 경로 + `utm_*` + `sc=코드`로 302(no-store). 미리보기 봇·HEAD·UA 없음은 `counted=0`으로 따로 기록. 모르는/보관된 코드는 `/?utm_source=short-link&utm_medium=unknown`. 클릭 기록에는 IP·UA 원문을 저장하지 않고 `ua_family`(예: `kakaotalk-inapp`)만 남긴다. 목적지는 `/`로 시작하는 경로만(외부 URL·`//`·`\`·`:`·`..`·`/admin`·`/api`·`/l` 불가). QR 생성은 새 의존성 없이 구현하지 않았다.
- 유입 추적: 랜딩 URL의 `utm_source/medium/campaign/content/term`과 단축코드 `sc`를 첫 유입 기준으로 브라우저에 보관했다가 계산 요청의 `client` 객체로 보낸다.

## 개인정보와 배포

출생 입력과 이름, 무작위 방문자 ID, UTM은 계산 요청 시 관리자 전용 SQLite에 저장된다(입력 화면에 고지). 관리자만 열람하며 요청 시 입력 기록 또는 방문자 단위로 삭제한다. 서버는 접근 로그를 남기지 않으며 외부 분석/LLM을 호출하지 않는다. 다운로드 기능을 사용하면 선택한 결과를 로컬 파일로 저장한다. 참조 자료와 결과 파일은 개인정보로 취급한다.

`python server.py`는 로컬 전용 개발 서버다(127.0.0.1 바인딩). 공개 배포는 아래 Vercel 경로로만 하며, 공개 전 사용자 인증·운영 보안·지역/역사 검증을 별도로 수행해야 한다. [Swiss Ephemeris 라이선스 안내](https://www.astro.com/swisseph/swephprg.htm)에 따라 공개 서비스/배포 전에 라이선스 경로를 확정하고, Python binding의 별도 AGPL 조건도 함께 검토해야 한다. 상용 Swiss 라이선스만으로 binding의 조건까지 해결된다고 가정하지 않는다. 유료 구매나 공개 배포는 수행하지 않았다.

## 배포 전 라이선스 확인

- **Swiss Ephemeris**: 이중 라이선스(AGPL 또는 Astrodienst 상용 라이선스). 공개 서비스는 AGPL 조건(서버 이용자에게 전체 소스 공개 — 공개 GitHub 레포가 이를 돕지만 충족 여부는 직접 확인) 또는 상용 라이선스 구매 중 하나를 확정해야 한다. `pyswisseph` binding의 AGPL 조건도 별도 검토한다.
- **Open-Meteo 지오코딩**(`/api/places`): 무료 API는 비상업적 이용만 허용한다. 상업적 서비스라면 유료 API 키/플랜 또는 다른 provider가 필요하다. 이번 변경은 동작을 바꾸지 않았다.
- `data/ephe/` 파일의 배포(재배포) 조건도 Swiss Ephemeris 라이선스를 따른다.

## Vercel + Neon 배포

구성: 모든 경로를 `vercel.json` rewrite로 `api/index.py`(Vercel Python runtime, `ChartHandler` 재사용)에 보낸다. `web/`, `natal/`, `data/ephe/`, `data/manifest.json`, `server.py`는 `functions.includeFiles`로 함수에 포함한다. `outputDirectory: public`에는 `robots.txt`만 있어 저장소의 다른 파일이 정적 파일로 노출되지 않는다(Vercel은 rewrite보다 정적 파일을 먼저 찾는다). Python은 `.python-version`으로 3.12 고정.

1. Vercel 프로젝트의 **Storage → Create Database → Neon**(Marketplace)으로 DB를 만들고 프로젝트에 연결한다(리전은 Vercel 함수 리전과 가깝게). 통합이 `DATABASE_URL`(pooled, PgBouncer), `DATABASE_URL_UNPOOLED`(direct), `PGHOST`·`PGUSER`… 및 호환용 `POSTGRES_*` 변수를 자동 주입한다.
2. Neon 콘솔 **SQL Editor**에서 `db/schema.sql` 전체를 실행하거나 `psql "$DATABASE_URL_UNPOOLED" -f db/schema.sql`을 쓴다. 여러 번 실행해도 안전하다(IF NOT EXISTS). 모든 테이블에 RLS를 켜고(정책 없음 → 소유자 외 거부), `anon`/`authenticated` 역할이 있는 환경에서만 권한을 회수한다(Neon에는 없어 건너뜀). 서버는 소유자 계정으로 접속한다.
3. 앱은 `DATABASE_URL`(없으면 `POSTGRES_URL`)을 그대로 쓴다. pooled 연결은 PgBouncer transaction 모드라 서버는 prepared statement를 끈다(`prepare_threshold=None`). URL의 `sslmode=require`를 지우지 않는다.
4. 이 폴더를 **공개 GitHub 레포**로 push한 뒤(`.gitignore`가 `.venv/`, `ref/`, `artifacts/`, `.env*`, `data/admin.sqlite3*` 등을 제외하는지 확인) Vercel에서 **Add New → Project → Import**한다. Framework Preset은 `Other`.
5. **Settings → Environment Variables**(Production)에 설정한다(값은 `.env.example` 참고, 실제 값은 파일에 쓰지 않는다):
   - `DATABASE_URL` — Neon 통합이 자동 주입(pooled). 수동 설정 시 `-pooler` 호스트 문자열
   - `NATAL_ADMIN_PASSWORD` — 긴 비밀번호
   - `NATAL_ADMIN_SECRET` — 32자 이상 임의 문자열. **Vercel에서는 필수**(없으면 관리자 503: 인스턴스마다 다른 임의 키로는 세션이 유지되지 않는다). DB URL이 없어도 관리자는 503.
   - `NATAL_ALLOWED_HOSTS` — 처음에는 비워 두어도 된다.
6. Deploy.
7. 배포 도메인(예: `my-app.vercel.app`)과 커스텀 도메인을 `NATAL_ALLOWED_HOSTS=my-app.vercel.app,www.example.com`으로 설정한다. (Vercel이 주는 `VERCEL_URL`·`VERCEL_BRANCH_URL`·`VERCEL_PROJECT_PRODUCTION_URL`은 자동 허용되지만, 커스텀 도메인은 반드시 이 변수에 넣어야 한다.)
8. Redeploy 후 `/`, `/api/health`, `/admin/login` 로그인(쿠키에 `Secure`), 단축 링크 `/l/...`를 확인한다.

운영 동작:
- Host/Origin 검사: 허용 호스트 = `NATAL_ALLOWED_HOSTS` + (로컬이면 `127.0.0.1:포트`, `localhost:포트`; Vercel이면 Vercel 도메인). `X-Forwarded-Host`/`X-Forwarded-Proto`/`X-Real-IP`는 `VERCEL` 환경변수가 있을 때만(=Vercel edge가 설정한 값) 신뢰한다.
- 단축/UTM URL은 관리자 화면이 현재 접속한 허용 호스트(`window.location.origin`) 기준으로 만든다.
- `DATABASE_URL` 없이 Vercel에 올리면 입력 기록은 저장되지 않고(읽기 전용 파일시스템) 관리자는 503이다.
