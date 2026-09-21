import test from 'node:test';
import assert from 'node:assert/strict';
import { ATTRIBUTION_KEY, VISITOR_KEY, buildClientContext, captureAttribution, getVisitorId, isVisitorId, parseAttribution, readAttribution } from '../web/client-context.js';

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)), data };
}

const throwingStorage = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };

test('visitor id is random, valid, persisted and reused', () => {
  const storage = memoryStorage();
  const first = getVisitorId(storage);
  assert.ok(isVisitorId(first));
  assert.equal(getVisitorId(storage), first);
  assert.equal(storage.data.get(VISITOR_KEY), first);
  assert.notEqual(getVisitorId(memoryStorage()), first);
});

test('invalid stored visitor id is replaced and blocked storage still yields an id', () => {
  const storage = memoryStorage({ [VISITOR_KEY]: '<script>' });
  assert.ok(isVisitorId(getVisitorId(storage)));
  assert.ok(isVisitorId(getVisitorId(throwingStorage)));
  assert.ok(isVisitorId(getVisitorId(null)));
});

test('UTM params are validated and first touch wins', () => {
  assert.equal(parseAttribution('?q=1'), null);
  assert.deepEqual(parseAttribution('?utm_source=threads&utm_campaign=%EA%B0%80%EC%9D%84_%EB%9F%B0%EC%B9%AD&utm_medium=%3Cscript%3E&sc=abc234'),
    { utm: { utm_source: 'threads', utm_campaign: '가을_런칭' }, short_code: 'abc234' });
  const storage = memoryStorage();
  captureAttribution(storage, '?utm_source=first');
  assert.deepEqual(captureAttribution(storage, '?utm_source=second'), { utm: { utm_source: 'first' }, short_code: null });
  assert.equal(captureAttribution(throwingStorage, '?utm_source=x').utm.utm_source, 'x');
});

test('tampered stored attribution is re-validated', () => {
  const storage = memoryStorage({ [ATTRIBUTION_KEY]: JSON.stringify({ utm: { utm_source: '"><img>' }, short_code: '../x' }) });
  assert.equal(readAttribution(storage), null);
  assert.equal(readAttribution(memoryStorage({ [ATTRIBUTION_KEY]: '{bad json' })), null);
});

test('client context is separate from the chart payload and trims name', () => {
  const context = buildClientContext({ visitorId: 'visitorAAAAAAAAAAAAAA', name: '  가상인물  ', attribution: { utm: { utm_source: 'ig' }, short_code: null } });
  assert.deepEqual(context, { visitor_id: 'visitorAAAAAAAAAAAAAA', name: '가상인물', consent: true, utm: { utm_source: 'ig' }, short_code: null });
  assert.equal(buildClientContext({ visitorId: 'bad', name: '', attribution: null }).visitor_id, null);
});

test('short-link redirect query (/l/CODE -> /?utm_*&sc=CODE) is captured as first touch', () => {
  const storage = memoryStorage();
  const redirect = '?utm_source=instagram&utm_medium=social&utm_campaign=fall&utm_content=reel&sc=k7m2xq';
  const captured = captureAttribution(storage, redirect);
  assert.deepEqual(captured, { utm: { utm_source: 'instagram', utm_medium: 'social', utm_campaign: 'fall', utm_content: 'reel' }, short_code: 'k7m2xq' });
  const context = buildClientContext({ visitorId: getVisitorId(storage), name: '', attribution: readAttribution(storage) });
  assert.equal(context.short_code, 'k7m2xq');
  // a later short link does not overwrite the first touch
  assert.equal(captureAttribution(storage, '?utm_source=kakao&sc=abcdef').short_code, 'k7m2xq');
  assert.deepEqual(parseAttribution('?utm_source=short-link&utm_medium=unknown'), { utm: { utm_source: 'short-link', utm_medium: 'unknown' }, short_code: null });
});
