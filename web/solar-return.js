import { createNatalWheel } from './chart.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, TIME_DEPENDENT_NOTE, conditionalHeading, mountPlaceSlot, mountToolPage, orbText, rangeText, splitStability } from './tool-page.js';

const SIGNS = ['양', '황소', '쌍둥이', '게', '사자', '처녀', '천칭', '전갈', '사수', '염소', '물병', '물고기'];
const yearInput = document.querySelector('#return-year');
const samePlace = document.querySelector('#same-place');
const placeWrap = document.querySelector('#return-place-wrap');

// Default: the birthday return of the current year.
yearInput.value = String(new Date().getFullYear());
let page = null;
const returnPlace = mountPlaceSlot(document.querySelector('[data-place-prefix]'), () => page?.invalidate());
samePlace.addEventListener('change', () => { placeWrap.hidden = samePlace.checked; page?.invalidate(); });

function location(natal) {
  if (!samePlace.checked) return returnPlace.payload();
  const { latitude, longitude, timezone, place, location_source: source } = natal;
  return { latitude, longitude, timezone, place, location_source: source };
}

const point = (chart, id) => [...chart.bodies, ...chart.angles].find((item) => item.id === id);
const signOf = (item) => (item ? SIGNS[item.sign_index] : '—');

function definitionList(entries) {
  const list = make('dl', 'metadata-list');
  for (const [term, value] of entries) {
    const row = make('div');
    row.append(make('dt', '', term), make('dd', '', value));
    list.append(row);
  }
  return list;
}

const windowText = (w) => `${w.earliest.local.replace('T', ' ')} ~ ${w.latest.local.replace('T', ' ')}`;

function aspectTable(items) {
  const table = make('table', 'synastry-table');
  const body = make('tbody');
  body.append(...items.map((aspect) => {
    const [glyph, name] = ASPECT_NAMES[aspect.name] || ['', aspect.name];
    const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
    tr.append(make('td', '', BODY_NAMES[aspect.a] || aspect.a), make('td', 'aspect-name', `${glyph} ${name}`),
      make('td', '', BODY_NAMES[aspect.b] || aspect.b), make('td', 'mono', `${orbText(aspect)} / ${aspect.allowed_orb}°`));
    return tr;
  }));
  table.append(body);
  return table;
}

function renderUnknown(result) {
  const chart = result.return;
  const w = result.return_window;
  document.querySelector('#chart-stage').replaceChildren(createNatalWheel({ ...chart, normalized: { ...chart.normalized, time_accuracy: 'unknown' } }));
  document.querySelector('#result-title').textContent = `${result.year}년 솔라 리턴 · 생시 미상`;
  document.querySelector('#result-subtitle').textContent = `귀환 순간 범위 ${windowText(w)} (${result.exact.timezone}) · ${chart.input.place || '선택한 장소'} 기준 · ASC·하우스 없음`;
  document.querySelector('#positions-body').replaceChildren(...chart.bodies.filter((b) => BODY_NAMES[b.id] && b.id !== 'SouthNode').map((body) => {
    const tr = make('tr');
    const where = body.time_range && body.time_range.degrees > 0.01 ? `${formatWheelPosition(body)} · 범위 ${rangeText(body)}` : formatWheelPosition(body);
    tr.append(make('td', '', `${body.symbol} ${BODY_NAMES[body.id]}`), make('td', '', where), make('td', '', '—'), make('td', '', '—'));
    return tr;
  }));
  const [settled, conditional] = splitStability(chart.aspects);
  const register = document.querySelector('#aspects-register');
  register.className = 'detail-content';
  register.replaceChildren(
    make('p', 'register-note', '생시를 모르면 네이털 태양 위치가 하루 동안 약 1° 달라져, 귀환 순간도 약 하루 범위로 퍼집니다. 그래서 귀환 ASC·MC·하우스(솔라 리턴의 핵심)는 정할 수 없고, 행성의 사인과 어스펙트만 봅니다. 위치는 범위 한가운데의 대표값입니다.'),
    definitionList([
      ['귀환 순간 범위', `${windowText(w)} (${result.exact.timezone})`],
      ['대표 귀환 순간', `${result.exact.local.replace('T', ' ')} · UTC ${result.exact.utc} (출생 정오 기준)`],
      ['달', `${point(chart, 'Moon').position} · 범위 ${rangeText(point(chart, 'Moon'))}`],
    ]),
    make('h4', 'register-subhead', '귀환 차트 어스펙트 · 확정'),
    settled.length ? aspectTable(settled) : make('p', '', '확정된 어스펙트가 없습니다.'),
    ...(conditional.length ? [conditionalHeading(conditional.length), make('p', 'register-note', TIME_DEPENDENT_NOTE), aspectTable(conditional)] : []));
  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  evidence.replaceChildren(definitionList([
    ['Rule', result.rule_version],
    ['Definition', result.settings.definition],
    ['Window', `${w.earliest.utc} → ${w.latest.utc} (출생일 첫 순간·마지막 순간의 태양 귀환)`],
    ['Location', `${chart.normalized.latitude}, ${chart.normalized.longitude} · ${chart.normalized.timezone}`],
    ['Engine', `${chart.metadata.engine} ${chart.metadata.engine_version}`],
  ]));
}

function render(result) {
  if (result.time_accuracy === 'unknown') { renderUnknown(result); return; }
  const chart = result.return;
  const natalHouse = new Map(result.return_in_natal_houses.map((item) => [item.body, item.house]));
  document.querySelector('#chart-stage').replaceChildren(createNatalWheel(chart));
  document.querySelector('#result-title').textContent = `${result.year}년 솔라 리턴`;
  document.querySelector('#result-subtitle').textContent =
    `${result.exact.local.replace('T', ' ')} (${result.exact.offset} ${result.exact.timezone}) · ${chart.input.place || '선택한 장소'} 기준`;
  document.querySelector('#positions-body').replaceChildren(...chart.bodies.filter((b) => BODY_NAMES[b.id] && b.id !== 'SouthNode').map((body) => {
    const tr = make('tr');
    tr.append(make('td', '', `${body.symbol} ${BODY_NAMES[body.id]}`), make('td', '', formatWheelPosition(body)),
      make('td', '', String(body.house ?? '—')), make('td', '', String(natalHouse.get(body.id) ?? '—')));
    return tr;
  }));
  const sun = point(chart, 'Sun');
  const moon = point(chart, 'Moon');
  const register = document.querySelector('#aspects-register');
  register.className = 'detail-content';
  register.replaceChildren(
    make('p', 'register-note', '솔라 리턴은 보통 귀환 ASC 사인, 태양이 놓인 귀환 하우스, 달의 사인·하우스로 한 해의 주제를 읽습니다. 연간 흐름을 보는 성찰의 틀로 쓰세요.'),
    definitionList([
      ['귀환 ASC', `${signOf(point(chart, 'ASC'))} · ${point(chart, 'ASC').position}`],
      ['귀환 MC', `${signOf(point(chart, 'MC'))} · ${point(chart, 'MC').position}`],
      ['태양', `귀환 ${sun.house}하우스 · 네이털 ${natalHouse.get('Sun')}하우스`],
      ['달', `${signOf(moon)} · 귀환 ${moon.house}하우스 · 네이털 ${natalHouse.get('Moon')}하우스`],
      ['귀환 순간 (UTC)', result.exact.utc],
    ]));
  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  evidence.replaceChildren(definitionList([
    ['Rule', result.rule_version],
    ['Definition', result.settings.definition],
    ['Search', result.settings.search],
    ['Location', `${result.settings.location} · ${chart.normalized.latitude}, ${chart.normalized.longitude} · ${chart.normalized.timezone}`],
    ['Natal Sun', `${result.exact.sun_longitude.toFixed(8)}° · 귀환 잔차 ${result.exact.residual_arcsec.toFixed(4)}″`],
    ['Chart time', `${chart.input.date} ${chart.input.time} · ${result.exact.chart_rounding_note}`],
    ['Engine', `${chart.metadata.engine} ${chart.metadata.engine_version}`],
  ]));
}

function markdownUnknown(result, n) {
  const chart = result.return;
  const [settled, conditional] = splitStability(chart.aspects);
  const lines = [`# ${n.a}의 ${result.year}년 솔라 리턴 (출생 시각 미상)`, '',
    '아래는 태양이 네이털 황경으로 돌아오는 순간의 하늘입니다. 출생 시각을 몰라 네이털 태양 위치가 약 1° 불확실하고, 귀환 순간이 약 하루 범위로 퍼집니다. 그래서 귀환 ASC·MC·하우스는 계산하지 않았습니다. 이것들을 추정하지 말고, 행성의 사인과 "확정" 어스펙트를 중심으로 이 한 해의 분위기를 한국어로 해석해 주세요. 범위가 사인 경계를 넘는 행성(특히 달)과 "조건부" 어스펙트는 단정하지 마세요. 예언이 아니라 성찰의 틀로 쓰고, 계산값은 수정하지 마세요.', '',
    `- 귀환 순간 범위: ${windowText(result.return_window)} (${result.exact.timezone})`,
    `- 장소: ${chart.input.place || '—'} (${chart.normalized.latitude}, ${chart.normalized.longitude})`, '', '## 귀환 차트 행성 (대표값과 가능 범위)'];
  for (const body of chart.bodies.filter((b) => BODY_NAMES[b.id] && !['SouthNode', 'Fortune', 'Spirit'].includes(b.id))) {
    lines.push(`- ${BODY_NAMES[body.id]}: ${body.position}${body.time_range && body.time_range.degrees > 0.01 ? ` (가능 범위 ${rangeText(body)})` : ''}`);
  }
  const line = (a) => `- ${BODY_NAMES[a.a] || a.a} ${a.name} ${BODY_NAMES[a.b] || a.b} · orb ${a.stability === 'time_dependent' ? `${a.orb_range[0].toFixed(2)}–${a.orb_range[1].toFixed(2)}` : a.orb.toFixed(2)}°`;
  lines.push('', '## 귀환 차트 어스펙트 — 확정', ...settled.map(line));
  if (conditional.length) lines.push('', '## 귀환 차트 어스펙트 — 조건부 (출생 시각에 따라)', ...conditional.map(line));
  return lines.join('\n');
}

function markdown(result, n) {
  if (result.time_accuracy === 'unknown') return markdownUnknown(result, n);
  const chart = result.return;
  const natalHouse = new Map(result.return_in_natal_houses.map((item) => [item.body, item.house]));
  const lines = [`# ${n.a}의 ${result.year}년 솔라 리턴`, '',
    '아래는 태양이 네이털 황경으로 돌아온 순간을 선택한 장소에서 세운 차트입니다. 귀환 ASC, 태양·달의 귀환 하우스를 중심으로 이 한 해의 주제를 한국어로 해석해 주세요. 예언이 아니라 성찰의 틀로 쓰고, 계산값은 수정하지 마세요.', '',
    `- 귀환 순간: ${result.exact.local.replace('T', ' ')} (${result.exact.offset} ${result.exact.timezone}) · UTC ${result.exact.utc}`,
    `- 장소: ${chart.input.place || '—'} (${chart.normalized.latitude}, ${chart.normalized.longitude})`,
    `- 귀환 ASC: ${point(chart, 'ASC').position} · MC: ${point(chart, 'MC').position}`, '', '## 귀환 차트 행성'];
  for (const body of chart.bodies.filter((b) => BODY_NAMES[b.id] && !['SouthNode', 'Fortune', 'Spirit'].includes(b.id))) {
    lines.push(`- ${BODY_NAMES[body.id]}: ${body.position} · 귀환 ${body.house}H · 네이털 ${natalHouse.get(body.id)}H`);
  }
  lines.push('', '## 귀환 차트 어스펙트');
  for (const a of chart.aspects) lines.push(`- ${BODY_NAMES[a.a] || a.a} ${a.name} ${BODY_NAMES[a.b] || a.b} · orb ${a.orb.toFixed(2)}°`);
  return lines.join('\n');
}

page = mountToolPage({
  kind: 'solar-return',
  endpoint: '/api/solar-return',
  shareable: false,
  allowUnknownTime: true,
  busyText: '태양이 네이털 황경으로 돌아오는 순간을 찾는 중입니다.',
  doneText: '솔라 리턴 계산을 완료했습니다.',
  extraValidate: () => {
    const year = Number(yearInput.value);
    if (!Number.isInteger(year) || year < 1901 || year > 2100) return '귀환 연도를 1901–2100 사이 정수로 입력하세요.';
    return samePlace.checked ? '' : returnPlace.validate();
  },
  buildInput: (people) => {
    const natal = people[0].payload();
    return { natal, year: Number(yearInput.value), location: location(natal) };
  },
  defaultTitle: (n) => `${n.a} 솔라 리턴`,
  render,
  markdown,
});
