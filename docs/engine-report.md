# 계산 엔진 구현 및 검증 기록

2026-09-21. 담당 범위: `natal/`, `tests/test_engine.py`, `requirements.txt`, `data/manifest.json`.

## 구현 결과

`natal.engine.calculate_chart(dict)`가 고정 Swiss Ephemeris 2.10.03 / pyswisseph 2.10.3.2와 공식 천체력 세 파일로 실제 계산한다. IANA 2025b는 tzdata 2025.2 패키지 파일을 직접 열어 OS 시간대 데이터와 분리했다. 본 프로필은 geocentric apparent tropical, 요청/반환 flags 258, Placidus 기본, True/Mean Node 선택, Mean Lilith, Chiron을 사용한다.

현지 시각→UTC→Swiss `utc_to_jd`의 TT/UT1 분리, 10행성·노드 대척·Lilith·Chiron, ASC/MC/DSC/IC, 12커스프, 실제 적위/기하학적 고도, 주야 Fortune/Spirit, antiscia, 황경 기반 하우스 소속, 10행성 상호 및 10행성↔추가 대상의 5개 주요 어스펙트를 구현했다. Fortune/Spirit의 실제 천체 적위·속도를 만들어 넣지 않으며 해당 필드는 null이다. 표시 최근접 초의 carry와 원시 사인·하우스 판정을 분리했다.

전체 Swiss 전역 상태 트랜잭션을 하나의 lock으로 직렬화한다. 매 요청 데이터 SHA-256과 버전을 검증하고 실제 열린 파일 경로·JD 범위를 검사한다. Moshier/JPL fallback, flags 변경, 비유한값, 누락·손상 파일, 고정되지 않은 추가 천체력/시간 보정 파일과 외부 경로 override를 거부한다. 해당 프로필은 Chiron 데이터 실패도 blocked로 처리한다.

지원 입력은 **1970-01-01 이후 현지 Gregorian 날짜이며 확정 UTC 시각이 현재보다 늦지 않은 reported 시각**이다. 1900–1969는 역사 시간대 검토 필요(`TIMEZONE_NEEDS_REVIEW`), 1900년 이전과 미래 시각은 `UNSUPPORTED_DATE`다. approximate/unknown, 음력, 윤초 입력은 명시적으로 거부한다. 수동 좌표와 IANA zone의 지리적 일치 확인은 사용자 책임으로 반환한다. 외부 geocoding 또는 개인 출생 데이터 전송은 없다.

## 실제 수행한 검증

먼저 adapter가 없는 상태에서 참조 literal 테스트를 실행했고 `실제 calculate_chart adapter가 필요합니다` assertion failure를 확인했다. 구현 후 아래 명령으로 20개 엔진 테스트를 통과했다.

```sh
.venv/bin/python -m unittest discover -s tests -p test_engine.py -v
```

- 가상 인물(1985-07-14 21:45 America/New_York, 40.7128/−74.006) 기준 10행성·True Node·Mean Lilith·ASC/MC/Fortune **엔진 회귀 스냅샷**(≤1초각). 독립 외부 검증이 아니다.
- 개발 중에는 비공개 외부 앱 화면 두 건(실존 인물 차트)과 행성 ≤2″, ASC/MC ≤5″ 호환성을 확인했으나, 개인정보 보호를 위해 공개 저장소의 테스트·문서에서는 제거했다.
- UTC 다음날 전환, New York/London DST gap/fold 및 두 UTC 후보, 1988 한국 DST, 인도 30분·네팔 45분 offset, Apia 날짜 건너뜀.
- 유효하지 않은 날짜·시각·달력, NaN/Infinity·범위 밖·400자리 정수 좌표, 잘못된 zone/옵션, 생시 미상/추정 시각 거부, 역사/미래 범위.
- local 다음날이 이미 지난 시각인 경우 허용 및 UTC 당일의 미래 시각 거부. 두 결함의 회귀 실패를 먼저 관찰하고 수정했다.
- P/W/E/K/O 정상 계산, 극지 P/K 실패, Whole Sign/Equal의 MC 독립성, 커스프 정확 경계 및 0° wrap.
- True/Mean Node 차이, 실제 True Node 순행 날짜, 노드/각도 대척, 주야 Lot 반전과 태양 고도 정확 0° 경계.
- 오브 정확 경계·경계 밖, Sun–Moon +2° 한 번만 가산, 추가 포인트 3° 상한, 추가 대상 상호 제외.
- 초 반올림 사인 경계/360° carry와 원시 sign 분리, 반복 호출 동일 결과, 다른 시점 결과 변화, JSON 유한성.
- 실제 파일 누락/손상/추가 보정 파일 거부, Moshier/비유한값/flags 변경 거부, 고정 tzdata mismatch 거부.
- 4개 thread에서 다른 장소·시스템·Node 설정을 반복 호출하여 단일 계산 동시 진입 수 1과 직렬 결과의 일치를 확인.

## 외부 화면 원시 잔차

비공개 참조 차트의 입력·잔차 표는 실존 인물의 출생 정보라 공개 저장소에서 제외했다. 방법과 해석 경계는 [참조 비교](REFERENCE_COMPARISON.md)에 남긴다. 당시 결과는 행성/노드/Lilith 1″ 미만, ASC/MC/Fortune 2–4″ 잔차였고, 값을 이미지에 맞추는 보정은 하지 않았다.

## 남은 제약

독립 `swetest` 동일버전 원시 fixture, 완전한 전 세계 역사 시간대/경계 검증, unknown/approximate 민감도, dignity/pattern/applying-separating, 해석과 확장 기능은 미구현/미검증으로 metadata에 명시한다. 이름을 계산에 사용하지 않으며 입력 fingerprint는 반환 결과 내부 증거이고 공개 로그로 전송하지 않는다. Swiss 라이선스 선택·공개 배포 승인은 별도이며 이번 로컬 구현이 그 승인이나 출시 인증은 아니다.

공식 API 근거: [Swiss Programmer's Manual](https://www.astro.com/swisseph/swephprg.htm). 데이터 출처와 고정 commit/hash는 [manifest](../data/manifest.json), 외부 자료의 차이는 [참조 비교](REFERENCE_COMPARISON.md)에 기록했다.
