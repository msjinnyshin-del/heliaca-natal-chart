# 참조 자료 비교 방법

개발 중에는 비공개 참조 차트(외부 앱 화면·저장 HTML)의 **관찰값**과 실제 Swiss 계산을 비교해 엔진 설정을 점검했다. 그 참조 차트는 실존 인물의 출생 정보이므로 공개 저장소에는 입력값·관찰값·잔차를 싣지 않는다(원본은 git 제외 `ref/`에만 로컬 보관). 저장소의 테스트는 가상 인물 기준(1985-07-14 21:45 America/New_York, 40.7128, −74.006)의 **엔진 회귀 스냅샷**만 사용하며, 이는 독립 외부 검증이 아니다.

## 비교 절차

1. 입력부터 맞춘다: 날짜·시각·IANA 시간대·정밀 좌표. 같은 인물이라도 자료마다 좌표가 다르면 ASC/MC 차이는 오류 증거가 아니다. 다른 인물·다른 시각의 차트끼리는 비교하지 않는다.
2. 설정을 맞춘다: True/Mean Node, Mean/Osculating Lilith, 하우스 시스템, Fortune 주야 공식, 반올림(최근접 초 vs truncation). 저장 JSON에 `True Node:false` 같은 설정이 있으면 그 설정으로 비교한다.
3. 시간척도를 확인한다: `utc_to_jd`의 TT/UT1 분리. civil UTC JD를 `swe_calc(TT)`에 넣으면 달에서 소수 4자리 수준의 차이가 난다. 외부 값이 그 패턴과 일치하면 **시간척도 혼동 가능성에 대한 추론**으로만 기록한다.
4. 잔차를 그대로 남긴다: 관찰값에 맞추기 위한 상수 보정은 하지 않는다. 외부 앱의 엔진 버전·ΔT 처리·숨은 옵션이 미확인이면 결과는 **화면 호환성 검사**이며 PROJECT_SPEC §13의 동일 설정 ≤1″ 인증이 아니다.

개발 당시 관찰(수치 없이): 행성/노드/Lilith는 0–1″, ASC/MC/Fortune은 2–4″ 잔차가 남았고, 한 저장 HTML은 Mean Node 설정 및 civil-UTC-as-TT 계산과 부합했다.

## 구현 및 해석 경계

- 휠·천체표·주요 포인트·하우스·어스펙트·좌표/시간/flags 증거를 계산한다. 원시 황경에 기반하며 라벨 충돌 회피로 실제 위치를 바꾸지 않는다.
- 정확한 외부 앱 이름/버전은 미확인. 유료라는 사실 자체가 수치 정확성의 증거는 아니다.
- Almuten Figuris, Auriga, Doryphoros, period/year lord, 항성 선택, V% 기준, term/face의 선택표, N/U 규칙은 screenshot만으로 완전 복원 불가. 미검증 결과를 하드코딩하지 않는다.
- 노드·Lilith·Fortune·오브·반올림·좌표 선택은 각각 별개 설정이다. 모든 앱의 기본값이 같다는 전제는 금지한다.

공식 근거: [Swiss API](https://www.astro.com/swisseph/swephprg.htm), [Swiss 고정 데이터](https://github.com/aloistr/swisseph/tree/9083a12d59e98034fb2337061481ac8800c16e64/ephe), [ZET 표 열 정의](https://astrozet.net/usermanual/zet9/65), [ZET 계산 옵션](https://astrozet.net/usermanual/zet9/138).
