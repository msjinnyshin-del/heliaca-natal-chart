# 기준 차트 재현 구현 계획

기준: PROJECT_SPEC.md. 사용자 요청: 세 자료의 차이를 먼저 분석하고 2번의 실제 계산 결과에 가깝게 생성한다. 단순 수치 복사나 역산 보정은 금지한다.

## 구조와 범위

Python 3.9+, pyswisseph 2.10.3.2(Swiss 2.10.03), tzdata 2025.2(IANA 2025b), 고정 공식 ephe 3파일. Python stdlib loopback HTTP server와 의존성 없는 ES module/SVG UI. 첫 구현은 reported 시각의 실제 네이털 계산과 기준값 비교. 생시 미상은 지원된 것으로 노출하지 않으며 요청하면 명확히 거절한다. 해석/Almuten Figuris/프로프렉션 등 미검증 기능은 계산한 것처럼 표시하지 않는다.

- Task 1: `natal/` 계산 adapter, 시간 정규화, 규칙, `tests/test_engine.py`, 고정 manifest, `requirements.txt`. 실제 failing tests → 구현 → 전체 tests.
- Task 2: `web/` 입력/휠/천체표/하우스/어스펙트/비교/근거 UI와 JS geometry tests. Task 1과 병렬로 아래 계약에 의존.
- Task 3: `server.py`, API integration tests, 참조 비교 문서/README, 브라우저 검증. 두 작업 통합 후 별도 reviewer.

## API 계약 (Task 1 생산, Task 2 소비, Task 3 전달)

`POST /api/chart` → `natal.engine.calculate_chart(payload: dict) -> dict`. 오류는 `natal.errors.ChartError(code, message, details=None)`; HTTP 422 `{error:{code,message,details}}`. payload:

```json
{"date":"1985-07-14","time":"21:45:00","timezone":"America/New_York","latitude":40.7128,"longitude":-74.006,"place":"New York, New York, USA","house_system":"P","node_mode":"true","time_accuracy":"reported","fold":null}
```

선택 하우스 P/W/E/K/O, Node true/mean. 장소는 제공된 정밀 좌표+IANA를 직접 입력하거나 명시적 로컬 preset(외부 geocoding 없음). 이름은 선택/서버 계산에 불필요. 반환:

```json
{
 "status":"calculated",
 "input":{},
 "normalized":{"utc":"1985-07-15T01:45:00Z","offset":"-04:00","timezone":"America/New_York","latitude":40.7128,"longitude":-74.006,"jd_tt":2446261.5735553703,"jd_ut1":2446261.5729230656},
 "settings":{"house_system":"P","node_mode":"true","lilith_mode":"mean","zodiac":"tropical","rounding":"nearest_second"},
 "bodies":[{"id":"Sun","name":"태양","symbol":"☉","longitude":112.52751159426715,"latitude":0.0,"speed":0.95,"retrograde":false,"house":6,"sign_index":3,"position":"게 22°31′39″","declination":21.56,"altitude":-12.75,"antiscia":67.47248840573285,"flags":258}],
 "angles":[{"id":"ASC","longitude":319.33084029039867,"sign_index":10,"position":"물병 19°19′51″"}],
 "houses":[{"number":1,"longitude":319.33084029039867,"sign_index":10,"position":"물병 19°19′51″"}],
 "aspects":[{"a":"Sun","b":"Mars","name":"Conjunction","angle":0,"separation":0.9256488,"orb":0.9256488,"allowed_orb":10}],
 "sect":"night",
 "metadata":{"engine":"Swiss Ephemeris","engine_version":"2.10.03","binding_version":"2.10.3.2","tzdb":"2025b","profile":"reference-tropical-v1","data":[]},
 "warnings":[]
}
```

body IDs: Sun Moon Mercury Venus Mars Jupiter Saturn Uranus Neptune Pluto NorthNode SouthNode Lilith Chiron Fortune Spirit. angles ASC MC DSC IC. Fortune/Spirit의 speed/retrograde/latitude/declination/altitude는 null을 허용하며 house/position은 실제 계산한다. Spirit은 명시적 Lot of Spirit 공식이며 이미지의 다이아몬드 명칭 확인과 구분한다. 기본 어스펙트는 10행성 상호 및 10행성↔추가 body/angle의 주요 어스펙트다(추가 대상끼리 제외). Applying·dignity는 미검증 상태에서 표시하지 않는다.

## 검증 기준

원본 screenshot2는 다른 엔진/버전/시간 설정이 미확인. §13 동일 설정 ≤1″ 인증으로 취급하지 않는다. 기록된 외부 관찰값과 차이를 그대로 공개한다. 초기 관찰 기준 10행성·노드·Lilith ≤2″, ASC/MC/Fortune ≤5″, 그림의 분 단위 커스프 ≤60″. 이는 screenshot 호환성 검사이지 수치 정확성 인증이 아니다. 별도 core test는 Swiss 호출 경로와 설정/경계 확인.

필수 tests: 실제 screenshot 값, 날짜 다음날 UTC, Mean/True Node 차이, 다른날 입력 값 변화, DST gap/fold, invalid/future date/NaN/범위, 생시 미상 거부, 극지 Placidus 실패, Whole Sign vs Equal, house wrap/boundary, 누락/손상 파일 실패 및 Moshier 거부, 주야 Fortune 반전, 전체 엔진 직렬화, 출력 반올림 carry와 raw classification 분리.

## 진행 기록

- [x] 비교 자료 텍스트 추출과 실제 Swiss 탐색 계산.
- [x] Task 1 엔진 및 테스트: 엔진 20건 통과, 시간 경계 P2 수정 재검토 완료.
- [x] Task 2 프런트 및 tests: 기하/요청 상태 8건 통과, 실제 위치 유지하며 라벨만 충돌 회피.
- [x] Task 3 통합/독립 검토/브라우저 QA: HTTP 7건, 실제 Chrome 8건 통과. 독립 리뷰 P2 3건(DST선택, SVG스타일, stale저장) 수정 확인. 전체 출시/동일 설정 1초각 인증과 구분.

작업 폴더는 git repository가 아니므로 worktree/commit 절차는 적용 불가. 기존 사용자 파일은 유지한다. 승인된 프로젝트 명세와 개발 진행 요청에 따라 반복 설계 승인 없이 이 범위를 구현한다.

시간대 판정에 대한 보수적 구현 결정: 초기 운영 범위를 1970년부터 현재까지로 한정하고 이전 날짜는 TIMEZONE_NEEDS_REVIEW로 거절한다. 지리 좌표와 IANA의 일치 여부는 사용자가 확인하며 전 세계 자동 판정 기능으로 소개하지 않는다.
