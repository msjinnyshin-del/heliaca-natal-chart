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
import { aspectTimingLabel, buildWheelMetadata, formatWheelPosition, isUnknownTime, motionMarker, sensitivityNote, wheelAspects } from '../web/chart-profile.js';

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

const UNKNOWN_RESULT = {
  input: { date: '1990-05-01', place: '서울', time_accuracy: 'unknown' },
  normalized: { time_accuracy: 'unknown', representative_local_time: '12:00:00', utc: '1990-05-01T03:00:00Z', offset: '+09:00',
    latitude: 37.5665, longitude: 126.978, timezone: 'Asia/Seoul' },
  settings: { zodiac: 'tropical', house_system: 'P', aspect_rule: 'major-v2' },
  sect: null, metadata: { engine: 'Swiss Ephemeris', engine_version: '2.10.03' },
  aspects: [
    { a: 'Sun', b: 'Mercury', name: 'Conjunction', stability: 'stable',
      windows: [{ start_local: '1990-05-01T00:00:00', end_local: '1990-05-02T00:00:00' }] },
    { a: 'Sun', b: 'Moon', name: 'Square', stability: 'partial',
      windows: [{ start_local: '1990-05-01T13:42:10', end_local: '1990-05-02T00:00:00' }] },
    { a: 'Moon', b: 'Venus', name: 'Trine', stability: 'partial',
      windows: [{ start_local: '1990-05-01T00:00:00', end_local: '1990-05-01T03:05:00' },
                { start_local: '1990-05-01T20:00:00', end_local: '1990-05-01T21:30:59' }] },
  ],
};

test('unknown birth time is labelled on the wheel and never shows houses or sect as values', () => {
  assert.equal(isUnknownTime(UNKNOWN_RESULT), true);
  assert.equal(isUnknownTime({ normalized: { time_accuracy: 'reported' } }), false);
  const lines = buildWheelMetadata(UNKNOWN_RESULT);
  assert.match(lines[0], /1990-05-01 생시 미상 \(정오 12:00 대표\)/);
  assert.doesNotMatch(lines.join(' '), /Placidus|undefined/);
  assert.match(lines[2], /하우스·ASC 없음/);
});

test('only aspects that hold all day are drawn on an unknown-time wheel', () => {
  assert.deepEqual(wheelAspects(UNKNOWN_RESULT).map((a) => a.name), ['Conjunction']);
  const reported = { normalized: { time_accuracy: 'reported' }, aspects: [{ name: 'Trine' }, { name: 'Square' }] };
  assert.equal(wheelAspects(reported).length, 2);
});

test('time-dependent aspects show their local windows', () => {
  assert.equal(aspectTimingLabel(UNKNOWN_RESULT.aspects[0]), '하루 종일 유지');
  assert.equal(aspectTimingLabel(UNKNOWN_RESULT.aspects[1]), '13:42–24:00에 태어난 경우만');
  assert.equal(aspectTimingLabel(UNKNOWN_RESULT.aspects[2]), '00:00–03:05, 20:00–21:30에 태어난 경우만');
  assert.equal(aspectTimingLabel({ name: 'Trine' }), '');
});

test('sign changes and stations during the day are spelled out', () => {
  assert.equal(sensitivityNote({ time_sensitivity: { sign_stable: true, direction_stable: true, ingresses: [], stations: [] } }), '');
  assert.equal(sensitivityNote({}), '');
  assert.equal(sensitivityNote({ time_sensitivity: { sign_stable: false, direction_stable: true, stations: [],
    ingresses: [{ local: '1990-05-01T09:08:21', from_sign_index: 3, to_sign_index: 4 }] } }), '09:08 게→사자');
  assert.equal(sensitivityNote({ time_sensitivity: { sign_stable: true, direction_stable: false, ingresses: [],
    stations: [{ local: '1990-05-17T14:20:05', to: 'D' }] } }), '14:20 순행 전환');
});

test('repeated local hours show which occurrence a time belongs to', () => {
  const aspect = { stability: 'partial', windows: [{ start_local: '2024-11-03T01:20:00', start_offset: '-05:00', end_local: '2024-11-04T00:00:00', end_offset: '-05:00' }] };
  assert.equal(aspectTimingLabel(aspect, { repeatedHour: true }), '01:20(UTC-05:00)–24:00에 태어난 경우만');
  assert.equal(aspectTimingLabel(aspect), '01:20–24:00에 태어난 경우만');
});

test('24:00 is used only for an end on the next date', () => {
  const sameDate = { stability: 'partial', windows: [{ start_local: '1990-10-07T20:00:00', start_offset: '+01:00', end_local: '1990-10-07T00:00:00', end_offset: '+00:00' }] };
  assert.equal(aspectTimingLabel(sameDate, { repeatedHour: true }), '20:00(UTC+01:00)–00:00(UTC+00:00)에 태어난 경우만');
  const afterGap = { stability: 'partial', windows: [{ start_local: '1919-03-30T20:00:00', end_local: '1919-03-31T00:30:00' }] };
  assert.equal(aspectTimingLabel(afterGap), '20:00–다음 날 00:30에 태어난 경우만');
});
