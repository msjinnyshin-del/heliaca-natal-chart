import { createSynastryWheel } from './synastry-wheel.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, formatOrb, mountToolPage, withMore } from './tool-page.js';

const ROWS = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto', 'Chiron', 'NorthNode'];
const isUnknown = (chart) => chart.normalized?.time_accuracy === 'unknown';
const timeDependent = (aspect) => aspect.stability === 'time_dependent';
// Unknown birth time: the noon position stands in; a sign that changes during the day is flagged.
function positionCell(chart, body) {
  if (!body) return '—';
  const text = formatWheelPosition(body);
  if (!isUnknown(chart)) return text;
  return body.time_sensitivity && !body.time_sensitivity.sign_stable ? `${text} · 사인 변동` : text;
}

function renderPositions(result, n) {
  document.querySelector('#col-a').textContent = n.a;
  document.querySelector('#col-b').textContent = n.b;
  const a = new Map(result.person_a.bodies.map((body) => [body.id, body]));
  const b = new Map(result.person_b.bodies.map((body) => [body.id, body]));
  const rows = ROWS.filter((id) => a.has(id)).map((id) => {
    const tr = make('tr');
    tr.append(make('td', '', `${a.get(id).symbol} ${BODY_NAMES[id]}`), make('td', '', positionCell(result.person_a, a.get(id))), make('td', '', positionCell(result.person_b, b.get(id))));
    return tr;
  });
  const angleCell = (chart, id) => (isUnknown(chart) ? '생시 미상' : formatWheelPosition(chart.angles.find((x) => x.id === id)));
  for (const angle of ['ASC', 'MC']) {
    const tr = make('tr');
    tr.append(make('td', '', angle), make('td', '', angleCell(result.person_a, angle)), make('td', '', angleCell(result.person_b, angle)));
    rows.push(tr);
  }
  const blind = [[result.person_a, n.a], [result.person_b, n.b]].filter(([chart]) => isUnknown(chart)).map(([, name]) => name);
  if (blind.length) {
    const tr = make('tr');
    const td = make('td', 'empty-cell', `${blind.join('·')}: 생시 미상 · 현지 정오 대표 위치입니다. 달은 하루에 약 12–15° 움직입니다.`);
    td.colSpan = 3;
    tr.append(td);
    rows.push(tr);
  }
  document.querySelector('#positions-body').replaceChildren(...rows);
}

function aspectRow(aspect, n) {
  const [glyph, name] = ASPECT_NAMES[aspect.name];
  const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
  tr.append(make('td', '', `${n.a} ${BODY_NAMES[aspect.a]}`), make('td', 'aspect-name', `${glyph} ${name}`), make('td', '', `${n.b} ${BODY_NAMES[aspect.b]}`),
    make('td', 'mono', timeDependent(aspect)
      ? `${formatOrb(aspect.orb_range[0])}–${formatOrb(aspect.orb_range[1])} / ${aspect.allowed_orb}°`
      : `${formatOrb(aspect.orb)} / ${aspect.allowed_orb}°`));
  return tr;
}

function renderAspects(result, n) {
  const register = document.querySelector('#aspect-register');
  register.className = 'detail-content';
  if (!result.aspects.length) { register.textContent = '허용 orb 안의 상호 어스펙트가 없습니다.'; return; }
  const table = (items) => {
    const t = make('table', 'synastry-table');
    const body = make('tbody');
    body.append(...items.map((aspect) => aspectRow(aspect, n)));
    t.append(body);
    return t;
  };
  const settled = result.aspects.filter((a) => !timeDependent(a));
  const strong = settled.filter((a) => a.strong);
  const weak = settled.filter((a) => !a.strong);
  const conditional = result.aspects.filter(timeDependent);
  const nodes = [
    make('p', 'register-note', '상호 어스펙트는 한 사람의 행성이 다른 사람의 행성과 맺는 각도입니다. 네이털보다 좁은 orb를 쓰며, 어스펙트 종류·행성 비중·orb로 매긴 강도 순입니다. 초록=조화, 산호=긴장, 금=합.'),
    ...withMore([table(strong)], weak.length ? [table(weak)] : [], '약한 어스펙트', weak.length),
  ];
  if (conditional.length) {
    nodes.push(make('h4', 'register-subtitle', `출생 시각에 따라 달라지는 어스펙트 ${conditional.length}개`),
      make('p', 'register-note', '생시를 모르는 사람의 행성(주로 달)이 하루 중 어느 때 태어났느냐에 따라 orb 안에 들어오거나 벗어납니다. orb는 그날 가능한 범위입니다. 확정 결과로 해석하지 마세요.'),
      table(conditional));
  }
  register.replaceChildren(...nodes);
}

function overlayItem(item, owner, host) {
  const li = make('li', item.strong ? 'overlay-strong' : '');
  const houses = item.stability === 'time_dependent' ? `${item.houses.join('·')}하우스 (출생 시각에 따라)` : `${item.house}하우스`;
  li.append(make('b', '', `${owner}의 ${BODY_NAMES[item.body]}`), document.createTextNode(' → '), make('b', '', `${host}의 ${houses}`));
  return li;
}

function renderOverlays(result, n) {
  const register = document.querySelector('#overlay-register');
  register.className = 'detail-content';
  const all = [
    ...(result.overlays.b_in_a || []).map((item) => ({ ...item, owner: n.b, host: n.a })),
    ...(result.overlays.a_in_b || []).map((item) => ({ ...item, owner: n.a, host: n.b })),
  ];
  const skipped = [[result.overlays.b_in_a, n.a], [result.overlays.a_in_b, n.b]].filter(([rows]) => rows === null).map(([, host]) => host);
  const skipNote = skipped.length ? [make('p', 'register-note', `${skipped.join('·')}의 생시를 몰라 그 사람의 하우스(삶의 방)는 계산하지 않았습니다. 하우스는 출생 시각이 있어야 정해집니다.`)] : [];
  if (!all.length) { register.replaceChildren(...skipNote); return; }
  const rank = (h) => ([1, 4, 7, 10].includes(h) ? 0 : [5, 8].includes(h) ? 1 : 2);
  all.sort((x, y) => (x.strong === y.strong ? 0 : x.strong ? -1 : 1) || rank(x.house) - rank(y.house) || x.house - y.house);
  const list = (items) => {
    const ul = make('ul', 'overlay-sentences');
    ul.append(...items.map((item) => overlayItem(item, item.owner, item.host)));
    return ul;
  };
  const weak = all.filter((item) => !item.strong);
  register.replaceChildren(
    make('p', 'register-note', '하우스 오버레이는 한 사람의 행성이 상대의 어느 하우스(삶의 방)에 들어가는지 보여줍니다. 개인 행성(해·달·수성·금성·화성)과 ASC를 먼저, 앵귤러 하우스(1·4·7·10) → 5·8 → 나머지 순으로 정렬합니다.'),
    ...skipNote,
    ...withMore([list(all.filter((item) => item.strong))], weak.length ? [list(weak)] : [], '외행성·포인트', weak.length));
}

function renderEvidence(result, n) {
  const register = document.querySelector('#evidence-register');
  register.className = 'detail-content';
  const list = make('dl', 'metadata-list');
  const s = result.settings;
  const entries = [
    ['Rule', result.rule_version],
    ['Orbs', `${Object.entries(s.orbs).map(([k, v]) => `${k} ${v}°`).join(' · ')} · 해·달 +${s.luminary_bonus}° · Chiron/Node/ASC/MC ${s.point_orb}°`],
    ...[[result.person_a, n.a], [result.person_b, n.b]].map(([chart, name]) => [`${name} UTC`,
      `${chart.normalized.utc} (${chart.normalized.offset} ${chart.normalized.timezone})${isUnknown(chart) ? ` · 생시 미상: 현지 정오 대표값, 하루 ${chart.normalized.day_range?.hours}시간 전체 검사` : ''}`]),
    ['House', `${result.person_a.settings.house_system} · node ${result.person_a.settings.node_mode}`],
    ['Engine', `${result.person_a.metadata.engine} ${result.person_a.metadata.engine_version}`],
  ];
  for (const [term, value] of entries) {
    const row = make('div');
    row.append(make('dt', '', term), make('dd', '', value));
    list.append(row);
  }
  const warnings = make('ul', 'warning-list');
  for (const w of new Set([...result.person_a.warnings, ...result.person_b.warnings])) warnings.append(make('li', '', w));
  register.replaceChildren(list, warnings);
}

export function synastryMarkdown(result, n) {
  const lines = [`# ${n.a} × ${n.b} 시너스트리`, '', '아래는 Swiss Ephemeris로 계산한 두 사람의 시너스트리입니다. 궁합 점수가 아니라, 가장 타이트한 어스펙트와 하우스 오버레이를 근거로 관계의 역학(끌림·긴장·성장 과제)을 한국어로 해석해 주세요. 계산값은 수정하지 마세요.', ''];
  for (const [key, label] of [['person_a', n.a], ['person_b', n.b]]) {
    const chart = result[key];
    const blind = isUnknown(chart);
    lines.push(`## ${label} (${chart.input.date} ${blind ? '생시 미상 — 현지 정오 대표 위치, ASC·MC·하우스 없음' : chart.input.time} · ${chart.input.place})`);
    for (const body of chart.bodies.filter((x) => ROWS.includes(x.id))) {
      const changes = blind && body.time_sensitivity && !body.time_sensitivity.sign_stable ? ' (이날 사인 변동)' : '';
      lines.push(`- ${BODY_NAMES[body.id]}: ${body.position}${blind ? '' : ` · ${body.house}H`}${body.direction === 'R' ? ' R' : ''}${changes}`);
    }
    for (const angle of chart.angles.filter((x) => ['ASC', 'MC'].includes(x.id))) lines.push(`- ${angle.id}: ${angle.position}`);
    lines.push('');
  }
  lines.push(`## 상호 어스펙트 (${n.a} → ${n.b}, 강도 순 · 강한 것만)`);
  for (const a of result.aspects.filter((x) => x.strong)) lines.push(`- ${n.a} ${BODY_NAMES[a.a]} ${ASPECT_NAMES[a.name][1]} ${n.b} ${BODY_NAMES[a.b]} (orb ${a.orb.toFixed(2)}°)`);
  const conditional = result.aspects.filter(timeDependent);
  if (conditional.length) {
    lines.push('', '## 출생 시각에 따라 달라지는 어스펙트 (확정 아님 — 조건부로만 언급)');
    for (const a of conditional) lines.push(`- ${n.a} ${BODY_NAMES[a.a]} ${ASPECT_NAMES[a.name][1]} ${n.b} ${BODY_NAMES[a.b]} (그날 가능한 orb ${a.orb_range[0].toFixed(2)}–${a.orb_range[1].toFixed(2)}°, 허용 ${a.allowed_orb}°)`);
  }
  lines.push('', `## 하우스 오버레이 (개인 행성·ASC)`);
  const overlayLine = (item, owner, host) => `- ${owner} ${BODY_NAMES[item.body]} → ${host} ${item.stability === 'time_dependent' ? `${item.houses.join('·')}H 중 하나(출생 시각에 따라)` : `${item.house}H`}`;
  for (const [rows, owner, host] of [[result.overlays.b_in_a, n.b, n.a], [result.overlays.a_in_b, n.a, n.b]]) {
    if (rows === null) lines.push(`- ${host}: 생시 미상이라 하우스 오버레이 없음`);
    else for (const item of rows.filter((x) => x.strong)) lines.push(overlayLine(item, owner, host));
  }
  lines.push('', `규칙: ${result.rule_version} · ${result.person_a.settings.zodiac} · house ${result.person_a.settings.house_system}`);
  return lines.join('\n');
}

function render(result, n) {
  document.querySelector('#chart-stage').replaceChildren(createSynastryWheel(result, n));
  document.querySelector('#result-title').textContent = `${n.a} × ${n.b} 시너스트리`;
  const conditional = result.aspects.filter(timeDependent).length;
  const blind = [[result.person_a, n.a], [result.person_b, n.b]].filter(([chart]) => isUnknown(chart)).map(([, name]) => name);
  document.querySelector('#result-subtitle').textContent = `${result.aspects.length - conditional}개의 상호 어스펙트${conditional ? ` + 시각에 따라 ${conditional}개` : ''} · ${result.person_a.settings.house_system} 하우스${blind.length ? ` · ${blind.join('·')} 생시 미상` : ''}`;
  const keyA = make('span', 'syn-key-a', n.a);
  const keyB = make('span', 'syn-key-b', n.b);
  const text = (value) => document.createTextNode(value);
  document.querySelector('#synastry-caption').replaceChildren(...(isUnknown(result.person_a)
    ? [text('생시를 몰라 하우스 없이 양자리 0°를 왼쪽에 둡니다 · 안쪽: '), keyA, text(' · 바깥 띠: '), keyB, text(' · 중앙선: 하루 내내 유지되는 어스펙트만')]
    : [text('안쪽: '), keyA, text('의 하우스와 행성(ASC가 왼쪽) · 바깥 띠: '), keyB, text(`의 행성 · 중앙선: 두 사람 사이 어스펙트${blind.length ? '(하루 내내 유지되는 것만)' : ''}`)]));
  renderPositions(result, n);
  renderAspects(result, n);
  renderOverlays(result, n);
  renderEvidence(result, n);
}

mountToolPage({
  kind: 'synastry',
  endpoint: '/api/synastry',
  shareable: true,
  allowUnknownTime: true,
  busyText: '두 차트를 계산하는 중입니다.',
  doneText: '시너스트리 계산을 완료했습니다.',
  buildInput: (people) => ({ person_a: people[0].payload(), person_b: people[1].payload() }),
  defaultTitle: (n) => `${n.a} & ${n.b}`,
  render,
  markdown: synastryMarkdown,
});
