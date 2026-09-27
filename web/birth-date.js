// Birth date typed as digits (19720827) or with separators (1972.8.27); stored as YYYY-MM-DD.
// A plain text field instead of <input type="date">: no calendar scrolling back decades, and lunar
// months may have a 30th day that a Gregorian picker rejects.
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

/** Progressive mask for typing: digits become YYYY-MM-DD; a separated date is zero-padded. */
export function formatDateTyping(raw) {
  const text = String(raw ?? '').trim();
  const parts = text.split(/[.\-/\s년월일]+/).filter(Boolean);
  // Typing with separators ("1972.8.") is left alone until the day starts, so "8" is not glued to the day.
  if (parts.length < 3 && /[.\-/\s년월일]$/.test(text) && parts.length > 1) return text;
  if (parts.length === 3 && parts.every((part) => /^\d+$/.test(part)) && parts[0].length === 4) {
    return `${parts[0]}-${parts[1].padStart(2, '0').slice(-2)}-${parts[2].padStart(2, '0').slice(-2)}`;
  }
  const digits = text.replace(/\D/g, '').slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

/** { ok, message, year, month, day } — Gregorian dates must exist; lunar days run 1–30 (the server checks the month). */
export function checkBirthDate(value, calendar = 'gregorian') {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? '').trim());
  if (!match) return { ok: false, message: '생년월일 8자리를 입력하세요. 예: 19900515' };
  const [year, month, day] = match.slice(1).map(Number);
  const lunar = calendar === 'lunar';
  if (year < 1900 || year > (lunar ? 2050 : 2100)) return { ok: false, message: lunar ? '음력은 1900–2050년만 변환할 수 있습니다.' : '1900년 이후 날짜를 입력하세요.' };
  if (month < 1 || month > 12) return { ok: false, message: '월은 1–12 사이여야 합니다.' };
  if (lunar) {
    if (day < 1 || day > 30) return { ok: false, message: '음력 날짜는 1–30일입니다.' };
    return { ok: true, year, month, day };
  }
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return { ok: false, message: `${year}년 ${month}월에는 ${day}일이 없습니다.` };
  return { ok: true, year, month, day, weekday: WEEKDAYS[date.getUTCDay()] };
}

export function describeBirthDate(check, calendar = 'gregorian', leap = false) {
  if (!check.ok) return check.message;
  if (calendar === 'lunar') return `음력 ${check.year}년 ${check.month}월 ${check.day}일${leap ? ' (윤달)' : ''} · 계산 시 양력으로 변환`;
  return `${check.year}년 ${check.month}월 ${check.day}일 ${check.weekday}요일`;
}

/**
 * input: the text field; calendar(): 'gregorian' | 'lunar'; leap(): boolean; hint: element for the readable echo.
 * Returns { refresh() } to re-validate after the calendar changes.
 */
export function mountBirthDate({ input, calendar, leap = () => false, hint }) {
  input.type = 'text';
  input.inputMode = 'numeric';
  input.autocomplete = 'bday';
  // No maxlength: a pasted "1972. 8. 27." must not be cut to "1972. 8. 2" (a valid, wrong date).
  input.removeAttribute('maxlength');
  if (!input.placeholder) input.placeholder = '19900515';

  function refresh({ quiet = false } = {}) {
    const value = input.value.trim();
    const check = checkBirthDate(value, calendar());
    input.setCustomValidity(value && !check.ok ? check.message : '');
    if (!hint) return check;
    hint.textContent = value ? describeBirthDate(check, calendar(), leap()) : '';
    hint.classList.toggle('is-invalid', Boolean(value) && !check.ok && !quiet);
    return check;
  }

  input.addEventListener('input', (event) => {
    // Deleting keeps the text as typed so the dash can be removed; typing or pasting reformats.
    // Editing in the middle (e.g. retyping the month) is left as typed so the caret does not jump;
    // it is normalised on blur.
    const atEnd = input.selectionStart === input.value.length;
    if (!event.inputType?.startsWith('delete') && atEnd) {
      const formatted = formatDateTyping(input.value);
      if (formatted !== input.value) input.value = formatted;
    }
    // Partial input is not an error yet; the echo turns red only once 8 digits are in.
    refresh({ quiet: input.value.replace(/\D/g, '').length < 8 });
  });
  input.addEventListener('blur', () => {
    const formatted = formatDateTyping(input.value);
    if (formatted !== input.value) input.value = formatted;
    refresh();
  });
  return { refresh };
}
