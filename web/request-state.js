export function requestFingerprint(payload) {
  return JSON.stringify(payload);
}

export function createRequestState() {
  let fold = null;
  return {
    get fold() { return fold; },
    selectFold(value) {
      if (value !== 0 && value !== 1) throw new TypeError('fold must be 0 or 1');
      fold = value;
    },
    resetFold() { fold = null; },
    withFold(payload) { return { ...payload, fold }; },
  };
}
