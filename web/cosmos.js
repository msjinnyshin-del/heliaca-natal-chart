export function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function createOrbitField(seed = 20260921, count = 150) {
  const random = seededRandom(seed);
  return Array.from({ length: count }, (_, index) => ({
    radiusX: .24 + random() * .42,
    radiusY: .10 + random() * .24,
    rotation: -.34 + random() * .16,
    start: random() * Math.PI * 2,
    length: .35 + random() * 2.8,
    alpha: .08 + random() * .26,
    width: .28 + random() * .62,
    teal: random() > .48,
    speed: (.000015 + random() * .000035) * (index % 2 ? 1 : -1),
  }));
}

export function orbitPoint(orbit, angle) {
  const cos = Math.cos(orbit.rotation);
  const sin = Math.sin(orbit.rotation);
  const ellipseX = Math.cos(angle) * orbit.radiusX;
  const ellipseY = Math.sin(angle) * orbit.radiusY;
  return {
    x: orbit.centerX + ellipseX * cos - ellipseY * sin,
    y: orbit.centerY + ellipseX * sin + ellipseY * cos,
  };
}

function setupCosmos(canvas) {
  const context = canvas.getContext('2d', { alpha: true });
  if (!context) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let width = 0;
  let height = 0;
  let dpr = 1;
  let field = [];
  let buffer = document.createElement('canvas');
  let bufferContext = buffer.getContext('2d');
  let animationFrame = 0;

  const drawArc = (target, orbit) => {
    target.beginPath();
    const steps = 38;
    for (let step = 0; step <= steps; step += 1) {
      const point = orbitPoint(orbit, orbit.start + orbit.length * step / steps);
      if (step === 0) target.moveTo(point.x, point.y);
      else target.lineTo(point.x, point.y);
    }
    target.strokeStyle = orbit.teal ? `rgba(90, 222, 205, ${orbit.alpha})` : `rgba(232, 239, 235, ${orbit.alpha * .8})`;
    target.lineWidth = orbit.width * dpr;
    target.stroke();
  };

  const rebuild = () => {
    const bounds = canvas.getBoundingClientRect();
    width = Math.max(1, Math.round(bounds.width));
    height = Math.max(1, Math.round(bounds.height));
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    buffer.width = canvas.width;
    buffer.height = canvas.height;
    const count = Math.min(180, Math.max(80, Math.round(width * height / 6500)));
    field = createOrbitField(20260921, count).map((orbit) => ({
      ...orbit,
      centerX: width * (.53 + (orbit.radiusY - .22) * .16) * dpr,
      centerY: height * .52 * dpr,
      radiusX: orbit.radiusX * width * dpr,
      radiusY: orbit.radiusY * height * dpr,
    }));
    bufferContext = buffer.getContext('2d');
    bufferContext.clearRect(0, 0, buffer.width, buffer.height);
    field.forEach((orbit) => drawArc(bufferContext, orbit));

    const random = seededRandom(771);
    const starCount = Math.min(170, Math.round(width / 5));
    for (let index = 0; index < starCount; index += 1) {
      const x = random() * buffer.width;
      const y = random() * buffer.height;
      const radius = (.35 + random() * 1.15) * dpr;
      bufferContext.beginPath();
      bufferContext.arc(x, y, radius, 0, Math.PI * 2);
      bufferContext.fillStyle = `rgba(228, 241, 236, ${.18 + random() * .58})`;
      bufferContext.fill();
    }
  };

  const render = (time = 0) => {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(buffer, 0, 0);
    field.filter((_, index) => index % 13 === 0).forEach((orbit, index) => {
      const point = orbitPoint(orbit, orbit.start + orbit.length * .58 + time * orbit.speed);
      context.beginPath();
      context.arc(point.x, point.y, (index % 3 === 0 ? 1.45 : .75) * dpr, 0, Math.PI * 2);
      context.fillStyle = index % 3 === 0 ? 'rgba(140, 242, 225, .9)' : 'rgba(239, 246, 242, .72)';
      context.fill();
    });
    if (!reducedMotion) animationFrame = window.requestAnimationFrame(render);
  };

  const resize = new ResizeObserver(() => {
    window.cancelAnimationFrame(animationFrame);
    rebuild();
    render();
  });
  resize.observe(canvas);
}

if (typeof document !== 'undefined') {
  const canvas = document.querySelector('#cosmos-field');
  if (canvas) setupCosmos(canvas);
}
