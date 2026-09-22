import { createNatalWheel } from './chart.js';
import { buildHouseGrid, make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, formatOrb, mountToolPage } from './tool-page.js';

function definitionList(entries) {
  const list = make('dl', 'metadata-list');
  for (const [term, value] of entries) {
    const row = make('div');
    row.append(make('dt', '', term), make('dd', '', value));
    list.append(row);
  }
  return list;
}

function render(result, n) {
  const chart = result.composite;
  document.querySelector('#chart-stage').replaceChildren(createNatalWheel(chart));
  document.querySelector('#result-title').textContent = `${n.a} × ${n.b} 컴포지트`;
  const sun = chart.bodies.find((b) => b.id === 'Sun');
  const moon = chart.bodies.find((b) => b.id === 'Moon');
  const asc = chart.angles.find((a) => a.id === 'ASC');
  document.querySelector('#result-subtitle').textContent = `관계의 태양 ${sun.position} · 달 ${moon.position} · ASC ${asc.position}`;
  const rows = chart.bodies.map((body) => {
    const tr = make('tr');
    tr.append(make('td', '', `${body.symbol} ${BODY_NAMES[body.id] || body.name}`), make('td', '', body.position), make('td', '', String(body.house)));
    return tr;
  });
  for (const angle of chart.angles.filter((a) => ['ASC', 'MC'].includes(a.id))) {
    const tr = make('tr');
    tr.append(make('td', '', angle.id), make('td', '', angle.position), make('td', '', '—'));
    rows.push(tr);
  }
  document.querySelector('#positions-body').replaceChildren(...rows);

  const aspects = document.querySelector('#aspects-register');
  aspects.className = 'detail-content';
  const table = make('table', 'synastry-table');
  const body = make('tbody');
  for (const aspect of [...chart.aspects].sort((x, y) => x.orb - y.orb)) {
    const [glyph, name] = ASPECT_NAMES[aspect.name];
    const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
    tr.append(make('td', '', BODY_NAMES[aspect.a] || aspect.a), make('td', 'aspect-name', `${glyph} ${name}`),
      make('td', '', BODY_NAMES[aspect.b] || aspect.b), make('td', 'mono', `${formatOrb(aspect.orb)} / ${aspect.allowed_orb}°`));
    body.append(tr);
  }
  table.append(body);
  aspects.replaceChildren(make('p', 'register-note', '컴포지트 차트 안에서 행성끼리 맺는 어스펙트입니다(네이털과 같은 major 규칙, orb 순). 관계 자체의 성격과 긴장을 보여줍니다.'),
    chart.aspects.length ? table : make('p', '', '허용 orb 안의 어스펙트가 없습니다.'));

  const houses = document.querySelector('#houses-register');
  houses.className = 'detail-content';
  houses.replaceChildren(buildHouseGrid(chart));

  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  evidence.replaceChildren(definitionList([
    ['Method', `${result.rule_version} · ${result.settings.houses}`],
    ['Note', result.settings.note],
    [`${n.a} UTC`, `${result.person_a.normalized.utc} (${result.person_a.normalized.offset} ${result.person_a.normalized.timezone})`],
    [`${n.b} UTC`, `${result.person_b.normalized.utc} (${result.person_b.normalized.offset} ${result.person_b.normalized.timezone})`],
    ['House', `${result.person_a.settings.house_system} · node ${result.person_a.settings.node_mode}`],
    ['Engine', `${result.person_a.metadata.engine} ${result.person_a.metadata.engine_version}`],
  ]));
}

function markdown(result, n) {
  const chart = result.composite;
  const lines = [`# ${n.a} × ${n.b} 컴포지트 차트`, '',
    '아래는 두 사람의 네이털 차트를 미드포인트로 합친 컴포지트 차트입니다. 한 사람의 네이털처럼 읽되 “관계 그 자체”의 초상으로, 태양(관계의 목적)·달(정서적 기반)·금성(사랑하는 방식)·ASC와 하우스 강조점을 중심으로 한국어로 해석해 주세요. 계산값은 수정하지 마세요.', '',
    '## 컴포지트 배치'];
  for (const body of chart.bodies) lines.push(`- ${BODY_NAMES[body.id] || body.name}: ${body.position} · ${body.house}H`);
  for (const angle of chart.angles.filter((a) => ['ASC', 'MC'].includes(a.id))) lines.push(`- ${angle.id}: ${angle.position}`);
  lines.push('', '## 컴포지트 어스펙트 (orb 순)');
  for (const a of [...chart.aspects].sort((x, y) => x.orb - y.orb)) lines.push(`- ${BODY_NAMES[a.a] || a.a} ${ASPECT_NAMES[a.name][1]} ${BODY_NAMES[a.b] || a.b} (orb ${a.orb.toFixed(2)}°)`);
  lines.push('', `규칙: ${result.rule_version} · house ${result.person_a.settings.house_system}`,
    `원 차트: ${n.a} ${result.person_a.input.date} ${result.person_a.input.time} ${result.person_a.input.place} / ${n.b} ${result.person_b.input.date} ${result.person_b.input.time} ${result.person_b.input.place}`);
  return lines.join('\n');
}

mountToolPage({
  kind: 'composite',
  endpoint: '/api/composite',
  shareable: true,
  busyText: '두 차트와 미드포인트를 계산하는 중입니다.',
  doneText: '컴포지트 계산을 완료했습니다.',
  buildInput: (people) => ({ person_a: people[0].payload(), person_b: people[1].payload() }),
  defaultTitle: (n) => `${n.a} & ${n.b} 컴포지트`,
  render,
  markdown,
});
