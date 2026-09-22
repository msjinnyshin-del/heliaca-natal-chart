import { createSynastryWheel } from './synastry-wheel.js';
import { mountPlaceSearch } from './place-search.js';
import { formatWheelPosition } from './chart-profile.js';
import { make } from './chart-tables.js';

const form = document.querySelector('#synastry-form');
const message = document.querySelector('#message');
const button = document.querySelector('#calculate-button');
const badge = document.querySelector('#freshness-badge');
const copyButton = document.querySelector('#copy-markdown');
const workbench = document.querySelector('#synastry-workbench');
const sharePanel = document.querySelector('#share-panel');
const SAVED_KEY = 'heliaca.synastry.saved';

const BODY_NAMES = { Sun: '태양', Moon: '달', Mercury: '수성', Venus: '금성', Mars: '화성', Jupiter: '목성', Saturn: '토성',
  Uranus: '천왕성', Neptune: '해왕성', Pluto: '명왕성', Chiron: '키론', NorthNode: '북노드', ASC: 'ASC', MC: 'MC' };
const ASPECT_NAMES = { Conjunction: ['☌', '합'], Sextile: ['⚹', '섹스타일'], Square: ['□', '스퀘어'], Trine: ['△', '트라인'], Quincunx: ['⚻', '퀸컹스'], Opposition: ['☍', '대립'] };
const ROWS = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto', 'Chiron', 'NorthNode'];

function personFields(prefix, label) {
  const p = (id) => `${prefix}${id}`;
  const wrap = make('fieldset', 'synastry-person fields-grid');
  wrap.innerHTML = `
    <legend class="person-legend">${label}</legend>
    <label class="field field-name"><span>이름 <em>선택</em></span><input id="${p('name')}" placeholder="이름 · 닉네임" autocomplete="off"></label>
    <div class="field field-date">
      <span><label for="${p('date')}">생년월일</label></span>
      <div class="calendar-toggle" role="radiogroup" aria-label="달력 종류">
        <label><input type="radio" name="${p('calendar')}" value="gregorian" checked> 양력</label>
        <label><input type="radio" name="${p('calendar')}" value="lunar"> 음력</label>
        <label class="lunar-leap" hidden><input type="checkbox" id="${p('lunar_leap')}"> 윤달</label>
      </div>
      <input id="${p('date')}" type="date" required>
    </div>
    <label class="field field-time"><span>태어난 시각 <b>현지</b></span><input id="${p('time')}" type="time" step="60" required></label>
    <div class="place-field">
      <label class="field-label" for="${p('place')}">출생지</label>
      <div class="place-search-row">
        <input id="${p('place')}" type="search" role="combobox" aria-autocomplete="list" aria-controls="${p('place-results')}" aria-expanded="false" autocomplete="off" placeholder="예: 서울, 부산, New York" required>
        <button id="${p('place-search-button')}" class="place-search-button" type="button">검색</button>
      </div>
      <p id="${p('place-status')}" class="place-status" aria-live="polite">도시를 입력한 뒤 검색하세요.</p>
      <ul id="${p('place-results')}" class="place-results" role="listbox" hidden></ul>
      <p id="${p('place-warning')}" class="place-warning" role="alert" hidden></p>
    </div>
    <div class="location-controls">
      <label class="manual-location-control"><input id="${p('manual-location-toggle')}" type="checkbox"> <span>좌표 직접 입력</span></label>
      <details id="${p('location-details')}" class="settings-details location-details">
        <summary>좌표와 시간대 확인</summary>
        <div class="location-grid">
          <label class="field"><span>위도</span><input id="${p('latitude')}" type="number" step="any" min="-90" max="90" readonly required></label>
          <label class="field"><span>경도</span><input id="${p('longitude')}" type="number" step="any" min="-180" max="180" readonly required></label>
          <label class="field"><span>IANA timezone</span><input id="${p('timezone')}" spellcheck="false" readonly required></label>
        </div>
      </details>
    </div>`;
  return wrap;
}

const people = ['a-', 'b-'].map((prefix) => {
  const slot = document.querySelector(`[data-prefix="${prefix}"]`);
  slot.replaceWith(personFields(prefix, slot.dataset.label));
  const get = (id) => document.getElementById(`${prefix}${id}`);
  const calendar = () => form.querySelector(`input[name="${prefix}calendar"]:checked`).value;
  for (const radio of form.querySelectorAll(`input[name="${prefix}calendar"]`)) {
    radio.addEventListener('change', () => {
      const lunar = calendar() === 'lunar';
      const date = get('date');
      const value = date.value;
      date.type = lunar ? 'text' : 'date';
      date.placeholder = lunar ? 'YYYY-MM-DD (음력)' : '';
      date.value = value;
      get('lunar_leap').closest('label').hidden = !lunar;
      if (!lunar) get('lunar_leap').checked = false;
    });
  }
  const place = mountPlaceSearch({ onChange: invalidate, prefix });
  return {
    get, place,
    name: () => get('name').value.trim(),
    payload: () => {
      const lunar = calendar() === 'lunar';
      return {
        date: get('date').value.trim(), calendar: lunar ? 'lunar' : 'gregorian', ...(lunar ? { lunar_leap: get('lunar_leap').checked } : {}),
        time: get('time').value, timezone: get('timezone').value.trim(),
        latitude: get('latitude').value === '' ? null : Number(get('latitude').value),
        longitude: get('longitude').value === '' ? null : Number(get('longitude').value),
        place: get('place').value.trim(), house_system: form.querySelector('#house-system').value,
        node_mode: form.querySelector('input[name="node_mode"]:checked').value, time_accuracy: 'reported',
        location_source: place.source(),
      };
    },
  };
});

let current = null;
let currentInput = null;
let sharedNames = null;
let serial = 0;

function setMessage(text = '', type = '') {
  message.textContent = text;
  message.className = `message${type ? ` is-${type}` : ''}`;
}
function setBadge(text, state = '') {
  badge.textContent = text;
  badge.className = `status-badge${state ? ` is-${state}` : ''}`;
}
function names() {
  if (sharedNames) return sharedNames;
  return { a: people[0].name() || 'A', b: people[1].name() || 'B' };
}
function invalidate() {
  serial += 1;
  button.disabled = false;
  if (current) {
    copyButton.disabled = true;
    sharePanel.hidden = true;
    setBadge('다시 계산 필요', 'stale');
  }
}
form.addEventListener('input', (event) => { if (!event.target.id.endsWith('name')) invalidate(); });

function signed(x) { return `${Math.floor(x)}°${String(Math.floor((x % 1) * 60)).padStart(2, '0')}′`; }

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
    make('td', 'mono', `${signed(aspect.orb)} / ${aspect.allowed_orb}°`));
  return tr;
}

function withMore(visible, hidden, label, count) {
  const nodes = [...visible];
  if (hidden.length) {
    const more = make('details', 'more-toggle');
    more.append(make('summary', '', `${label} ${count}개 더 보기`), ...hidden);
    nodes.push(more);
  }
  return nodes;
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

function render(result) {
  const n = names();
  current = result;
  document.querySelector('#chart-stage').replaceChildren(createSynastryWheel(result, n));
  document.querySelector('#result-title').textContent = `${n.a} × ${n.b} 시너스트리`;
  document.querySelector('#result-subtitle').textContent = `${result.aspects.length}개의 상호 어스펙트 · ${result.person_a.settings.house_system} 하우스`;
  renderPositions(result, n);
  renderAspects(result, n);
  renderOverlays(result, n);
  renderEvidence(result, n);
  copyButton.disabled = false;
  setBadge(sharedNames ? '공유된 결과' : '현재 입력 결과');
  sharePanel.hidden = Boolean(sharedNames);
  document.querySelector('#share-result').hidden = true;
  document.querySelector('#share-title-input').value = `${n.a} & ${n.b}`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  for (const [index, person] of people.entries()) {
    const label = index ? '상대(B)' : '나(A)';
    if (!person.place.validate()) { setMessage(`${label}의 출생지를 검색해 선택하거나 좌표를 직접 입력하세요.`, 'error'); return; }
    if (!person.get('date').value || !person.get('time').value) { setMessage(`${label}의 생년월일과 시각을 입력하세요.`, 'error'); person.get('date').focus(); return; }
  }
  const request = ++serial;
  button.disabled = true;
  workbench.setAttribute('aria-busy', 'true');
  setBadge('계산 중', 'loading');
  setMessage('두 차트를 계산하는 중입니다.', 'info');
  const input = { person_a: people[0].payload(), person_b: people[1].payload() };
  try {
    const response = await fetch('/api/synastry', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(input),
    });
    const data = await response.json();
    if (request !== serial) return;
    if (!response.ok || data.error) {
      const who = data.error?.details?.person === 'person_b' ? '상대(B)' : data.error?.details?.person === 'person_a' ? '나(A)' : '';
      throw new Error(`${who ? `${who} · ` : ''}${data.error?.code || ''} ${data.error?.message || `HTTP ${response.status}`}`);
    }
    sharedNames = null;
    document.querySelector('#shared-banner').hidden = true;
    currentInput = input;
    render(data);
    setMessage('시너스트리 계산을 완료했습니다.', 'info');
  } catch (error) {
    if (request !== serial) return;
    setBadge('계산 실패', 'error');
    setMessage(error.message, 'error');
  } finally {
    if (request === serial) button.disabled = false;
    workbench.setAttribute('aria-busy', 'false');
  }
});

copyButton.addEventListener('click', async () => {
  if (!current) return;
  try {
    await navigator.clipboard.writeText(synastryMarkdown(current, names()));
    setMessage('해석용 마크다운을 복사했습니다. 두 사람의 출생 정보가 포함되어 있으니 공유에 주의하세요.', 'info');
  } catch {
    setMessage('클립보드 복사에 실패했습니다.', 'error');
  }
});

document.querySelectorAll('[role="tab"]').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[role="tab"]').forEach((item) => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.querySelector(`#${item.getAttribute('aria-controls')}`).hidden = !selected;
    });
  });
});

// ---- save & share ----------------------------------------------------------

function readSaved() {
  try { return JSON.parse(window.localStorage.getItem(SAVED_KEY) || '[]').filter((x) => x && typeof x.token === 'string'); } catch { return []; }
}
function writeSaved(items) {
  try { window.localStorage.setItem(SAVED_KEY, JSON.stringify(items)); } catch { /* private mode: link still works */ }
}
function shareUrl(token) {
  return `${window.location.origin}/synastry.html?s=${encodeURIComponent(token)}`;
}

async function deleteShare(item) {
  const response = await fetch(`/api/share/${encodeURIComponent(item.token)}/delete`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ delete_key: item.delete_key }),
  });
  // 404 means it is already gone; either way drop it locally.
  if (!response.ok && response.status !== 404) throw new Error('링크를 삭제하지 못했습니다.');
  writeSaved(readSaved().filter((x) => x.token !== item.token));
  renderSaved();
}

function renderSaved() {
  const items = readSaved();
  document.querySelector('#saved-panel').hidden = !items.length;
  document.querySelector('#saved-list').replaceChildren(...items.map((item) => {
    const li = make('li');
    const link = make('a', '', item.title || '제목 없음');
    link.href = shareUrl(item.token);
    const remove = make('button', 'text-button', '삭제');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (!window.confirm(`“${item.title}” 링크를 삭제할까요? 링크를 받은 사람도 더 이상 볼 수 없습니다.`)) return;
      try { await deleteShare(item); setMessage('공유 링크를 삭제했습니다.', 'info'); } catch (error) { setMessage(error.message, 'error'); }
    });
    li.append(link, make('small', '', (item.created || '').slice(0, 10)), remove);
    return li;
  }));
}

let lastShare = null;
document.querySelector('#share-create').addEventListener('click', async () => {
  if (!current || !currentInput) return;
  const title = document.querySelector('#share-title-input').value.trim() || `${names().a} & ${names().b}`;
  const createButton = document.querySelector('#share-create');
  createButton.disabled = true;
  try {
    const response = await fetch('/api/share', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ kind: 'synastry', title, names: names(), input: currentInput }),
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error?.message || '링크를 만들지 못했습니다.');
    lastShare = { token: data.token, delete_key: data.delete_key, title, created: new Date().toISOString() };
    writeSaved([lastShare, ...readSaved()]);
    renderSaved();
    document.querySelector('#share-url').value = shareUrl(data.token);
    document.querySelector('#share-result').hidden = false;
    setMessage('저장했습니다. 링크를 복사해 공유하세요.', 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  } finally {
    createButton.disabled = false;
  }
});
document.querySelector('#share-copy').addEventListener('click', async () => {
  const input = document.querySelector('#share-url');
  try { await navigator.clipboard.writeText(input.value); setMessage('링크를 복사했습니다.', 'info'); } catch { input.select(); }
});
document.querySelector('#share-delete').addEventListener('click', async () => {
  if (!lastShare || !window.confirm('이 공유 링크를 삭제할까요?')) return;
  try {
    await deleteShare(lastShare);
    lastShare = null;
    document.querySelector('#share-result').hidden = true;
    setMessage('공유 링크를 삭제했습니다.', 'info');
  } catch (error) { setMessage(error.message, 'error'); }
});

async function openShared(token) {
  setBadge('불러오는 중', 'loading');
  try {
    const response = await fetch(`/api/share/${encodeURIComponent(token)}`, { headers: { Accept: 'application/json' } });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error?.message || '공유 링크를 열 수 없습니다.');
    sharedNames = { a: data.names?.a || 'A', b: data.names?.b || 'B' };
    currentInput = null;
    render(data.result);
    if (data.title) document.querySelector('#result-title').textContent = data.title;
    const banner = document.querySelector('#shared-banner');
    banner.hidden = false;
    banner.replaceChildren(make('span', '', `공유된 시너스트리 · ${sharedNames.a} & ${sharedNames.b}. 새 차트를 만들려면 위에 출생 정보를 입력하세요.`));
    workbench.scrollIntoView({ block: 'start' });
  } catch (error) {
    setBadge('열기 실패', 'error');
    setMessage(error.message, 'error');
  }
}

renderSaved();
const sharedToken = new URLSearchParams(window.location.search).get('s');
if (sharedToken) openShared(sharedToken);
