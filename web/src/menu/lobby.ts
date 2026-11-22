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
  ['목표', ['다른 나라의 거점과 병사를 모두 없애면 승리.', '내 거점과 병사를 모두 잃으면 패배 (자원지·망루만 남아도).']],
  ['자원', ['비옥한 들판에 농장 → 식량, 숲에 벌목장 → 목재, 바위 지대에 채석장 → 석재.',
    '병사를 고르고 지도 위 자원지 아이콘을 오른쪽 클릭하면 짓는다.',
    '병사는 식량을 먹는다. 바닥나면 굶어서 약해진다.']],
  ['건물', ['아래 버튼이나 숫자 키(1~6)를 누르고 땅을 클릭하면 가까운 병사가 짓는다.',
    '거점: 병사 훈련.  망루: 다가오는 적을 쏜다.  항구: 바다에 맞닿은 해안에만.',
    'Q 보병, W 궁수, E 전함: 내 건물들에서 돌아가며 만든다 (건물을 고르면 그곳에서).']],
  ['야생 동물', ['넓은 초원에 야생말이 흩어져 산다. 병사를 고르고 말을 오른쪽 클릭(터치: 탭)하면 말마다 한 명씩 가서 길들인다.',
    '다 길들이면 병사가 말에 올라탄다: 보병 → 창기병, 궁수 → 기마궁수. 빠르고 세게 치지만 훈련 버튼은 없다.',
    '창기병은 달려와 처음 치는 한 방이 세고 궁수에 강하다. 보병은 기병에 강하다.',
    '길들이는 동안 맞거나 다른 명령을 받으면 끊긴다. 말은 사람이 다가오면 달아나고, 겨울엔 거의 새로 나지 않는다.']],
  ['화염탑과 유황', ['화염탑(7)은 2초마다 궁수보다 먼 곳(1.25배)까지 불을 뿜어 맞은 자리 둘레까지 태운다. 드래곤(용기사·야생 드래곤)은 불에 약하고, 바위거북은 잘 견딘다.',
    '불을 뿜을 때마다 유황 1을 쓰고, 유황이 없으면 약한 불을 뿜는다. 짓는 데 석재 80과 유황 40이 든다.',
    '유황은 사막의 유황 웅덩이(맵 생성 화면에 노란 표시)에 유황 채취장(8)을 지어 모은다. 용기사와 1대1이면 화염탑이 아슬아슬하게 이기지만, 눈 위에서는 용기사가 이긴다.']],
  ['바위거북', ['넓은 사막에 거대 바위거북이 1~2마리씩 산다. 병사를 고르고 오른쪽 클릭(탭)하면 한 명이 가서 먹이(식량 300)를 주고 4초 만에 길들인다.',
    '병사는 그대로이고 바위거북이 함께 싸운다 (수 제한 없음, 식량을 많이 먹는다). 체력이 높고 바위 껍질이 화살을 막는 이동형 탱커.',
    '발 구르기: 붙은 적을 몇 초마다 한꺼번에 친다. 낮은 포효: 가끔 둘레 적이 바위거북만 노리게 한다. 위험하면 껍질 속으로 숨어 버틴다.']],
  ['드래곤', ['넓은 설원의 가장 높은 곳에 드래곤 둥지가 있다 (지도에 최대 3, 지도 만들기 화면에 표시). 다가가거나 치면 깨어 서리 숨결을 뿜는다.',
    '체력을 30% 아래로 깎으면 30초 동안 쓰러진다. 그동안 병사를 고르고 오른쪽 클릭(탭)하면 한 명이 가서 15초 동안 길들인다.',
    '어느 병사가 길들여도 용기사가 된다: 움직이거나 싸울 때 날아서 산·바다를 넘고, 숨결로 범위 피해. 나는 동안은 활·망루·전함만 맞힌다 (멈춰 내려앉으면 누구에게나 맞는다).',
    '용기사는 나라마다 2기까지, 식량을 많이 먹고, 눈 위에서 회복한다. 길들여진 둥지에는 6분 뒤 새 드래곤이 난다.']],
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
    // 모바일만 (CSS: body.touch), 앱으로 열었으면 숨김: 홈 화면에 설치하면 주소창 없이 전체 화면
    button(col, '앱으로 설치', () => void installApp(), { size: 20, w: 260, h: 50 }).classList.add('install-btn');
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
