// 조작 설명 창 (메뉴 '설명', F1): 마우스는 누르는 버튼을 칠한 마우스 그림, 키보드는 키캡 모양으로.
// 마우스·키보드가 아닌 것(외교, 길들이기, 패배)은 아래에 짧게.
// 터치 화면 (☰ 메뉴 '조작 설명'): 손가락 동작은 그림으로, 화면 버튼은 실제 버튼 모양으로 (touchHelpBox).
// 로비의 '게임 방법' 창도 같은 그림을 쓴다 (fillHelp / fillTouchHelp, lobby: 싱글 전용 키는 '(싱글)'로 표시, '그 밖에'는 줄글에 있어 뺀다).

import { el, panel } from './gameMenu.ts';

type MousePart = 'left' | 'right' | 'wheel';

/** 마우스 그림 (누르는 곳을 금색으로). */
export function mouse(part: MousePart): string {
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

export const kbd = (k: string) => `<span class="kbd">${k}</span>`;
const plus = '<span class="help-plus">+</span>';
const or = '<span class="help-plus">/</span>';

/** 줄: 왼쪽 그림(HTML), 오른쪽 설명. */
function row(parent: HTMLElement, keys: string, text: string) {
  const r = el('div', 'help-row', parent);
  el('div', 'help-keys', r).innerHTML = keys;
  el('div', 'help-text', r, text);
}

/** 그 밖에 (마우스·키보드·손가락이 아닌 것): 한 줄씩 짧게. */
function others(parent: HTMLElement, solo: boolean, press: string) {
  el('div', 'help-head', parent, '그 밖에');
  const other = el('div', 'help-other', parent);
  for (const [k, v] of [
    ['외교', `다른 나라의 거점을 ${press} 동맹 요청 · 자원·병력 지원 · 공격 요청`],
    ['길들이기', '야생 말 → 기병, 바위거북 → 함께 싸우는 탱커, 드래곤은 쓰러뜨린 뒤 → 용기사'],
    ['패배', `거점과 병사를 모두 잃으면 진다. 오른쪽 위 메뉴에서 ${solo ? '나가기' : '항복 · 나가기'}`],
  ]) {
    const line = el('div', 't-help', other);
    el('b', '', line, k);
    line.append(` ${v}`);
  }
}

/** solo: 사람이 1명인 판 (일시정지·속도·새 판 키도 보인다). */
export function helpBox(solo: boolean) {
  const { box, close } = panel('help-panel');
  el('div', 't-menu-title', box, '조작 설명');
  fillHelp(box, solo);
  const foot = el('div', 't-menu-row help-foot', box);
  el('button', 't-btn wide', foot, '닫기').addEventListener('click', close);
}

/** PC 조작 그림 (왼쪽 마우스·그 밖에, 오른쪽 키보드)을 parent에. lobby: 로비 '게임 방법' 창 (판 밖). */
export function fillHelp(parent: HTMLElement, solo: boolean, lobby = false) {
  const only = lobby ? ' (싱글)' : '';
  const cols = el('div', 'help-cols', parent);
  const left = el('div', 'help-col mouse', cols), right = el('div', 'help-col', cols);

  el('div', 'help-head', left, '마우스');
  row(left, mouse('left'), '병사·건물 고르기 (Shift를 누르고 클릭: 더 고르기)');
  row(left, `${mouse('left')}<span class="help-drag">끌기</span>`, '네모로 여러 병사를 한꺼번에 고르기');
  row(left, mouse('right'), '이동 · 공격 · 자원지에 짓기 · 길들이기 (바다 건너는 배로)');
  row(left, mouse('wheel'), '굴리기: 확대 · 축소');
  row(left, `${mouse('wheel')}<span class="help-drag">끌기</span>`, '휠을 누른 채 끌기: 화면 옮기기');

  if (!lobby) others(left, solo, '누르면');

  el('div', 'help-head', right, '키보드');
  row(right, kbd('A'), '공격 이동 (가다가 만나는 적과 싸운다)');
  row(right, kbd('S'), '멈춤');
  row(right, `${kbd('1')}<span class="help-plus">~</span>${kbd('9')}`, '건물 짓기: 1 거점 · 2 무역소 · 3~6 자원 건물 · 7 망루 · 8 화염탑 · 9 항구 (고른 병사가, 없으면 가까운 쉬는 병사가)');
  row(right, `${kbd('Q')}${kbd('W')}${kbd('E')}`, '보병 · 궁수 · 전함 만들기');
  row(right, `${kbd('Ctrl')}${plus}${kbd('1~9')}`, '고른 병사를 부대로 지정');
  row(right, `${kbd('Shift')}${plus}${kbd('1~9')}`, '그 부대를 부르기');
  row(right, kbd('Space'), '내 거점으로 화면 옮기기');
  row(right, `${kbd('←')}${kbd('↑')}${kbd('↓')}${kbd('→')}`, '화면 옮기기 (마우스를 화면 끝에 대도 된다)');
  row(right, kbd('Esc'), '취소 · 고른 것 풀기');
  if (solo) {
    row(right, `${kbd('P')}${or}${kbd('.')}`, '일시정지 · 속도' + only);
    row(right, `${kbd('F5')}${or}${kbd('F6')}`, '같은 지도로 새 판 · 새 지도' + only);
  }
  if (!solo || lobby) row(right, kbd('Enter'), '대화 입력 (멀티) · 💬 빠른 대화 · 안 쓰면 왼쪽 아래 💬로 접힌다');
  row(right, `${kbd('F1')}${or}${kbd('F12')}`, lobby ? '게임 중 조작 설명 · 화면 저장' : '이 설명 · 화면 저장');
}

// ------------------------------------------------------------- 터치

type Gesture = 'tap' | 'hold' | 'drag' | 'box' | 'pinch';

/** 손가락 동작 그림: 금색 점 = 손가락이 닿은 곳, 고리 = 탭/길게, 화살표 = 끌기. */
export function gesture(kind: Gesture): string {
  const on = 'rgb(255,214,120)', dim = 'rgba(255,214,120,0.45)', line = 'rgb(220,214,196)';
  const dot = (x: number, y: number) => `<circle cx="${x}" cy="${y}" r="4.5" fill="${on}" stroke="#000" stroke-width="1"/>`;
  const arrow = (x1: number, y1: number, x2: number, y2: number) => {
    const a = Math.atan2(y2 - y1, x2 - x1), h = 5;
    const p = (da: number) => `${x2 - h * Math.cos(a + da)},${y2 - h * Math.sin(a + da)}`;
    return `<path d="M${x1} ${y1}L${x2} ${y2}M${p(0.5)}L${x2} ${y2}L${p(-0.5)}" stroke="${line}" stroke-width="1.6" fill="none"/>`;
  };
  const body = {
    tap: `<circle cx="20" cy="16" r="9" fill="none" stroke="${dim}" stroke-width="1.5"/><circle cx="20" cy="16" r="13" fill="none" stroke="${dim}" stroke-width="1"/>${dot(20, 16)}`,
    hold: `<circle cx="20" cy="16" r="9" fill="none" stroke="${on}" stroke-width="2.5" stroke-dasharray="40 17"/>${dot(20, 16)}`,
    drag: `${arrow(14, 16, 36, 16)}<circle cx="9" cy="16" r="7.5" fill="none" stroke="${dim}" stroke-width="1.2"/>${dot(9, 16)}`,
    box: `<rect x="6" y="5" width="28" height="22" fill="rgba(255,214,120,0.12)" stroke="${line}" stroke-width="1.2" stroke-dasharray="3 2"/>${dot(34, 27)}`,
    pinch: `${arrow(16, 20, 5, 30)}${arrow(24, 12, 35, 2)}${dot(16, 20)}${dot(24, 12)}`,
  }[kind];
  return `<svg class="help-mouse" width="40" height="32" viewBox="0 0 40 32" aria-hidden="true">${body}</svg>`;
}

/** 화면 버튼 모양 (touchUi의 .t-btn을 작게). */
export const tbtn = (t: string, cls = '') => `<span class="tkey ${cls}">${t}</span>`;

export function touchHelpBox(solo: boolean) {
  const { box, close } = panel('help-panel');
  el('div', 't-menu-title', box, '조작 설명');
  fillTouchHelp(box, solo);
  const foot = el('div', 't-menu-row help-foot', box);
  el('button', 't-btn wide', foot, '닫기').addEventListener('click', close);
}

/** 터치 조작 그림 (왼쪽 손가락·그 밖에, 오른쪽 화면 버튼)을 parent에. lobby: 로비 '게임 방법' 창. */
export function fillTouchHelp(parent: HTMLElement, solo: boolean, lobby = false) {
  const cols = el('div', 'help-cols', parent);
  const left = el('div', 'help-col mouse', cols), right = el('div', 'help-col', cols);

  el('div', 'help-head', left, '손가락');
  row(left, gesture('tap'), '병사·건물·배 고르기 (멀리서 보면 무리 배지를 탭: 무리 전체)');
  row(left, gesture('tap'), '고른 뒤 땅: 이동 · 적: 공격 · 빈 자원지: 짓기 · 야생 동물: 길들이기 (바다 건너는 배로)');
  row(left, gesture('box'), '길게 누른 채 끌기: 네모로 여러 병사 고르기');
  row(left, gesture('drag'), '한 손가락으로 끌기: 화면 옮기기');
  row(left, gesture('pinch'), '두 손가락 벌리기 · 오므리기: 확대 · 축소');
  row(left, gesture('hold'), '빈 땅을 길게 누르기: 지형 · 자원지 설명');
  if (!lobby) others(left, solo, '탭하면');

  el('div', 'help-head', right, '화면 버튼');
  row(right, `${tbtn('1')}${tbtn('2')}${tbtn('3')}`, '부대: 탭하면 부르기, 길게 누르면 지금 고른 병사를 부대로');
  row(right, tbtn('⌂'), '내 거점으로 화면 옮기기');
  row(right, tbtn('▣'), '화면 안의 내 병사 모두 고르기');
  row(right, tbtn('⚔ 공격이동', 'warm'), '고른 병사가 가다가 만나는 적과 싸운다');
  row(right, tbtn('■ 정지'), '멈춤');
  row(right, tbtn('+ 더 고르기'), '켜 두면 지금 고른 것은 두고 탭·네모·▣로 고른 병사를 더한다 (다시 누르면 꺼짐)');
  row(right, tbtn('✕'), '고른 것 풀기 · 취소');
  row(right, `${tbtn('건물')}<span class="help-plus">→</span>${tbtn('✓ 짓기', 'ok')}`, '아래 건물 버튼 → 그림을 끌어 자리에 놓고 ✓ (고른 병사가, 없으면 가까운 쉬는 병사가)');
  row(right, `${tbtn('보병')}${tbtn('궁수')}${tbtn('전함')}`, '만들기 (거점·항구를 골라 두면 그곳에서)');
  if (solo) row(right, `${tbtn('⏸')}${tbtn('×1')}`, '일시정지 · 속도' + (lobby ? ' (싱글)' : ''));
  if (!solo || lobby) row(right, tbtn('💬'), '대화창 (멀티): 빠른 대사 · 입력');
  row(right, tbtn('☰'), lobby ? '메뉴: 조작 설명 · 항복 · 나가기' : '메뉴');
}
