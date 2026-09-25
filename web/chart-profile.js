const SIGN_GLYPHS = ['♈︎', '♉︎', '♊︎', '♋︎', '♌︎', '♍︎', '♎︎', '♏︎', '♐︎', '♑︎', '♒︎', '♓︎'];
const SIGN_NAMES = ['양', '황소', '쌍둥이', '게', '사자', '처녀', '천칭', '전갈', '사수', '염소', '물병', '물고기'];
export const HOUSE_NAMES = { P: 'Placidus', W: 'Whole Sign', E: 'Equal', K: 'Koch', O: 'Porphyry', R: 'Regiomontanus', C: 'Campanus', B: 'Alcabitius' };
const HARMONIC = new Set(['Trine', 'Sextile']);
const DYNAMIC = new Set(['Square', 'Opposition']);
const MINOR = new Set(['Quincunx', 'SemiSquare', 'Sesquiquadrate', 'Quintile']);

export function aspectTone(name) {
  return HARMONIC.has(name) ? 'harmonic' : DYNAMIC.has(name) ? 'dynamic' : MINOR.has(name) ? 'minor' : 'neutral';
}

export function lilithLegend(result) {
  return result?.settings?.lilith_mode === 'osculating' ? '⚸ Osculating Lilith' : '⚸ Mean Lilith';
}

export function isUnknownTime(result) {
  return result?.normalized?.time_accuracy === 'unknown';
}

// Unknown birth time: only aspects that hold for the whole local day are drawn as chart facts.
export function wheelAspects(result) {
  const aspects = result?.aspects || [];
  return isUnknownTime(result) ? aspects.filter((aspect) => aspect.stability === 'stable') : aspects;
}

// On a 25-hour day a wall-clock time can occur twice; the UTC offset says which one is meant.
// Only an end that falls on the next calendar date reads as 24:00 (or "다음 날 HH:MM" after a midnight gap);
// a second 00:00 on the same date (clocks turned back at midnight) keeps its own time and offset.
function clock(local, offset, isEnd, repeatedHour, dayDate) {
  const text = String(local || '').slice(11, 16);
  const nextDay = isEnd && dayDate && String(local || '').slice(0, 10) > dayDate;
  if (nextDay) return text === '00:00' ? '24:00' : `다음 날 ${text}`;
  return repeatedHour && offset ? `${text}(UTC${offset})` : text;
}

export function hasRepeatedHour(result) {
  return Number(result?.normalized?.day_range?.hours) > 24;
}

export function aspectTimingLabel(aspect, { repeatedHour = false } = {}) {
  if (!aspect?.stability) return '';
  if (aspect.stability === 'stable') return '하루 종일 유지';
  const dayDate = String(aspect.windows?.[0]?.start_local || '').slice(0, 10);
  const spans = (aspect.windows || []).map((w) =>
    `${clock(w.start_local, w.start_offset, false, repeatedHour, dayDate)}–${clock(w.end_local, w.end_offset, true, repeatedHour, dayDate)}`);
  return `${spans.join(', ')}에 태어난 경우만`;
}

export function sensitivityNote(body, { repeatedHour = false } = {}) {
  const sensitivity = body?.time_sensitivity;
  if (!sensitivity) return '';
  const notes = [
    ...(sensitivity.ingresses || []).map((item) => `${clock(item.local, item.offset, false, repeatedHour)} ${SIGN_NAMES[item.from_sign_index]}→${SIGN_NAMES[item.to_sign_index]}`),
    ...(sensitivity.stations || []).map((item) => `${clock(item.local, item.offset, false, repeatedHour)} ${item.to === 'R' ? '역행' : '순행'} 전환`),
  ];
  return notes.join(' · ');
}

// Bodies that travel at least 1° in the day get their start–end positions shown next to the noon value.
export function dailyRangeNote(body) {
  const range = body?.time_sensitivity?.range;
  if (!range || !(Number(range.degrees) >= 1)) return '';
  return `하루 범위 ${range.start?.position || '—'} → ${range.end?.position || '—'}`;
}

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
  const unknown = isUnknownTime(result);
  const house = unknown ? '하우스·ASC 없음 (생시 미상)' : HOUSE_NAMES[settings.house_system] || settings.house_system || '—';
  const time = unknown ? `생시 미상 (정오 ${String(normalized.representative_local_time || '12:00').slice(0, 5)} 대표)` : input.time || '—';
  return [
    `${input.calendar === 'lunar' ? `음력 ${input.date}${input.lunar_leap ? '(윤)' : ''} = 양력 ${normalized.solar_date || '—'}` : (input.date || '—')} ${time} ${normalized.offset || ''} · UTC ${normalized.utc || '—'}`,
    `${coordinate(normalized.latitude, 'N', 'S')}  ${coordinate(normalized.longitude, 'E', 'W')} · ${input.place || ''}`,
    `${String(settings.zodiac || 'tropical').toUpperCase()} · ${house} · ${result.sect || '—'} · ${settings.aspect_rule || '—'}`,
    `${metadata.engine || 'Swiss Ephemeris'} ${metadata.engine_version || ''} · TZ ${normalized.timezone || '—'}`,
  ];
}

export { SIGN_GLYPHS };
