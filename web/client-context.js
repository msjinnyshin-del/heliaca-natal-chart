// Operational context sent next to (never inside) the chart payload:
// an anonymous random visitor id and first-touch UTM attribution. No fingerprinting.
export const VISITOR_KEY = 'heliaca.visitor_id';
export const ATTRIBUTION_KEY = 'heliaca.attribution';
export const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
const VISITOR_PATTERN = /^[A-Za-z0-9_-]{16,64}$/;
const UTM_PATTERN = /^[\p{L}\p{N}_.~+\- ]{1,100}$/u;
const SHORT_CODE_PATTERN = /^[A-Za-z0-9_-]{3,32}$/;

function safeGet(storage, key) {
  try { return storage?.getItem(key) ?? null; } catch { return null; }
}

function safeSet(storage, key, value) {
  try { storage?.setItem(key, value); return true; } catch { return false; }
}

export function isVisitorId(value) {
  return typeof value === 'string' && VISITOR_PATTERN.test(value);
}

export function randomVisitorId(cryptoImpl = globalThis.crypto) {
  const bytes = new Uint8Array(16);
  cryptoImpl.getRandomValues(bytes);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function getVisitorId(storage, cryptoImpl = globalThis.crypto) {
  const existing = safeGet(storage, VISITOR_KEY);
  if (isVisitorId(existing)) return existing;
  const created = randomVisitorId(cryptoImpl);
  safeSet(storage, VISITOR_KEY, created);
  return created;
}

export function cleanUtmValue(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  return UTM_PATTERN.test(text) ? text : null;
}

export function parseAttribution(search) {
  const params = new URLSearchParams(search || '');
  const utm = {};
  for (const key of UTM_KEYS) {
    const value = cleanUtmValue(params.get(key));
    if (value) utm[key] = value;
  }
  const code = params.get('sc');
  const shortCode = typeof code === 'string' && SHORT_CODE_PATTERN.test(code) ? code : null;
  if (!Object.keys(utm).length && !shortCode) return null;
  return { utm, short_code: shortCode };
}

// First touch wins: a later landing URL never overwrites stored attribution.
export function captureAttribution(storage, search) {
  const stored = readAttribution(storage);
  if (stored) return stored;
  const parsed = parseAttribution(search);
  if (parsed) safeSet(storage, ATTRIBUTION_KEY, JSON.stringify(parsed));
  return parsed;
}

export function readAttribution(storage) {
  const raw = safeGet(storage, ATTRIBUTION_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    const utm = {};
    for (const key of UTM_KEYS) {
      const clean = cleanUtmValue(value?.utm?.[key]);
      if (clean) utm[key] = clean;
    }
    const shortCode = SHORT_CODE_PATTERN.test(value?.short_code ?? '') ? value.short_code : null;
    return Object.keys(utm).length || shortCode ? { utm, short_code: shortCode } : null;
  } catch {
    return null;
  }
}

// Storing the name and raw birth input is opt-in; without consent the name is not even sent.
export function buildClientContext({ visitorId, name, consent, attribution }) {
  const stored = consent === true;
  const trimmed = stored && typeof name === 'string' ? name.trim().slice(0, 80) : '';
  return {
    visitor_id: isVisitorId(visitorId) ? visitorId : null,
    name: trimmed || null,
    store_consent: stored,
    utm: attribution?.utm ?? {},
    short_code: attribution?.short_code ?? null,
  };
}
