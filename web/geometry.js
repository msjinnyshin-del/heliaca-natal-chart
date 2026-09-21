export function norm(value) {
  return ((Number(value) % 360) + 360) % 360;
}

export function chartAngle(longitude, ascendant) {
  return norm(180 - norm(Number(longitude) - Number(ascendant)));
}

export function polarPoint(longitude, ascendant, cx, cy, radius) {
  const radians = chartAngle(longitude, ascendant) * Math.PI / 180;
  const clean = (value) => Math.abs(value) < 1e-12 ? 0 : Number(value.toFixed(10));
  return {
    x: clean(cx + Math.cos(radians) * radius),
    y: clean(cy + Math.sin(radians) * radius),
  };
}

export function angularDistance(a, b) {
  const delta = Math.abs(norm(Number(a) - Number(b)));
  return Number(Math.min(delta, 360 - delta).toFixed(12));
}

export function circularMidpoint(start, end) {
  return norm(Number(start) + norm(Number(end) - Number(start)) / 2);
}

export function spreadLabelLongitudes(items, minimumSeparation = 12) {
  if (items.length < 2) return items.map(item => ({ ...item, labelLongitude: norm(item.longitude) }));
  const sorted = items.map((item, index) => ({ ...item, index })).sort((a, b) => norm(a.longitude) - norm(b.longitude));
  const gap = Math.min(minimumSeparation, 360 / items.length);
  let best = null;
  // Try every circular cut; each linear fit minimizes label movement under a
  // minimum angular spacing constraint. Actual longitude/ticks never move.
  for (let cut = 0; cut < sorted.length; cut++) {
    const rotated = [...sorted.slice(cut), ...sorted.slice(0, cut)];
    const desired = rotated.map(item => norm(item.longitude));
    for (let i = 1; i < desired.length; i++) while (desired[i] < desired[i - 1]) desired[i] += 360;
    const blocks = [];
    desired.forEach((angle, i) => {
      blocks.push({ start: i, end: i, mean: angle - i * gap, count: 1 });
      while (blocks.length > 1 && blocks.at(-2).mean > blocks.at(-1).mean) {
        const right = blocks.pop(), left = blocks.pop();
        const count = left.count + right.count;
        blocks.push({ start: left.start, end: right.end, mean: (left.mean * left.count + right.mean * right.count) / count, count });
      }
    });
    const fitted = [];
    for (const block of blocks) for (let i = block.start; i <= block.end; i++) fitted[i] = block.mean + i * gap;
    if (fitted[0] + 360 - fitted.at(-1) < gap - 1e-8) continue;
    const cost = fitted.reduce((sum, value, i) => sum + (value - desired[i]) ** 2, 0);
    if (!best || cost < best.cost) best = { cost, items: rotated.map((item, i) => ({ ...item, labelLongitude: norm(fitted[i]) })) };
  }
  if (!best) throw new Error('Could not lay out circular labels');
  return best.items.sort((a, b) => a.index - b.index).map(({ index, ...item }) => item);
}

export function staggerLabels(items, options = {}) {
  const {
    asc = 0,
    baseRadius = 200,
    step = 16,
    threshold = 4,
    center = 360,
    labelSeparation = 0,
  } = options;
  const placed = labelSeparation ? spreadLabelLongitudes(items, labelSeparation) : items;
  const sorted = [...placed].sort((a, b) => norm(a.longitude) - norm(b.longitude));

  return sorted.map((item, index) => {
    const previous = sorted[(index - 1 + sorted.length) % sorted.length];
    const close = sorted.length > 1 && angularDistance(item.longitude, previous.longitude) < threshold;
    const labelRadius = baseRadius + (close ? step : 0);
    return {
      ...item,
      longitude: Number(item.longitude),
      labelRadius,
      tick: polarPoint(item.longitude, asc, center, center, baseRadius),
      label: polarPoint(item.labelLongitude ?? item.longitude, asc, center, center, labelRadius),
    };
  });
}

export function formatDifference(degrees) {
  const seconds = Number(degrees) * 3600;
  const rounded = Math.round(seconds * 100) / 100;
  if (Object.is(rounded, -0) || rounded === 0) return '0.00″';
  return `${rounded > 0 ? '+' : '−'}${Math.abs(rounded).toFixed(2)}″`;
}

export function annularSector(startLongitude, endLongitude, asc, cx, cy, innerRadius, outerRadius) {
  const start = polarPoint(startLongitude, asc, cx, cy, outerRadius);
  const end = polarPoint(endLongitude, asc, cx, cy, outerRadius);
  const innerEnd = polarPoint(endLongitude, asc, cx, cy, innerRadius);
  const innerStart = polarPoint(startLongitude, asc, cx, cy, innerRadius);
  const span = norm(Number(endLongitude) - Number(startLongitude));
  const largeArc = span > 180 ? 1 : 0;
  // Longitude increases counter-clockwise, hence SVG sweep=0 on the outer arc.
  return [
    `M ${start.x} ${start.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArc} 0 ${end.x} ${end.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArc} 1 ${innerStart.x} ${innerStart.y}`,
    'Z',
  ].join(' ');
}
