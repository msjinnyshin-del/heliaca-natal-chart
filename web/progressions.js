import { createSynastryWheel } from './synastry-wheel.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';
import { ASPECT_NAMES, BODY_NAMES, formatOrb, mountToolPage } from './tool-page.js';

const dateInput = document.querySelector('#moment-date');
const timeInput = document.querySelector('#moment-time');
const zoneInput = document.querySelector('#moment-timezone');
const pad = (value) => String(value).padStart(2, '0');
const SHOWN = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'ASC', 'MC'];

function setNow() {
  const now = new Date();
  dateInput.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  timeInput.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  zoneInput.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}
setNow();

const moment = () => ({ date: dateInput.value, time: timeInput.value, timezone: zoneInput.value.trim() });
const label = (id) => BODY_NAMES[id] || id;

function aspectTable(items) {
  const table = make('table', 'synastry-table');
  const body = make('tbody');
  body.append(...items.map((aspect) => {
    const [glyph, name] = ASPECT_NAMES[aspect.name] || ['', aspect.name];
    const tr = make('tr', `aspect-${aspect.name.toLowerCase()}`);
    tr.append(make('td', '', `진행 ${label(aspect.progressed)}`), make('td', 'aspect-name', `${glyph} ${name}`),
      make('td', '', `네이털 ${label(aspect.natal)}`), make('td', 'mono', formatOrb(aspect.orb)));
    return tr;
  }));
  table.append(body);
  return table;
}

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
  const natalHouse = new Map(result.progressed_in_natal_houses.map((item) => [item.body, item.house]));
  document.querySelector('#chart-stage').replaceChildren(createSynastryWheel(
    { person_a: result.natal, person_b: result.progressed, aspects: result.aspects }, { a: n.a, b: '진행' }));
  document.querySelector('#result-title').textContent = `${n.a === 'A' ? '나' : n.a}의 진행 차트`;
  document.querySelector('#result-subtitle').textContent =
    `${result.target.local} (${result.target.timezone}) 기준 · 만 ${result.age_years.toFixed(2)}세 · 진행 어스펙트 ${result.aspects.length}개`;
  const points = [...result.progressed.bodies, ...result.progressed.angles];
  document.querySelector('#positions-body').replaceChildren(...SHOWN.map((id) => points.find((p) => p.id === id)).filter(Boolean).map((item) => {
    const tr = make('tr');
    tr.append(make('td', '', `${item.symbol || ''} ${label(item.id)}`.trim()), make('td', '', formatWheelPosition(item)),
      make('td', '', String(natalHouse.get(item.id) ?? '—')));
    return tr;
  }));
  const register = document.querySelector('#aspects-register');
  register.className = 'detail-content';
  register.replaceChildren(make('p', 'register-note',
    '진행 달은 약 2년 반마다 사인을 바꾸며 감정의 계절을, 진행 태양은 약 30년마다 사인을 바꾸며 정체성의 큰 전환을 보여 줍니다. 오브 1° 이내만 표시합니다.'));
  register.append(result.aspects.length ? aspectTable(result.aspects) : make('p', '', '오브 1° 이내의 진행 어스펙트가 없습니다.'));
  const evidence = document.querySelector('#evidence-register');
  evidence.className = 'detail-content';
  evidence.replaceChildren(definitionList([
    ['Rule', `${result.rule_version} · ${result.settings.key} (${result.settings.year_length_days}일)`],
    ['Angles', `${result.settings.angles} · solar arc ${result.solar_arc.toFixed(6)}° · ${result.settings.obliquity}`],
    ['Excluded', result.settings.excluded.join(', ')],
    ['Note', result.settings.note],
    ['Natal UTC', `${result.natal.normalized.utc} (${result.natal.normalized.offset} ${result.natal.normalized.timezone})`],
    ['Progressed UTC', result.progressed.normalized.utc],
    ['Target UTC', result.target.utc],
  ]));
}

function markdown(result, n) {
  const lines = [`# ${n.a}의 세컨더리 프로그레션 (${result.target.local} ${result.target.timezone}, 만 ${result.age_years.toFixed(2)}세)`, '',
    '아래는 출생 후 하루를 인생 1년으로 대응시킨 진행 차트입니다. 진행 달·태양의 사인과 네이털 하우스, 진행→네이털 어스펙트를 중심으로 지금 시기의 내면 흐름을 한국어로 해석해 주세요. 예언이 아니라 성찰의 틀로 쓰고, 계산값은 수정하지 마세요.', '',
    '## 진행 위치'];
  const natalHouse = new Map(result.progressed_in_natal_houses.map((item) => [item.body, item.house]));
  const points = [...result.progressed.bodies, ...result.progressed.angles];
  for (const id of SHOWN) {
    const item = points.find((p) => p.id === id);
    if (item) lines.push(`- 진행 ${label(id)}: ${item.position}${natalHouse.has(id) ? ` · 네이털 ${natalHouse.get(id)}H` : ''}`);
  }
  lines.push('', '## 진행 → 네이털 어스펙트 (오브 1°)');
  for (const a of result.aspects) lines.push(`- 진행 ${label(a.progressed)} ${(ASPECT_NAMES[a.name] || ['', a.name])[1]} 네이털 ${label(a.natal)} · orb ${a.orb.toFixed(2)}°`);
  lines.push('', `각도점은 ${result.settings.angles}(태양 호 ${result.solar_arc.toFixed(2)}°) 방식입니다.`);
  return lines.join('\n');
}

const page = mountToolPage({
  kind: 'progressions',
  momentLabel: '진행 기준 시점',
  endpoint: '/api/progressions',
  shareable: false,
  busyText: '진행 시점과 각도점을 계산하는 중입니다.',
  doneText: '프로그레션 계산을 완료했습니다.',
  extraValidate: () => (!dateInput.value || !timeInput.value || !zoneInput.value.trim() ? '기준 날짜·시각·시간대를 입력하세요.' : ''),
  buildInput: (people) => ({ natal: people[0].payload(), moment: moment() }),
  defaultTitle: (n) => `${n.a} 프로그레션`,
  render,
  markdown,
});

function rerun() {
  const input = page.currentInput();
  if (input) page.run({ ...input, moment: moment() });
}
document.querySelectorAll('[data-shift]').forEach((button) => button.addEventListener('click', () => {
  const [y, m, d] = dateInput.value.split('-').map(Number);
  const shifted = new Date(Date.UTC(y, m - 1, d + Number(button.dataset.shift)));
  dateInput.value = `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`;
  rerun();
}));
document.querySelector('#moment-now').addEventListener('click', () => { setNow(); rerun(); });
