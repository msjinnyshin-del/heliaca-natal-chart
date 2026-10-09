// Admin engine inspector: birth input → the engine's whole output, field by field, for comparing against
// reference apps. Nothing here generates or corrects astronomical values; every number is the engine's.
import { mountPerson, mountPlaceSlot } from '/tool-page.js';
import { make } from '/chart-tables.js';
import { createNatalWheel } from '/chart.js';
import { createProfileStore, profileLabel } from '/profiles.js';
import { syncChoicePills } from '/birth-date.js';

const TOOLS = [
  { id: 'chart', label: '네이털', people: 1 },
  { id: 'synastry', label: '시너스트리', people: 2 },
  { id: 'composite', label: '컴포지트', people: 2 },
  { id: 'transits', label: '트랜짓', people: 1, moment: true },
  { id: 'solar-return', label: '솔라 리턴', people: 1, solar: true },
  { id: 'progressions', label: '프로그레션', people: 1, moment: true },
];
// Fixed test person used by the engine regression tests (not a real person).
const SAMPLE = { id: 'sample', name: '테스트 NY 1985', calendar: 'gregorian', date: '1985-07-14', time: '21:45', time_unknown: false,
  place: { label: 'New York', latitude: 40.7128, longitude: -74.006, timezone: 'America/New_York',
    source: { mode: 'manual', provider: 'user', place_id: null, label: 'New York', reference_latitude: 40.7128, reference_longitude: -74.006, reference_timezone: 'America/New_York' } } };
const KEY_LABELS = {
  id: 'ID', name: '이름', symbol: '기호', longitude: '황경°', sign_index: 'sign idx', display_sign_index: '표시 sign idx', position: '표기',
  latitude: '황위°', speed: '속도°/일', retrograde: '역행', direction: '운동', near_station: '정지 근접', station_threshold: '정지 임계', house: '하우스',
  declination: '적위°', altitude: '고도°', antiscia: '안티샤°', flags: 'flags', number: '#', a: 'A', b: 'B', angle: '목표각', separation: '분리각°',
  orb: '오브°', allowed_orb: '허용 오브°', rule_version: '규칙', profile_version: '프로파일', target_group: '그룹', motion: '접근/분리',
  stability: '안정성', in_orb_at_representative: '대표 시각 orb 내', windows: '성립 구간', strength: 'strength', strong: 'strong', body: '천체',
  slow: '느린 천체', natal: '네이털', transit: '트랜짓', progressed: '진행', time_sensitivity: '시간 민감도', time_range: '하루 범위',
};
const state = { tool: 'chart', result: null, sections: [], serial: 0, presets: [], envPresets: [], editing: null };

// ---- formatting ---------------------------------------------------------------

function fmt(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? '✓' : '✕';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
  if (Array.isArray(value)) return value.every((item) => typeof item !== 'object' || item === null) ? value.map(fmt).join(', ') : JSON.stringify(value);
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}
const label = (key) => KEY_LABELS[key] || key;

function windowsText(windows) {
  if (!Array.isArray(windows) || !windows.length) return '—';
  return windows.map((w) => `${w.start_local ?? w.start_utc ?? '?'} → ${w.end_local ?? w.end_utc ?? '?'}`).join(' · ');
}

/** Table section from a list of objects: columns are the union of keys, preferred ones first. */
function objectTable(title, items, preferred = [], { note = '', transform = {} } = {}) {
  const list = Array.isArray(items) ? items : [];
  const keys = [...preferred.filter((key) => list.some((item) => key in item))];
  for (const item of list) for (const key of Object.keys(item)) if (!keys.includes(key)) keys.push(key);
  return { title, note, columns: keys.map(label), rows: list.map((item) => keys.map((key) => (transform[key] ? transform[key](item[key], item) : fmt(item[key])))) };
}

function kvTable(title, object, { note = '' } = {}) {
  const entries = object && typeof object === 'object' && !Array.isArray(object) ? Object.entries(object) : [['값', object]];
  return { title, note, columns: ['키', '값'], rows: entries.map(([key, value]) => [key, fmt(value)]) };
}

function jsonSection(title, value) {
  return { title, json: value };
}

// ---- section builders ---------------------------------------------------------

const BODY_ORDER = ['id', 'name', 'symbol', 'longitude', 'position', 'sign_index', 'display_sign_index', 'house', 'latitude', 'speed', 'direction', 'retrograde', 'near_station', 'station_threshold', 'declination', 'altitude', 'antiscia', 'flags'];
const ASPECT_ORDER = ['a', 'b', 'name', 'angle', 'separation', 'orb', 'allowed_orb', 'motion', 'target_group', 'stability', 'in_orb_at_representative', 'windows', 'strength', 'strong', 'slow', 'retrograde', 'rule_version', 'profile_version', 'id'];
const POINT_ORDER = ['id', 'number', 'longitude', 'position', 'sign_index', 'display_sign_index'];

/** Every top-level key of a chart result, in a fixed order; unknown keys fall through as JSON. */
function chartSections(chart, prefix = '') {
  const t = (title) => (prefix ? `${prefix} · ${title}` : title);
  const out = [];
  const used = new Set();
  const take = (key) => { used.add(key); return chart[key]; };
  out.push({ title: t('상태'), columns: ['키', '값'], rows: [['status', fmt(take('status'))], ['calculation_status', fmt(take('calculation_status'))], ['sect (주야)', fmt(take('sect'))], ['rule_version', fmt(take('rule_version'))]] });
  if ('normalized' in chart) out.push(kvTable(t('정규화 (UTC · JD · 시간대)'), take('normalized')));
  if ('unknown_time' in chart) out.push(kvTable(t('생시 모름 · 스캔 범위'), take('unknown_time')));
  if ('bodies' in chart) {
    const bodies = take('bodies');
    out.push(objectTable(t('천체'), bodies.map(({ time_sensitivity, time_range, ...rest }) => rest), BODY_ORDER));
    const sensitive = bodies.filter((b) => b.time_sensitivity || b.time_range);
    if (sensitive.length) {
      out.push(objectTable(t('천체 · 생시 모름 시간 민감도'), sensitive.map((b) => {
        const s = b.time_sensitivity || {};
        const r = s.range || b.time_range || {};
        return { id: b.id, 시작: r.start?.position, 끝: r.end?.position, '이동°': r.degrees, 사인_안정: s.sign_stable, 사인들: s.signs, 진입: s.ingresses, 운동_안정: s.direction_stable, 정지: s.stations,
          ...Object.fromEntries(Object.entries(s).filter(([k]) => !['range', 'sign_stable', 'signs', 'ingresses', 'direction_stable', 'stations'].includes(k))) };
      })));
    }
  }
  if ('angles' in chart) out.push(objectTable(t('각도점'), take('angles'), POINT_ORDER));
  if ('houses' in chart) out.push(objectTable(t('하우스 커스프'), take('houses'), POINT_ORDER));
  if ('aspects' in chart) out.push(objectTable(t('어스펙트'), take('aspects'), ASPECT_ORDER, { transform: { windows: windowsText } }));
  if ('input' in chart) out.push(kvTable(t('입력 echo'), take('input')));
  if ('settings' in chart) out.push(kvTable(t('설정'), take('settings')));
  if ('metadata' in chart) out.push(kvTable(t('메타데이터'), take('metadata')));
  if ('warnings' in chart) out.push({ title: t('경고'), columns: ['#', '내용'], rows: (take('warnings') || []).map((w, i) => [i + 1, fmt(w)]) });
  for (const key of Object.keys(chart)) if (!used.has(key)) out.push(jsonSection(t(key), chart[key]));
  return out;
}

function toolSections(tool, result) {
  const used = new Set();
  const take = (key) => { used.add(key); return result[key]; };
  const out = [];
  const scalars = Object.fromEntries(Object.entries(result).filter(([, v]) => typeof v !== 'object' || v === null));
  for (const key of Object.keys(scalars)) used.add(key);
  const top = (title, key, order, options) => { if (key in result) out.push(objectTable(title, take(key), order, options)); };
  const kv = (title, key) => { if (key in result) out.push(kvTable(title, take(key))); };
  switch (tool) {
    case 'chart':
      return chartSections(result);
    case 'synastry':
      out.push(kvTable('시너스트리 · 결과 상태', scalars));
      top('상호 어스펙트 (A ↔ B)', 'aspects', ASPECT_ORDER);
      if ('overlays' in result) {
        const o = take('overlays');
        out.push(objectTable('하우스 오버레이 · A 천체 → B 하우스', o.a_in_b, ['body', 'longitude', 'house', 'strong']));
        out.push(objectTable('하우스 오버레이 · B 천체 → A 하우스', o.b_in_a, ['body', 'longitude', 'house', 'strong']));
        for (const key of Object.keys(o)) if (!['a_in_b', 'b_in_a'].includes(key)) out.push(jsonSection(`overlays.${key}`, o[key]));
      }
      kv('time_accuracy', 'time_accuracy');
      kv('설정 (orb · 가중)', 'settings');
      if ('person_a' in result) out.push(...chartSections(take('person_a'), 'A'));
      if ('person_b' in result) out.push(...chartSections(take('person_b'), 'B'));
      break;
    case 'composite':
      out.push(kvTable('컴포지트 · 결과 상태', scalars));
      if ('composite' in result) out.push(...chartSections(take('composite'), '컴포지트'));
      kv('time_accuracy', 'time_accuracy');
      kv('설정 (방법)', 'settings');
      if ('person_a' in result) out.push(...chartSections(take('person_a'), 'A'));
      if ('person_b' in result) out.push(...chartSections(take('person_b'), 'B'));
      break;
    case 'transits':
      out.push(kvTable('트랜짓 · 결과 상태', scalars));
      top('트랜짓 → 네이털 어스펙트', 'aspects', ['transit', 'natal', 'name', 'angle', 'separation', 'orb', 'allowed_orb', 'motion', 'slow', 'retrograde', 'a', 'b', 'rule_version']);
      top('트랜짓 천체의 네이털 하우스', 'transit_houses', ['body', 'house']);
      kv('설정 (orb)', 'settings');
      if ('transit' in result) out.push(...chartSections(take('transit'), '트랜짓 시점 차트'));
      if ('natal' in result) out.push(...chartSections(take('natal'), '네이털'));
      break;
    case 'solar-return':
      out.push(kvTable('솔라 리턴 · 결과 상태', scalars));
      kv('귀환 순간 (exact)', 'exact');
      kv('귀환 범위 (return_window · 생시 모름)', 'return_window');
      top('귀환 천체의 네이털 하우스', 'return_in_natal_houses', ['body', 'house']);
      kv('설정', 'settings');
      if ('return' in result) out.push(...chartSections(take('return'), '귀환 차트'));
      if ('natal' in result) out.push(...chartSections(take('natal'), '네이털'));
      break;
    case 'progressions':
      out.push(kvTable('프로그레션 · 상태 (age · solar_arc)', scalars));
      kv('목표 시점 (target)', 'target');
      top('진행 → 네이털 어스펙트', 'aspects', ['progressed', 'natal', 'name', 'angle', 'separation', 'orb', 'allowed_orb', 'a', 'b', 'rule_version']);
      top('진행 천체의 네이털 하우스', 'progressed_in_natal_houses', ['body', 'house']);
      kv('설정', 'settings');
      if ('progressed' in result) out.push(...chartSections(take('progressed'), '진행 차트'));
      if ('natal' in result) out.push(...chartSections(take('natal'), '네이털'));
      break;
    default:
      break;
  }
  for (const key of Object.keys(result)) if (!used.has(key)) out.push(jsonSection(key, result[key]));
  return out;
}

// ---- rendering: DOM and Markdown from the same section model ------------------------

function renderSection(section) {
  const card = make('section', 'adm-card eng-section');
  card.append(make('h3', 'plate-number', section.title));
  if (section.note) card.append(make('p', 'adm-note', section.note));
  if ('json' in section) {
    const pre = make('pre', 'adm-raw', JSON.stringify(section.json, null, 2));
    card.append(pre);
    return card;
  }
  const scroll = make('div', 'table-scroll');
  const table = make('table', 'adm-table eng-table');
  const head = make('thead');
  const headRow = make('tr');
  for (const column of section.columns) { const th = make('th', '', column); th.scope = 'col'; headRow.append(th); }
  head.append(headRow);
  const body = make('tbody');
  if (!section.rows.length) {
    const empty = make('tr', 'adm-muted');
    const td = make('td', '', '(비어 있음)');
    td.colSpan = Math.max(1, section.columns.length);
    empty.append(td);
    body.append(empty);
  }
  for (const row of section.rows) {
    const tr = make('tr');
    for (const cell of row) tr.append(make('td', 'adm-mono', String(cell)));
    body.append(tr);
  }
  table.append(head, body);
  scroll.append(table);
  card.append(scroll);
  return card;
}

const mdCell = (value) => String(value).replace(/\|/g, '\\|').replace(/\n/g, ' ');

function sectionMarkdown(section) {
  const lines = [`## ${section.title}`, ''];
  if (section.note) lines.push(section.note, '');
  if ('json' in section) {
    lines.push('```json', JSON.stringify(section.json, null, 2), '```', '');
    return lines;
  }
  lines.push(`| ${section.columns.map(mdCell).join(' | ')} |`, `| ${section.columns.map(() => '---').join(' | ')} |`);
  for (const row of section.rows) lines.push(`| ${row.map(mdCell).join(' | ')} |`);
  lines.push('');
  return lines;
}

function markdown(tool, input, result, sections) {
  const toolLabel = TOOLS.find((t) => t.id === tool)?.label || tool;
  const lines = [`# 엔진 검토 · ${toolLabel}`, '', `- 도구: \`${tool}\` · 엔진 ${engineVersion(result)}`, `- 입력: \`${JSON.stringify(input)}\``, ''];
  for (const section of sections) lines.push(...sectionMarkdown(section));
  lines.push('## 원본 JSON', '', '```json', JSON.stringify(result, null, 2), '```', '');
  return lines.join('\n');
}

function engineVersion(result) {
  const chart = result?.metadata ? result : (result?.natal || result?.person_a || result?.composite || null);
  const meta = chart?.metadata;
  return meta ? `${meta.engine} ${meta.engine_version} · pyswisseph ${meta.binding_version} · tzdb ${meta.tzdb}` : '—';
}

// ---- page -----------------------------------------------------------------------

const form = document.querySelector('#tool-form');
const message = document.querySelector('#message');
const badge = document.querySelector('#freshness-badge');
const button = document.querySelector('#calculate-button');
const copyMd = document.querySelector('#copy-markdown');
const copyJson = document.querySelector('#copy-json');
const resultHost = document.querySelector('#eng-result');
const profiles = createProfileStore();

const setMessage = (text = '', type = '') => { message.textContent = text; message.className = `message${type ? ` is-${type}` : ''}`; };
const setBadge = (text, kind = '') => { badge.textContent = text; badge.className = `status-badge${kind ? ` is-${kind}` : ''}`; };

function invalidate() {
  state.serial += 1;
  if (state.result) { setBadge('다시 계산 필요', 'stale'); copyMd.disabled = true; copyJson.disabled = true; }
}

const people = [...form.querySelectorAll('[data-prefix]')].map((slot) => mountPerson(form, slot, invalidate, { allowUnknownTime: true, recents: () => [] }));
const returnPlace = mountPlaceSlot(document.querySelector('[data-place-prefix]'), invalidate);
syncChoicePills(form);
form.addEventListener('input', (event) => { if (!event.target.id.endsWith('name')) invalidate(); });

const tool = () => TOOLS.find((t) => t.id === state.tool);

function renderTools() {
  const list = document.querySelector('#eng-tools');
  list.replaceChildren(...TOOLS.map((t) => {
    const b = make('button', '', t.label);
    b.type = 'button';
    b.id = `tool-${t.id}`;
    b.setAttribute('role', 'tab');
    b.addEventListener('click', () => selectTool(t.id));
    return b;
  }));
}

function selectTool(id) {
  state.tool = id;
  const t = tool();
  for (const item of TOOLS) {
    const b = document.querySelector(`#tool-${item.id}`);
    b.setAttribute('aria-selected', String(item.id === id));
    b.tabIndex = item.id === id ? 0 : -1;
  }
  const bFieldset = people[1].get('name').closest('fieldset');
  bFieldset.hidden = t.people < 2;
  document.querySelector('#eng-save-b').hidden = t.people < 2;
  document.querySelector('#eng-moment').hidden = !t.moment;
  document.querySelector('#eng-return').hidden = !t.solar;
  invalidate();
}

// ---- presets ----------------------------------------------------------------------
// Registered people live in the admin database (/api/admin/engine/presets). People still only in the
// NATAL_ADMIN_PRESETS environment variable and old browser-saved profiles are shown so they can be moved in.

const PRESETS_API = '/api/admin/engine/presets';
const presetLabel = (profile) => `${profile.name}${profile.time_unknown ? ' · 생시 모름' : ''}`;

async function presetRequest(method, path = '', body) {
  const response = await fetch(`${PRESETS_API}${path}`, {
    method, credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) { window.location.assign('/admin/login'); return null; }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message || `HTTP ${response.status}`);
  return data;
}

function chipButton(text, title, onClick, extra = '') {
  const b = make('button', `text-button${extra ? ` ${extra}` : ''}`, text);
  b.type = 'button';
  b.title = title;
  b.addEventListener('click', onClick);
  return b;
}

function fillButtons(profile) {
  return [[0, 'A'], [1, 'B']].map(([index, short]) => chipButton(short, `${short}에 채우기`, () => {
    const note = people[index].restore(profile);
    // Refilling A from another chip ends an edit, so "A 내용으로 저장" can never overwrite the wrong person.
    if (index === 0 && state.editing) { state.editing = null; renderPresets(); }
    if (index === 1 && tool().people < 2) setMessage('B는 시너스트리·컴포지트에서만 씁니다.', 'info');
    else setMessage(note || `${short}에 ${profile.name || profileLabel(profile)}을(를) 채웠습니다.`, note ? 'error' : 'info');
    invalidate();
  }));
}

function renderPresets() {
  const host = document.querySelector('#eng-preset-list');
  const chips = [];
  const sample = make('span', 'eng-chip is-builtin');
  sample.append(make('span', 'eng-chip-label', SAMPLE.name), ...fillButtons(SAMPLE));
  chips.push(sample);
  for (const profile of state.presets) {
    const chip = make('span', `eng-chip${state.editing?.id === profile.id ? ' is-editing' : ''}`);
    chip.append(make('span', 'eng-chip-label', presetLabel(profile)), ...fillButtons(profile),
      chipButton('✎', '수정: A 칸에 불러와 고친 뒤 저장', () => startEdit(profile)),
      chipButton('✕', '명단에서 삭제', () => removePreset(profile), 'adm-danger'));
    chips.push(chip);
  }
  for (const profile of state.envPresets) {
    const chip = make('span', 'eng-chip is-builtin is-env');
    chip.title = '환경 변수 NATAL_ADMIN_PRESETS의 사람 (읽기 전용). "가져오기"로 명단에 옮기면 수정·삭제할 수 있습니다.';
    chip.append(make('span', 'eng-chip-label', `${presetLabel(profile)} · env`), ...fillButtons(profile));
    chips.push(chip);
  }
  for (const profile of profiles.list()) {
    const chip = make('span', 'eng-chip is-local');
    chip.title = '이 브라우저(localStorage)에만 저장된 사람';
    chip.append(make('span', 'eng-chip-label', profileLabel(profile)), ...fillButtons(profile),
      chipButton('⇪', '서버 명단에 등록', () => register(profile, () => profiles.remove(profile.id))),
      chipButton('✕', '이 브라우저에서 삭제', () => { profiles.remove(profile.id); renderPresets(); }, 'adm-danger'));
    chips.push(chip);
  }
  host.replaceChildren(...chips);
  const importButton = document.querySelector('#eng-import-env');
  importButton.hidden = !state.envPresets.length;
  importButton.textContent = `환경 변수 ${state.envPresets.length}명 가져오기`;
  const bar = document.querySelector('#eng-edit-bar');
  bar.hidden = !state.editing;
  if (state.editing) document.querySelector('#eng-edit-name').textContent = state.editing.name;
}

async function loadPresets() {
  try {
    const data = await presetRequest('GET');
    if (!data) return;
    state.presets = Array.isArray(data.presets) ? data.presets : [];
    state.envPresets = Array.isArray(data.env_presets) ? data.env_presets : [];
    if (state.editing && !state.presets.some((p) => p.id === state.editing.id)) state.editing = null;
  } catch (error) {
    setMessage(`빠른 입력 명단을 불러오지 못했습니다: ${error.message}`, 'error');
  }
  renderPresets();
}

/** Registers a snapshot of a person; `after` runs only when the server accepted it. */
async function register(profile, after) {
  try {
    const saved = await presetRequest('POST', '', profile);
    if (!saved) return;
    after?.();
    setMessage(`${presetLabel(saved)}을(를) 명단에 등록했습니다.`, 'info');
    await loadPresets();
  } catch (error) {
    setMessage(`등록 실패: ${error.message}`, 'error');
  }
}

function personSnapshot(index) {
  const person = people[index];
  const error = person.validate() || (person.name() ? '' : '명단에 등록하려면 이름을 입력하세요.');
  if (error) { setMessage(error, 'error'); return null; }
  return person.snapshot();
}

function startEdit(profile) {
  state.editing = { id: profile.id, name: profile.name };
  const note = people[0].restore(profile);
  setMessage(note || `${profile.name}을(를) A 칸에 불러왔습니다. 고친 뒤 "A 내용으로 저장"을 누르세요.`, note ? 'error' : 'info');
  invalidate();
  renderPresets();
  people[0].get('name').focus();
}

async function saveEdit() {
  const snapshot = personSnapshot(0);
  if (!snapshot || !state.editing) return;
  try {
    if (!(await presetRequest('POST', `/${state.editing.id}`, snapshot))) return;
    setMessage(`${presetLabel(snapshot)} 수정을 저장했습니다.`, 'info');
    state.editing = null;
    await loadPresets();
  } catch (error) {
    setMessage(`수정 실패: ${error.message}`, 'error');
  }
}

async function removePreset(profile) {
  if (!window.confirm(`${profile.name}을(를) 빠른 입력 명단에서 삭제합니다. 되돌릴 수 없습니다.`)) return;
  try {
    if (!(await presetRequest('DELETE', `/${profile.id}`))) return;
    if (state.editing?.id === profile.id) state.editing = null;
    setMessage(`${profile.name}을(를) 삭제했습니다.`, 'info');
    await loadPresets();
  } catch (error) {
    setMessage(`삭제 실패: ${error.message}`, 'error');
  }
}

for (const [index, id] of [[0, '#eng-save-a'], [1, '#eng-save-b']]) {
  document.querySelector(id).addEventListener('click', () => {
    const snapshot = personSnapshot(index);
    if (snapshot) register(snapshot);
  });
}
document.querySelector('#eng-edit-save').addEventListener('click', saveEdit);
document.querySelector('#eng-edit-cancel').addEventListener('click', () => { state.editing = null; setMessage('수정을 취소했습니다.', 'info'); renderPresets(); });
document.querySelector('#eng-import-env').addEventListener('click', async () => {
  try {
    const data = await presetRequest('POST', '/import');
    if (!data) return;
    setMessage(`환경 변수 명단에서 ${data.imported}명을 가져왔습니다.`, 'info');
    await loadPresets();
  } catch (error) {
    setMessage(`가져오기 실패: ${error.message}`, 'error');
  }
});

// ---- moment / solar return controls ------------------------------------------------

const pad = (n) => String(n).padStart(2, '0');
function setMoment(date) {
  document.querySelector('#moment-date').value = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  document.querySelector('#moment-time').value = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function momentNow() {
  setMoment(new Date());
  document.querySelector('#moment-timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Seoul';
}
momentNow();
document.querySelector('#return-year').value = String(new Date().getFullYear());
for (const b of document.querySelectorAll('[data-shift]')) {
  b.addEventListener('click', () => {
    if (b.dataset.shift === 'now') { momentNow(); invalidate(); return; }
    const [y, m, d] = document.querySelector('#moment-date').value.split('-').map(Number);
    const [hh, mm] = (document.querySelector('#moment-time').value || '00:00').split(':').map(Number);
    const date = new Date(y, m - 1, d, hh, mm);
    if (Number.isNaN(date.getTime())) return;
    date.setDate(date.getDate() + Number(b.dataset.shift));
    setMoment(date);
    invalidate();
  });
}
document.querySelector('#return-same-place').addEventListener('change', (event) => {
  document.querySelector('#eng-return-place').hidden = event.target.checked;
  invalidate();
});

// ---- payload --------------------------------------------------------------------

function aspectProfile() {
  const byName = (name) => form.querySelector(`[name="${name}"]`);
  return {
    version: 'aspects-v3',
    minor: [...form.querySelectorAll('input[name="minor_aspect"]:checked')].map((input) => input.value),
    orb_scale: Number(byName('orb_scale').value),
    targets: { chiron: byName('aspect_chiron').checked, lilith: byName('aspect_lilith').checked, nodes: byName('aspect_nodes').checked,
      lots: byName('aspect_lots').checked, angles: byName('aspect_angles').checked ? ['ASC', 'MC'] : [] },
    orbs: Object.fromEntries(['chiron', 'lilith', 'nodes', 'lots', 'angles'].map((group) => [group, Number(document.querySelector(`#orb-${group}`).value)])),
  };
}

function personPayload(person) {
  return { ...person.payload(), lilith_mode: form.querySelector('input[name="lilith_mode"]:checked').value, aspect_profile: aspectProfile() };
}

function moment() {
  return { date: document.querySelector('#moment-date').value, time: document.querySelector('#moment-time').value, timezone: document.querySelector('#moment-timezone').value.trim() };
}

function validateAndBuild() {
  const t = tool();
  for (const person of people.slice(0, t.people)) {
    const error = person.validate();
    if (error) return { error };
  }
  const a = personPayload(people[0]);
  if (t.people === 2) return { input: { person_a: a, person_b: personPayload(people[1]) } };
  if (t.moment) {
    const m = moment();
    if (!m.date || !m.time || !m.timezone) return { error: '시점의 날짜·시각·시간대를 모두 입력하세요.' };
    return { input: { natal: a, moment: m } };
  }
  if (t.solar) {
    const year = Number(document.querySelector('#return-year').value);
    if (!Number.isInteger(year) || year < 1901 || year > 2100) return { error: '귀환 연도를 1901–2100 사이 정수로 입력하세요.' };
    let location;
    if (document.querySelector('#return-same-place').checked) {
      const { latitude, longitude, timezone, place, location_source } = a;
      location = { latitude, longitude, timezone, place, location_source };
    } else {
      const error = returnPlace.validate();
      if (error) return { error };
      location = returnPlace.payload();
    }
    return { input: { natal: a, year, location } };
  }
  return { input: a };
}

// ---- run ------------------------------------------------------------------------

async function run(event) {
  event.preventDefault();
  const built = validateAndBuild();
  if (built.error) { setMessage(built.error, 'error'); return; }
  const serial = ++state.serial;
  const t = tool();
  button.disabled = true;
  setBadge('계산 중', 'loading');
  setMessage(`${t.label} 계산 중…`);
  try {
    const response = await fetch(`/api/admin/engine/${t.id}`, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(built.input),
    });
    if (response.status === 401) { window.location.assign('/admin/login'); return; }
    const data = await response.json().catch(() => null);
    if (serial !== state.serial) return;
    if (!response.ok) {
      const error = data?.error || {};
      setBadge('오류', 'error');
      setMessage(`${error.code || `HTTP ${response.status}`} · ${error.message || '요청에 실패했습니다.'}${error.details ? ` · ${JSON.stringify(error.details)}` : ''}`, 'error');
      return;
    }
    state.result = data;
    state.input = built.input;
    state.sections = toolSections(t.id, data);
    renderResult(t, data, built.input);
    setBadge('최신 결과');
    setMessage(`${t.label} 계산 완료 · ${state.sections.length}개 섹션 · ${engineVersion(data)}`, 'info');
    copyMd.disabled = false;
    copyJson.disabled = false;
  } catch (error) {
    if (serial !== state.serial) return;
    setBadge('오류', 'error');
    setMessage(`요청 실패: ${error.message}`, 'error');
  } finally {
    button.disabled = false;
  }
}

function renderResult(t, data, input) {
  const nodes = [];
  const chart = t.id === 'chart' ? data : null;
  if (chart && chart.angles?.length) {
    const stage = make('div', 'chart-stage eng-wheel');
    try { stage.append(createNatalWheel(chart)); nodes.push(stage); } catch { /* wheel is optional */ }
  }
  nodes.push(...state.sections.map(renderSection));
  const raw = make('details', 'adm-card eng-raw');
  raw.append(make('summary', 'plate-number', '원본 JSON'), make('pre', 'adm-raw', JSON.stringify(data, null, 2)));
  const inputCard = make('details', 'adm-card eng-raw');
  inputCard.append(make('summary', 'plate-number', '보낸 입력 JSON'), make('pre', 'adm-raw', JSON.stringify(input, null, 2)));
  nodes.push(inputCard, raw);
  resultHost.replaceChildren(...nodes);
  document.querySelector('#eng-version').textContent = engineVersion(data);
}

async function copy(text, done) {
  try { await navigator.clipboard.writeText(text); setMessage(done, 'info'); } catch { setMessage('클립보드에 복사할 수 없습니다. 브라우저 권한을 확인하세요.', 'error'); }
}
copyMd.addEventListener('click', () => copy(markdown(state.tool, state.input, state.result, state.sections), '결과를 Markdown으로 복사했습니다.'));
copyJson.addEventListener('click', () => copy(JSON.stringify(state.result, null, 2), '원본 JSON을 복사했습니다.'));
form.addEventListener('submit', run);

renderTools();
renderPresets();
selectTool('chart');
loadPresets();
