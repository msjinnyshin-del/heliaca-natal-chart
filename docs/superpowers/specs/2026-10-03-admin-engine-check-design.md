# 관리자 엔진 검토 페이지 (Engine Inspector) 설계

작성 2026-10-03. 참조: SAJU&CO `engine-check.html`(사주 엔진 검토 페이지)의 구성을 서양 점성술 엔진에 맞춰 옮긴다.

## 목적

- 관리자가 출생 입력 → **엔진 출력 전체**를 한 화면에서 필드별로 대조한다. 외부 참조 앱(Astro-Seek 등)을 옆에 띄워 수치를 맞춰 보는 용도.
- 서비스 프론트(`/`, 도구 페이지)와 무관하다. 해석·요약·숨김 없이 엔진이 돌려준 값을 그대로 보여준다.
- 네이털·시너스트리·컴포지트·트랜짓·솔라 리턴·세컨더리 프로그레션 **6개 계산 모두**를 다룬다.

## 범위 밖

- 엔진·규칙 변경. 프론트는 수치를 생성·보정하지 않는다.
- 입력 저장. 관리자 검토 입력은 `submissions`에 기록하지 않는다(통계 오염 방지).
- 공유 링크, 비관리자 접근.

## 구성

### 서버 (`server.py`)

- 정적: `/admin/engine-check.html`, `/admin/engine-check.js`를 `ADMIN_PRIVATE_FILES`에 추가(로그인 필요, noindex, 기존 CSP 유지).
- API: `POST /api/admin/engine/<tool>` (`tool` ∈ `chart, synastry, composite, transits, solar-return, progressions`). 관리자 세션 + 같은 출처(Origin) 검사 후 해당 계산 함수를 호출하고 결과를 그대로 반환한다. `store.record_submission`을 호출하지 않는다. 에러는 기존 `ChartError` → 422, 그 외 → 500 규칙 그대로.

### 프론트 (`web/admin/engine-check.html`, `engine-check.js`, `admin.css` 추가분)

- **입력 영역**
  - 사람 A·B 폼: `tool-page.js`의 `mountPerson`을 export 해 재사용(이름·양력/음력/윤달·날짜·시각·생시 모름·장소 검색·수동 좌표). B는 시너스트리·컴포지트에서만 보인다.
  - 공통 설정: 하우스 시스템, Node, Lilith, 어스펙트 대상·부가 어스펙트·오브 배율·추가점 오브(메인 페이지와 동일 `aspect_profile` 구조).
  - 도구 선택 탭: 네이털 / 시너스트리 / 컴포지트 / 트랜짓 / 솔라 리턴 / 프로그레션. 트랜짓·프로그레션은 시점(날짜·시각·시간대, 기본 지금·브라우저 시간대), 솔라 리턴은 연도와 장소(기본 출생지).
  - 빠른 입력: 내장 가상 인물 1건(1985-07-14 21:45 New York, 테스트 기준) + 이 브라우저의 저장 프로필(`profiles.js`). 칩마다 `A`/`B` 버튼. "현재 입력 저장" 버튼으로 프로필 추가.
- **출력 영역** — 하나의 섹션 모델 `{title, note?, columns, rows}`를 DOM 표와 Markdown 표 양쪽으로 렌더링한다. 결과에 있는 **모든 최상위 키**를 다룬다. 명시 렌더러가 없는 키는 JSON 블록으로 그대로 출력해 누락이 없게 한다.
  - 차트 공통(네이털·트랜짓 시점·귀환·진행·컴포지트): 상태·규칙 버전, 입력 echo, 정규화(UTC·오프셋·JD TT/UT1·ΔT·해석 기준), 설정, 천체 표(황경 소수·표기·사인·하우스·황위·속도·역행/정지·적위·고도·안티샤·플래그), 각도, 하우스 커스프, 어스펙트(대상·종류·목표각·실제 분리각·오브·허용 오브·접근/분리·그룹), 주야, 메타데이터(엔진/바인딩/tzdb/데이터 파일/fingerprint/미평가 항목), 경고.
  - 생시 모름: `unknown_time`(스캔 범위·시간), 천체별 `time_range`/사인 진입·정지, 어스펙트 `stability`·`windows`.
  - 시너스트리: 상호 어스펙트(strength·strong 포함), 하우스 오버레이 A→B·B→A, 설정.
  - 컴포지트: 미드포인트 차트(천체·각도·하우스·어스펙트), 입력·정규화·설정.
  - 트랜짓: 트랜짓→네이털 어스펙트(slow·retrograde 포함), 트랜짓 천체의 네이털 하우스, orb 설정.
  - 솔라 리턴: `exact`(UTC·JD·현지·태양 황경·잔차), `return_window`, 귀환 천체의 네이털 하우스, 설정.
  - 프로그레션: `age_years`·`solar_arc`·`target`, 진행→네이털 어스펙트, 진행 천체의 네이털 하우스, 설정.
  - 네이털 휠(`createNatalWheel`)은 시각 확인용으로 네이털 탭에만 그린다.
  - 맨 아래 `원본 JSON` `<details>`.
- **MD 복사**: 섹션 모델 전체를 Markdown 표로 직렬화 + 원본 JSON 코드블록. 해석용 MD(`interpretation-export.js`)와 별개.
- 상태 표시: 계산 중·완료·오류(코드+메시지+details). 입력이 바뀌면 "다시 계산 필요" 배지.

## 데이터 흐름

폼 → 도구별 payload 조립(기존 도구 페이지와 동일 구조: `natal`/`person_a`/`person_b`/`moment`/`year`/`location`) → `POST /api/admin/engine/<tool>` → 결과 JSON → 섹션 모델 → DOM + Markdown. 출생 원문은 URL·로그에 담지 않는다(프로필은 localStorage).

## 오류 처리

- 422: 엔진 오류 코드·메시지·details를 결과 영역 상단에 표시한다.
- 401: 로그인 페이지로 이동. 503: 관리자 비활성 메시지.
- 네트워크 오류: 메시지 표시, 이전 결과 유지(stale 배지).

## 검증

- `tests/test_admin.py`: 비로그인 시 정적 파일 303·API 401, 로그인 후 6개 도구 각각 200과 핵심 키 존재, Origin 없는 POST 403, 계산 후 `submissions` 건수 0 유지, 잘못된 tool 이름 404, 422 전달.
- 브라우저: 로컬 서버에서 각 탭 실제 계산·렌더·MD 복사 확인(스크린샷).
- 기존 테스트 전체 통과.
