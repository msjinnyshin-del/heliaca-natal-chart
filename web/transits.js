import { createSynastryWheel } from './synastry-wheel.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, formatOrb, mountToolPage, withMore } from './tool-page.js';

const dateInput = document.querySelector('#moment-date');
const timeInput = document.querySelector('#moment-time');
const zoneInput = document.querySelector('#moment-timezone');
const pad = (value) => String(value).padStart(2, '0');

function setNow() {
  const now = new Date();
  dateInput.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  timeInput.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  zoneInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}
setNow();

const MOTION = { applying: '접근', separating: '분리', stationary: '정지' };

function aspectRow(aspect) {
  const [glyph, name] = ASPECT_NAMES[aspect.name];
  const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
  tr.append(make('td', '', `트랜짓 ${BODY_NAMES[aspect.transit]}${aspect.retrograde ? ' R' : ''}`), make('td', 'aspect-name', `${glyph} ${name}`),
    make('td', '', `네이털 ${BODY_NAMES[aspect.natal]}`), make('td', 'mono', `${formatOrb(aspect.orb)} · ${MOTION[aspect.motion]}`));
  return tr;
}

function table(items) {
  const t = make('table', 'synastry-table');
  const body = make('tbody');
  body.append(...items.map(aspectRow));
  t.append(body);
  return t;
}

function render(result, n) {
  const houses = new Map(result.transit_houses.map((item) => [item.body, item.house]));
  document.querySelector('#chart-stage').replaceChildren(createSynastryWheel(
    { person_a: result.natal, person_b: result.transit, aspects: result.aspects }, { a: n.a, b: '트랜짓' }));
  document.querySelector('#result-title').textContent = `${n.a === 'A' ? '나' : n.a}의 트랜짓`;
  document.querySelector('#result-subtitle').textContent = `${result.transit.input.date} ${result.transit.input.time} (${result.transit.normalized.timezone}) 기준 · ${result.aspects.length}개 트랜짓 어스펙트`;
  document.querySelector('#positions-body').replaceChildren(...result.transit.bodies.filter((b) => houses.has(b.id)).map((body) => {
    const tr = make('tr');
    tr.append(make('td', '', `${body.symbol} ${BODY_NAMES[body.id]}`), make('td', '', formatWheelPosition(body)), make('td', '', String(houses.get(body.id))));
    return tr;
  }));
  const register = document.querySelector('#aspects-register');
  register.className = 'detail-content';
  const slow = result.aspects.filter((a) => a.slow);
  const fast = result.aspects.filter((a) => !a.slow);
  register.replaceChildren(
    make('p', 'register-note', '느린 행성(목성~명왕성·키론·노드)의 트랜짓이 몇 주~몇 년의 큰 흐름, 빠른 행성은 며칠 단위의 분위기입니다. 접근=점점 정확해지는 중, 분리=지나가는 중.'),
    ...(slow.length ? [make('h4', 'register-subhead', '큰 흐름 · 느린 행성'), table(slow)] : []),
    ...withMore(fast.length ? [make('h4', 'register-subhead', '요즘의 날씨 · 빠른 행성'), table(fast.slice(0, 8))] : [],
      fast.length > 8 ? [table(fast.slice(8))] : [], '빠른 행성 어스펙트', fast.length - 8));
  if (!result.aspects.length) register.append(make('p', '', '허용 orb 안의 트랜짓 어스펙트가 없습니다.'));
  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  const list = make('dl', 'metadata-list');
  for (const [term, value] of [
    ['Rule', `${result.rule_version} · ${Object.entries(result.settings.orbs).map(([k, v]) => `${k} ${v}°`).join(' · ')}`],
    ['Note', result.settings.note],
    ['Natal UTC', `${result.natal.normalized.utc} (${result.natal.normalized.offset} ${result.natal.normalized.timezone})`],
    ['Transit UTC', `${result.transit.normalized.utc} (${result.transit.normalized.offset} ${result.transit.normalized.timezone})`],
    ['Engine', `${result.natal.metadata.engine} ${result.natal.metadata.engine_version}`],
  ]) {
    const row = make('div');
    row.append(make('dt', '', term), make('dd', '', value));
    list.append(row);
  }
  evidence.replaceChildren(list);
}

function markdown(result, n) {
  const lines = [`# ${n.a}의 트랜짓 (${result.transit.input.date} ${result.transit.input.time} ${result.transit.normalized.timezone})`, '',
    '아래는 네이털 차트 위에 해당 시점의 행성을 겹친 트랜짓입니다. 느린 행성 트랜짓을 중심으로 지금 시기의 주제와 타이밍(접근/분리)을 한국어로 해석해 주세요. 예언이 아니라 성찰의 틀로 써 주세요. 계산값은 수정하지 마세요.', '',
    `## 네이털 (${result.natal.input.date} ${result.natal.input.time} · ${result.natal.input.place})`];
  for (const body of result.natal.bodies.filter((b) => BODY_NAMES[b.id] && !['Fortune', 'Spirit', 'SouthNode', 'Lilith'].includes(b.id))) lines.push(`- ${BODY_NAMES[body.id]}: ${body.position} · ${body.house}H`);
  lines.push('', '## 트랜짓 어스펙트');
  for (const a of result.aspects) lines.push(`- 트랜짓 ${BODY_NAMES[a.transit]}${a.retrograde ? '(R)' : ''} ${ASPECT_NAMES[a.name][1]} 네이털 ${BODY_NAMES[a.natal]} · orb ${a.orb.toFixed(2)}° · ${MOTION[a.motion]}`);
  lines.push('', '## 트랜짓 행성의 네이털 하우스');
  for (const item of result.transit_houses) lines.push(`- ${BODY_NAMES[item.body]} → ${item.house}H`);
  return lines.join('\n');
}

const page = mountToolPage({
  kind: 'transits',
  endpoint: '/api/transits',
  shareable: false,
  busyText: '네이털과 트랜짓 시점을 계산하는 중입니다.',
  doneText: '트랜짓 계산을 완료했습니다.',
  extraValidate: () => (!dateInput.value || !timeInput.value || !zoneInput.value.trim() ? '트랜짓 날짜·시각·시간대를 입력하세요.' : ''),
  buildInput: (people) => ({ natal: people[0].payload(), moment: { date: dateInput.value, time: timeInput.value, timezone: zoneInput.value.trim() } }),
  defaultTitle: (n) => `${n.a} 트랜짓`,
  render,
  markdown,
});

function rerunWithMoment() {
  const input = page.currentInput();
  if (!input) return;
  page.run({ ...input, moment: { date: dateInput.value, time: timeInput.value, timezone: zoneInput.value.trim() } });
}
document.querySelectorAll('[data-shift]').forEach((button) => button.addEventListener('click', () => {
  const [y, m, d] = dateInput.value.split('-').map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d + Number(button.dataset.shift)));
  dateInput.value = `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
  rerunWithMoment();
}));
document.querySelector('#moment-now').addEventListener('click', () => { setNow(); rerunWithMoment(); });
