// 조작 설명 창 (메뉴 '설명', F1): 마우스는 누르는 버튼을 칠한 마우스 그림, 키보드는 키캡 모양으로.
// 마우스·키보드가 아닌 것(외교, 길들이기, 패배)은 아래에 짧게. 터치 화면은 ☰ 메뉴의 손가락 설명을 쓴다 (touchUi).

import { el, panel } from './gameMenu.ts';

type MousePart = 'left' | 'right' | 'wheel';

/** 마우스 그림 (누르는 곳을 금색으로). */
function mouse(part: MousePart): string {
  const on = 'rgb(255,214,120)', line = 'rgb(220,214,196)';
  const fill = (p: MousePart) => (p === part ? on : 'none');
  return `<svg class="help-mouse" width="27" height="36" viewBox="0 0 24 32" aria-hidden="true">
    <path d="M12 1C5 1 2 5 2 11v10c0 6 4 10 10 10s10-4 10-10V11C22 5 19 1 12 1z" fill="rgb(46,52,64)" stroke="${line}" stroke-width="1.5"/>
    <path d="M12 1.8C6.2 1.8 2.8 5.6 2.8 11v2H12z" fill="${fill('left')}"/>
    <path d="M12 1.8c5.8 0 9.2 3.8 9.2 9.2v2H12z" fill="${fill('right')}"/>
    <path d="M2 13h20M12 1v12" stroke="${line}" stroke-width="1.2"/>
    <rect x="9.8" y="4.5" width="4.4" height="6.5" rx="2.2" fill="${part === 'wheel' ? on : 'rgb(70,76,90)'}" stroke="${line}" stroke-width="1"/>
  </svg>`;
}

const kbd = (k: string) => `<span class="kbd">${k}</span>`;
const plus = '<span class="help-plus">+</span>';
const or = '<span class="help-plus">/</span>';

/** 줄: 왼쪽 그림(HTML), 오른쪽 설명. */
function row(parent: HTMLElement, keys: string, text: string) {
  const r = el('div', 'help-row', parent);
  el('div', 'help-keys', r).innerHTML = keys;
  el('div', 'help-text', r, text);
}

/** solo: 사람이 1명인 판 (일시정지·속도·새 판 키도 보인다). */
export function helpBox(solo: boolean) {
  const { box, close } = panel('help-panel');
  el('div', 't-menu-title', box, '조작 설명');
  const cols = el('div', 'help-cols', box);
  const left = el('div', 'help-col mouse', cols), right = el('div', 'help-col', cols);

  el('div', 'help-head', left, '마우스');
  row(left, mouse('left'), '병사·건물 고르기 (Shift를 누르고 클릭: 더 고르기)');
  row(left, `${mouse('left')}<span class="help-drag">끌기</span>`, '네모로 여러 병사를 한꺼번에 고르기');
  row(left, mouse('right'), '이동 · 공격 · 자원지에 짓기 · 길들이기 (바다 건너는 배로)');
  row(left, mouse('wheel'), '굴리기: 확대 · 축소');
  row(left, `${mouse('wheel')}<span class="help-drag">끌기</span>`, '휠을 누른 채 끌기: 화면 옮기기');

  el('div', 'help-head', left, '그 밖에');
  const other = el('div', 'help-other', left);
  for (const [k, v] of [
    ['외교', '다른 나라의 거점을 누르면 동맹 요청 · 자원·병력 지원 · 공격 요청'],
    ['길들이기', '야생 말 → 기병, 바위거북 → 함께 싸우는 탱커, 드래곤은 쓰러뜨린 뒤 → 용기사'],
    ['패배', `거점과 병사를 모두 잃으면 진다. 오른쪽 위 메뉴에서 ${solo ? '나가기' : '항복 · 나가기'}`],
  ]) {
    const line = el('div', 't-help', other);
    el('b', '', line, k);
    line.append(` ${v}`);
  }

  el('div', 'help-head', right, '키보드');
  row(right, kbd('A'), '공격 이동 (가다가 만나는 적과 싸운다)');
  row(right, kbd('S'), '멈춤');
  row(right, `${kbd('1')}<span class="help-plus">~</span>${kbd('9')}`, '건물 짓기 (고른 병사가, 없으면 가까운 쉬는 병사가)');
  row(right, `${kbd('Q')}${kbd('W')}${kbd('E')}`, '보병 · 궁수 · 전함 만들기');
  row(right, `${kbd('Ctrl')}${plus}${kbd('1~9')}`, '고른 병사를 부대로 지정');
  row(right, `${kbd('Shift')}${plus}${kbd('1~9')}`, '그 부대를 부르기');
  row(right, kbd('Space'), '내 거점으로 화면 옮기기');
  row(right, `${kbd('←')}${kbd('↑')}${kbd('↓')}${kbd('→')}`, '화면 옮기기 (마우스를 화면 끝에 대도 된다)');
  row(right, kbd('Esc'), '취소 · 고른 것 풀기');
  if (solo) {
    row(right, `${kbd('P')}${or}${kbd('.')}`, '일시정지 · 속도');
    row(right, `${kbd('F5')}${or}${kbd('F6')}`, '같은 지도로 새 판 · 새 지도');
  }
  row(right, `${kbd('F1')}${or}${kbd('F12')}`, '이 설명 · 화면 저장');

  const foot = el('div', 't-menu-row help-foot', box);
  el('button', 't-btn wide', foot, '닫기').addEventListener('click', close);
}
