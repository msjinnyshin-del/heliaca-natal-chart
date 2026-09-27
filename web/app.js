import { createNatalWheel } from './chart.js';
import { norm } from './geometry.js';
import { createRequestState, requestFingerprint } from './request-state.js';
import { mountInterpretationHandoff } from './interpretation-handoff.js';
import { mountPlaceSearch } from './place-search.js';
import { buildAngleEntries, buildAspectGrid, buildHouseGrid, buildPositionRows, make, sectLabel } from './chart-tables.js';
import { buildClientContext, captureAttribution, getVisitorId } from './client-context.js';
import { mountBirthDate, syncChoicePills } from './birth-date.js';
import { createProfileStore, profileLabel, setHandoff } from './profiles.js';

const form = document.querySelector('#chart-form');
const workbench = document.querySelector('#chart-workbench');
const message = document.querySelector('#message');
const calculateButton = document.querySelector('#calculate-button');
const downloadButton = document.querySelector('#download-svg');
const freshnessBadge = document.querySelector('#freshness-badge');
const chartStage = document.querySelector('#chart-stage');
const resultTitle = document.querySelector('#result-title');
const resultSubtitle = document.querySelector('#result-subtitle');

const ERROR_MESSAGES = {
  INVALID_INPUT: '입력값을 다시 확인해 주세요.',
  AMBIGUOUS_LOCAL_TIME: 'DST가 겹치는 현지 시각입니다. 서버가 제시한 fold 후보를 확인해 주세요.',
  NONEXISTENT_LOCAL_TIME: 'DST 전환으로 존재하지 않는 현지 시각입니다. 실제 시각을 수정해 주세요.',
  TIMEZONE_NEEDS_REVIEW: '이 시간대의 역사 자료는 추가 검토가 필요합니다.',
  UNSUPPORTED_DATE: '현재 계산 엔진이 지원하지 않는 날짜입니다.',
  EPHEMERIS_DATA_MISSING: '필수 Swiss Ephemeris 데이터가 없습니다.',
  UNEXPECTED_EPHEMERIS_FALLBACK: '승인되지 않은 천체력 fallback이 감지되어 계산을 중단했습니다.',
  HOUSE_SYSTEM_UNAVAILABLE: '해당 위치에서 요청한 하우스 시스템을 계산할 수 없습니다. 다른 시스템을 명시적으로 선택하세요.',
};

// Anonymous random id + first-touch UTM; storage failures (private mode) only lose attribution.
let storage = null;
try { storage = window.localStorage; } catch { storage = null; }
const visitorId = getVisitorId(storage);
const attribution = captureAttribution(storage, window.location.search);

function clientContext() {
  return buildClientContext({ visitorId, name: byName('name').value, consent: byName('store_consent').checked, attribution });
}

// Deletes every row this browser's anonymous id produced (stored input and statistics alike).
document.querySelector('#delete-my-data').addEventListener('click', async () => {
  if (!visitorId) {
    setMessage('이 브라우저에서는 저장 기록을 식별할 수 없습니다.', 'error');
    return;
  }
  if (!window.confirm('이 브라우저에서 계산한 모든 저장 기록(서버)과 이 브라우저에 기억한 프로필을 삭제합니다. 되돌릴 수 없습니다.')) return;
  profiles.clear();
  renderProfileShelf();
  try {
    const response = await fetch('/api/my-data/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ visitor_id: visitorId }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error?.message || `HTTP ${response.status}`);
    setMessage(data.deleted ? `저장 기록 ${data.deleted}건을 삭제했습니다.` : '이 브라우저로 저장된 기록이 없습니다.', 'info');
  } catch (error) {
    setMessage(`저장 기록을 삭제하지 못했습니다 · ${error.message}`, 'error');
  }
});

let currentResult = null;
let currentFingerprint = '';
let currentPayload = null;
let requestSerial = 0;
let controller = null;
const requestState = createRequestState();
const handoff = mountInterpretationHandoff({
  getCurrentExport: () => currentResult && currentPayload && requestFingerprint(getPayload()) === currentFingerprint
    ? {chart: currentResult, payload: currentPayload, name: byName('name').value.trim()} : null,
  onMessage: setMessage,
});
const profiles = createProfileStore();
const placeSearch = mountPlaceSearch({onChange: invalidateResult, recents: recentPlaces});
const dateField = mountBirthDate({
  input: form.elements.namedItem('date'), calendar: selectedCalendar,
  leap: () => form.elements.namedItem('lunar_leap').checked, hint: document.querySelector('#date-hint'),
});
const synastryLink = document.querySelector('#to-synastry');
let currentProfile = null;

function recentPlaces() {
  const seen = new Set();
  return profiles.list().map((item) => item.place).filter((place) => {
    const source = place.source || {};
    if (source.mode !== 'geocoded' || !Number.isInteger(source.place_id) || seen.has(source.place_id)) return false;
    seen.add(source.place_id);
    return true;
  }).slice(0, 5).map((place) => ({ id: place.source.place_id, label: place.source.label || place.label,
    latitude: place.source.reference_latitude, longitude: place.source.reference_longitude, timezone: place.source.reference_timezone }));
}

function profileFromForm() {
  const place = placeSearch.snapshot();
  if (!place) return null;
  return { name: byName('name').value.trim(), calendar: selectedCalendar(), date: byName('date').value.trim(),
    lunar_leap: selectedCalendar() === 'lunar' && byName('lunar_leap').checked,
    time_unknown: timeUnknown(), time: timeUnknown() ? null : byName('time').value, place };
}

const refreshPills = syncChoicePills(form);

function applyProfile(profile) {
  byName('name').value = profile.name || '';
  form.querySelector(`input[name="calendar"][value="${profile.calendar === 'lunar' ? 'lunar' : 'gregorian'}"]`).checked = true;
  syncCalendarControls();
  byName('lunar_leap').checked = Boolean(profile.lunar_leap);
  byName('date').value = profile.date;
  byName('time_unknown').checked = Boolean(profile.time_unknown);
  syncTimeControls();
  if (!profile.time_unknown) byName('time').value = profile.time;
  placeSearch.restore(profile.place);
  dateField.refresh();
  refreshPills();  // programmatic .checked changes fire no change event
  invalidateResult();
}

function renderProfileShelf() {
  const shelf = document.querySelector('#profile-shelf');
  const items = profiles.list();
  shelf.hidden = !items.length;
  document.querySelector('#profile-chips').replaceChildren(...items.map((item) => {
    const chip = make('span', 'profile-chip');
    const load = make('button', 'profile-load', profileLabel(item));
    load.type = 'button';
    load.title = `${item.place.label} · 불러와서 계산`;
    load.addEventListener('click', () => { applyProfile(item); form.requestSubmit(); });
    const remove = make('button', 'profile-remove', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', `${profileLabel(item)} 프로필 삭제`);
    remove.addEventListener('click', () => {
      if (!window.confirm(`“${profileLabel(item)}”을(를) 이 브라우저에서 지울까요?`)) return;
      profiles.remove(item.id);
      renderProfileShelf();
    });
    chip.append(load, remove);
    return chip;
  }));
}

const precisionSummary = document.querySelector('#precision-summary');
function syncPrecisionSummary() {
  const house = byName('house_system').selectedOptions[0]?.textContent.split(' · ')[0] || 'Placidus';
  const minor = form.querySelectorAll('input[name="minor_aspect"]:checked').length;
  const orb = Number(byName('orb_scale').value);
  precisionSummary.textContent = `${house} · ${byName('node_mode').value === 'mean' ? 'Mean' : 'True'} Node · ${byName('lilith_mode').value === 'osculating' ? 'Osculating' : 'Mean'} Lilith · ${minor ? `부가 어스펙트 ${minor}종` : '기본 어스펙트'}${orb !== 1 ? ` · 오브 ${Math.round(orb * 100)}%` : ''}${document.querySelector('#manual-location-toggle').checked ? ' · 좌표 직접 입력' : ''}`;
}
document.querySelector('#precision-panel').addEventListener('toggle', (event) => {
  event.currentTarget.querySelector('.precision-state').textContent = event.currentTarget.open ? '닫기' : '열기';
});
synastryLink.addEventListener('click', () => {
  if (!currentProfile) return;
  // Only the name can change without invalidating the result; hand over the one on screen now.
  if (!setHandoff({ ...currentProfile, name: byName('name').value.trim() })) { setMessage('이 브라우저에서는 정보를 넘길 수 없습니다. 시너스트리에서 다시 입력하세요.', 'error'); return; }
  window.location.href = '/synastry.html';
});

// The interpretation prompt is built around ASC, houses and sect, so it stays off for unknown birth time.
function interpretationAvailable() {
  return !downloadButton.disabled && currentResult?.normalized?.time_accuracy === 'reported';
}

function setExportAvailability(available) {
  downloadButton.disabled = !available;
  handoff.setAvailable(interpretationAvailable());
}

function timeUnknown() {
  return byName('time_unknown').checked;
}

function syncTimeControls() {
  const time = byName('time');
  time.disabled = timeUnknown();
  time.required = !timeUnknown();
  if (timeUnknown()) time.value = '';
}

function byName(name) {
  return form.elements.namedItem(name);
}

function selectedCalendar() {
  return form.querySelector('input[name="calendar"]:checked')?.value === 'lunar' ? 'lunar' : 'gregorian';
}

function syncCalendarControls() {
  const lunar = selectedCalendar() === 'lunar';
  // The date is a typed text field for both calendars (lunar months can have a 30th day).
  byName('date').placeholder = lunar ? '19900515 (음력)' : '19900515';
  form.querySelector('.lunar-leap').hidden = !lunar;
  document.querySelector('#lunar-note').hidden = !lunar;
  if (!lunar) byName('lunar_leap').checked = false;
  dateField.refresh();
}

for (const radio of form.querySelectorAll('input[name="calendar"]')) {
  radio.addEventListener('change', () => { syncCalendarControls(); invalidateResult(); });
}
byName('lunar_leap').addEventListener('change', () => dateField.refresh());
byName('time_unknown').addEventListener('change', syncTimeControls);
syncTimeControls();

function getPayload() {
  const calendar = selectedCalendar();
  return requestState.withFold({
    date: byName('date').value.trim(),
    calendar,
    ...(calendar === 'lunar' ? { lunar_leap: byName('lunar_leap').checked } : {}),
    ...(timeUnknown() ? {} : { time: byName('time').value }),
    timezone: byName('timezone').value.trim(),
    latitude: byName('latitude').value === '' ? null : Number(byName('latitude').value),
    longitude: byName('longitude').value === '' ? null : Number(byName('longitude').value),
    place: byName('place').value.trim(),
    house_system: byName('house_system').value,
    node_mode: byName('node_mode').value,
    lilith_mode: byName('lilith_mode').value,
    time_accuracy: timeUnknown() ? 'unknown' : 'reported',
    location_source: placeSearch.source(),
    aspect_profile: {
      version: 'aspects-v3',
      minor: [...form.querySelectorAll('input[name="minor_aspect"]:checked')].map((input) => input.value),
      orb_scale: Number(byName('orb_scale').value),
      targets: {
        chiron: byName('aspect_chiron').checked, lilith: byName('aspect_lilith').checked,
        nodes: byName('aspect_nodes').checked, lots: byName('aspect_lots').checked,
        angles: byName('aspect_angles').checked ? ['ASC', 'MC'] : [],
      },
      orbs: Object.fromEntries(['chiron','lilith','nodes','lots','angles'].map(group => [group, Number(document.querySelector(`#orb-${group}`).value)])),
    },
  });
}

function setMessage(text = '', type = '') {
  message.textContent = text;
  message.className = `message${type ? ` is-${type}` : ''}`;
}

function showFoldChoices(error, basePayload) {
  const candidates = error?.details?.candidates;
  if (error?.code !== 'AMBIGUOUS_LOCAL_TIME' || !Array.isArray(candidates) || candidates.length < 2) return;
  const choices = make('div', 'fold-choices');
  choices.append(make('strong', '', '같은 현지 시각에 대응하는 UTC를 선택하세요:'));
  for (const candidate of candidates) {
    const button = make('button', 'fold-choice', `${candidate.utc} (${candidate.offset})`);
    button.type = 'button';
    button.addEventListener('click', () => {
      requestState.selectFold(candidate.fold);
      calculate(requestState.withFold(basePayload));
    });
    choices.append(button);
  }
  message.append(choices);
}

function setBadge(text, state = '') {
  freshnessBadge.textContent = text;
  freshnessBadge.className = `status-badge${state ? ` is-${state}` : ''}`;
}

function clear(node) {
  node.replaceChildren();
}


function setTextDefinition(list, term, value) {
  const wrapper = document.createElement('div');
  wrapper.append(make('dt', '', term), make('dd', '', value ?? '미제공'));
  list.append(wrapper);
}

function renderPositions(result) {
  document.querySelector('#positions-body').replaceChildren(...buildPositionRows(result));
  document.querySelector('#angle-list').replaceChildren(...buildAngleEntries(result));
  document.querySelector('#sect-chip').textContent = sectLabel(result);
}

function renderAspects(result) {
  const register = document.querySelector('#aspect-register');
  clear(register);
  register.className = 'detail-content';
  const grid = buildAspectGrid(result);
  if (!grid) {
    register.classList.add('empty-state');
    register.textContent = '표시할 주요 어스펙트가 없습니다.';
    return;
  }
  register.append(grid);
}

function renderHouses(result) {
  const register = document.querySelector('#house-register');
  clear(register);
  register.className = 'detail-content';
  if (!result.houses?.length) {
    register.classList.add('empty-state');
    register.textContent = '생시 미상에서는 하우스를 계산하지 않습니다. 출생 시각을 알게 되면 다시 계산하세요.';
    return;
  }
  register.append(buildHouseGrid(result));
}

function metadataValue(value) {
  if (Array.isArray(value)) return value.length ? value.map((item) => typeof item === 'object' ? JSON.stringify(item) : item).join(', ') : '없음';
  if (value === null || value === undefined || value === '') return '미제공';
  return String(value);
}

function formatEphemerisData(data) {
  if (!Array.isArray(data) || data.length === 0) return '없음';
  return data.map((file) => {
    if (!file || typeof file !== 'object') return String(file);
    const hash = file.sha256 ? ` · sha256 ${file.sha256}` : '';
    return `${file.name || 'unnamed'}${file.range ? ` · ${file.range}` : ''}${hash}`;
  }).join(' / ');
}

function renderEvidence(result) {
  const register = document.querySelector('#evidence-register');
  clear(register);
  register.className = 'detail-content';
  const list = make('dl', 'metadata-list');
  const metadata = result.metadata || {};
  const normalized = result.normalized || {};
  const settings = result.settings || {};
  const entries = [
    ['Engine', `${metadataValue(metadata.engine)} ${metadataValue(metadata.engine_version)}`],
    ['Binding', metadataValue(metadata.binding_version)],
    ['UTC', metadataValue(normalized.utc)],
    ['Offset / TZ', `${metadataValue(normalized.offset)} · ${metadataValue(normalized.timezone)}`],
    ['Coordinates', `${metadataValue(normalized.latitude)}, ${metadataValue(normalized.longitude)}`],
    ['Location source', typeof metadata.geocoding === 'object' ? JSON.stringify(metadata.geocoding) : metadataValue(metadata.geocoding)],
    ['Julian dates', `TT ${metadataValue(normalized.jd_tt)} · UT1 ${metadataValue(normalized.jd_ut1)}`],
    ...(normalized.time_accuracy === 'unknown' ? [
      ['Time accuracy', `생시 미상 · 대표 시각 현지 ${metadataValue(normalized.representative_local_time)}`],
      ['Scanned local day', `${metadataValue(normalized.day_range?.start_utc)} → ${metadataValue(normalized.day_range?.end_utc)} (${metadataValue(normalized.day_range?.hours)}h)`],
      ['Scan rule', JSON.stringify(metadata.unknown_time_scan ?? {})],
      ['Excluded by mode', metadataValue(metadata.excluded_by_mode)],
    ] : []),
    ['Calculation profile', metadataValue(metadata.profile)],
    ['Rules', `${metadataValue(settings.zodiac)} · house ${metadataValue(settings.house_system)} · node ${metadataValue(settings.node_mode)} · Lilith ${metadataValue(settings.lilith_mode)}`],
    ['Aspect profile', JSON.stringify(settings.aspect_profile ?? {})],
    ['Rounding', metadataValue(settings.rounding)],
    ['TZ database', metadataValue(metadata.tzdb)],
    ['Ephemeris data', formatEphemerisData(metadata.data)],
  ];
  for (const [term, value] of entries) setTextDefinition(list, term, value);
  register.append(list);
  if (result.warnings?.length) {
    const warnings = make('ul', 'warning-list');
    for (const warning of result.warnings) warnings.append(make('li', '', typeof warning === 'string' ? warning : JSON.stringify(warning)));
    register.append(warnings);
  }
}

function renderResult(result, payload) {
  currentResult = result;
  currentPayload = { ...payload };
  currentFingerprint = requestFingerprint(payload);
  clear(chartStage);
  chartStage.append(createNatalWheel(result));
  document.querySelector('#wheel-caption').textContent = result.normalized?.time_accuracy === 'unknown'
    ? '생시 미상: 양자리 0°를 왼쪽에 둔 tropical wheel. 현지 정오 대표 위치와 하루 종일 유지되는 어스펙트만 그립니다. ASC·하우스는 없습니다.'
    : 'ASC를 왼쪽에 둔 tropical wheel. 바깥 사인은 균등 30°, 안쪽 하우스는 실제 cusp 간격입니다.';
  renderPositions(result);
  renderAspects(result);
  renderHouses(result);
  renderEvidence(result);

  const displayName = byName('name').value.trim();
  resultTitle.textContent = displayName ? `${displayName}의 네이털 차트` : '네이털 차트';
  resultSubtitle.textContent = `${payload.calendar === 'lunar' ? `음력 ${payload.date}${payload.lunar_leap ? '(윤달)' : ''} → 양력 ${result.normalized?.solar_date || '—'}` : payload.date} ${payload.time_accuracy === 'unknown' ? '생시 미상' : payload.time} · ${payload.place} · ${result.settings?.house_system || payload.house_system} / ${result.settings?.node_mode || payload.node_mode} node`;
  workbench.setAttribute('aria-busy', 'false');
  const success = result.status === 'calculated' && result.calculation_status === 'success';
  setExportAvailability(success);
  currentProfile = success ? profileFromForm() : null;
  if (currentProfile && byName('remember_profile').checked) {
    currentProfile = profiles.save(currentProfile) || currentProfile;
    renderProfileShelf();
  }
  synastryLink.hidden = !currentProfile;
  setBadge(result.status === 'partial' ? '부분 결과' : '현재 입력 결과', result.status === 'partial' ? 'stale' : '');
}

function describeError(error) {
  const fallback = '차트를 계산하지 못했습니다.';
  if (!error || typeof error !== 'object') return fallback;
  const prefix = ERROR_MESSAGES[error.code] || error.message || fallback;
  if (!error.details) return `${error.code ? `${error.code} · ` : ''}${prefix}`;
  const detail = typeof error.details === 'string' ? error.details : JSON.stringify(error.details);
  return `${error.code ? `${error.code} · ` : ''}${prefix} ${detail}`;
}

async function calculate(payload) {
  const serial = ++requestSerial;
  controller?.abort();
  controller = new AbortController();
  calculateButton.disabled = true;
  setExportAvailability(false);
  workbench.setAttribute('aria-busy', 'true');
  setBadge('계산 중', 'loading');
  setMessage('Swiss Ephemeris 계산 결과를 기다리는 중입니다.', 'info');

  try {
    const response = await fetch('/api/chart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ ...payload, client: clientContext() }),
      signal: controller.signal,
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`서버가 JSON이 아닌 응답을 반환했습니다. HTTP ${response.status}`);
    }
    if (!response.ok || data?.error) {
      const errorBody = data && typeof data === 'object' && data.error && typeof data.error === 'object' ? data.error : null;
      const apiError = new Error(errorBody ? describeError(errorBody) : `차트를 계산하지 못했습니다. HTTP ${response.status}`);
      apiError.api = true;
      apiError.payload = errorBody;
      throw apiError;
    }
    if (serial !== requestSerial) return;
    if (requestFingerprint(getPayload()) !== requestFingerprint(payload)) {
      setBadge('입력 변경됨', 'stale');
      setMessage('계산 중 입력이 바뀌어 도착한 결과를 폐기했습니다. 현재 입력으로 다시 계산하세요.', 'error');
      return;
    }
    renderResult(data, payload);
    setMessage(data.normalized?.time_accuracy === 'unknown'
      ? '생시 미상으로 계산했습니다. 정오 대표 위치이며 ASC·하우스는 없습니다. 해석용 복사는 출생 시각이 있을 때만 지원합니다.'
      : '현재 입력으로 계산을 완료했습니다.', 'info');
  } catch (error) {
    if (error.name === 'AbortError') return;
    if (serial !== requestSerial) return;
    workbench.setAttribute('aria-busy', 'false');
    setBadge('계산 실패', 'error');
    setMessage(error.api ? error.message : `연결 오류 · ${error.message}`, 'error');
    if (error.api) showFoldChoices(error.payload, payload);
  } finally {
    if (serial === requestSerial) calculateButton.disabled = false;
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!placeSearch.validate()) {
    setMessage('출생지를 선택하고 좌표·시간대를 확인해 주세요.', 'error');
    return;
  }
  if (!form.checkValidity()) {
    for (let node = form.querySelector(':invalid')?.closest('details'); node; node = node.parentElement?.closest('details')) node.open = true;
    form.reportValidity();
    setMessage('필수 입력과 좌표 범위를 확인하세요.', 'error');
    return;
  }
  const payload = getPayload();
  if (![payload.latitude, payload.longitude].every(Number.isFinite)) {
    setMessage('위도와 경도는 유효한 숫자여야 합니다.', 'error');
    return;
  }
  calculate(payload);
});

function invalidateResult() {
  synastryLink.hidden = true;
  syncPrecisionSummary();
  requestState.resetFold();
  controller?.abort();
  requestSerial += 1;
  calculateButton.disabled = false;
  setExportAvailability(false);
  workbench.setAttribute('aria-busy', 'false');
  if (currentResult && requestFingerprint(getPayload()) !== currentFingerprint) {
    setBadge('다시 계산 필요', 'stale');
    setMessage('입력이 변경되었습니다. 화면의 수치는 이전 입력 결과이므로 다시 계산하세요.', 'error');
  }
}

form.addEventListener('input', (event) => {
  if (['store_consent', 'remember_profile'].includes(event.target.name)) return;  // storage choices never change the chart
  if (event.target.name === 'name') {
    if (currentResult) resultTitle.textContent = event.target.value.trim() ? `${event.target.value.trim()}의 네이털 차트` : '네이털 차트';
    handoff.setAvailable(interpretationAvailable());
    return;
  }
  invalidateResult();
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
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[role="tab"]')];
    const offset = event.key === 'ArrowRight' ? 1 : -1;
    const next = tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length];
    next.click();
    next.focus();
  });
});

downloadButton.addEventListener('click', () => {
  const svg = chartStage.querySelector('svg');
  if (!svg) return;
  const exportSvg = svg.cloneNode(true);
  const originals = [svg, ...svg.querySelectorAll('*')];
  const copies = [exportSvg, ...exportSvg.querySelectorAll('*')];
  const properties = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor', 'dominant-baseline', 'letter-spacing', 'paint-order'];
  // Snapshot presentation, not external stylesheets; exports follow any future theme.
  originals.forEach((node, index) => {
    const style = getComputedStyle(node);
    for (const property of properties) copies[index].setAttribute(property, style.getPropertyValue(property));
  });
  const dimensions = svg.viewBox.baseVal;
  exportSvg.setAttribute('width', String(dimensions.width));
  exportSvg.setAttribute('height', String(dimensions.height));
  const source = new XMLSerializer().serializeToString(exportSvg);
  const blob = new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${source}`], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `natal-chart-${currentPayload?.date || 'result'}.svg`;
  link.click();
  URL.revokeObjectURL(url);
});

// No personal birth record is prefilled or calculated without an explicit action
// (a saved-profile chip is one: it loads and calculates only when clicked).
setExportAvailability(false);
renderProfileShelf();
syncPrecisionSummary();
