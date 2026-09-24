import { annularSector, circularMidpoint, polarPoint, staggerLabels } from './geometry.js';
import { buildWheelMetadata, formatWheelPosition, isUnknownTime, wheelAspects } from './chart-profile.js';

const NS = 'http://www.w3.org/2000/svg';
const SIGNS = [
  ['양', '♈︎'], ['황소', '♉︎'], ['쌍둥이', '♊︎'], ['게', '♋︎'],
  ['사자', '♌︎'], ['처녀', '♍︎'], ['천칭', '♎︎'], ['전갈', '♏︎'],
  ['사수', '♐︎'], ['염소', '♑︎'], ['물병', '♒︎'], ['물고기', '♓︎'],
];
const SECTOR_COLORS = ['#2d3428', '#363126', '#283a32', '#173f3a', '#193c3c', '#273b35', '#2d343a', '#342e39', '#3c2e2d', '#302f3b', '#213740', '#263a30'];
const HARMONIC = new Set(['Trine', 'Sextile']);
const DYNAMIC = new Set(['Square', 'Opposition']);

function el(name, attributes = {}, text = '') {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== '') node.textContent = text;
  return node;
}

function drawLine(svg, from, to, className) {
  svg.append(el('line', { x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: className }));
}

export function createNatalWheel(result) {
  const asc = result.angles.find((angle) => angle.id === 'ASC')?.longitude ?? result.houses[0]?.longitude ?? 0;
  const svg = el('svg', {
    class: 'natal-wheel',
    viewBox: '0 0 720 804',
    role: 'img',
    'aria-labelledby': 'wheel-title wheel-desc',
    xmlns: NS,
  });
  const metadataLines = buildWheelMetadata(result);
  const unknown = isUnknownTime(result);
  svg.append(el('title', { id: 'wheel-title' }, `${result.input?.date || ''} ${unknown ? '생시 미상' : result.input?.time || ''} 네이털 차트`));
  svg.append(el('desc', { id: 'wheel-desc' }, unknown
    ? `생시 미상 tropical chart. ASC와 하우스 없이 양자리 0°를 왼쪽에 두고, 현지 정오 대표 위치와 하루 종일 유지되는 major aspect만 표시합니다. ${metadataLines.join('. ')}`
    : `ASC가 왼쪽인 tropical chart. 실제 황경 tick, 12개 하우스 커스프, major aspect를 표시합니다. ${metadataLines.join('. ')}`));
  svg.append(el('rect', { x: 0, y: 0, width: 720, height: 804, rx: 18, fill: '#020606', class: 'wheel-background' }));

  const group = el('g');
  svg.append(group);
  group.append(el('circle', { cx: 360, cy: 360, r: 339, class: 'wheel-backdrop' }));

  for (let i = 0; i < 12; i += 1) {
    group.append(el('path', {
      d: annularSector(i * 30, (i + 1) * 30, asc, 360, 360, 270, 324),
      fill: SECTOR_COLORS[i],
      class: 'wheel-zodiac',
    }));
    const signPoint = polarPoint(i * 30 + 15, asc, 360, 360, 297);
    group.append(el('text', { x: signPoint.x, y: signPoint.y, class: 'wheel-zodiac-symbol', 'aria-label': SIGNS[i][0] }, SIGNS[i][1]));
  }

  group.append(el('circle', { cx: 360, cy: 360, r: 269, class: 'wheel-orbit' }));
  group.append(el('circle', { cx: 360, cy: 360, r: 232, class: 'wheel-orbit' }));
  group.append(el('circle', { cx: 360, cy: 360, r: 122, class: 'wheel-orbit' }));

  const houses = [...result.houses].sort((a, b) => a.number - b.number);
  houses.forEach((house, index) => {
    const inner = polarPoint(house.longitude, asc, 360, 360, 122);
    const outer = polarPoint(house.longitude, asc, 360, 360, 269);
    drawLine(group, inner, outer, `wheel-house ${[1, 4, 7, 10].includes(house.number) ? 'angular' : ''}`);
    const next = houses[(index + 1) % houses.length];
    const numberPoint = polarPoint(circularMidpoint(house.longitude, next.longitude), asc, 360, 360, 246);
    group.append(el('text', { x: numberPoint.x, y: numberPoint.y, class: 'wheel-house-number' }, String(house.number)));
    const cuspPoint = polarPoint(house.longitude, asc, 360, 360, 258);
    group.append(el('text', { x: cuspPoint.x, y: cuspPoint.y - 3, class: 'wheel-cusp-label',
      fill: '#a9c4be', 'font-size': '7.5', 'font-family': 'monospace', 'text-anchor': 'middle' }, formatWheelPosition(house)));
  });

  const longitudeById = new Map();
  [...result.bodies, ...result.angles].forEach((item) => longitudeById.set(item.id, item.longitude));
  for (const aspect of wheelAspects(result)) {
    const a = longitudeById.get(aspect.a);
    const b = longitudeById.get(aspect.b);
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
    const from = polarPoint(a, asc, 360, 360, 118);
    const to = polarPoint(b, asc, 360, 360, 118);
    const tone = HARMONIC.has(aspect.name) ? 'harmonic' : DYNAMIC.has(aspect.name) ? 'dynamic' : 'neutral';
    drawLine(group, from, to, `wheel-aspect ${tone}`);
  }

  const displayBodies = result.bodies.filter((body) => Number.isFinite(body.longitude));
  const labels = staggerLabels(displayBodies, { asc, baseRadius: 199, step: 0, labelSeparation: 12, center: 360 });
  for (const body of labels) {
    const tickInner = polarPoint(body.longitude, asc, 360, 360, 225);
    const tickOuter = polarPoint(body.longitude, asc, 360, 360, 237);
    drawLine(group, tickInner, tickOuter, 'wheel-body-tick');
    drawLine(group, tickInner, body.label, 'wheel-leader');
    group.append(el('text', { x: body.label.x, y: body.label.y - 4, class: 'wheel-body-symbol' }, body.symbol || body.id.slice(0, 2)));
    group.append(el('text', { x: body.label.x, y: body.label.y + 14, class: 'wheel-body-position' }, formatWheelPosition(body)));
  }

  for (const angle of result.angles) {
    const axisInner = polarPoint(angle.longitude, asc, 360, 360, ['ASC', 'MC'].includes(angle.id) ? 110 : 270);
    const axisOuter = polarPoint(angle.longitude, asc, 360, 360, 338);
    drawLine(group, axisInner, axisOuter, `wheel-axis wheel-axis-${angle.id.toLowerCase()}`);
    const label = polarPoint(angle.longitude, asc, 360, 360, 346);
    const anchor = label.x < 75 ? 'start' : label.x > 645 ? 'end' : 'middle';
    group.append(el('text', { x: label.x, y: label.y, class: 'wheel-angle-label', 'text-anchor': anchor }, `${angle.id} ${formatWheelPosition(angle)}`));
  }

  group.append(el('circle', { cx: 360, cy: 360, r: 16, class: 'wheel-center' }));
  group.append(el('line', { x1: 344, y1: 360, x2: 376, y2: 360, class: 'wheel-orbit' }));
  group.append(el('line', { x1: 360, y1: 344, x2: 360, y2: 376, class: 'wheel-orbit' }));

  const band = el('g', { class: 'wheel-provenance' });
  band.append(el('rect', { x: 25, y: 710, width: 670, height: 78, rx: 8, class: 'wheel-meta-band',
    fill: '#081210', stroke: '#2e5d57', 'stroke-width': '.8' }));
  metadataLines.forEach((line, index) => {
    band.append(el('text', { x: 40, y: 728 + index * 14, class: 'wheel-metadata',
      fill: '#a9c4be', 'font-size': '8.5', 'font-family': 'monospace' }, line));
  });
  band.append(el('text', { x: 680, y: 780, class: 'wheel-legend', fill: '#d6ece7', 'font-size': '8',
    'font-family': 'monospace', 'text-anchor': 'end' }, unknown
    ? '생시 미상 · 정오 대표 위치 · ⚸ Mean Lilith · R retrograde · S near-station'
    : '⊗ Fortune · ◇ Spirit · ⚸ Mean Lilith · R retrograde · S near-station'));
  svg.append(band);
  return svg;
}
