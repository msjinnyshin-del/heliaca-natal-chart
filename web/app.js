import { createNatalWheel } from './chart.js';
import { norm } from './geometry.js';
import { createRequestState, requestFingerprint } from './request-state.js';
import { mountInterpretationHandoff } from './interpretation-handoff.js';
import { mountPlaceSearch } from './place-search.js';
import { buildAngleEntries, buildAspectGrid, buildHouseGrid, buildPositionRows, make, sectLabel } from './chart-tables.js';
import { buildClientContext, captureAttribution, getVisitorId } from './client-context.js';

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
  if (!window.confirm('이 브라우저에서 계산한 모든 저장 기록을 삭제합니다. 되돌릴 수 없습니다.')) return;
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
const placeSearch = mountPlaceSearch({onChange: invalidateResult});

function setExportAvailability(available) {
  downloadButton.disabled = !available;
  handoff.setAvailable(available);
}

function byName(name) {
  return form.elements.namedItem(name);
}

function selectedCalendar() {
  return form.querySelector('input[name="calendar"]:checked')?.value === 'lunar' ? 'lunar' : 'gregorian';
}

function syncCalendarControls() {
  const lunar = selectedCalendar() === 'lunar';
  const dateInput = byName('date');
  const value = dateInput.value;
  // Lunar months can have day 30 in any month (e.g. 2월 30일), which type=date rejects.
  dateInput.type = lunar ? 'text' : 'date';
  dateInput.inputMode = lunar ? 'numeric' : '';
  dateInput.placeholder = lunar ? 'YYYY-MM-DD (음력)' : '';
  dateInput.pattern = lunar ? '\\d{4}-\\d{2}-\\d{2}' : '';
  dateInput.value = value;
  form.querySelector('.lunar-leap').hidden = !lunar;
  document.querySelector('#lunar-note').hidden = !lunar;
  document.querySelector('#date-calendar-hint').textContent = lunar ? '음력 · Korean lunar' : '양력 · Gregorian';
  if (!lunar) byName('lunar_leap').checked = false;
}

for (const radio of form.querySelectorAll('input[name="calendar"]')) {
  radio.addEventListener('change', () => { syncCalendarControls(); invalidateResult(); });
}

function getPayload() {
  const calendar = selectedCalendar();
  return requestState.withFold({
    date: byName('date').value.trim(),
    calendar,
    ...(calendar === 'lunar' ? { lunar_leap: byName('lunar_leap').checked } : {}),
    time: byName('time').value,
    timezone: byName('timezone').value.trim(),
    latitude: byName('latitude').value === '' ? null : Number(byName('latitude').value),
    longitude: byName('longitude').value === '' ? null : Number(byName('longitude').value),
    place: byName('place').value.trim(),
    house_system: byName('house_system').value,
    node_mode: byName('node_mode').value,
    time_accuracy: 'reported',
    location_source: placeSearch.source(),
    aspect_profile: {
      version: 'major-v2',
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
  renderPositions(result);
  renderAspects(result);
  renderHouses(result);
  renderEvidence(result);

  const displayName = byName('name').value.trim();
  resultTitle.textContent = displayName ? `${displayName}의 네이털 차트` : '네이털 차트';
  resultSubtitle.textContent = `${payload.calendar === 'lunar' ? `음력 ${payload.date}${payload.lunar_leap ? '(윤달)' : ''} → 양력 ${result.normalized?.solar_date || '—'}` : payload.date} ${payload.time} · ${payload.place} · ${result.settings?.house_system || payload.house_system} / ${result.settings?.node_mode || payload.node_mode} node`;
  workbench.setAttribute('aria-busy', 'false');
  setExportAvailability(result.status === 'calculated' && result.calculation_status === 'success');
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
    setMessage('현재 입력으로 계산을 완료했습니다.', 'info');
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
    form.querySelector(':invalid')?.closest('details')?.setAttribute('open', '');
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
  if (event.target.name === 'store_consent') return;  // storage choice never changes the chart
  if (event.target.name === 'name') {
    if (currentResult) resultTitle.textContent = event.target.value.trim() ? `${event.target.value.trim()}의 네이털 차트` : '네이털 차트';
    handoff.setAvailable(!downloadButton.disabled);
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

// No personal birth record is prefilled or calculated without an explicit submit.
setExportAvailability(false);
