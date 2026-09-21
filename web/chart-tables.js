// Shared DOM builders for chart result tables, used by the public workbench and admin viewer.
// All values are written with textContent; nothing from the result is parsed as HTML.

export function make(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== '') node.textContent = text;
  return node;
}

export function buildPositionRows(result) {
  return result.bodies.map((item) => {
    const row = document.createElement('tr');
    const nameCell = document.createElement('td');
    const name = make('span', 'body-name');
    name.append(make('span', 'body-glyph', item.symbol || '·'), document.createTextNode(item.name || item.id));
    nameCell.append(name);
    row.append(nameCell);
    row.append(make('td', '', item.position || '계산 불가'));
    row.append(make('td', '', Number.isInteger(item.house) ? String(item.house) : '—'));
    const motion = item.direction === 'S' ? 'S' : item.retrograde === true ? 'R' : item.retrograde === false ? 'D' : '—';
    const motionCell = make('td', item.retrograde ? 'retrograde' : '', motion);
    if (motion === 'S') motionCell.title = `근정지: |speed| < ${item.station_threshold}°/day. 정확한 정지 시각을 뜻하지 않습니다.`;
    row.append(motionCell);
    return row;
  });
}

export function buildAngleEntries(result) {
  return result.angles.map((angle) => {
    const wrapper = document.createElement('div');
    wrapper.append(make('dt', '', angle.id), make('dd', '', angle.position || `${angle.longitude.toFixed(6)}°`));
    return wrapper;
  });
}

export function sectLabel(result) {
  return result.sect === 'day' ? '☀ DAY CHART' : result.sect === 'night' ? '☾ NIGHT CHART' : 'SECT —';
}

export function buildAspectGrid(result) {
  if (!result.aspects?.length) return null;
  const grid = make('div', 'card-grid');
  for (const aspect of result.aspects) {
    const card = make('article', 'register-card');
    card.append(make('small', '', aspect.name));
    card.append(make('strong', '', `${aspect.a} — ${aspect.b}`));
    const separation = Number.isFinite(aspect.separation) ? `${aspect.separation.toFixed(4)}° separation` : '분리각 미제공';
    const orb = Number.isFinite(aspect.orb) ? `${aspect.orb.toFixed(4)}° orb` : 'orb 미제공';
    const allowed = Number.isFinite(aspect.allowed_orb) ? ` / 허용 ${aspect.allowed_orb}°` : '';
    card.append(make('p', '', `${separation} · ${orb}${allowed}`));
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
