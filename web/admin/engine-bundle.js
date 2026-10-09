// Pure helpers for the engine inspector's all-charts report (years list, per-year dates). No DOM.

export const MAX_BUNDLE_YEARS = 20;

/** "2026-2028, 2030" → [2026, 2027, 2028, 2030]; returns { error } on anything else. */
export function parseYears(text) {
  const years = new Set();
  for (const part of String(text).split(/[,\s]+/).filter(Boolean)) {
    const match = /^(\d{4})(?:[-~](\d{4}))?$/.exec(part);
    if (!match) return { error: `연도 "${part}"를 읽을 수 없습니다. 예: 2026-2028 또는 2026, 2030` };
    const [from, to] = [Number(match[1]), Number(match[2] ?? match[1])];
    if (to < from) return { error: `연도 범위 "${part}"의 끝이 시작보다 앞입니다.` };
    if (from < 1901 || to > 2100) return { error: '연도는 1901–2100 사이여야 합니다.' };
    if (to - from >= MAX_BUNDLE_YEARS) return { error: `한 번에 최대 ${MAX_BUNDLE_YEARS}개 연도까지 계산합니다.` };
    for (let y = from; y <= to; y += 1) years.add(y);
  }
  if (!years.size) return { error: '볼 연도를 입력하세요.' };
  if (years.size > MAX_BUNDLE_YEARS) return { error: `한 번에 최대 ${MAX_BUNDLE_YEARS}개 연도까지 계산합니다.` };
  return { years: [...years].sort((x, y) => x - y) };
}

/** Month-day moved into `year`; Feb 29 becomes Feb 28 in a common year. */
export function dayInYear(year, monthDay) {
  const [month, day] = monthDay.split('-').map(Number);
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const safeDay = month === 2 && day === 29 && !leap ? 28 : day;
  return `${year}-${String(month).padStart(2, '0')}-${String(safeDay).padStart(2, '0')}`;
}

