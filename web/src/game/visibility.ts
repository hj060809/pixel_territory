// 시인성 강조 (내 것·남의 것 구분): 나라색 바닥 고리 + 밝은 테두리. 그리는 쪽(draw.ts)이 visOn()을 본다.
// 사람마다 따로 (화면에만 영향, 서버와 상관없다). 기본값은 켜기.
//   싱글: 설정 화면에서 고른 값 = 다음 판에도 쓰는 기본값 (localStorage). 게임 중 메뉴에서 바꿔도 기본값이 같이 바뀐다.
//   멀티: 방 설정(setup.vis, 방장이 정함)으로 시작하고, 게임 중 메뉴에서 각자 바꾼다 (그 판에만, 새로고침해도 유지: sessionStorage).

const PREF = 'pt.vis', GAME = 'pt.vis.game';

function read(store: Storage, key: string): boolean | null {
  try { const v = store.getItem(key); return v === null ? null : v === '1'; } catch { return null; }
}
function write(store: Storage, key: string, on: boolean) {
  try { store.setItem(key, on ? '1' : '0'); } catch { /* 저장 못 해도 이번 화면에선 쓴다 */ }
}

let on = read(sessionStorage, GAME) ?? read(localStorage, PREF) ?? true;

let clean = false;

/** 지금 그리기에 쓰는 값 (예쁜 스크린샷을 찍는 동안은 꺼진다). */
export const visOn = () => on && !clean;

/** 예쁜 스크린샷 (view.ts): 찍는 한 장면 동안 고리·테두리를 끈다. */
export function setCleanShot(v: boolean) { clean = v; }

/** 싱글 기본값 (설정 화면). */
export const visPref = () => read(localStorage, PREF) ?? true;
export function setVisPref(v: boolean) { write(localStorage, PREF, v); }

/** 판을 시작할 때: 그 판의 값으로 정한다. */
export function startVis(v: boolean) { on = v; write(sessionStorage, GAME, v); }

/** 게임 중 메뉴에서 켜고 끄기. solo면 싱글 기본값도 같이. */
export function toggleVis(solo: boolean) {
  on = !on;
  write(sessionStorage, GAME, on);
  if (solo) setVisPref(on);
}
