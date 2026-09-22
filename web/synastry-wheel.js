import { annularSector, circularMidpoint, polarPoint, staggerLabels } from './geometry.js';
import { formatWheelPosition } from './chart-profile.js';

const NS = 'http://www.w3.org/2000/svg';
const SIGN_SYMBOLS = ['♈︎', '♉︎', '♊︎', '♋︎', '♌︎', '♍︎', '♎︎', '♏︎', '♐︎', '♑︎', '♒︎', '♓︎'];
const SECTOR_COLORS = ['#2d3428', '#363126', '#283a32', '#173f3a', '#193c3c', '#273b35', '#2d343a', '#342e39', '#3c2e2d', '#302f3b', '#213740', '#263a30'];
const WHEEL_BODIES = ['Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto', 'Chiron', 'NorthNode'];
const TONE = { Trine: 'harmonic', Sextile: 'harmonic', Square: 'dynamic', Opposition: 'dynamic', Conjunction: 'neutral' };

function el(name, attributes = {}, text = '') {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== '') node.textContent = text;
  return node;
}

function line(group, from, to, className) {
  group.append(el('line', { x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: className }));
}

function wheelBodies(chart) {
  return chart.bodies.filter((body) => WHEEL_BODIES.includes(body.id) && Number.isFinite(body.longitude));
}

/** Bi-wheel: person A's houses and bodies inside, person B's bodies on the outer band, A's ASC at left. */
export function createSynastryWheel(result, names = {}) {
  const a = result.person_a;
  const b = result.person_b;
  const asc = a.angles.find((angle) => angle.id === 'ASC')?.longitude ?? 0;
  const svg = el('svg', { class: 'natal-wheel synastry-wheel', viewBox: '0 0 720 720', role: 'img', 'aria-labelledby': 'syn-title', xmlns: NS });
  svg.append(el('title', { id: 'syn-title' }, `${names.a || 'A'} · ${names.b || 'B'} 시너스트리 바이휠`));
  svg.append(el('rect', { x: 0, y: 0, width: 720, height: 720, rx: 18, class: 'wheel-background' }));
  const g = el('g');
  svg.append(g);
  g.append(el('circle', { cx: 360, cy: 360, r: 346, class: 'wheel-backdrop' }));

  for (let i = 0; i < 12; i += 1) {
    g.append(el('path', { d: annularSector(i * 30, (i + 1) * 30, asc, 360, 360, 298, 342), fill: SECTOR_COLORS[i], class: 'wheel-zodiac' }));
    const point = polarPoint(i * 30 + 15, asc, 360, 360, 320);
    g.append(el('text', { x: point.x, y: point.y, class: 'wheel-zodiac-symbol' }, SIGN_SYMBOLS[i]));
  }
  for (const r of [298, 240, 122]) g.append(el('circle', { cx: 360, cy: 360, r, class: r === 240 ? 'wheel-orbit syn-divider' : 'wheel-orbit' }));

  const houses = [...a.houses].sort((x, y) => x.number - y.number);
  houses.forEach((house, index) => {
    line(g, polarPoint(house.longitude, asc, 360, 360, 122), polarPoint(house.longitude, asc, 360, 360, 240),
      `wheel-house ${[1, 4, 7, 10].includes(house.number) ? 'angular' : ''}`);
    const next = houses[(index + 1) % 12];
    const numberPoint = polarPoint(circularMidpoint(house.longitude, next.longitude), asc, 360, 360, 134);
    g.append(el('text', { x: numberPoint.x, y: numberPoint.y, class: 'wheel-house-number' }, String(house.number)));
  });

  const aLon = new Map([...a.bodies, ...a.angles].map((item) => [item.id, item.longitude]));
  const bLon = new Map([...b.bodies, ...b.angles].map((item) => [item.id, item.longitude]));
  for (const aspect of result.aspects) {
    const from = aLon.get(aspect.a);
    const to = bLon.get(aspect.b);
    if (!Number.isFinite(from) || !Number.isFinite(to)) continue;
    line(g, polarPoint(from, asc, 360, 360, 118), polarPoint(to, asc, 360, 360, 118), `wheel-aspect ${TONE[aspect.name] || 'neutral'}`);
  }

  // Inner ring: person A. Ticks sit on the actual longitude; only labels spread.
  for (const body of staggerLabels(wheelBodies(a), { asc, baseRadius: 188, step: 0, labelSeparation: 10, center: 360 })) {
    const tickInner = polarPoint(body.longitude, asc, 360, 360, 230);
    line(g, tickInner, polarPoint(body.longitude, asc, 360, 360, 240), 'wheel-body-tick');
    line(g, tickInner, body.label, 'wheel-leader');
    g.append(el('text', { x: body.label.x, y: body.label.y - 4, class: 'wheel-body-symbol syn-a' }, body.symbol));
    g.append(el('text', { x: body.label.x, y: body.label.y + 13, class: 'wheel-body-position' }, formatWheelPosition(body)));
  }
  // Outer band: person B.
  for (const body of staggerLabels(wheelBodies(b), { asc, baseRadius: 262, step: 0, labelSeparation: 10, center: 360 })) {
    const tickOuter = polarPoint(body.longitude, asc, 360, 360, 298);
    line(g, polarPoint(body.longitude, asc, 360, 360, 288), tickOuter, 'wheel-body-tick syn-b-tick');
    line(g, polarPoint(body.longitude, asc, 360, 360, 288), body.label, 'wheel-leader');
    g.append(el('text', { x: body.label.x, y: body.label.y - 3, class: 'wheel-body-symbol syn-b' }, body.symbol));
    g.append(el('text', { x: body.label.x, y: body.label.y + 13, class: 'wheel-body-position' }, formatWheelPosition(body)));
  }

  for (const angle of a.angles.filter((item) => ['ASC', 'MC'].includes(item.id))) {
    line(g, polarPoint(angle.longitude, asc, 360, 360, 110), polarPoint(angle.longitude, asc, 360, 360, 346), 'wheel-axis');
  }
  g.append(el('circle', { cx: 360, cy: 360, r: 16, class: 'wheel-center' }));
  return svg;
}
