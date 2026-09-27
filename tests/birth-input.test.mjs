import test from 'node:test';
import assert from 'node:assert/strict';

import { checkBirthDate, describeBirthDate, formatDateTyping } from '../web/birth-date.js';
import { createProfileStore, isValidProfile, profileKey, setHandoff, takeHandoff } from '../web/profiles.js';

test('typed digits become YYYY-MM-DD progressively; separated dates are zero-padded', () => {
  assert.equal(formatDateTyping('1972'), '1972');
  assert.equal(formatDateTyping('19720'), '1972-0');
  assert.equal(formatDateTyping('197208'), '1972-08');
  assert.equal(formatDateTyping('19720827'), '1972-08-27');
  assert.equal(formatDateTyping('1972082799'), '1972-08-27');   // extra digits ignored
  assert.equal(formatDateTyping('1972.8.27'), '1972-08-27');
  assert.equal(formatDateTyping('1972/8/7'), '1972-08-07');
  assert.equal(formatDateTyping('1972년 8월 27일'), '1972-08-27');
  assert.equal(formatDateTyping('1985-07-14'), '1985-07-14');    // already formatted stays put
  assert.equal(formatDateTyping('1972. 8. 27.'), '1972-08-27');  // pasted Korean style, never cut short
  assert.equal(formatDateTyping('1972.8.'), '1972.8.');          // typing with separators: wait for the day
  assert.equal(formatDateTyping('1972-8-'), '1972-8-');
  assert.equal(formatDateTyping('1972.8.2'), '1972-08-02');
  assert.equal(formatDateTyping('1972-08-027'), '1972-08-27');   // next keystroke after the padded day
});

test('Gregorian dates must exist; lunar allows a 30th day in any month', () => {
  assert.equal(checkBirthDate('1972-08-27').weekday, '일');
  assert.equal(checkBirthDate('1972-02-30').ok, false);
  assert.match(checkBirthDate('1972-02-30').message, /30일이 없습니다/);
  assert.equal(checkBirthDate('2000-02-29').ok, true);
  assert.equal(checkBirthDate('1900-02-29').ok, false);         // 1900 is not a leap year
  assert.equal(checkBirthDate('1972-02-30', 'lunar').ok, true);
  assert.equal(checkBirthDate('1972-02-31', 'lunar').ok, false);
  assert.equal(checkBirthDate('1899-12-31').ok, false);
  assert.equal(checkBirthDate('2051-01-01', 'lunar').ok, false);
  assert.equal(checkBirthDate('1972-13-01').ok, false);
  assert.equal(checkBirthDate('1972-08').ok, false);
  assert.equal(describeBirthDate(checkBirthDate('1972-07-20', 'lunar'), 'lunar', true), '음력 1972년 7월 20일 (윤달) · 계산 시 양력으로 변환');
});

function memoryStorage() {
  const data = new Map();
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k) };
}

const PLACE = { label: '서울특별시, 대한민국', latitude: 37.566, longitude: 126.9784, timezone: 'Asia/Seoul',
  source: { mode: 'geocoded', place_id: 1835848, label: '서울특별시, 대한민국', reference_latitude: 37.566, reference_longitude: 126.9784, reference_timezone: 'Asia/Seoul' } };
const JIN = { name: '지니', calendar: 'gregorian', date: '1972-08-27', lunar_leap: false, time_unknown: false, time: '22:20', place: PLACE };

test('profiles upsert by birth data, keep the newest first, and can be removed', () => {
  const store = createProfileStore(memoryStorage());
  const first = store.save(JIN);
  assert.ok(first.id);
  assert.equal(store.save({ ...JIN }).id, first.id);             // same person again: one entry
  const partner = store.save({ ...JIN, name: '상대', date: '1967-12-24', time_unknown: true, time: null });
  assert.deepEqual(store.list().map((p) => p.name), ['상대', '지니']);
  assert.equal(store.get(partner.id).time_unknown, true);
  store.remove(first.id);
  assert.deepEqual(store.list().map((p) => p.name), ['상대']);
  store.clear();
  assert.deepEqual(store.list(), []);
});

test('invalid or tampered entries are never returned or stored', () => {
  const storage = memoryStorage();
  storage.setItem('heliaca.profiles.v1', JSON.stringify([{ id: 'x', date: 'nope' }, { ...JIN, id: 'ok' }]));
  const store = createProfileStore(storage);
  assert.deepEqual(store.list().map((p) => p.id), ['ok']);
  assert.equal(store.save({ ...JIN, place: { ...PLACE, latitude: 'north' } }), null);
  assert.equal(isValidProfile({ ...JIN, id: 'a', time: '' }), false);   // known time needs a time
  assert.equal(isValidProfile({ ...JIN, id: 'a', time: null, time_unknown: true }), true);
  assert.equal(isValidProfile({ ...JIN, id: 'a', place: { ...PLACE, source: { ...PLACE.source, reference_latitude: 'x' } } }), false);
  assert.equal(isValidProfile({ ...JIN, id: 'a', place: { ...PLACE, source: { mode: 'manual', place_id: null } } }), true);
  storage.setItem('heliaca.profiles.v1', '{broken');
  assert.deepEqual(createProfileStore(storage).list(), []);
  assert.deepEqual(createProfileStore(null).list(), []);                // storage blocked (private mode)
});

test('settings do not split a profile, birth data does', () => {
  assert.equal(profileKey({ ...JIN, extra: 1 }), profileKey(JIN));
  assert.notEqual(profileKey({ ...JIN, time: '22:21' }), profileKey(JIN));
  assert.equal(profileKey({ ...JIN, time_unknown: true, time: '10:00' }), profileKey({ ...JIN, time_unknown: true, time: null }));
});

test('hand-off to the next page is one-shot and validated', () => {
  const session = memoryStorage();
  assert.equal(setHandoff({ ...JIN }, session), true);                  // "기억하기" off: no stored id
  assert.equal(takeHandoff(session).name, '지니');
  assert.equal(setHandoff({ ...JIN, id: 'h1' }, session), true);
  assert.equal(takeHandoff(session).id, 'h1');
  assert.equal(takeHandoff(session), null);                             // consumed
  session.setItem('heliaca.handoff.v1', JSON.stringify({ id: 'bad' }));
  assert.equal(takeHandoff(session), null);
});
