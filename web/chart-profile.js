const SIGN_GLYPHS = ['♈︎', '♉︎', '♊︎', '♋︎', '♌︎', '♍︎', '♎︎', '♏︎', '♐︎', '♑︎', '♒︎', '♓︎'];
const HOUSE_NAMES = { P: 'Placidus', W: 'Whole Sign', E: 'Equal', K: 'Koch', O: 'Porphyry' };

export function motionMarker(item) {
  return item?.direction === 'R' || item?.direction === 'S' ? item.direction : '';
}

export function formatWheelPosition(item) {
  const longitude = ((Number(item.longitude) % 360) + 360) % 360;
  const signIndex = Number.isInteger(item.sign_index) ? item.sign_index : Math.floor(longitude / 30);
  const within = longitude - signIndex * 30;
  const degrees = Math.floor(within);
  const minutes = Math.floor((within - degrees) * 60 + 1e-8);
  const marker = motionMarker(item);
  return `${SIGN_GLYPHS[signIndex]} ${String(degrees).padStart(2, '0')}°${String(minutes).padStart(2, '0')}′${marker ? ` ${marker}` : ''}`;
}

function coordinate(value, positive, negative) {
  const numeric = Number(value);
  return `${numeric < 0 ? '−' : ''}${Math.abs(numeric).toFixed(6)}°${numeric < 0 ? negative : positive}`;
}

export function buildWheelMetadata(result) {
  const input = result.input || {};
  const normalized = result.normalized || {};
  const settings = result.settings || {};
  const metadata = result.metadata || {};
  const house = HOUSE_NAMES[settings.house_system] || settings.house_system || '—';
  return [
    `${input.date || '—'} ${input.time || '—'} ${normalized.offset || ''} · UTC ${normalized.utc || '—'}`,
    `${coordinate(normalized.latitude, 'N', 'S')}  ${coordinate(normalized.longitude, 'E', 'W')} · ${input.place || ''}`,
    `${String(settings.zodiac || 'tropical').toUpperCase()} · ${house} · ${result.sect || '—'} · ${settings.aspect_rule || '—'}`,
    `${metadata.engine || 'Swiss Ephemeris'} ${metadata.engine_version || ''} · TZ ${normalized.timezone || '—'}`,
  ];
}

export { SIGN_GLYPHS };
