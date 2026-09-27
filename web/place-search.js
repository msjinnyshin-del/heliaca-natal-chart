/** City selection is explicit; changing text never silently reuses old coordinates. */
export function createPlaceState() {
  let selected = null;
  let reference = null;
  let manual = false;
  return {
    select(place) {
      if (!place || !Number.isInteger(place.id) || !place.label || !place.timezone
          || !Number.isFinite(place.latitude) || Math.abs(place.latitude) > 90
          || !Number.isFinite(place.longitude) || Math.abs(place.longitude) > 180) {
        throw new TypeError('유효하지 않은 장소 검색 결과입니다.');
      }
      selected = {...place}; reference = {...place}; manual = false;
    },
    edit(query) {
      if (selected && query.trim() !== selected.label) { selected = null; reference = null; }
    },
    setManual(value) { manual = Boolean(value); if (!manual) { selected = null; reference = null; } },
    canCalculate(query) { return Boolean(query.trim() && (manual || selected?.label === query.trim())); },
    source() {
      return {mode: manual ? 'manual' : 'geocoded', provider: manual ? 'user' : 'Open-Meteo / GeoNames',
        place_id: reference?.id ?? null, label: reference?.label ?? '',
        reference_latitude: reference?.latitude ?? null, reference_longitude: reference?.longitude ?? null,
        reference_timezone: reference?.timezone ?? null};
    },
    warning(latitude, longitude, timezone) {
      if (!manual || !reference) return '';
      if (timezone !== reference.timezone) return '검색 결과와 다른 시간대입니다. 출생 당시 해당 지역의 IANA 시간대인지 확인하세요.';
      const lonDistance = Math.abs((longitude - reference.longitude + 540) % 360 - 180);
      if (Math.abs(latitude - reference.latitude) >= 5 / 60 || lonDistance >= 5 / 60) {
        return '수동 좌표가 검색된 도시 중심에서 위도 또는 경도 기준 5′ 이상 다릅니다. 정확한 출생지 좌표인지 확인하세요.';
      }
      return '';
    },
  };
}

export function mountPlaceSearch({onChange, prefix = '', recents = () => []}) {
  const byId = id => document.getElementById(prefix + id);
  const input = byId('place');
  const list = byId('place-results');
  const status = byId('place-status');
  const warning = byId('place-warning');
  const button = byId('place-search-button');
  const manual = byId('manual-location-toggle');
  const details = byId('location-details');
  const fields = ['latitude', 'longitude', 'timezone'].map(id => byId(id));
  const state = createPlaceState();
  let timer, controller, serial = 0, results = [], active = -1;
  const field = input.closest('.band-place, .place-field');
  function setStatus(text, selectedState = false) {
    status.textContent = text;
    status.classList.toggle('is-selected', selectedState);
    field?.classList.toggle('has-place', selectedState);
  }

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }
  function cancel() {
    clearTimeout(timer); controller?.abort(); serial += 1;
    button.disabled = false; input.removeAttribute('aria-busy'); close();
  }
  // The coordinate panel may sit inside a collapsed "정밀 설정" panel; open every enclosing <details>.
  function openDetails() {
    for (let node = details; node; node = node.parentElement?.closest('details')) node.open = true;
  }
  function clearCoordinates() { fields.forEach(field => { field.value = ''; }); }
  function updateWarning() {
    warning.textContent = state.warning(Number(fields[0].value), Number(fields[1].value), fields[2].value.trim());
    warning.hidden = !warning.textContent;
  }
  function choose(place, {focus = true, notify = true} = {}) {
    cancel(); state.select(place);
    input.value = place.label; manual.checked = false;
    fields.forEach((field, index) => {
      field.value = [place.latitude, place.longitude, place.timezone][index]; field.readOnly = true;
    });
    setStatus(`✓ ${place.label} · ${place.timezone} (도시 중심 좌표)`, true);
    updateWarning(); if (notify) onChange(); if (focus) input.focus();
  }
  function renderOptions(places, note = '', preselect = true) {
    results = places; list.replaceChildren();
    for (const [index, place] of results.entries()) {
      const item = document.createElement('li');
      item.id = `${prefix}place-option-${index}`; item.setAttribute('role','option'); item.setAttribute('aria-selected','false');
      const label = document.createElement('strong'); label.textContent = place.label;
      const info = document.createElement('small');
      info.textContent = `${note ? `${note} · ` : ''}${place.timezone} · ${Number(place.latitude).toFixed(2)}, ${Number(place.longitude).toFixed(2)}`;
      item.append(label, info);
      item.addEventListener('pointerdown', event => event.preventDefault());
      item.addEventListener('click', () => choose(place));
      list.append(item);
    }
    list.hidden = !results.length; input.setAttribute('aria-expanded', String(results.length > 0));
    // The first match is pre-highlighted so Enter picks it; picking is still an explicit action.
    if (results.length && preselect) highlight(0);
  }
  function showRecents() {
    if (manual.checked || input.value.trim() || !list.hidden) return;
    const places = recents().filter(place => { try { createPlaceState().select(place); return true; } catch { return false; } });
    // Not pre-highlighted: Enter on an empty field must not pick a city the user never chose.
    if (places.length) { renderOptions(places, '최근 사용', false); setStatus('최근 사용한 출생지에서 고르거나 도시 이름을 입력하세요.'); }
  }
  function highlight(index) {
    active = index;
    [...list.children].forEach((item, i) => item.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', `${prefix}place-option-${active}`);
    list.children[active]?.scrollIntoView({block:'nearest'});
  }
  async function search() {
    cancel();
    if (manual.checked) { setStatus('직접 입력 모드를 해제하면 도시를 검색할 수 있습니다.'); return; }
    const query = input.value.trim();
    if (query.length < 2) { setStatus('도시 이름을 두 글자 이상 입력하세요.'); return; }
    const request = serial;
    controller = new AbortController();
    button.disabled = true; input.setAttribute('aria-busy', 'true');
    setStatus('도시를 검색하고 있습니다…');
    try {
      const response = await fetch(`/api/places?q=${encodeURIComponent(query)}`, {signal:controller.signal, headers:{Accept:'application/json'}});
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error?.message || '장소 검색을 사용할 수 없습니다.');
      if (request !== serial || input.value.trim() !== query || manual.checked) return;
      if (!Array.isArray(data.results)) throw new Error('장소 검색 응답이 올바르지 않습니다.');
      renderOptions(data.results);
      setStatus(results.length ? `${results.length}개 결과 · 목록에서 출생 도시를 누르세요 (Enter = 첫 번째)` : '일치하는 도시가 없습니다. 영문 도시명(예: Gainesville)으로 검색하거나 정밀 설정에서 좌표를 직접 입력하세요.');
      if (data.warnings?.length) status.textContent += ` ${data.warnings.join(' ')}`;
    } catch (error) {
      if (error.name !== 'AbortError' && request === serial) setStatus(`${error.message} 다시 검색하거나 좌표 직접 입력을 이용하세요.`);
    } finally {
      if (request === serial) { button.disabled = false; input.removeAttribute('aria-busy'); }
    }
  }
  input.addEventListener('input', event => {
    cancel(); results = []; state.edit(input.value); if (!manual.checked) clearCoordinates(); updateWarning();
    setStatus(manual.checked ? '장소명과 좌표·시간대를 직접 입력하세요.' : '입력하면 자동으로 검색합니다 · 목록에서 도시를 선택하세요.');
    if (!input.value.trim()) showRecents();
    if (!manual.checked && !event.isComposing && input.value.trim().length >= 2) timer = setTimeout(search, 450);
  });
  input.addEventListener('compositionend', () => {
    if (!manual.checked && input.value.trim().length >= 2) { clearTimeout(timer); timer = setTimeout(search,450); }
  });
  input.addEventListener('keydown', event => {
    if (event.isComposing) return;
    if (event.key === 'Escape') { cancel(); return; }
    if (event.key === 'Enter' && !manual.checked) {
      event.preventDefault();
      if (!list.hidden && active >= 0) choose(results[active]); else search();
    }
    if (!list.hidden && ['ArrowDown','ArrowUp'].includes(event.key)) {
      event.preventDefault(); highlight((active + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length);
    }
  });
  input.addEventListener('blur', close);
  input.addEventListener('focus', () => {
    if (results.length && list.hidden && !state.canCalculate(input.value) && input.value.trim()) {
      list.hidden = false; input.setAttribute('aria-expanded', 'true'); highlight(0);
    } else showRecents();
  });
  button.addEventListener('click', search);
  manual.addEventListener('change', () => {
    cancel(); state.setManual(manual.checked);
    fields.forEach(field => { field.readOnly = !manual.checked; });
    if (!manual.checked) clearCoordinates(); else openDetails();
    setStatus(manual.checked ? '직접 입력 모드 · 위도·경도와 IANA 시간대를 모두 확인하세요.' : '검색 결과에서 출생 도시를 다시 선택하세요.');
    updateWarning(); onChange();
  });
  fields.forEach(field => field.addEventListener('input', updateWarning));
  return {
    validate() {
      if (!state.canCalculate(input.value)) {
        input.focus();
        setStatus(input.value.trim() && results.length ? '아직 도시를 고르지 않았습니다 · 아래 목록에서 출생 도시를 누르세요.' : '출생지를 입력하고 목록에서 도시를 선택하세요.');
        return false;
      }
      if (fields.some(field => !field.value.trim())) { openDetails(); setStatus('위도·경도와 시간대를 모두 입력하세요.'); return false; }
      return true;
    },
    source: () => {
      const source = state.source();
      return {...source, label: source.label || input.value.trim()};
    },
    /** Current place as a storable snapshot, or null when nothing valid is chosen. */
    snapshot() {
      if (!state.canCalculate(input.value) || fields.some(field => !field.value.trim())) return null;
      return {label: input.value.trim(), latitude: Number(fields[0].value), longitude: Number(fields[1].value),
        timezone: fields[2].value.trim(), source: this.source()};
    },
    /** Re-applies a snapshot: a geocoded city is re-selected; manual coordinates come back in manual mode. */
    restore(saved) {
      const source = saved?.source || {};
      const reference = Number.isInteger(source.place_id) ? {id: source.place_id, label: source.label || saved.label,
        latitude: source.reference_latitude, longitude: source.reference_longitude, timezone: source.reference_timezone} : null;
      if (source.mode !== 'manual' && reference) {
        try { choose(reference, {focus: false, notify: false}); return; } catch { /* unusable reference: fall back to the saved coordinates */ }
      }
      cancel();
      state.setManual(false);  // drop any city selected before, so it cannot become this profile's reference
      if (reference) { try { state.select(reference); } catch { /* manual values below still apply */ } }
      state.setManual(true); manual.checked = true;
      input.value = saved.label;
      fields.forEach((field, index) => { field.readOnly = false; field.value = [saved.latitude, saved.longitude, saved.timezone][index]; });
      openDetails();
      setStatus(`✓ ${saved.label} · 직접 입력한 좌표 ${saved.latitude}, ${saved.longitude} · ${saved.timezone}`, true);
      updateWarning();
    },
  };
}
