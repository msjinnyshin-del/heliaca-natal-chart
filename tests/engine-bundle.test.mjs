import test from 'node:test';
import assert from 'node:assert/strict';

import { dayInYear, parseYears } from '../web/admin/engine-bundle.js';

test('years accept ranges and lists, sorted without duplicates', () => {
  assert.deepEqual(parseYears('2026-2028'), { years: [2026, 2027, 2028] });
  assert.deepEqual(parseYears('2030, 2026 2027~2028 2026'), { years: [2026, 2027, 2028, 2030] });
});

test('years reject bad text, reversed ranges, out-of-range and too many years', () => {
  assert.ok(parseYears('').error);
  assert.ok(parseYears('26').error);
  assert.ok(parseYears('2028-2026').error);
  assert.ok(parseYears('1900').error);
  assert.ok(parseYears('2101').error);
  assert.ok(parseYears('2000-2019').years);
  assert.ok(parseYears('2000-2020').error);
  assert.ok(parseYears('2000-2010, 2020-2029').error);
});

test('month-day moves into each year; Feb 29 falls back to Feb 28 in common years', () => {
  assert.equal(dayInYear(2027, '07-14'), '2027-07-14');
  assert.equal(dayInYear(2028, '02-29'), '2028-02-29');
  assert.equal(dayInYear(2027, '02-29'), '2027-02-28');
  assert.equal(dayInYear(2100, '02-29'), '2100-02-28');
});
