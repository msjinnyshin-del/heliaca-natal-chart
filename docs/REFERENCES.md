# 프로젝트 레퍼런스와 확인 상태

확인일: 2026-09-21. 사용자가 제공한 사이트를 개발 참고용으로 정리했다. 기본 계산 규칙은 [프로젝트 명세](PROJECT_SPEC.md)를 따른다. 사이트 추가는 해당 기능의 구현 확정이나 기본값 변경을 뜻하지 않는다.

## 사용 순서

1. 아래 표에서 기능·디자인·수치 비교에 맞는 자료를 고른다. 페이지 설명 확인과 계산 정확성 검증을 구분한다.
2. 수치 비교 전 프로젝트 명세 §13.1의 입력·설정 일치 조건을 기록한다. Almuten을 비교할 때는 이 문서의 추가 비교 항목도 기록한다.
3. 같은 조건의 수치·점수 내역을 재현한 후에만 검증 사례로 채택한다. 결과가 다르면 설정·중간 계산부터 조사한다.

현재까지 공개 페이지와 문서를 읽었으며 사용자 출생 정보 입력, 계정 생성, 프로그램 설치, 실제 계산 결과 대조는 수행하지 않았다. 아래 모든 사이트의 수치 정확성은 **미검증**이다.

## 1. 차트·기능·화면 참고

| 자료 | 프로젝트에서 참고할 용도 | 직접 확인한 내용과 한계 |
| --- | --- | --- |
| [Astrodienst / astro.com](https://www.astro.com/cgi/genchart.cgi) | 행성·각도·하우스 결과의 우선 비교 후보, 상세 설정 흐름 | Extended Chart Selection 진입 화면 확인. 이번 열람에서는 출생 정보/프로필 진입 단계까지만 확인했으며 실제 결과와 개별 설정 동작은 미확인 |
| [Astro-Seek](https://www.astro-seek.com/) | 네이털·관계 차트·트랜짓·프로그레션 등의 기능 구성과 결과 표 참고 | 직접 열람은 403으로 제한됨. 검색 색인의 해당 사이트 안내에서 Synastry·Composite·Davison·Secondary Progressions 메뉴를 확인했으나 색인이 오래되어 현행 동작은 미확인 |
| [Astro-Charts](https://astro-charts.com/tools/new/birth-chart/) | 입력 폼, 차트 레이어, 패턴 표시 방식 | 입력 폼과 사이트의 하우스/레이어 설정·패턴 탐지 기능 설명 확인. 결과 화면, 판정 오브, 실제 패턴 검출 정확성은 미확인 |
| [Morinus 8.1.0 배포처](https://sourceforge.net/projects/morinus/files/Morinus/) | 전통 점성술 표와 동일 설정의 보조 수치 대조 | [개발자 페이지](https://sites.google.com/site/pymorinus7/)에서 배포처 연결·현대판 종료·알려진 버그 공개 확인. 버전과 옵션을 고정해야 하며 유일한 정답 기준으로 사용하지 않음 |

사용자 표의 ‘모든 기능 무료’, ‘한국어 일부 지원’, ‘Almuten 미지원/부분 지원’은 별도 확인 전 확정된 비교 정보로 재사용하지 않는다. 기능 설명이 없다는 이유만으로 미지원으로 판정하지 않는다. Astro-Charts의 자동 탐지 결과도 프로젝트 명세 §6의 검출 규칙을 자동으로 대체하지 않는다.

## 2. Almuten 계산기 후보

### Augurine — Figuris 규칙과 결과 구조 참고

[Almuten Figuris Calculator](https://www.augurine.com/tools/almuten-figuris-calculator) 본문에서 전통 7행성, Sun·Moon·ASC·Fortune·가용한 prenatal syzygy, dignity 점수 5/4/3/2/1, Dorothean triplicity, Egyptian bounds, 요일 +7·행성시 +6·하우스 보너스, 야간 Fortune 반전, Whole Sign 기본값을 확인했다. 동점 공동 1위 표시도 설명한다.

프로젝트의 **점수 근거를 펼쳐 보여주는 UI 후보**다. Triplicity의 각 지배자에게 실제로 점수를 배분하는 조건, syzygy 누락 시 결과 처리, 일출/일몰 계산 조건, 문서와 실제 구현의 일치는 추가 확인이 필요하다. Whole Sign을 프로젝트의 Placidus 기본값으로 착각해 비교하지 않는다. 해당 사이트의 계산값을 검증된 정답으로 등록하지 않는다.

### Astrolium — 점수표 참고, 설명의 불일치 확인 필요

사용자 원본 링크는 [Essential Dignities](https://astrolium.com/tools/essential-dignities)다. 이번 도구에서는 원본 접근이 실패하여 [동일 사이트 프랑스어 설명](https://astrolium.com/fr/tools/essential-dignities)을 읽었다. 전통 7행성 dignity 표와 5지점 Figuris 점수표, Dorothean triplicity, Egyptian bounds 기본값 및 Ptolemaic 옵션을 안내한다. 실제 펼침 UI와 점수 결과는 실행하지 않았다.

본문의 ‘처녀자리 6° Mercury’ 예시는 Mercury에 지구 원소의 낮 triplicity 점수를 더하지만, 같은 페이지의 지구 낮 지배자 표는 Venus다. **설명 내부의 불일치**이며 이것만으로 실행 엔진도 틀렸다고 단정하지 않는다. 보너스 포함 범위와 Fortune 공식도 해당 페이지에서 확인되지 않았다. Dignity 상태표의 detriment/fall 감점을 Figuris의 지점별 점수에도 적용하는지는 별도 확인 대상이다.

### Şira Nur Uysal — 단일 지점 Almuten

[Almuten Calculator](https://sirauysal.com/en/tools/almuten-calculator/)는 사인·도수·주야를 입력하는 **단일 황도 지점** 계산기다. 본문에서 5/4/3/2/1 점수, 주야별 triplicity, Egyptian bounds, Chaldean face 규칙을 확인했다.

태양·달·ASC 등의 각 지점에서 dignity 점수를 대조하는 후보로 쓸 수 있다. 이 입력 폼 자체를 출생 정보에서 Fortune·prenatal syzygy·요일·행성시까지 산출하는 전체 Almuten Figuris 계산기로 분류하지 않는다. 계산 결과와 표 경계는 아직 검증하지 않았다.

## 3. Almuten 비교 시 추가로 맞출 조건

이 항목은 후보 자료 평가용이다. 실제 기능을 구현할 때 채택 규칙을 프로젝트 명세에 버전과 함께 정의한다.

| 비교 항목 | 기록해야 할 내용 |
| --- | --- |
| 계산 대상 | 특정 도수의 Point Almuten / 5지점 Figuris / topical 등 어느 계산인지 |
| 참여 행성·지점 | 전통 7행성, Sun·Moon·ASC·Fortune·prenatal syzygy의 원시 도수, 누락 지점 처리 |
| Dignity 표 | Domicile·exaltation·triplicity·bounds·face의 출처와 버전, 경계 포함 방향 |
| 점수 | 항목별 가중치·중복 합산·감점 적용 범위; 각 행성 자신의 dignity와 특정 지점에 대한 지배 점수를 구분 |
| Triplicity | 주야별 한 지배자 또는 복수 지배자 적용 여부, participating ruler 처리 |
| Fortune·syzygy | Fortune 주야 공식, 출생 직전 삭/망 선택, 만월 시 사용할 도수의 정의, 정확한 사건 시각 |
| Accidental 보너스 | 하우스 시스템·소속 방식·가중치, 태양 위상 등 추가 항목의 포함 여부 |
| 요일·행성시 | 자정/일출 등 요일 경계, 행성시 계산법, 일출/일몰의 태양 중심·가장자리·굴절 조건, 극지 예외 |
| 결과 | 지점별·항목별 점수, 소계·총점, 공동 최고점과 tie-break 정책, 계산 규칙 ID |

[Morinus의 Almutens 설명](https://sites.google.com/site/pymorinus/)도 essential 설정과 accidental 설정, triplicity의 OneRuler 선택 등을 구분한다. 따라서 ‘Morinus와 일치’만 기록하지 말고 **어느 버전의 어떤 옵션과 일치하는지** 남긴다. 최고점은 선택한 점수 규칙의 결과이며 기존 Chart Ruler를 대체하거나 삶의 유일한 지배자로 단정하지 않는다.

검증 사례에는 주간/야간, 일출 전후, dignity 표 경계, 동점, 다른 하우스 시스템, syzygy 확보 실패를 포함한다. 생시 미상에서 ASC·Fortune·행성시 등을 임의로 채워 완전한 Figuris 결과를 만들지 않는다. 일부 점수만 계산하면 그 범위와 누락을 명시한다.

## 4. 다음 단계에 넘길 상태

- 기능·화면 참고 후보: astro.com, Astro-Seek, Astro-Charts 및 사용자 제공 차트 이미지.
- 수치 비교 후보: astro.com, Morinus. 기본 검증 절차는 프로젝트 명세 §13을 유지한다.
- Almuten 확장 참고 후보: Augurine의 Figuris 구조, Astrolium의 점수표 구성, Şira Uysal의 단일 지점 계산.
- **검증 완료된 기준값: 아직 없음.** 후보 소개 문구·점수 설명·사이트 평판을 수치 검증 통과로 취급하지 않는다.
