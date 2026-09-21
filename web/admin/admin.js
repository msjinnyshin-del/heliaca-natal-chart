import { createNatalWheel } from '/chart.js';
import { buildAngleEntries, buildAspectGrid, buildPositionRows, make } from '/chart-tables.js';

// Tabs are data-driven: a tab is added here only once it is implemented.
const TABS = [
  { id: 'stats', label: '통계', load: loadStats },
  { id: 'users', label: '사용자', load: loadUsers },
  { id: 'submissions', label: '입력 기록', load: loadSubmissions },
  { id: 'utm', label: 'UTM 빌더', load: loadBuilder },
  { id: 'links', label: '링크 장부', load: loadLedger },
  { id: 'channels', label: '채널 · 캠페인', load: loadChannelsAdmin },
];
const PAGE_SIZE = 50;
const state = { tab: 'stats', visitor: null, offset: 0, total: 0, detailId: null };
const $ = (selector) => document.querySelector(selector);

function setMessage(text = '', type = '') {
  const node = $('#adm-message');
  node.textContent = text;
  node.className = `adm-message${type ? ` is-${type}` : ''}`;
}

function range() {
  const params = new URLSearchParams();
  if ($('#range-from').value) params.set('from', $('#range-from').value);
  if ($('#range-to').value) params.set('to', $('#range-to').value);
  return params;
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' }, ...options });
  if (response.status === 401) {
    window.location.assign('/admin/login');
    throw new Error('로그인이 필요합니다.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error?.message || `요청에 실패했습니다. HTTP ${response.status}`);
    error.code = data?.error?.code;
    throw error;
  }
  return data;
}

function cell(text, className = '') {
  return make('td', className, text === null || text === undefined || text === '' ? '—' : String(text));
}

function shortId(value) {
  return value ? `${value.slice(0, 8)}…` : '—';
}

// ---- tabs -------------------------------------------------------------------

function renderTabs() {
  const list = $('#adm-tabs');
  list.replaceChildren(...TABS.map((tab) => {
    const button = make('button', '', tab.label);
    button.id = `tab-${tab.id}`;
    button.type = 'button';
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-controls', `panel-${tab.id}`);
    button.addEventListener('click', () => selectTab(tab.id));
    return button;
  }));
}

function selectTab(id) {
  state.tab = id;
  for (const tab of TABS) {
    const selected = tab.id === id;
    const button = $(`#tab-${tab.id}`);
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(`#panel-${tab.id}`).hidden = !selected;
  }
  refresh();
}

async function refresh() {
  setMessage('');
  try {
    await TABS.find((tab) => tab.id === state.tab).load();
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

// ---- stats ------------------------------------------------------------------

function kpi(label, value) {
  const tile = make('div', 'adm-kpi');
  tile.append(make('small', '', label), make('strong', '', String(value ?? 0)));
  return tile;
}

function dailyChart(daily) {
  const NS = 'http://www.w3.org/2000/svg';
  const width = 720, height = 200, pad = 28;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('class', 'adm-daily-svg');
  svg.setAttribute('role', 'img');
  const title = document.createElementNS(NS, 'title');
  title.textContent = '일별 입력 수 (성공/실패)';
  svg.append(title);
  if (!daily.length) {
    const text = document.createElementNS(NS, 'text');
    text.setAttribute('x', String(width / 2));
    text.setAttribute('y', String(height / 2));
    text.setAttribute('class', 'adm-axis-label adm-center');
    text.textContent = '기간 내 기록이 없습니다';
    svg.append(text);
    return svg;
  }
  const max = Math.max(...daily.map((d) => d.total), 1);
  const slot = (width - pad * 2) / daily.length;
  const bar = Math.max(2, Math.min(28, slot * 0.7));
  const rect = (x, y, w, h, className, label) => {
    const node = document.createElementNS(NS, 'rect');
    for (const [k, v] of Object.entries({ x, y, width: w, height: h, class: className })) node.setAttribute(k, String(v));
    const tip = document.createElementNS(NS, 'title');
    tip.textContent = label;
    node.append(tip);
    svg.append(node);
  };
  daily.forEach((day, index) => {
    const x = pad + index * slot + (slot - bar) / 2;
    const scale = (height - pad * 2) / max;
    const successH = (day.success || 0) * scale;
    const failedH = (day.failed || 0) * scale;
    rect(x, height - pad - successH, bar, successH, 'adm-bar-ok', `${day.day} 성공 ${day.success}`);
    rect(x, height - pad - successH - failedH, bar, failedH, 'adm-bar-fail', `${day.day} 실패 ${day.failed}`);
    if (daily.length <= 14 || index % Math.ceil(daily.length / 10) === 0) {
      const label = document.createElementNS(NS, 'text');
      label.setAttribute('x', String(x + bar / 2));
      label.setAttribute('y', String(height - 8));
      label.setAttribute('class', 'adm-axis-label adm-center');
      label.textContent = day.day.slice(5);
      svg.append(label);
    }
  });
  const top = document.createElementNS(NS, 'text');
  top.setAttribute('x', '4');
  top.setAttribute('y', String(pad - 8));
  top.setAttribute('class', 'adm-axis-label');
  top.textContent = `max ${max}`;
  svg.append(top);
  return svg;
}

function distribution(title, rows) {
  const card = make('section', 'adm-card');
  card.append(make('h3', 'plate-number', title));
  if (!rows?.length) {
    card.append(make('p', 'adm-note', '데이터 없음'));
    return card;
  }
  const max = Math.max(...rows.map((row) => row.count), 1);
  const list = make('ol', 'adm-dist');
  for (const row of rows) {
    const item = make('li');
    item.append(make('span', 'adm-dist-key', row.key ?? '(없음)'));
    const track = make('span', 'adm-dist-track');
    const fill = make('span', 'adm-dist-fill');
    fill.style.width = `${(row.count / max) * 100}%`;
    track.append(fill);
    item.append(track, make('span', 'adm-dist-count', String(row.count)));
    list.append(item);
  }
  card.append(list);
  return card;
}

async function loadStats() {
  const data = await api(`/api/admin/stats?${range()}`);
  const t = data.totals;
  $('#kpi-grid').replaceChildren(kpi('입력 수', t.submissions), kpi('성공', t.success), kpi('실패', t.failed),
    kpi('고유 방문자', t.unique_visitors), kpi('고유 이름', t.unique_names));
  $('#daily-chart').replaceChildren(dailyChart(data.daily));
  $('#distribution-grid').replaceChildren(
    distribution('상태 · 오류 코드', data.by_status),
    distribution('출생지 TOP 10', data.top_places),
    distribution('태양 사인', data.signs.sun),
    distribution('달 사인', data.signs.moon),
    distribution('ASC 사인', data.signs.asc),
    distribution('utm_source', data.utm.source),
    distribution('utm_campaign', data.utm.campaign),
  );
  await loadUtmStats();
}

// ---- users ------------------------------------------------------------------

async function loadUsers() {
  const params = range();
  const q = $('#users-q').value.trim();
  if (q) params.set('q', q);
  const data = await api(`/api/admin/users?${params}`);
  $('#users-anon').textContent = `visitor ID 없는 입력 ${data.anonymous_submissions}건은 목록에서 제외됩니다.`;
  const body = $('#users-body');
  if (!data.users.length) {
    body.replaceChildren(emptyRow(8, '해당 기간의 사용자가 없습니다.'));
    return;
  }
  body.replaceChildren(...data.users.map((user) => {
    const row = document.createElement('tr');
    const visitor = cell(shortId(user.visitor_id), 'adm-mono');
    visitor.title = user.visitor_id;
    const actions = make('td', 'adm-actions');
    const view = make('button', 'text-button', '기록 보기');
    view.type = 'button';
    view.addEventListener('click', () => {
      state.visitor = user.visitor_id;
      state.offset = 0;
      selectTab('submissions');
    });
    const remove = make('button', 'text-button adm-danger', '전체 삭제');
    remove.type = 'button';
    remove.addEventListener('click', () => deleteVisitor(user));
    actions.append(view, remove);
    row.append(cell(user.latest_name), cell(user.names.join(', ')), cell(user.count), cell(user.success),
      cell(user.first_seen), cell(user.last_seen), visitor, actions);
    return row;
  }));
}

async function deleteVisitor(user) {
  const label = user.latest_name || shortId(user.visitor_id);
  if (!window.confirm(`${label}의 입력 기록 ${user.count}건을 모두 삭제합니다. 되돌릴 수 없습니다.`)) return;
  try {
    const result = await api(`/api/admin/users/${encodeURIComponent(user.visitor_id)}`, { method: 'DELETE' });
    await loadUsers();
    setMessage(`${result.deleted}건을 삭제했습니다.`, 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

function emptyRow(span, text) {
  const row = document.createElement('tr');
  const td = make('td', 'empty-cell', text);
  td.colSpan = span;
  row.append(td);
  return row;
}

// ---- submissions --------------------------------------------------------------

async function loadSubmissions() {
  const params = range();
  const q = $('#subs-q').value.trim();
  if (q) params.set('q', q);
  if ($('#subs-status').value) params.set('status', $('#subs-status').value);
  if (state.visitor) params.set('visitor_id', state.visitor);
  params.set('limit', String(PAGE_SIZE));
  params.set('offset', String(state.offset));
  $('#subs-visitor').hidden = !state.visitor;
  $('#subs-visitor-clear').hidden = !state.visitor;
  $('#subs-visitor').textContent = state.visitor ? `visitor ${shortId(state.visitor)}` : '';
  const data = await api(`/api/admin/submissions?${params}`);
  state.total = data.total;
  const body = $('#subs-body');
  body.replaceChildren(...(data.submissions.length ? data.submissions.map(submissionRow) : [emptyRow(7, '조건에 맞는 기록이 없습니다.')]));
  const page = Math.floor(state.offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  $('#subs-page').textContent = `${page} / ${pages} · 총 ${data.total}건`;
  $('#subs-prev').disabled = state.offset === 0;
  $('#subs-next').disabled = state.offset + PAGE_SIZE >= data.total;
}

function submissionRow(item) {
  const row = document.createElement('tr');
  row.className = 'adm-clickable';
  row.tabIndex = 0;
  const status = cell(item.status === 'success' ? '성공' : item.status, item.status === 'success' ? '' : 'adm-fail');
  const signs = [item.sun_sign, item.moon_sign, item.asc_sign].map((s) => s || '—').join(' · ');
  const utm = [item.utm_source, item.utm_campaign].filter(Boolean).join(' / ');
  row.append(cell(item.id, 'adm-mono'), cell(item.created_at, 'adm-mono'), cell(item.display_name), cell(item.place), status, cell(signs), cell(utm));
  const open = () => openDetail(item.id);
  row.addEventListener('click', open);
  row.addEventListener('keydown', (event) => { if (event.key === 'Enter') open(); });
  return row;
}

// ---- detail drawer --------------------------------------------------------------

function define(list, term, value) {
  const wrapper = document.createElement('div');
  wrapper.append(make('dt', '', term), make('dd', '', value === null || value === undefined || value === '' ? '—' : String(value)));
  list.append(wrapper);
}

async function openDetail(id) {
  state.detailId = id;
  const dialog = $('#detail');
  $('#detail-title').textContent = `입력 기록 #${id}`;
  for (const selector of ['#detail-meta', '#detail-wheel', '#detail-positions', '#detail-angles', '#detail-aspects']) $(selector).replaceChildren();
  $('#detail-raw').textContent = '';
  $('#detail-chart-status').textContent = '불러오는 중…';
  if (!dialog.open) dialog.showModal();
  try {
    const item = await api(`/api/admin/submissions/${id}`);
    const meta = $('#detail-meta');
    define(meta, '시각 (UTC)', item.created_at);
    define(meta, '이름', item.display_name);
    define(meta, 'visitor', item.visitor_id);
    define(meta, '상태', item.status);
    define(meta, '고지 동의', item.consent ? '표시됨' : '미확인');
    define(meta, 'UTM', ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].map((k) => item[k] && `${k.slice(4)}=${item[k]}`).filter(Boolean).join(' · '));
    define(meta, 'short code', item.short_code);
    define(meta, 'fingerprint', item.fingerprint);
    $('#detail-raw').textContent = JSON.stringify(item.raw_input, null, 2);
  } catch (error) {
    $('#detail-chart-status').textContent = error.message;
    return;
  }
  try {
    const chart = await api(`/api/admin/submissions/${id}/chart`);
    if (state.detailId !== id) return;
    $('#detail-chart-status').textContent = `재계산 완료 · ${chart.calculation_status}`;
    $('#detail-wheel').replaceChildren(createNatalWheel(chart));
    $('#detail-positions').replaceChildren(...buildPositionRows(chart));
    $('#detail-angles').replaceChildren(...buildAngleEntries(chart));
    const aspects = buildAspectGrid(chart);
    if (aspects) $('#detail-aspects').replaceChildren(aspects);
  } catch (error) {
    if (state.detailId !== id) return;
    $('#detail-chart-status').textContent = `차트를 재계산할 수 없습니다: ${error.code ? `${error.code} · ` : ''}${error.message}`;
  }
}

async function deleteCurrent() {
  const id = state.detailId;
  if (!id || !window.confirm(`입력 기록 #${id}을 삭제합니다. 되돌릴 수 없습니다.`)) return;
  try {
    await api(`/api/admin/submissions/${id}`, { method: 'DELETE' });
    $('#detail').close();
    setMessage(`#${id}을 삭제했습니다.`, 'info');
    await refresh();
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

// ---- UTM ----------------------------------------------------------------------

const utm = { channels: [], campaigns: [], editChannel: null, editCampaign: null };

function postJson(path, body) {
  return api(path, { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}) });
}

function percent(value) {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
}

function button(label, onClick, className = 'text-button') {
  const node = make('button', className, label);
  node.type = 'button';
  node.addEventListener('click', onClick);
  return node;
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    setMessage('복사했습니다.', 'info');
  } catch {
    setMessage('클립보드 접근이 막혀 있습니다. 주소를 직접 선택해 복사하세요.', 'error');
  }
}

function urlRow(label, value) {
  const row = make('div', 'adm-url-row');
  const output = make('output', '', value);
  row.append(make('small', '', label), output, button('복사', () => copyText(value)));
  return row;
}

async function loadUtmRefs() {
  const [channels, campaigns] = await Promise.all([api('/api/admin/utm/channels'), api('/api/admin/utm/campaigns')]);
  utm.channels = channels.channels;
  utm.campaigns = campaigns.campaigns;
}

function fillSelect(select, items, emptyLabel) {
  const previous = select.value;
  const options = items.map((item) => {
    const option = make('option', '', `${item.label_ko} (${item.key})${item.is_active ? '' : ' · 비활성'}`);
    option.value = item.key;
    return option;
  });
  if (emptyLabel !== undefined) {
    const empty = make('option', '', emptyLabel);
    empty.value = '';
    options.unshift(empty);
  }
  select.replaceChildren(...options);
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
}

async function loadBuilder() {
  await loadUtmRefs();
  const active = utm.campaigns.filter((item) => item.is_active);
  fillSelect($('#utm-campaign'), active, active.length ? undefined : '활성 캠페인이 없습니다 — 채널 · 캠페인 탭에서 추가');
  const checked = new Set([...document.querySelectorAll('#utm-channel-list input:checked')].map((input) => input.value));
  $('#utm-channel-list').replaceChildren(...utm.channels.filter((item) => item.is_active).map((item) => {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = item.key;
    input.checked = checked.has(item.key);
    label.append(input, document.createTextNode(`${item.label_ko} · ${item.utm_source}/${item.utm_medium}`));
    return label;
  }));
}

async function createLinks(event) {
  event.preventDefault();
  const preset = $('#utm-target-preset').value;
  const body = {
    target_path: preset === 'custom' ? $('#utm-target-custom').value.trim() : preset,
    channel_keys: [...document.querySelectorAll('#utm-channel-list input:checked')].map((input) => input.value),
    campaign_key: $('#utm-campaign').value,
    utm_content: $('#utm-content').value.trim() || null,
    memo: $('#utm-memo').value.trim() || null,
    created_by: $('#utm-created-by').value.trim() || null,
    utm_source_override: $('#utm-source-override').value.trim() || null,
    utm_medium_override: $('#utm-medium-override').value.trim() || null,
  };
  try {
    const data = await postJson('/api/admin/utm/links', body);
    const origin = window.location.origin;
    $('#utm-result').replaceChildren(...data.links.map((link) => {
      const card = make('section', 'adm-card adm-stack');
      const title = make('h3', 'plate-number', `${link.channel_key} · ${link.code}`);
      title.append(make('span', 'adm-badge', link.existed ? '기존 링크 재사용' : '새로 생성'));
      card.append(title, urlRow('단축 URL', `${origin}${link.short_path}`), urlRow('UTM URL', `${origin}${link.full_path}`));
      return card;
    }));
    setMessage(`${data.links.length}개 링크를 준비했습니다.`, 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

async function loadLedger() {
  await loadUtmRefs();
  fillSelect($('#links-channel'), utm.channels, '전체');
  fillSelect($('#links-campaign'), utm.campaigns, '전체');
  const params = new URLSearchParams();
  const q = $('#links-q').value.trim();
  if (q) params.set('q', q);
  for (const [key, selector] of [['channel', '#links-channel'], ['campaign', '#links-campaign'], ['archived', '#links-archived']]) {
    if ($(selector).value) params.set(key, $(selector).value);
  }
  const data = await api(`/api/admin/utm/links?${params}`);
  const body = $('#links-body');
  if (!data.links.length) {
    body.replaceChildren(emptyRow(13, '조건에 맞는 링크가 없습니다.'));
    return;
  }
  const origin = window.location.origin;
  body.replaceChildren(...data.links.map((link) => {
    const row = document.createElement('tr');
    if (link.archived_at) row.className = 'adm-muted';
    const actions = make('td', 'adm-actions');
    actions.append(
      button('단축 복사', () => copyText(`${origin}${link.short_path}`)),
      button('UTM 복사', () => copyText(`${origin}${link.full_path}`)),
      link.archived_at
        ? button('복원', () => archiveLink(link.code, false))
        : button('보관', () => archiveLink(link.code, true), 'text-button adm-danger'),
    );
    const source = link.utm_source === link.channel_key ? link.channel_key : `${link.channel_key} (${link.utm_source}/${link.utm_medium})`;
    row.append(cell(link.code, 'adm-mono'), cell(source), cell(link.utm_campaign), cell(link.utm_content), cell(link.target_path, 'adm-mono'),
      cell(link.clicks), cell(link.bot_clicks), cell(link.submissions), cell(link.success), cell(percent(link.conversion)),
      cell(link.memo), cell(`${link.created_at.slice(0, 10)}${link.created_by ? ` · ${link.created_by}` : ''}`), actions);
    return row;
  }));
}

async function archiveLink(code, archive) {
  if (archive && !window.confirm(`링크 ${code}를 보관합니다. 보관된 코드는 홈으로 이동하며 클릭을 세지 않습니다.`)) return;
  try {
    await postJson(`/api/admin/utm/links/${encodeURIComponent(code)}/${archive ? 'archive' : 'unarchive'}`);
    await loadLedger();
    setMessage(archive ? `${code}를 보관했습니다.` : `${code}를 복원했습니다.`, 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

async function loadChannelsAdmin() {
  await loadUtmRefs();
  $('#channels-body').replaceChildren(...(utm.channels.length ? utm.channels.map((item) => {
    const row = document.createElement('tr');
    if (!item.is_active) row.className = 'adm-muted';
    const actions = make('td', 'adm-actions');
    actions.append(button('편집', () => editChannel(item)),
      button(item.is_active ? '비활성' : '활성', () => toggle('channels', item)));
    row.append(cell(item.key, 'adm-mono'), cell(item.label_ko), cell(item.utm_source), cell(item.utm_medium), cell(item.sort_order),
      cell(item.note), cell(item.is_active ? '활성' : '비활성'), actions);
    return row;
  }) : [emptyRow(8, '채널이 없습니다.')]));
  $('#campaigns-body').replaceChildren(...(utm.campaigns.length ? utm.campaigns.map((item) => {
    const row = document.createElement('tr');
    if (!item.is_active) row.className = 'adm-muted';
    const actions = make('td', 'adm-actions');
    actions.append(button('편집', () => editCampaign(item)),
      button(item.is_active ? '비활성' : '활성', () => toggle('campaigns', item)));
    row.append(cell(item.key, 'adm-mono'), cell(item.label_ko), cell([item.starts_on, item.ends_on].map((d) => d || '…').join(' ~ ')),
      cell(item.note), cell(item.is_active ? '활성' : '비활성'), actions);
    return row;
  }) : [emptyRow(6, '캠페인이 없습니다. 링크를 만들려면 캠페인이 하나 이상 필요합니다.')]));
}

async function toggle(kind, item) {
  try {
    await postJson(`/api/admin/utm/${kind}/${encodeURIComponent(item.key)}`, { is_active: !item.is_active });
    await loadChannelsAdmin();
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

function editChannel(item) {
  utm.editChannel = item?.key ?? null;
  $('#channel-form-title').textContent = item ? `채널 편집 · ${item.key}` : '채널 추가';
  $('#channel-key').value = item?.key ?? '';
  $('#channel-key').disabled = Boolean(item);
  $('#channel-label').value = item?.label_ko ?? '';
  $('#channel-source').value = item?.utm_source ?? '';
  $('#channel-medium').value = item?.utm_medium ?? '';
  $('#channel-order').value = String(item?.sort_order ?? 100);
  $('#channel-note').value = item?.note ?? '';
  $('#channel-cancel').hidden = !item;
}

function editCampaign(item) {
  utm.editCampaign = item?.key ?? null;
  $('#campaign-form-title').textContent = item ? `캠페인 편집 · ${item.key}` : '캠페인 추가';
  $('#campaign-key').value = item?.key ?? '';
  $('#campaign-key').disabled = Boolean(item);
  $('#campaign-label').value = item?.label_ko ?? '';
  $('#campaign-starts').value = item?.starts_on ?? '';
  $('#campaign-ends').value = item?.ends_on ?? '';
  $('#campaign-note').value = item?.note ?? '';
  $('#campaign-cancel').hidden = !item;
}

async function saveChannel(event) {
  event.preventDefault();
  const body = {
    label_ko: $('#channel-label').value.trim(), utm_source: $('#channel-source').value.trim(), utm_medium: $('#channel-medium').value.trim(),
    sort_order: Number.parseInt($('#channel-order').value, 10) || 0, note: $('#channel-note').value.trim() || null,
  };
  try {
    if (utm.editChannel) await postJson(`/api/admin/utm/channels/${encodeURIComponent(utm.editChannel)}`, body);
    else await postJson('/api/admin/utm/channels', { key: $('#channel-key').value.trim(), ...body });
    editChannel(null);
    await loadChannelsAdmin();
    setMessage('채널을 저장했습니다.', 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

async function saveCampaign(event) {
  event.preventDefault();
  const body = {
    label_ko: $('#campaign-label').value.trim(), starts_on: $('#campaign-starts').value || null,
    ends_on: $('#campaign-ends').value || null, note: $('#campaign-note').value.trim() || null,
  };
  try {
    if (utm.editCampaign) await postJson(`/api/admin/utm/campaigns/${encodeURIComponent(utm.editCampaign)}`, body);
    else await postJson('/api/admin/utm/campaigns', { key: $('#campaign-key').value.trim(), ...body });
    editCampaign(null);
    await loadChannelsAdmin();
    setMessage('캠페인을 저장했습니다.', 'info');
  } catch (error) {
    setMessage(error.message, 'error');
  }
}

function metricTable(title, columns, rows) {
  const card = make('div', 'adm-stack');
  card.append(make('h4', 'plate-number', title));
  const table = make('table', 'adm-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  for (const [label] of columns) {
    const th = make('th', '', label);
    th.scope = 'col';
    headRow.append(th);
  }
  head.append(headRow);
  const body = document.createElement('tbody');
  body.replaceChildren(...(rows.length ? rows.map((row) => {
    const tr = document.createElement('tr');
    tr.append(...columns.map(([, value]) => cell(value(row))));
    return tr;
  }) : [emptyRow(columns.length, '데이터 없음')]));
  table.append(head, body);
  const scroll = make('div', 'table-scroll');
  scroll.append(table);
  card.append(scroll);
  return card;
}

function utmDailyChart(daily) {
  const NS = 'http://www.w3.org/2000/svg';
  const width = 720, height = 180, pad = 26;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('class', 'adm-daily-svg');
  svg.setAttribute('role', 'img');
  const title = document.createElementNS(NS, 'title');
  title.textContent = '일별 클릭(청록) 대 단축 링크 입력(산호)';
  svg.append(title);
  const text = (x, y, value, className) => {
    const node = document.createElementNS(NS, 'text');
    node.setAttribute('x', String(x));
    node.setAttribute('y', String(y));
    node.setAttribute('class', className);
    node.textContent = value;
    svg.append(node);
  };
  if (!daily.length) {
    text(width / 2, height / 2, '기간 내 클릭·입력이 없습니다', 'adm-axis-label adm-center');
    return svg;
  }
  const max = Math.max(...daily.map((d) => Math.max(d.clicks, d.submissions)), 1);
  const slot = (width - pad * 2) / daily.length;
  const bar = Math.max(2, Math.min(14, slot * 0.35));
  const scale = (height - pad * 2) / max;
  daily.forEach((day, index) => {
    const x = pad + index * slot + slot / 2 - bar;
    for (const [offset, value, className, label] of [[0, day.clicks, 'adm-bar-click', '클릭'], [bar, day.submissions, 'adm-bar-sub', '입력']]) {
      const rect = document.createElementNS(NS, 'rect');
      const h = value * scale;
      for (const [k, v] of Object.entries({ x: x + offset, y: height - pad - h, width: bar, height: h, class: className })) rect.setAttribute(k, String(v));
      const tip = document.createElementNS(NS, 'title');
      tip.textContent = `${day.day} ${label} ${value}`;
      rect.append(tip);
      svg.append(rect);
    }
    if (daily.length <= 14 || index % Math.ceil(daily.length / 10) === 0) text(x + bar, height - 8, day.day.slice(5), 'adm-axis-label adm-center');
  });
  text(4, pad - 8, `max ${max}`, 'adm-axis-label');
  return svg;
}

async function loadUtmStats() {
  const data = await api(`/api/admin/utm-stats?${range()}`);
  const t = data.totals;
  $('#utm-kpis').replaceChildren(kpi('클릭', t.clicks), kpi('봇 · HEAD', t.bot_clicks), kpi('단축 링크 입력', t.submissions),
    kpi('성공', t.success), kpi('전환율', percent(t.conversion)), kpi('UTM 직접 유입', t.direct_submissions));
  $('#utm-daily').replaceChildren(utmDailyChart(data.daily));
  const metricColumns = [['클릭', (r) => r.clicks], ['봇', (r) => r.bot_clicks], ['입력', (r) => r.submissions], ['성공', (r) => r.success],
    ['전환율', (r) => percent(r.conversion)]];
  const direct = [['UTM 직접 유입', (r) => r.direct_submissions], ['직접 성공', (r) => r.direct_success]];
  $('#utm-stat-tables').replaceChildren(
    metricTable('채널별', [['채널', (r) => `${r.label} (${r.key})`], ...metricColumns, ...direct], data.by_channel),
    metricTable('캠페인별', [['캠페인', (r) => `${r.label} (${r.key})`], ...metricColumns, ...direct], data.by_campaign),
    metricTable('링크별', [['코드', (r) => r.code], ['채널', (r) => r.channel_key], ['캠페인', (r) => r.utm_campaign],
      ['content', (r) => r.utm_content], ...metricColumns], data.links),
    metricTable('UTM 직접 유입 (단축코드 없음)', [['source', (r) => r.utm_source], ['medium', (r) => r.utm_medium],
      ['campaign', (r) => r.utm_campaign], ['입력', (r) => r.submissions], ['성공', (r) => r.success]], data.direct),
  );
}

// ---- wiring -------------------------------------------------------------------

$('#range-apply').addEventListener('click', () => { state.offset = 0; refresh(); });
$('#users-search').addEventListener('click', refresh);
$('#subs-search').addEventListener('click', () => { state.offset = 0; refresh(); });
$('#subs-visitor-clear').addEventListener('click', () => { state.visitor = null; state.offset = 0; refresh(); });
$('#subs-prev').addEventListener('click', () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); refresh(); });
$('#subs-next').addEventListener('click', () => { state.offset += PAGE_SIZE; refresh(); });
$('#detail-close').addEventListener('click', () => $('#detail').close());
$('#detail-delete').addEventListener('click', deleteCurrent);
for (const input of ['#users-q', '#subs-q']) {
  $(input).addEventListener('keydown', (event) => { if (event.key === 'Enter') { state.offset = 0; refresh(); } });
}

$('#utm-form').addEventListener('submit', createLinks);
$('#utm-target-preset').addEventListener('change', () => { $('#utm-target-custom-field').hidden = $('#utm-target-preset').value !== 'custom'; });
$('#links-search').addEventListener('click', refresh);
$('#links-q').addEventListener('keydown', (event) => { if (event.key === 'Enter') refresh(); });
$('#channel-form').addEventListener('submit', saveChannel);
$('#campaign-form').addEventListener('submit', saveCampaign);
$('#channel-cancel').addEventListener('click', () => editChannel(null));
$('#campaign-cancel').addEventListener('click', () => editCampaign(null));

renderTabs();
selectTab('stats');
