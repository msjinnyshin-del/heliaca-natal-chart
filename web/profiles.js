// Birth profiles remembered in this browser only (localStorage). Nothing here is sent to the server;
// a hand-off to another tool page goes through sessionStorage, never the URL.
const KEY = 'heliaca.profiles.v1';
const HANDOFF_KEY = 'heliaca.handoff.v1';
const LIMIT = 12;

function safeStorage(kind) {
  try { return window[kind]; } catch { return null; }
}

function randomId() {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** Same person + same birth data is one profile, whatever the settings. */
export function profileKey(profile) {
  return JSON.stringify([profile.name || '', profile.calendar, profile.date, Boolean(profile.lunar_leap),
    profile.time_unknown ? null : profile.time, profile.place?.label, profile.place?.latitude, profile.place?.longitude]);
}

/** Birth data complete enough to fill a form; a stored profile additionally needs an id (isValidProfile). */
export function isBirthProfile(item) {
  const source = item?.place?.source;
  // A geocoded reference must itself be a usable city, or restoring it would fail half-way.
  const sourceOk = !source || source.mode === 'manual' || (Number.isInteger(source.place_id)
    && Number.isFinite(source.reference_latitude) && Number.isFinite(source.reference_longitude) && typeof source.reference_timezone === 'string');
  return Boolean(item && sourceOk && /^\d{4}-\d{2}-\d{2}$/.test(item.date || '')
    && ['gregorian', 'lunar'].includes(item.calendar) && (item.time_unknown || /^\d{2}:\d{2}/.test(item.time || ''))
    && item.place && typeof item.place.label === 'string' && Number.isFinite(item.place.latitude)
    && Number.isFinite(item.place.longitude) && typeof item.place.timezone === 'string');
}

export function isValidProfile(item) {
  return isBirthProfile(item) && typeof item.id === 'string';
}

export function createProfileStore(storage = safeStorage('localStorage')) {
  const read = () => {
    try { return (JSON.parse(storage?.getItem(KEY) || '[]') || []).filter(isValidProfile); } catch { return []; }
  };
  const write = (items) => {
    try { storage?.setItem(KEY, JSON.stringify(items)); return true; } catch { return false; }
  };
  return {
    list: read,
    get: (id) => read().find((item) => item.id === id) || null,
    /** Upserts by birth data; returns the stored profile (or null when storage is unavailable). */
    save(profile) {
      const items = read();
      const existing = items.find((item) => profileKey(item) === profileKey(profile));
      const stored = { ...profile, id: existing?.id || profile.id || randomId(), updated: new Date().toISOString() };
      if (!isValidProfile(stored)) return null;
      const next = [stored, ...items.filter((item) => item.id !== stored.id)].slice(0, LIMIT);
      return write(next) ? stored : null;
    },
    remove(id) { write(read().filter((item) => item.id !== id)); },
    clear() { try { storage?.removeItem(KEY); } catch { /* nothing stored */ } },
  };
}

export function profileLabel(profile) {
  const who = profile.name || '이름 없음';
  const date = `${profile.calendar === 'lunar' ? '음 ' : ''}${profile.date}`;
  return `${who} · ${date}${profile.time_unknown ? ' · 생시 모름' : ''}`;
}

/** One-shot hand-off of a profile to the next page in this tab. */
export function setHandoff(profile, storage = safeStorage('sessionStorage')) {
  try { storage?.setItem(HANDOFF_KEY, JSON.stringify(profile)); return true; } catch { return false; }
}

export function takeHandoff(storage = safeStorage('sessionStorage')) {
  try {
    const raw = storage?.getItem(HANDOFF_KEY);
    storage?.removeItem(HANDOFF_KEY);
    const profile = raw ? JSON.parse(raw) : null;
    return isBirthProfile(profile) ? profile : null;  // not necessarily a stored profile ("기억하기" off)
  } catch { return null; }
}
