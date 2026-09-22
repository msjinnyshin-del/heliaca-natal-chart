import { createSynastryWheel } from './synastry-wheel.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, formatOrb, mountToolPage, withMore } from './tool-page.js';

const ROWS = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto', 'Chiron', 'NorthNode'];

function renderPositions(result, n) {
  document.querySelector('#col-a').textContent = n.a;
  document.querySelector('#col-b').textContent = n.b;
  const a = new Map(result.person_a.bodies.map((body) => [body.id, body]));
  const b = new Map(result.person_b.bodies.map((body) => [body.id, body]));
  const rows = ROWS.filter((id) => a.has(id)).map((id) => {
    const tr = make('tr');
    tr.append(make('td', '', `${a.get(id).symbol} ${BODY_NAMES[id]}`), make('td', '', formatWheelPosition(a.get(id))), make('td', '', formatWheelPosition(b.get(id))));
    return tr;
  });
  for (const angle of ['ASC', 'MC']) {
    const tr = make('tr');
    tr.append(make('td', '', angle), make('td', '', formatWheelPosition(result.person_a.angles.find((x) => x.id === angle))),
      make('td', '', formatWheelPosition(result.person_b.angles.find((x) => x.id === angle))));
    rows.push(tr);
  }
  document.querySelector('#positions-body').replaceChildren(...rows);
}

function aspectRow(aspect, n) {
  const [glyph, name] = ASPECT_NAMES[aspect.name];
  const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
  tr.append(make('td', '', `${n.a} ${BODY_NAMES[aspect.a]}`), make('td', 'aspect-name', `${glyph} ${name}`), make('td', '', `${n.b} ${BODY_NAMES[aspect.b]}`),
    make('td', 'mono', `${formatOrb(aspect.orb)} / ${aspect.allowed_orb}°`));
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
  const strong = result.aspects.filter((a) => a.strong);
  const weak = result.aspects.filter((a) => !a.strong);
  register.replaceChildren(
    make('p', 'register-note', '상호 어스펙트는 한 사람의 행성이 다른 사람의 행성과 맺는 각도입니다. 네이털보다 좁은 orb를 쓰며, 어스펙트 종류·행성 비중·orb로 매긴 강도 순입니다. 초록=조화, 산호=긴장, 금=합.'),
    ...withMore([table(strong)], weak.length ? [table(weak)] : [], '약한 어스펙트', weak.length));
}

function overlayItem(item, owner, host) {
  const li = make('li', item.strong ? 'overlay-strong' : '');
  li.append(make('b', '', `${owner}의 ${BODY_NAMES[item.body]}`), document.createTextNode(' → '), make('b', '', `${host}의 ${item.house}하우스`));
  return li;
}

function renderOverlays(result, n) {
  const register = document.querySelector('#overlay-register');
  register.className = 'detail-content';
  const all = [
    ...result.overlays.b_in_a.map((item) => ({ ...item, owner: n.b, host: n.a })),
    ...result.overlays.a_in_b.map((item) => ({ ...item, owner: n.a, host: n.b })),
  ];
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
    [`${n.a} UTC`, `${result.person_a.normalized.utc} (${result.person_a.normalized.offset} ${result.person_a.normalized.timezone})`],
    [`${n.b} UTC`, `${result.person_b.normalized.utc} (${result.person_b.normalized.offset} ${result.person_b.normalized.timezone})`],
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
    lines.push(`## ${label} (${chart.input.date} ${chart.input.time} · ${chart.input.place})`);
    for (const body of chart.bodies.filter((x) => ROWS.includes(x.id))) lines.push(`- ${BODY_NAMES[body.id]}: ${body.position} · ${body.house}H${body.direction === 'R' ? ' R' : ''}`);
    for (const angle of chart.angles.filter((x) => ['ASC', 'MC'].includes(x.id))) lines.push(`- ${angle.id}: ${angle.position}`);
    lines.push('');
  }
  lines.push(`## 상호 어스펙트 (${n.a} → ${n.b}, 강도 순 · 강한 것만)`);
  for (const a of result.aspects.filter((x) => x.strong)) lines.push(`- ${n.a} ${BODY_NAMES[a.a]} ${ASPECT_NAMES[a.name][1]} ${n.b} ${BODY_NAMES[a.b]} (orb ${a.orb.toFixed(2)}°)`);
  lines.push('', `## 하우스 오버레이 (개인 행성·ASC)`);
  for (const item of result.overlays.b_in_a.filter((x) => x.strong)) lines.push(`- ${n.b} ${BODY_NAMES[item.body]} → ${n.a} ${item.house}H`);
  for (const item of result.overlays.a_in_b.filter((x) => x.strong)) lines.push(`- ${n.a} ${BODY_NAMES[item.body]} → ${n.b} ${item.house}H`);
  lines.push('', `규칙: ${result.rule_version} · ${result.person_a.settings.zodiac} · house ${result.person_a.settings.house_system}`);
  return lines.join('\n');
}

function render(result, n) {
  document.querySelector('#chart-stage').replaceChildren(createSynastryWheel(result, n));
  document.querySelector('#result-title').textContent = `${n.a} × ${n.b} 시너스트리`;
  document.querySelector('#result-subtitle').textContent = `${result.aspects.length}개의 상호 어스펙트 · ${result.person_a.settings.house_system} 하우스`;
  renderPositions(result, n);
  renderAspects(result, n);
  renderOverlays(result, n);
  renderEvidence(result, n);
}

mountToolPage({
  kind: 'synastry',
  endpoint: '/api/synastry',
  shareable: true,
  busyText: '두 차트를 계산하는 중입니다.',
  doneText: '시너스트리 계산을 완료했습니다.',
  buildInput: (people) => ({ person_a: people[0].payload(), person_b: people[1].payload() }),
  defaultTitle: (n) => `${n.a} & ${n.b}`,
  render,
  markdown: synastryMarkdown,
});
