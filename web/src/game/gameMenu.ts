// 게임 메뉴 창 (오른쪽 위 [메뉴] 버튼 · 확인 묻기 · 조작 설명): 화면 가운데 상자. 바깥을 누르거나 Esc면 닫힌다.
// 메뉴는 버튼을 세로로, 확인은 가로로. 모양은 터치 메뉴(touchUi의 .t-menu)와 같다. 한 번에 하나만 열린다.

export interface MenuItem { label: string; fn: () => void; warm?: boolean }

let open: { back: HTMLDivElement; close: () => void } | null = null;

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, parent: HTMLElement, text = '') {
  const e = document.createElement(tag);
  e.className = cls;
  if (text) e.textContent = text;
  parent.appendChild(e);
  return e;
}

/** 열려 있는 창을 닫는다 (있으면 true). */
export function closeMenu(): boolean {
  if (!open) return false;
  open.close();
  return true;
}

export const menuOpen = () => open !== null;

/** 빈 창 하나 (cls: 상자 클래스). 이미 열린 창은 닫는다. */
export function panel(cls: string): { box: HTMLDivElement; close: () => void } {
  closeMenu();
  const back = el('div', 't-menu-back', document.body);
  const box = el('div', 't-menu ' + cls, back);
  const close = () => { back.remove(); if (open?.back === back) open = null; };
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  open = { back, close };
  return { box, close };
}

/** 제목, (설명), 버튼들. 버튼을 누르면 창을 닫고 할 일을 한다. */
export function menuBox(title: string, items: MenuItem[], note = '', confirm = false) {
  const { box, close } = panel('game-menu' + (confirm ? ' confirm' : ''));
  el('div', 't-menu-title', box, title);
  if (note) el('div', 't-help', box, note);
  const row = el('div', 't-menu-row', box);
  for (const it of items) {
    const b = el('button', 't-btn wide' + (it.warm ? ' warm' : ''), row, it.label);
    b.addEventListener('click', () => { close(); it.fn(); });
  }
}

/** 되돌릴 수 없는 일 확인: [yes] [취소]. */
export function confirmBox(title: string, text: string, yes: string, fn: () => void) {
  menuBox(title, [{ label: yes, fn, warm: true }, { label: '취소', fn: () => {} }], text, true);
}
