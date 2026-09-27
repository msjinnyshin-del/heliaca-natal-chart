import { createNatalWheel } from './chart.js';
import { buildHouseGrid, make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, TIME_DEPENDENT_NOTE, conditionalHeading, mountToolPage, orbText, rangeText, splitStability } from './tool-page.js';

const blindNames = (result, n) => [['person_a', n.a], ['person_b', n.b]].filter(([key]) => result.time_accuracy?.[key] === 'unknown').map(([, name]) => name);

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
  const blind = blindNames(result, n);
  // Without both birth times the composite has no ASC or houses; the wheel then shows Aries at left and settled aspects only.
  document.querySelector('#chart-stage').replaceChildren(createNatalWheel(blind.length ? { ...chart, normalized: { ...chart.normalized, time_accuracy: 'unknown' } } : chart));
  document.querySelector('#result-title').textContent = `${n.a} × ${n.b} 컴포지트`;
  const sun = chart.bodies.find((b) => b.id === 'Sun');
  const moon = chart.bodies.find((b) => b.id === 'Moon');
  const asc = chart.angles.find((a) => a.id === 'ASC');
  document.querySelector('#result-subtitle').textContent = asc
    ? `관계의 태양 ${sun.position} · 달 ${moon.position} · ASC ${asc.position}`
    : `관계의 태양 ${sun.position} · 달 ${moon.position} · ${blind.join('·')} 생시 미상이라 ASC·하우스 없음`;
  const rows = chart.bodies.map((body) => {
    const tr = make('tr');
    const where = body.midpoint_ambiguous ? `${body.position} · 반대편(180°) 가능`
      : body.time_range && body.time_range.degrees > 0.01 ? `${body.position} · 범위 ${rangeText(body)}` : body.position;
    tr.append(make('td', '', `${body.symbol} ${BODY_NAMES[body.id] || body.name}`), make('td', '', where), make('td', '', body.house == null ? '—' : String(body.house)));
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
  const aspectTable = (items) => {
    const table = make('table', 'synastry-table');
    const body = make('tbody');
    for (const aspect of items) {
      const [glyph, name] = ASPECT_NAMES[aspect.name];
      const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
      tr.append(make('td', '', BODY_NAMES[aspect.a] || aspect.a), make('td', 'aspect-name', `${glyph} ${name}`),
        make('td', '', BODY_NAMES[aspect.b] || aspect.b), make('td', 'mono', `${orbText(aspect)} / ${aspect.allowed_orb}°`));
      body.append(tr);
    }
    table.append(body);
    return table;
  };
  const [settled, conditional] = splitStability([...chart.aspects].sort((x, y) => x.orb - y.orb));
  const ambiguous = chart.bodies.filter((b) => b.midpoint_ambiguous).map((b) => BODY_NAMES[b.id] || b.name);
  aspects.replaceChildren(make('p', 'register-note', '컴포지트 차트 안에서 행성끼리 맺는 어스펙트입니다(네이털과 같은 major 규칙, orb 순). 관계 자체의 성격과 긴장을 보여줍니다.'),
    settled.length ? aspectTable(settled) : make('p', '', '허용 orb 안의 어스펙트가 없습니다.'),
    ...(conditional.length ? [conditionalHeading(conditional.length), make('p', 'register-note', TIME_DEPENDENT_NOTE), aspectTable(conditional)] : []),
    ...(ambiguous.length ? [make('p', 'register-note', `${ambiguous.join('·')}: 두 사람의 위치가 거의 정반대라 출생 시각에 따라 미드포인트가 반대편(180°)으로 바뀔 수 있어 어스펙트에서 뺐습니다.`)] : []));

  const houses = document.querySelector('#houses-register');
  houses.className = 'detail-content';
  houses.replaceChildren(chart.houses.length ? buildHouseGrid(chart)
    : make('p', 'register-note', `${blind.join('·')}의 생시를 몰라 컴포지트 ASC·하우스를 계산하지 않았습니다. 하우스는 두 사람의 출생 시각이 모두 있어야 정해집니다.`));

  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  evidence.replaceChildren(definitionList([
    ['Method', `${result.rule_version} · ${result.settings.houses}`],
    ['Note', result.settings.note],
    ...[[result.person_a, n.a], [result.person_b, n.b]].map(([person, name]) => [`${name} UTC`,
      `${person.normalized.utc} (${person.normalized.offset} ${person.normalized.timezone})${person.normalized.time_accuracy === 'unknown' ? ' · 생시 미상: 정오 대표값, 하루 전체 범위 검사' : ''}`]),
    ['House', `${result.person_a.settings.house_system} · node ${result.person_a.settings.node_mode}`],
    ['Engine', `${result.person_a.metadata.engine} ${result.person_a.metadata.engine_version}`],
  ]));
}

function markdown(result, n) {
  const chart = result.composite;
  const lines = [`# ${n.a} × ${n.b} 컴포지트 차트`, '',
    '아래는 두 사람의 네이털 차트를 미드포인트로 합친 컴포지트 차트입니다. 한 사람의 네이털처럼 읽되 “관계 그 자체”의 초상으로, 태양(관계의 목적)·달(정서적 기반)·금성(사랑하는 방식)·ASC와 하우스 강조점을 중심으로 한국어로 해석해 주세요. 계산값은 수정하지 마세요.', '',
    '## 컴포지트 배치'];
  const blind = blindNames(result, n);
  if (blind.length) lines.splice(2, 1, `아래는 두 사람의 네이털 차트를 미드포인트로 합친 컴포지트 차트입니다. ${blind.join('·')}의 출생 시각을 몰라 ASC·MC·하우스는 계산하지 않았습니다. 이것들을 추정하지 말고, 태양·달·금성과 "확정" 어스펙트를 중심으로 관계 자체의 초상을 한국어로 해석해 주세요. 범위가 있는 천체와 "조건부" 어스펙트는 "출생 시각에 따라"라고 밝히고 단정하지 마세요. 계산값은 수정하지 마세요.`);
  for (const body of chart.bodies) {
    const extra = body.midpoint_ambiguous ? ' (출생 시각에 따라 반대편 180°일 수 있음)' : body.time_range && body.time_range.degrees > 0.01 ? ` (가능 범위 ${rangeText(body)})` : '';
    lines.push(`- ${BODY_NAMES[body.id] || body.name}: ${body.position}${body.house == null ? '' : ` · ${body.house}H`}${extra}`);
  }
  for (const angle of chart.angles.filter((a) => ['ASC', 'MC'].includes(a.id))) lines.push(`- ${angle.id}: ${angle.position}`);
  const [settled, conditional] = splitStability([...chart.aspects].sort((x, y) => x.orb - y.orb));
  lines.push('', `## 컴포지트 어스펙트${blind.length ? ' — 확정 (하루 내내 유지)' : ' (orb 순)'}`);
  for (const a of settled) lines.push(`- ${BODY_NAMES[a.a] || a.a} ${ASPECT_NAMES[a.name][1]} ${BODY_NAMES[a.b] || a.b} (orb ${a.orb.toFixed(2)}°)`);
  if (conditional.length) {
    lines.push('', '## 컴포지트 어스펙트 — 조건부 (출생 시각에 따라)');
    for (const a of conditional) lines.push(`- ${BODY_NAMES[a.a] || a.a} ${ASPECT_NAMES[a.name][1]} ${BODY_NAMES[a.b] || a.b} (가능한 orb ${a.orb_range[0].toFixed(2)}–${a.orb_range[1].toFixed(2)}°, 허용 ${a.allowed_orb}°)`);
  }
  const clock = (person) => (person.normalized.time_accuracy === 'unknown' ? '생시 미상' : person.input.time);
  lines.push('', `규칙: ${result.rule_version} · house ${result.person_a.settings.house_system}`,
    `원 차트: ${n.a} ${result.person_a.input.date} ${clock(result.person_a)} ${result.person_a.input.place} / ${n.b} ${result.person_b.input.date} ${clock(result.person_b)} ${result.person_b.input.place}`);
  return lines.join('\n');
}

mountToolPage({
  kind: 'composite',
  endpoint: '/api/composite',
  shareable: true,
  allowUnknownTime: true,
  busyText: '두 차트와 미드포인트를 계산하는 중입니다.',
  doneText: '컴포지트 계산을 완료했습니다.',
  buildInput: (people) => ({ person_a: people[0].payload(), person_b: people[1].payload() }),
  defaultTitle: (n) => `${n.a} & ${n.b} 컴포지트`,
  render,
  markdown,
});
