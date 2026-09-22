// Shared page controller for multi-chart tools (synastry, composite, transits):
// person forms, calculation request, stale-result handling, tabs, markdown copy and private share links.
import { mountPlaceSearch } from './place-search.js';
import { make } from './chart-tables.js';

export const BODY_NAMES = { Sun: '태양', Moon: '달', Mercury: '수성', Venus: '금성', Mars: '화성', Jupiter: '목성', Saturn: '토성',
  Uranus: '천왕성', Neptune: '해왕성', Pluto: '명왕성', Chiron: '키론', NorthNode: '북노드', SouthNode: '남노드', Lilith: '릴리스',
  Fortune: '포르투나', Spirit: '스피릿', ASC: 'ASC', MC: 'MC' };
export const ASPECT_NAMES = { Conjunction: ['☌', '합'], Sextile: ['⚹', '섹스타일'], Square: ['□', '스퀘어'], Trine: ['△', '트라인'],
  Quincunx: ['⚻', '퀸컹스'], Opposition: ['☍', '대립'] };

export function formatOrb(x) {
  return `${Math.floor(x)}°${String(Math.floor((x % 1) * 60)).padStart(2, '0')}′`;
}

export function withMore(visible, hidden, label, count) {
  const nodes = [...visible];
  if (hidden.length) {
    const more = make('details', 'more-toggle');
    more.append(make('summary', '', `${label} ${count}개 더 보기`), ...hidden);
    nodes.push(more);
  }
  return nodes;
}

function personFields(prefix, label) {
  const p = (id) => `${prefix}${id}`;
  const wrap = make('fieldset', 'synastry-person fields-grid');
  // Static template: only fixed ids/labels from this module, never user input.
  wrap.innerHTML = `
    <legend class="person-legend"></legend>
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
  wrap.querySelector('legend').textContent = label;
  return wrap;
}

function mountPerson(form, slot, onChange) {
  const prefix = slot.dataset.prefix;
  const label = slot.dataset.label;
  slot.replaceWith(personFields(prefix, label));
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
  const place = mountPlaceSearch({ onChange, prefix });
  return {
    get, place, label: slot.dataset.short || label,
    name: () => get('name').value.trim(),
    validate() {
      if (!place.validate()) return `${this.label}의 출생지를 검색해 선택하거나 좌표를 직접 입력하세요.`;
      if (!get('date').value || !get('time').value) return `${this.label}의 생년월일과 시각을 입력하세요.`;
      return '';
    },
    payload() {
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
}

/**
 * config: { kind, endpoint, buildInput(people), render(result, names, ctx), markdown(result, names),
 *           defaultTitle(names), shareable, busyText, doneText, extraValidate? }
 */
export function mountToolPage(config) {
  const form = document.querySelector('#tool-form');
  const message = document.querySelector('#message');
  const button = document.querySelector('#calculate-button');
  const badge = document.querySelector('#freshness-badge');
  const copyButton = document.querySelector('#copy-markdown');
  const workbench = document.querySelector('#tool-workbench');
  const sharePanel = document.querySelector('#share-panel');
  const savedKey = `heliaca.${config.kind}.saved`;
  let current = null;
  let currentInput = null;
  let sharedNames = null;
  let serial = 0;
  let lastShare = null;

  const setMessage = (text = '', type = '') => { message.textContent = text; message.className = `message${type ? ` is-${type}` : ''}`; };
  const setBadge = (text, state = '') => { badge.textContent = text; badge.className = `status-badge${state ? ` is-${state}` : ''}`; };
  function invalidate() {
    serial += 1;
    button.disabled = false;
    if (current) {
      copyButton.disabled = true;
      if (sharePanel) sharePanel.hidden = true;
      setBadge('다시 계산 필요', 'stale');
    }
  }
  const people = [...document.querySelectorAll('[data-prefix]')].map((slot) => mountPerson(form, slot, invalidate));
  const names = () => sharedNames || { a: people[0]?.name() || 'A', b: people[1]?.name() || 'B' };
  form.addEventListener('input', (event) => { if (!event.target.id.endsWith('name')) invalidate(); });

  function show(result) {
    const n = names();
    current = result;
    config.render(result, n);
    copyButton.disabled = false;
    setBadge(sharedNames ? '공유된 결과' : '현재 입력 결과');
    if (sharePanel) {
      sharePanel.hidden = Boolean(sharedNames) || !config.shareable;
      document.querySelector('#share-result').hidden = true;
      document.querySelector('#share-title-input').value = config.defaultTitle(n);
    }
  }

  async function run(input) {
    const request = ++serial;
    button.disabled = true;
    workbench.setAttribute('aria-busy', 'true');
    setBadge('계산 중', 'loading');
    setMessage(config.busyText, 'info');
    try {
      const response = await fetch(config.endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(input),
      });
      const data = await response.json();
      if (request !== serial) return;
      if (!response.ok || data.error) {
        const whoKey = data.error?.details?.person;
        const who = whoKey === 'person_a' ? people[0]?.label : whoKey === 'person_b' ? people[1]?.label : whoKey === 'moment' ? '트랜짓 시점' : '';
        throw new Error(`${who ? `${who} · ` : ''}${data.error?.code || ''} ${data.error?.message || `HTTP ${response.status}`}`);
      }
      sharedNames = null;
      document.querySelector('#shared-banner').hidden = true;
      currentInput = input;
      show(data);
      setMessage(config.doneText, 'info');
    } catch (error) {
      if (request !== serial) return;
      setBadge('계산 실패', 'error');
      setMessage(error.message, 'error');
    } finally {
      if (request === serial) button.disabled = false;
      workbench.setAttribute('aria-busy', 'false');
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    for (const person of people) {
      const problem = person.validate();
      if (problem) { setMessage(problem, 'error'); return; }
    }
    const extra = config.extraValidate?.();
    if (extra) { setMessage(extra, 'error'); return; }
    run(config.buildInput(people));
  });

  copyButton.addEventListener('click', async () => {
    if (!current) return;
    try {
      await navigator.clipboard.writeText(config.markdown(current, names()));
      setMessage('해석용 마크다운을 복사했습니다. 출생 정보가 포함되어 있으니 공유에 주의하세요.', 'info');
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

  // ---- save & share ---------------------------------------------------------
  const readSaved = () => {
    try { return JSON.parse(window.localStorage.getItem(savedKey) || '[]').filter((x) => x && typeof x.token === 'string'); } catch { return []; }
  };
  const writeSaved = (items) => { try { window.localStorage.setItem(savedKey, JSON.stringify(items)); } catch { /* link still works */ } };
  const shareUrl = (token) => `${window.location.origin}/${config.kind}.html?s=${encodeURIComponent(token)}`;

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
    const panel = document.querySelector('#saved-panel');
    if (!panel) return;
    const items = readSaved();
    panel.hidden = !items.length;
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

  if (config.shareable && sharePanel) {
    document.querySelector('#share-create').addEventListener('click', async () => {
      if (!current || !currentInput) return;
      const title = document.querySelector('#share-title-input').value.trim() || config.defaultTitle(names());
      const createButton = document.querySelector('#share-create');
      createButton.disabled = true;
      try {
        const response = await fetch('/api/share', {
          method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ kind: config.kind, title, names: names(), input: currentInput }),
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
  }

  async function openShared(token) {
    setBadge('불러오는 중', 'loading');
    try {
      const response = await fetch(`/api/share/${encodeURIComponent(token)}`, { headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error?.message || '공유 링크를 열 수 없습니다.');
      if (data.kind !== config.kind) throw new Error('다른 종류의 공유 링크입니다.');
      sharedNames = { a: data.names?.a || 'A', b: data.names?.b || 'B' };
      currentInput = null;
      show(data.result);
      if (data.title) document.querySelector('#result-title').textContent = data.title;
      const banner = document.querySelector('#shared-banner');
      banner.hidden = false;
      banner.replaceChildren(make('span', '', `공유된 차트 · ${sharedNames.a} & ${sharedNames.b}. 새 차트를 만들려면 위에 출생 정보를 입력하세요.`));
      workbench.scrollIntoView({ block: 'start' });
    } catch (error) {
      setBadge('열기 실패', 'error');
      setMessage(error.message, 'error');
    }
  }

  renderSaved();
  const sharedToken = new URLSearchParams(window.location.search).get('s');
  if (sharedToken && config.shareable) openShared(sharedToken);
  return { people, run, invalidate, setMessage, current: () => current, currentInput: () => currentInput };
}
