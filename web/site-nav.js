// Shared masthead navigation: grouped pills on desktop, a full-screen sheet on mobile.
// The current page is read from <body data-tool="...">; nothing here touches chart results.
const GROUPS = [
  { label: '나', items: [
    { id: 'natal', href: '/', name: '네이털 차트', note: '태어난 순간의 하늘' },
    { id: 'transits', href: '/transits.html', name: '트랜짓', note: '지금 하늘이 내 차트에 닿는 곳' },
  ] },
  { label: '관계', items: [
    { id: 'synastry', href: '/synastry.html', name: '시너스트리', note: '두 차트를 겹쳐 비교' },
    { id: 'composite', href: '/composite.html', name: '컴포지트', note: '두 사람의 중간점 차트' },
  ] },
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function mountSiteNav(current = document.body.dataset.tool) {
  const header = document.querySelector('.masthead');
  if (!header) return;
  const existing = header.querySelector('.mast-nav');
  const nav = el('nav', 'mast-nav');
  nav.setAttribute('aria-label', '도구');
  for (const [index, group] of GROUPS.entries()) {
    if (index) nav.append(el('span', 'mast-nav-divider'));
    const wrap = el('div', 'mast-nav-group');
    wrap.append(el('span', 'mast-nav-label', group.label));
    const pills = el('div', 'mast-nav-pills');
    for (const item of group.items) {
      const link = el('a', 'mast-pill', item.name);
      link.href = item.href;
      if (item.id === current) {
        link.classList.add('is-current');
        link.setAttribute('aria-current', 'page');
      }
      pills.append(link);
    }
    wrap.append(pills);
    nav.append(wrap);
  }

  const actions = el('div', 'mast-actions');
  const method = el('a', 'mast-link', '방법과 한계');
  method.href = current === 'natal' ? '#method' : '/#method';
  const cta = el('a', 'mast-cta', '내 차트 계산');
  cta.href = current === 'natal' ? '#chart-form' : '/#chart-form';
  actions.append(method, cta);

  const toggle = el('button', 'mast-burger');
  toggle.type = 'button';
  toggle.setAttribute('aria-label', '메뉴 열기');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.append(el('span'), el('span'), el('span'));

  // Mobile sheet mirrors the same links with a one-line description each.
  const sheet = el('div', 'nav-sheet');
  sheet.hidden = true;
  const sheetHead = el('div', 'nav-sheet-head');
  const close = el('button', 'nav-sheet-close', '✕');
  close.type = 'button';
  close.setAttribute('aria-label', '메뉴 닫기');
  const sheetBrand = document.createElement('img');
  sheetBrand.src = '/assets/heliaca-logo.svg';
  sheetBrand.alt = 'Heliaca';
  sheetBrand.className = 'nav-sheet-logo';
  sheetHead.append(sheetBrand, close);
  sheet.append(sheetHead);
  for (const group of GROUPS) {
    const section = el('section', 'nav-sheet-group');
    section.append(el('p', 'mast-nav-label', group.label));
    for (const item of group.items) {
      const link = el('a', 'nav-sheet-item');
      link.href = item.href;
      if (item.id === current) link.classList.add('is-current');
      const text = el('span', 'nav-sheet-text');
      text.append(el('strong', '', item.name), el('small', '', item.note));
      link.append(text, el('span', 'nav-sheet-mark', item.id === current ? '●' : '›'));
      section.append(link);
    }
    sheet.append(section);
  }
  const sheetFoot = el('div', 'nav-sheet-foot');
  const sheetMethod = el('a', '', '방법과 한계');
  sheetMethod.href = method.href;
  sheetFoot.append(sheetMethod);
  sheet.append(sheetFoot);

  function setOpen(open) {
    sheet.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
    document.body.classList.toggle('nav-open', open);
    if (open) close.focus();
  }
  toggle.addEventListener('click', () => setOpen(sheet.hidden));
  close.addEventListener('click', () => { setOpen(false); toggle.focus(); });
  sheet.addEventListener('click', (event) => { if (event.target.closest('a')) setOpen(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !sheet.hidden) { setOpen(false); toggle.focus(); } });

  if (existing) existing.replaceWith(nav);
  else header.append(nav);
  header.querySelector('.mast-meta')?.remove();
  header.append(actions, toggle);
  document.body.append(sheet);
}

mountSiteNav();
