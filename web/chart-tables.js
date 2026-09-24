// Shared DOM builders for chart result tables, used by the public workbench and admin viewer.
// All values are written with textContent; nothing from the result is parsed as HTML.
import { aspectTimingLabel, dailyRangeNote, hasRepeatedHour, isUnknownTime, sensitivityNote } from './chart-profile.js';

export function make(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = text;
  return node;
}

export function buildPositionRows(result) {
  const repeatedHour = hasRepeatedHour(result);
  return result.bodies.map((item) => {
    const row = document.createElement('tr');
    const nameCell = document.createElement('td');
    const name = make('span', 'body-name');
    name.append(make('span', 'body-glyph', item.symbol || '·'), document.createTextNode(item.name || item.id));
    nameCell.append(name);
    row.append(nameCell);
    const positionCell = make('td', '', item.position || '계산 불가');
    const range = dailyRangeNote(item);
    if (range) positionCell.append(make('small', 'daily-range', range));
    const note = sensitivityNote(item, { repeatedHour });
    if (note) positionCell.append(make('small', 'time-sensitive', `하루 중 변경: ${note}`));
    row.append(positionCell);
    row.append(make('td', '', Number.isInteger(item.house) ? String(item.house) : '—'));
    const motion = item.direction === 'S' ? 'S' : item.retrograde === true ? 'R' : item.retrograde === false ? 'D' : '—';
    const motionCell = make('td', item.retrograde ? 'retrograde' : '', motion);
    if (motion === 'S') motionCell.title = `근정지: |speed| < ${item.station_threshold}°/day. 정확한 정지 시각을 뜻하지 않습니다.`;
    row.append(motionCell);
    return row;
  });
}

export function buildAngleEntries(result) {
  if (isUnknownTime(result)) {
    const wrapper = document.createElement('div');
    wrapper.append(make('dt', '', 'ASC · MC'), make('dd', '', '생시 미상 — 계산하지 않음'));
    return [wrapper];
  }
  return result.angles.map((angle) => {
    const wrapper = document.createElement('div');
    wrapper.append(make('dt', '', angle.id), make('dd', '', angle.position || `${angle.longitude.toFixed(6)}°`));
    return wrapper;
  });
}

export function sectLabel(result) {
  if (isUnknownTime(result)) return 'SECT — 생시 미상';
  return result.sect === 'day' ? '☀ DAY CHART' : result.sect === 'night' ? '☾ NIGHT CHART' : 'SECT —';
}

export function buildAspectGrid(result) {
  if (!result.aspects?.length) return null;
  const grid = make('div', 'card-grid');
  const unknown = isUnknownTime(result);
  // Whole-day aspects first; time-dependent ones follow and are marked as conditional.
  const ordered = unknown ? [...result.aspects].sort((a, b) => (a.stability === 'stable' ? 0 : 1) - (b.stability === 'stable' ? 0 : 1)) : result.aspects;
  for (const aspect of ordered) {
    const card = make('article', `register-card${aspect.stability === 'partial' ? ' is-conditional' : ''}`);
    card.append(make('small', '', aspect.name));
    card.append(make('strong', '', `${aspect.a} — ${aspect.b}`));
    const separation = Number.isFinite(aspect.separation) ? `${aspect.separation.toFixed(4)}° separation` : '분리각 미제공';
    const orb = Number.isFinite(aspect.orb) ? `${aspect.orb.toFixed(4)}° orb` : 'orb 미제공';
    const allowed = Number.isFinite(aspect.allowed_orb) ? ` / 허용 ${aspect.allowed_orb}°` : '';
    card.append(make('p', '', `${unknown ? '정오 기준 ' : ''}${separation} · ${orb}${allowed}`));
    const timing = aspectTimingLabel(aspect, { repeatedHour: hasRepeatedHour(result) });
    if (timing) card.append(make('p', 'aspect-timing', timing));
    grid.append(card);
  }
  return grid;
}

export function buildHouseGrid(result) {
  const grid = make('div', 'card-grid');
  for (const house of [...result.houses].sort((a, b) => a.number - b.number)) {
    const card = make('article', 'register-card');
    card.append(make('small', '', `HOUSE ${house.number}`));
    card.append(make('strong', '', house.position || `${house.longitude.toFixed(6)}°`));
    card.append(make('p', '', `raw longitude ${Number(house.longitude).toFixed(8)}°`));
    grid.append(card);
  }
  return grid;
}
