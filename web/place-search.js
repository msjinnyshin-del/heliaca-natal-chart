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

export function mountPlaceSearch({onChange}) {
  const input = document.querySelector('#place');
  const list = document.querySelector('#place-results');
  const status = document.querySelector('#place-status');
  const warning = document.querySelector('#place-warning');
  const button = document.querySelector('#place-search-button');
  const manual = document.querySelector('#manual-location-toggle');
  const details = document.querySelector('#location-details');
  const fields = ['latitude', 'longitude', 'timezone'].map(id => document.getElementById(id));
  const state = createPlaceState();
  let timer, controller, serial = 0, results = [], active = -1;

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
  function clearCoordinates() { fields.forEach(field => { field.value = ''; }); }
  function updateWarning() {
    warning.textContent = state.warning(Number(fields[0].value), Number(fields[1].value), fields[2].value.trim());
    warning.hidden = !warning.textContent;
  }
  function choose(place) {
    cancel(); state.select(place);
    input.value = place.label; manual.checked = false;
    fields.forEach((field, index) => {
      field.value = [place.latitude, place.longitude, place.timezone][index]; field.readOnly = true;
    });
    details.open = true;
    status.textContent = `선택됨 · ${place.label} · ${place.timezone}. 도시 중심 좌표입니다. 정확한 출생지 좌표를 알고 있다면 직접 수정하세요.`;
    updateWarning(); onChange(); input.focus();
  }
  function highlight(index) {
    active = index;
    [...list.children].forEach((item, i) => item.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', `place-option-${active}`);
    list.children[active]?.scrollIntoView({block:'nearest'});
  }
  async function search() {
    cancel();
    if (manual.checked) { status.textContent = '직접 입력 모드를 해제하면 도시를 검색할 수 있습니다.'; return; }
    const query = input.value.trim();
    if (query.length < 2) { status.textContent = '도시 이름을 두 글자 이상 입력하세요.'; return; }
    const request = serial;
    controller = new AbortController();
    button.disabled = true; input.setAttribute('aria-busy', 'true');
    status.textContent = '도시를 검색하고 있습니다…';
    try {
      const response = await fetch(`/api/places?q=${encodeURIComponent(query)}`, {signal:controller.signal, headers:{Accept:'application/json'}});
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error?.message || '장소 검색을 사용할 수 없습니다.');
      if (request !== serial || input.value.trim() !== query || manual.checked) return;
      if (!Array.isArray(data.results)) throw new Error('장소 검색 응답이 올바르지 않습니다.');
      results = data.results; list.replaceChildren();
      for (const [index, place] of results.entries()) {
        const item = document.createElement('li');
        item.id = `place-option-${index}`; item.setAttribute('role','option'); item.setAttribute('aria-selected','false');
        const label = document.createElement('strong'); label.textContent = place.label;
        const info = document.createElement('small'); info.textContent = `${place.latitude}, ${place.longitude} · ${place.timezone}`;
        item.append(label, info);
        item.addEventListener('pointerdown', event => event.preventDefault());
        item.addEventListener('click', () => choose(place));
        list.append(item);
      }
      list.hidden = !results.length; input.setAttribute('aria-expanded', String(results.length > 0));
      status.textContent = results.length ? `${results.length}개 결과. 도시·지역·국가를 확인해 선택하세요.` : '일치하는 도시가 없습니다. 영문 도시명으로 검색하거나 좌표를 직접 입력하세요.';
      if (data.warnings?.length) status.textContent += ` ${data.warnings.join(' ')}`;
    } catch (error) {
      if (error.name !== 'AbortError' && request === serial) status.textContent = `${error.message} 다시 검색하거나 좌표 직접 입력을 이용하세요.`;
    } finally {
      if (request === serial) { button.disabled = false; input.removeAttribute('aria-busy'); }
    }
  }
  input.addEventListener('input', event => {
    cancel(); state.edit(input.value); if (!manual.checked) clearCoordinates(); updateWarning();
    status.textContent = manual.checked ? '장소명과 좌표·시간대를 직접 입력하세요.' : '검색 결과에서 출생 도시를 선택하세요.';
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
  button.addEventListener('click', search);
  manual.addEventListener('change', () => {
    cancel(); state.setManual(manual.checked);
    fields.forEach(field => { field.readOnly = !manual.checked; });
    if (!manual.checked) clearCoordinates(); else details.open = true;
    status.textContent = manual.checked ? '직접 입력 모드 · 위도·경도와 IANA 시간대를 모두 확인하세요.' : '검색 결과에서 출생 도시를 다시 선택하세요.';
    updateWarning(); onChange();
  });
  fields.forEach(field => field.addEventListener('input', updateWarning));
  return {
    validate() {
      if (!state.canCalculate(input.value)) { input.focus(); status.textContent = '검색 결과에서 도시를 선택하거나 좌표 직접 입력을 켜 주세요.'; return false; }
      if (fields.some(field => !field.value.trim())) { details.open = true; status.textContent = '위도·경도와 시간대를 모두 입력하세요.'; return false; }
      return true;
    },
    source: () => {
      const source = state.source();
      return {...source, label: source.label || input.value.trim()};
    },
  };
}
