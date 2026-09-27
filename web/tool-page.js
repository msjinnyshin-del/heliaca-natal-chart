// Shared page controller for multi-chart tools (synastry, composite, transits):
// person forms, calculation request, stale-result handling, tabs, markdown copy and private share links.
import { mountPlaceSearch } from './place-search.js';
import { make } from './chart-tables.js';
import { checkBirthDate, mountBirthDate } from './birth-date.js';
import { createProfileStore, profileLabel, takeHandoff } from './profiles.js';

export const BODY_NAMES = { Sun: '태양', Moon: '달', Mercury: '수성', Venus: '금성', Mars: '화성', Jupiter: '목성', Saturn: '토성',
  Uranus: '천왕성', Neptune: '해왕성', Pluto: '명왕성', Chiron: '키론', NorthNode: '북노드', SouthNode: '남노드', Lilith: '릴리스',
  Fortune: '포르투나', Spirit: '스피릿', ASC: 'ASC', MC: 'MC' };
export const ASPECT_NAMES = { Conjunction: ['☌', '합'], Sextile: ['⚹', '섹스타일'], Square: ['□', '스퀘어'], Trine: ['△', '트라인'],
  Quincunx: ['⚻', '퀸컹스'], Opposition: ['☍', '대립'], SemiSquare: ['∠', '세미스퀘어'], Sesquiquadrate: ['⚼', '세스퀴쿼드레이트'],
  Quintile: ['Q', '퀸타일'] };

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

function placeMarkup(p, placeLabel) {
  return `
    <div class="place-field">
      <label class="field-label" for="${p('place')}">${placeLabel}</label>
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
}

function personFields(prefix, label, allowUnknownTime) {
  const p = (id) => `${prefix}${id}`;
  const wrap = make('fieldset', 'synastry-person fields-grid');
  // Static template: only fixed ids/labels from this module, never user input.
  wrap.innerHTML = `
    <legend class="person-legend"></legend>
    <label class="profile-picker" hidden><span>저장된 프로필</span><select id="${p('profile')}"><option value="">불러올 사람을 고르세요</option></select></label>
    <label class="field field-name"><span>이름 <em>선택</em></span><input id="${p('name')}" placeholder="이름 · 닉네임" autocomplete="off"></label>
    <div class="field field-date">
      <span><label for="${p('date')}">생년월일</label></span>
      <div class="calendar-toggle" role="radiogroup" aria-label="달력 종류">
        <label><input type="radio" name="${p('calendar')}" value="gregorian" checked> 양력</label>
        <label><input type="radio" name="${p('calendar')}" value="lunar"> 음력</label>
        <label class="lunar-leap" hidden><input type="checkbox" id="${p('lunar_leap')}"> 윤달</label>
      </div>
      <input id="${p('date')}" placeholder="19900515" aria-describedby="${p('date-hint')}" required>
      <span id="${p('date-hint')}" class="date-hint" aria-live="polite"></span>
    </div>
    <div class="field field-time"><span><label for="${p('time')}">태어난 시각 <b>현지</b></label></span>
      ${allowUnknownTime ? `<label class="time-unknown-toggle"><input type="checkbox" id="${p('time_unknown')}"> 생시 모름</label>` : ''}
      <input id="${p('time')}" type="time" step="60" required></div>
    ${placeMarkup(p, '출생지')}`;
  wrap.querySelector('legend').textContent = label;
  return wrap;
}

function mountPerson(form, slot, onChange, { allowUnknownTime = false, recents } = {}) {
  const prefix = slot.dataset.prefix;
  const label = slot.dataset.label;
  slot.replaceWith(personFields(prefix, label, allowUnknownTime));
  const get = (id) => document.getElementById(`${prefix}${id}`);
  const calendar = () => form.querySelector(`input[name="${prefix}calendar"]:checked`).value;
  const unknown = () => Boolean(get('time_unknown')?.checked);
  const dateField = mountBirthDate({ input: get('date'), calendar, leap: () => get('lunar_leap').checked, hint: get('date-hint') });
  const syncCalendar = () => {
    const lunar = calendar() === 'lunar';
    get('date').placeholder = lunar ? '19900515 (음력)' : '19900515';
    get('lunar_leap').closest('label').hidden = !lunar;
    if (!lunar) get('lunar_leap').checked = false;
    dateField.refresh();
  };
  const syncTime = () => {
    get('time').disabled = unknown();
    get('time').required = !unknown();
    if (unknown()) get('time').value = '';
  };
  for (const radio of form.querySelectorAll(`input[name="${prefix}calendar"]`)) radio.addEventListener('change', syncCalendar);
  get('lunar_leap').addEventListener('change', () => dateField.refresh());
  get('time_unknown')?.addEventListener('change', syncTime);
  const place = mountPlaceSearch({ onChange, prefix, recents });
  return {
    get, place, label: slot.dataset.short || label,
    name: () => get('name').value.trim(),
    validate() {
      const date = checkBirthDate(get('date').value, calendar());
      if (!get('date').value.trim()) return `${this.label}의 생년월일을 입력하세요. 예: 19900515`;
      if (!date.ok) return `${this.label} · ${date.message}`;
      if (!unknown() && !get('time').value) {
        return allowUnknownTime ? `${this.label}의 태어난 시각을 입력하거나 ‘생시 모름’을 선택하세요.` : `${this.label}의 태어난 시각을 입력하세요. 이 도구는 출생 시각이 필요합니다.`;
      }
      if (!place.validate()) return `${this.label}의 출생지를 검색해 선택하거나 좌표를 직접 입력하세요.`;
      return '';
    },
    payload() {
      const lunar = calendar() === 'lunar';
      return {
        date: get('date').value.trim(), calendar: lunar ? 'lunar' : 'gregorian', ...(lunar ? { lunar_leap: get('lunar_leap').checked } : {}),
        ...(unknown() ? {} : { time: get('time').value }), timezone: get('timezone').value.trim(),
        latitude: get('latitude').value === '' ? null : Number(get('latitude').value),
        longitude: get('longitude').value === '' ? null : Number(get('longitude').value),
        place: get('place').value.trim(), house_system: form.querySelector('#house-system').value,
        node_mode: form.querySelector('input[name="node_mode"]:checked').value, time_accuracy: unknown() ? 'unknown' : 'reported',
        location_source: place.source(),
      };
    },
    /** Storable birth profile, or null while the person is incomplete. */
    snapshot() {
      const snapshot = place.snapshot();
      if (!snapshot || this.validate()) return null;
      const lunar = calendar() === 'lunar';
      return { name: this.name(), calendar: lunar ? 'lunar' : 'gregorian', date: get('date').value.trim(),
        lunar_leap: lunar && get('lunar_leap').checked, time_unknown: unknown(), time: unknown() ? null : get('time').value, place: snapshot };
    },
    /** Fills the fields from a saved profile; returns a note when this tool cannot use part of it. */
    restore(profile) {
      get('name').value = profile.name || '';
      form.querySelector(`input[name="${prefix}calendar"][value="${profile.calendar === 'lunar' ? 'lunar' : 'gregorian'}"]`).checked = true;
      syncCalendar();
      get('lunar_leap').checked = Boolean(profile.lunar_leap);
      get('date').value = profile.date;
      if (get('time_unknown')) get('time_unknown').checked = Boolean(profile.time_unknown);
      syncTime();
      get('time').value = profile.time_unknown ? '' : profile.time;
      place.restore(profile.place);
      dateField.refresh();
      return profile.time_unknown && !allowUnknownTime ? `${profileLabel(profile)}은(는) 출생 시각이 없습니다. 이 도구는 출생 시각이 필요하니 시각을 입력하세요.` : '';
    },
  };
}

/** A place-only slot (e.g. the location a solar return is cast for); same search and manual-coordinate rules. */
export function mountPlaceSlot(slot, onChange) {
  const prefix = slot.dataset.placePrefix;  // not data-prefix: that marks birth-data people
  const wrap = make('fieldset', 'synastry-person fields-grid');
  // Static template: only fixed ids/labels, never user input.
  wrap.innerHTML = `<legend class="person-legend"></legend>${placeMarkup((id) => `${prefix}${id}`, slot.dataset.placeLabel || '장소')}`;
  wrap.querySelector('legend').textContent = slot.dataset.label || '장소';
  slot.replaceWith(wrap);
  const get = (id) => document.getElementById(`${prefix}${id}`);
  const place = mountPlaceSearch({ onChange, prefix });
  return {
    element: wrap,
    validate: () => (place.validate() ? '' : `${slot.dataset.label || '장소'}를 검색해 선택하거나 좌표를 직접 입력하세요.`),
    payload: () => ({
      latitude: get('latitude').value === '' ? null : Number(get('latitude').value),
      longitude: get('longitude').value === '' ? null : Number(get('longitude').value),
      timezone: get('timezone').value.trim(), place: get('place').value.trim(), location_source: place.source(),
    }),
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
  const profiles = createProfileStore();
  const recents = () => {
    const seen = new Set();
    return profiles.list().map((item) => item.place.source || {}).filter((source) => {
      if (source.mode !== 'geocoded' || !Number.isInteger(source.place_id) || seen.has(source.place_id)) return false;
      seen.add(source.place_id);
      return true;
    }).slice(0, 5).map((source) => ({ id: source.place_id, label: source.label, latitude: source.reference_latitude,
      longitude: source.reference_longitude, timezone: source.reference_timezone }));
  };
  const people = [...document.querySelectorAll('[data-prefix]')].map((slot) => mountPerson(form, slot, invalidate,
    { allowUnknownTime: Boolean(config.allowUnknownTime), recents }));
  const names = () => sharedNames || { a: people[0]?.name() || 'A', b: people[1]?.name() || 'B' };
  const QUIET_IDS = new Set(['remember-profiles']);
  form.addEventListener('input', (event) => { if (!event.target.id.endsWith('name') && !QUIET_IDS.has(event.target.id)) invalidate(); });

  // House system / node choices live in a collapsed "정밀 설정" panel; defaults calculate as-is.
  const shared = form.querySelector('#house-system')?.closest('.synastry-shared');
  if (shared) {
    const panel = make('details', 'precision-panel tool-precision');
    const summary = make('summary', 'tool-precision-summary');
    summary.append(make('span', '', '정밀 설정 '), make('span', 'precision-state', '열기'), make('small', 'tool-precision-note', ' 기본값 Placidus · True Node로 바로 계산됩니다'));
    shared.replaceWith(panel);
    panel.append(summary, shared);
    panel.addEventListener('toggle', () => { summary.querySelector('.precision-state').textContent = panel.open ? '닫기' : '열기'; });
  }

  // Remember people in this browser (never sent to the server) and offer them in each person's picker.
  const notes = form.querySelector('.form-notes');
  if (notes && people.length) {
    const remember = make('label', 'consent-control');
    remember.innerHTML = '<input type="checkbox" id="remember-profiles" checked> <span>입력한 사람을 이 브라우저에 기억하기 <b>(서버로 보내지 않음)</b></span>';
    notes.prepend(remember);
  }
  function renderPickers() {
    const items = profiles.list();
    for (const person of people) {
      const select = person.get('profile');
      select.closest('label').hidden = !items.length;
      select.replaceChildren(make('option', '', '불러올 사람을 고르세요'), ...items.map((item) => {
        const option = make('option', '', profileLabel(item));
        option.value = item.id;
        return option;
      }));
      select.firstChild.value = '';
    }
  }
  for (const person of people) {
    person.get('profile').addEventListener('change', (event) => {
      const profile = profiles.get(event.target.value);
      event.target.value = '';
      if (!profile) return;
      const note = person.restore(profile);
      invalidate();
      setMessage(note || `${profileLabel(profile)} 정보를 ${person.label}에 불러왔습니다.`, note ? 'error' : 'info');
    });
  }
  function rememberPeople() {
    if (!document.querySelector('#remember-profiles')?.checked) return;
    for (const person of people) {
      const snapshot = person.snapshot();
      if (snapshot) profiles.save(snapshot);
    }
    renderPickers();
  }

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
        const who = whoKey === 'person_a' ? people[0]?.label : whoKey === 'person_b' ? people[1]?.label : whoKey === 'moment' ? (config.momentLabel || '기준 시점') : '';
        throw new Error(`${who ? `${who} · ` : ''}${data.error?.code || ''} ${data.error?.message || `HTTP ${response.status}`}`);
      }
      sharedNames = null;
      document.querySelector('#shared-banner').hidden = true;
      currentInput = input;
      show(data);
      rememberPeople();
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
  renderPickers();
  const sharedToken = new URLSearchParams(window.location.search).get('s');
  if (sharedToken && config.shareable) openShared(sharedToken);
  // A profile handed over from the natal chart fills the first person.
  const handoff = !sharedToken && people.length ? takeHandoff() : null;
  if (handoff) {
    const note = people[0].restore(handoff);
    setMessage(note || `네이털 차트에서 ${profileLabel(handoff)} 정보를 ${people[0].label}에 불러왔습니다.${people[1] ? ` ${people[1].label} 정보를 입력하거나 저장된 프로필에서 고르세요.` : ''}`, note ? 'error' : 'info');
    (people[1]?.get('name') || button).focus();
  }
  return { people, run, invalidate, setMessage, current: () => current, currentInput: () => currentInput };
}
