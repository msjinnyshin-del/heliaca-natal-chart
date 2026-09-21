import test from 'node:test';
import assert from 'node:assert/strict';

import {
  angularDistance,
  chartAngle,
  formatDifference,
  norm,
  polarPoint,
  staggerLabels,
  spreadLabelLongitudes,
} from '../web/geometry.js';
import { createRequestState, requestFingerprint } from '../web/request-state.js';
import { buildWheelMetadata, formatWheelPosition, motionMarker } from '../web/chart-profile.js';

test('norm wraps longitudes into [0, 360)', () => {
  assert.equal(norm(360), 0);
  assert.equal(norm(-1), 359);
  assert.equal(norm(721.25), 1.25);
});

test('ASC is placed exactly left and longitude increases counter-clockwise', () => {
  assert.equal(chartAngle(27, 27), 180);
  assert.equal(chartAngle(117, 27), 90);
  assert.deepEqual(polarPoint(27, 27, 100, 100, 80), { x: 20, y: 100 });
});

test('circular angular distance crosses the Aries boundary correctly', () => {
  assert.equal(angularDistance(359.8, 0.2), 0.4);
  assert.equal(angularDistance(10, 190), 180);
});

test('staggering changes label radius but preserves source longitude and tick point', () => {
  const items = staggerLabels([
    { id: 'a', longitude: 10 },
    { id: 'b', longitude: 11 },
    { id: 'c', longitude: 40 },
  ], { asc: 0, baseRadius: 100, step: 12, threshold: 3, center: 200 });

  assert.equal(items[0].labelRadius, 100);
  assert.equal(items[1].labelRadius, 112);
  assert.equal(items[2].labelRadius, 100);
  assert.equal(items[1].longitude, 11);
  assert.deepEqual(items[1].tick, polarPoint(11, 0, 200, 200, 100));
});

test('difference formatting preserves visible residual seconds', () => {
  assert.equal(formatDifference(0), '0.00″');
  assert.equal(formatDifference(1.49 / 3600), '+1.49″');
  assert.equal(formatDifference(-4.49 / 3600), '−4.49″');
});

test('DST fold selection becomes part of the exact request fingerprint and resets on edits', () => {
  const state = createRequestState();
  const base = { date: '2024-11-03', time: '01:30:00', timezone: 'America/New_York' };
  state.selectFold(1);
  const selected = state.withFold(base);
  assert.equal(selected.fold, 1);
  assert.equal(requestFingerprint(selected), requestFingerprint({ ...base, fold: 1 }));
  state.resetFold();
  assert.equal(state.withFold(base).fold, null);
});

test('dense labels spread without changing the actual planet longitudes', () => {
  const input = [154, 158, 162].map((longitude, index) => ({ id: String(index), longitude }));
  const labels = spreadLabelLongitudes(input, 12);
  assert.deepEqual(input.map(p => p.longitude), [154, 158, 162]);
  assert.deepEqual(labels.map(p => p.longitude), [154, 158, 162]);
  assert.deepEqual(labels.map(p => p.labelLongitude), [146, 158, 170]);
});

test('label collisions across zero and complete rings keep circular spacing', () => {
  for (const values of [[359, 0, 1], [0, 1, 2, 90, 91, 92, 180, 181, 182, 270, 271, 272], [8, 10, 11, 12, 13, 45, 120, 122, 124, 180, 250, 251, 253, 359]]) {
    const output = spreadLabelLongitudes(values.map((longitude, id) => ({id, longitude})), 12);
    for (let i = 0; i < output.length; i++) {
      for (let j = i + 1; j < output.length; j++) {
        assert.ok(angularDistance(output[i].labelLongitude, output[j].labelLongitude) >= 12 - 1e-8);
      }
    }
  }
});

test('wheel labels expose sign, degrees and verified motion markers', () => {
  assert.equal(motionMarker({ id: 'Jupiter', direction: 'S' }), 'S');
  assert.equal(motionMarker({ id: 'Chiron', direction: 'R' }), 'R');
  assert.equal(motionMarker({ id: 'Fortune', direction: 'not_applicable' }), '');
  assert.equal(formatWheelPosition({ sign_index: 3, longitude: 112.5275, direction: 'D' }), '♋︎ 22°31′');
  assert.equal(formatWheelPosition({ sign_index: 7, longitude: 211.9264, direction: 'S' }), '♏︎ 01°55′ S');
});

test('wheel metadata exposes the exact input, normalized time and calculation profile', () => {
  const lines = buildWheelMetadata({
    input: { date: '1985-07-14', time: '21:45:00', place: 'New York' },
    normalized: { utc: '1985-07-15T01:45:00Z', offset: '-04:00', latitude: 40.7128, longitude: -74.006 },
    settings: { zodiac: 'tropical', house_system: 'P', aspect_rule: 'major-v2' },
    sect: 'night', metadata: { engine: 'Swiss Ephemeris', engine_version: '2.10.03' },
  });
  assert.match(lines[0], /1985-07-14 21:45:00.*UTC 1985-07-15T01:45:00Z/);
  assert.match(lines.join(' '), /40\.712800.*−74\.006000.*night · major-v2/);
});
