// 로비 (데스크톱 game/menu.py의 Lobby): 도트 제목, 부제, 버튼(게임 시작, 게임 방법), 아래 한 줄, 게임 방법 창.
// 배경(LobbyArt)과 왼쪽 그늘은 메뉴 캔버스에 따로 그린다 (pages/game.ts).

import { button, div, pixelTitle } from './widgets.ts';
import { touchMode } from '../ui/device.ts';
import { installApp } from '../ui/install.ts';

/** 터치 기기에서 '조작' 항목 대신 */
const TOUCH_CONTROLS: string[] = [
  '탭: 고르기 · 고른 뒤 땅 탭: 이동 · 적 탭: 공격 · 빈 자원지 탭: 짓기',
  '한 손가락 끌기: 화면 이동,  두 손가락: 확대,  길게 누르고 끌기: 여러 명 고르기',
  '아래 버튼: 건물(그림을 옮기고 ✓)과 훈련,  왼쪽 1~3: 부대 (길게 눌러 지정),  ☰: 메뉴',
];

export const HOW_TO: [string, string[]][] = [
  ['목표', ['다른 나라의 거점과 병사를 모두 없애면 승리.', '내 거점과 병사를 모두 잃으면 패배.']],
  ['자원', ['농장은 식량, 벌목장은 목재, 채석장은 석재를 모은다.',
    '병사를 고르고 지도의 자원지를 오른쪽 클릭하면 짓는다.',
    '병사는 식량을 먹는다. 식량이 바닥나면 굶주려 약해진다.']],
  ['건물과 병사', ['아래 버튼이나 숫자 키로 건물을 고르고 땅을 클릭하면 가까운 병사가 짓는다.',
    '거점은 병사를 훈련하고, 망루는 다가오는 적을 쏘고, 항구는 해안에 지어 배를 띄운다.',
    'Q 보병, W 궁수, E 전함.  보병은 기병에 강하고, 기병은 궁수에 강하다.']],
  ['야생말', ['초원의 야생말을 오른쪽 클릭하면 병사가 다가가 길들인다.',
    '길들이면 말에 올라 빠르고 강한 기병이 된다.',
    '길들이는 중에 맞거나 다른 명령을 받으면 끊긴다.']],
  ['바위거북', ['사막의 바위거북은 병사가 먹이(식량)를 주면 길들일 수 있다.',
    '함께 싸우는 튼튼한 동료가 된다. 화살에 강하고, 둘레 적을 치며 적의 주의를 끈다.']],
  ['드래곤', ['넓은 설원의 둥지에서 잠들어 있다 (지도 만들기 화면에 표시). 다가가면 깨어 공격한다.',
    '체력을 많이 깎으면 잠시 쓰러진다. 그때 병사가 다가가 길들이면 용기사가 된다.',
    '용기사는 날아서 산과 바다를 넘고 넓은 범위를 공격한다. 나는 동안은 원거리 공격만 맞는다. 나라마다 2기까지.']],
  ['화염탑과 유황', ['화염탑은 넓은 범위에 불을 뿜는다. 드래곤에게 특히 강하다.',
    '불을 제대로 뿜으려면 유황이 필요하다. 사막의 유황 웅덩이에 채취장을 지어 모은다.']],
  ['바다', ['바다 건너로 보내면 병사들이 항구에서 배를 타고 함께 건넌다.',
    '섬에서 시작할 수도 있으니 항구를 지어 두자. 전함은 다른 나라의 배를 공격한다.']],
  ['자연과 계절', ['가을엔 수확이 많고, 추운 곳은 겨울에 농사가 멈춘다.',
    '숲과 산에선 느려지고, 숲 속에선 화살을 덜 맞는다.',
    '겨울엔 언 바다를 걸어서 건널 수 있지만, 녹으면 빠진다.']],
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
    // 모바일만 (CSS: body.touch), 앱으로 열었으면 숨김: 홈 화면에 설치하면 주소창 없이 전체 화면
    button(col, '앱으로 설치', () => void installApp(), { size: 20, w: 260, h: 50 }).classList.add('install-btn');
    div('footer', this.el, '자원지를 차지하고, 병사와 건물로 지키세요.');
  }

  showHelp() {
    if (this.help) return;
    const back = (this.help = div('modal-back', this.el));
    const box = div('modal howto', back);
    div('modal-title', box, '게임 방법');
    const body = div('howto-body', box);                     // 설명만 스크롤 (제목과 닫기 버튼은 그대로)
    const cols = div('howto-cols', body);                    // 두 단으로 고르게 (CSS columns)
    HOW_TO.forEach(([head, base]) => {
      const lines = head === '조작' && touchMode() ? TOUCH_CONTROLS : base;
      const sec = div('howto-sec', cols);
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
