// 로비 (데스크톱 game/menu.py의 Lobby): 도트 제목, 부제, 버튼(게임 시작, 게임 방법), 아래 한 줄, 게임 방법 창.
// 배경(LobbyArt)과 왼쪽 그늘은 메뉴 캔버스에 따로 그린다 (pages/game.ts).

import { button, div, pixelTitle } from './widgets.ts';
import { touchMode } from '../ui/device.ts';

/** 터치 기기에서 '조작' 항목 대신 */
const TOUCH_CONTROLS: string[] = [
  '탭: 고르기 · 고른 뒤 땅 탭: 이동 · 적 탭: 공격 · 빈 자원지 탭: 짓기',
  '한 손가락 끌기: 화면 이동,  두 손가락: 확대,  길게 누르고 끌기: 여러 명 고르기',
  '아래 버튼: 건물(그림을 옮기고 ✓)과 훈련,  왼쪽 1~3: 부대 (길게 눌러 지정),  ☰: 메뉴',
];

export const HOW_TO: [string, string[]][] = [
  ['목표', ['다른 나라의 건물과 병사를 모두 없애면 승리.', '내 건물과 병사를 모두 잃으면 패배.']],
  ['자원', ['비옥한 들판에 농장 → 식량, 숲에 벌목장 → 목재, 바위 지대에 채석장 → 석재.',
    '병사를 고르고 지도 위 자원지 아이콘을 오른쪽 클릭하면 짓는다.',
    '병사는 식량을 먹는다. 바닥나면 굶어서 약해진다.']],
  ['건물', ['아래 버튼이나 숫자 키(1~6)를 누르고 땅을 클릭하면 가까운 병사가 짓는다.',
    '거점: 병사 훈련.  망루: 다가오는 적을 쏜다.  항구: 바다에 맞닿은 해안에만.',
    'Q 보병, W 궁수, E 전함: 내 건물들에서 돌아가며 만든다 (건물을 고르면 그곳에서).']],
  ['바다', ['바다 건너로 보낸 병사들은 그 땅의 항구에 모여 차례로 나룻배를 타고, 다 타면 함께 건넌다.',
    '여러 섬에서 시작할 수 있으니, 내 섬에 항구를 지어 두자.',
    '전함(E)은 다른 나라의 나룻배와 전함을 쏜다. 나룻배는 한 방에 가라앉는다.']],
  ['자연과 계절', ['가을에 수확이 많고, 추운 곳은 겨울에 농사가 멈춘다.',
    '숲과 산에서는 느리고, 숲 속에선 화살을 덜 맞는다.',
    '겨울엔 언 바다를 걸어서 건너지만, 녹으면 빠진다.']],
  ['조작', ['왼쪽 클릭 · 드래그: 선택,  오른쪽 클릭: 이동 · 공격 · 짓기',
    'A: 공격 이동,  S: 정지,  Ctrl+숫자: 부대 지정,  Shift+숫자: 부대 부르기,  Space: 화면 이동',
    '휠: 확대,  P: 일시정지,  마침표: 속도,  F1: 도움말,  F10: 로비로']],
];

export class Lobby {
  readonly el = div('menu lobby');
  private help: HTMLDivElement | null = null;

  constructor(onStart: () => void) {
    this.el.appendChild(pixelTitle('Pixel Territory', 4));
    div('subtitle', this.el, '자연 속에서 플레이하는 실시간 전략 RTS');
    const col = div('lobby-buttons', this.el);
    button(col, '게임 시작', onStart, { size: 20, w: 260, h: 50 });
    button(col, '게임 방법', () => this.showHelp(), { size: 20, w: 260, h: 50 });
    div('footer', this.el, '자원지를 차지하고, 병사와 건물로 지키세요.');
  }

  showHelp() {
    if (this.help) return;
    const back = (this.help = div('modal-back', this.el));
    const box = div('modal howto', back);
    div('modal-title', box, '게임 방법');
    const cols = div('howto-cols', box);
    const left = div('howto-col', cols), right = div('howto-col', cols);
    HOW_TO.forEach(([head, base], i) => {
      const lines = head === '조작' && touchMode() ? TOUCH_CONTROLS : base;
      const sec = div('howto-sec', i < 3 ? left : right);
      div('howto-head', sec, head);
      for (const line of lines) div('howto-line', sec, line);
    });
    const foot = div('modal-foot', box);
    button(foot, '닫기', () => this.closeHelp(), { w: 120, h: 40 });
    back.addEventListener('mousedown', (e) => { if (e.target === back) this.closeHelp(); });
  }

  closeHelp() { this.help?.remove(); this.help = null; }

  /** Esc: 게임 방법 창을 닫는다. */
  key(e: KeyboardEvent) { if (e.key === 'Escape') this.closeHelp(); }
}
