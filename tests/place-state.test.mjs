import test from 'node:test';
import assert from 'node:assert/strict';

// A stale city selection must never authorize coordinates for a new query.
test('editing the selected city invalidates geographic selection', async () => {
  const module = await import('../web/place-search.js');
  assert.equal(typeof module.createPlaceState, 'function');
  const state = module.createPlaceState();
  state.select({id:1835848,label:'서울, 대한민국',latitude:37.566,longitude:126.978,timezone:'Asia/Seoul'});
  assert.equal(state.canCalculate('서울, 대한민국'), true);
  state.edit('부산');
  assert.equal(state.canCalculate('부산'), false);
  assert.equal(state.source().place_id, null);
});

test('manual coordinates are explicit, with five arcminute displacement warnings', async () => {
  const {createPlaceState} = await import('../web/place-search.js');
  const state = createPlaceState();
  state.select({id:1,label:'Seoul',latitude:37.5,longitude:127,timezone:'Asia/Seoul'});
  state.setManual(true);
  assert.equal(state.canCalculate('Seoul'), true);
  assert.equal(state.source().mode, 'manual');
  assert.equal(state.warning(37.51,127,'Asia/Seoul'), '');
  assert.match(state.warning(37.6,127,'Asia/Seoul'), /5′/);
  assert.match(state.warning(37.5,127,'America/New_York'), /시간대/);
  state.setManual(false);
  assert.equal(state.canCalculate('Seoul'), false);
});

test('invalid provider coordinates cannot become a selected location', async () => {
  const {createPlaceState} = await import('../web/place-search.js');
  const state = createPlaceState();
  assert.throws(() => state.select({id:1,label:'x',latitude:NaN,longitude:127,timezone:'Asia/Seoul'}));
  assert.throws(() => state.select({id:1,label:'x',latitude:37,longitude:181,timezone:'Asia/Seoul'}));
  assert.equal(state.canCalculate('x'), false);
});
