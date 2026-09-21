import test from 'node:test';
import assert from 'node:assert/strict';

import { createOrbitField, orbitPoint, seededRandom } from '../web/cosmos.js';

test('seeded orbit field is deterministic and bounded', () => {
  assert.deepEqual(createOrbitField(42, 3), createOrbitField(42, 3));
  const field = createOrbitField(42, 12);
  assert.equal(field.length, 12);
  for (const orbit of field) {
    assert.ok(orbit.radiusX >= 0.24 && orbit.radiusX <= 0.66);
    assert.ok(orbit.radiusY >= 0.10 && orbit.radiusY <= 0.34);
    assert.ok(orbit.alpha >= 0.08 && orbit.alpha <= 0.34);
  }
});

test('orbit points preserve their ellipse before rotation', () => {
  const point = orbitPoint({ centerX: 100, centerY: 80, radiusX: 40, radiusY: 20, rotation: 0 }, 0);
  assert.deepEqual(point, { x: 140, y: 80 });
  const top = orbitPoint({ centerX: 100, centerY: 80, radiusX: 40, radiusY: 20, rotation: 0 }, Math.PI / 2);
  assert.ok(Math.abs(top.x - 100) < 1e-10);
  assert.ok(Math.abs(top.y - 100) < 1e-10);
});

test('seeded random produces a stable sequence in [0, 1)', () => {
  const first = seededRandom(9);
  const second = seededRandom(9);
  for (let index = 0; index < 20; index += 1) {
    const value = first();
    assert.equal(value, second());
    assert.ok(value >= 0 && value < 1);
  }
});
