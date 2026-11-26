// 로비 (데스크톱 game/menu.py의 Lobby): 도트 제목, 부제, 버튼(싱글 플레이, 멀티 플레이, 튜토리얼, 게임 방법), 아래 한 줄, 게임 방법 창.
// 오른쪽 아래: 동그란 커피 버튼 → '커피 한 잔 사주세요!' 창 (Buy Me a Coffee로 가는 링크).
// 배경(LobbyArt)과 왼쪽 그늘은 메뉴 캔버스에 따로 그린다 (pages/game.ts).

import { button, div, pixelTitle } from './widgets.ts';
import { touchMode } from '../ui/device.ts';
import { fillHelp, fillTouchHelp } from '../game/help.ts';
import { installApp } from '../ui/install.ts';
import { busyBox, coffeeLink, cupIcon } from '../ui/coffee.ts';

export const HOW_TO: [string, string[]][] = [
  ['목표', ['다른 나라의 거점과 병사를 모두 없애면 승리.', '내 거점과 병사를 모두 잃으면 패배.']],
  ['자원', ['농장은 식량, 벌목장은 목재, 채석장은 석재를 모은다.',
    '병사를 고르고 지도의 자원지를 오른쪽 클릭하면 짓는다.',
    '건물은 목재와 석재로 짓는다 (목재가 조금 더 든다). 채석장만 목재로 지을 수 있어, 석재가 바닥나도 다시 캘 수 있다.',
    '병사는 식량을 먹는다. 식량이 바닥나면 굶주려 약해진다.',
    '화면 왼쪽 위에 가진 자원과 1초 수입이 보인다 (늘면 초록, 줄면 붉은색, 굶주리면 식량이 붉게 깜빡인다). 그 아래는 계절과 농사 배율, 시각, 게임 속도.']],
  ['부족', ['시작 거점 둘레의 지형으로 부족이 정해진다: 설원이 많으면 설원, 사막이 많으면 사막, 아니면 온대. 왼쪽 위 자원 표시 옆의 동그란 부족 버튼을 누르면 내 부족의 효과가 보인다.',
    '지도 만들기 화면과 대기실의 시작 자리에도 부족 아이콘이 보인다. 다른 나라의 부족은 그 나라 거점을 누르면 보인다.',
    '온대: 병사 훈련 시간 ×0.85 (15% 빠르게). 설원과 사막에선 느려지고 (×0.85) 추위·더위에 체력이 조금씩 깎인다. 사막에선 갈증으로 먹는 식량 ×1.2.',
    '설원: 설원에서 받는 피해 ×0.85, 설원에서 눈 때문에 느려지지 않는다 (다른 땅과 비슷한 빠르기). 사막에선 느려지고 더위에 깎이며 갈증으로 먹는 식량 ×1.2. 바위거북 길들이기 ×1.5.',
    '사막: 설원이 아닌 곳에서 공격력 ×1.2, 더위를 받지 않는다 (갈증은 받는다). 설원에선 느려지고 추위에 깎인다. 드래곤 길들이기 ×1.25.',
    '기후는 병사(보병·궁수·창기병·기마궁수)만 받는다 (용기사·바위거북·배는 아니다). 추위·더위는 3초에 반쯤의 확률로 최대 체력의 2%씩, 30% 아래로는 깎이지 않는다 (맞으면 머리 위에 눈송이·아지랑이). 사막 지역의 병사는 부족과 상관없이 갈증으로 먹는 식량 ×1.2.']],
  ['자원 한도', ['자원마다 모을 수 있는 한도가 따로 있다: 기본 200, 거점마다 모든 자원 +50, 자원 건물마다 그 자원 +25 (농장은 식량, 벌목장은 목재).',
    '한도에 닿으면 그 자원은 더 모이지 않는다 (왼쪽 위 자원 아래 막대가 가득 차면 주황).',
    '거점과 자원 건물이 창고를 겸한다: 무너지면 그 건물이 늘린 몫만큼의 자원을 마지막으로 친 나라가 빼앗아 간다.',
    '건물을 누르면 위에 말풍선: 체력, 보관된 자원, 생산량, 공격력. 다른 나라 건물도 볼 수 있다 (다른 곳을 누르면 닫힌다).']],
  ['건물과 병사', ['아래 버튼이나 숫자 키로 건물을 고르고 땅을 클릭하면 가까운 병사가 짓는다 (1 거점, 2~5 자원 건물, 6 목장, 7 망루, 8 화염탑, 9 항구).',
    '거점은 병사를 훈련하고, 망루는 다가오는 적을 쏘고, 항구는 해안에 지어 배를 띄운다.',
    'Q 보병, W 궁수, E 전함.  보병은 기병에 강하고, 기병은 궁수에 강하다.']],
  ['야생말', ['초원의 야생말을 오른쪽 클릭하면 병사가 다가가 길들인다.',
    '길들이면 말에 올라 빠르고 강한 기병이 된다.',
    '길들이는 중에 맞거나 다른 명령을 받으면 끊긴다.']],
  ['순록', ['넓고 낮은 설원·툰드라에 순록이 촘촘한 무리로 산다. 사람이 다가가면 달아난다.',
    '순록은 병사가 탈 수 없어 길들이지 못한다 (오른쪽 클릭하면 병사는 그 자리로 간다). 목장에 들일 수 있다.']],
  ['목장', ['목장(6번 키)을 고르고 말이나 순록 떼를 누르면 그 떼 둘레에 울타리를 두르고, 울타리 바로 옆에 목장 건물을 짓는다 (3마리 넘는 떼).',
    '멀리서 보면 목장을 지을 수 있는 떼(3마리부터)는 말·순록 그림 하나로 묶여 보인다 (병사 무리처럼).',
    '짓는 동안 떼는 내 병사를 보고도 달아나지 않고 울타리 안으로 걸어 들어온다. 다 지을 때 울타리 안에 있는 동물만 목장에 든다 (다른 나라 병사가 오면 달아난다).',
    '목장의 동물은 식량을 낸다: 순록 마리마다 0.12/초 (겨울에도 ×0.7), 말 0.07/초 (겨울 ×0.4). 봄·여름에 새끼가 늘어 10마리까지. 식량 한도 +25.',
    '보병·궁수를 고르고 내 말 목장(건물이나 울타리 안)을 오른쪽 클릭하면 병사마다 말을 한 마리씩 꺼내 타고 기병이 된다 (창기병·기마궁수). 새끼를 치게 2마리는 남긴다.',
    '울타리 안에는 다른 건물을 짓지 못한다. 목장 건물이 무너지면 안의 동물이 달아난다.']],
  ['바위거북', ['사막의 바위거북은 병사가 먹이(식량)를 주면 길들일 수 있다.',
    '함께 싸우는 튼튼한 동료가 된다. 화살에 강하고, 둘레 적을 치며 적의 주의를 끈다.']],
  ['드래곤', ['넓은 설원의 둥지에서 잠들어 있다 (지도 만들기 화면에 표시). 다가가면 깨어 공격한다.',
    '체력을 많이 깎으면 잠시 쓰러진다. 그때 병사가 다가가 길들이면 용기사가 된다.',
    '용기사는 날아서 산과 바다를 넘고 넓은 범위를 공격한다. 나는 동안은 원거리 공격만 맞는다. 나라마다 2기까지.']],
  ['화염탑과 유황', ['화염탑은 넓은 범위에 불을 뿜는다. 드래곤에게 특히 강하다.',
    '불을 제대로 뿜으려면 유황이 필요하다. 사막의 유황 웅덩이에 채취장을 지어 모은다.']],
  ['외교', ['다른 나라의 거점을 누르면 동맹을 청할 수 있다. 나라마다 우리를 보는 눈(우호·보통·경계·적대)이 있다.',
    '동맹끼리는 서로 공격하지 않고, 자원과 병력을 원하는 만큼 보내거나 함께 칠 나라를 정할 수 있다. 동맹은 기간이 있고 연장할 수 있다.',
    '기간 중에 동맹을 깨면 배신자가 되어 한동안 더 큰 피해를 받고, 모든 나라가 등을 돌린다.']],
  ['바다', ['바다 건너로 보내면 병사들이 항구에서 배를 타고 함께 건넌다.',
    '섬에서 시작할 수도 있으니 항구를 지어 두자. 전함은 다른 나라의 배를 공격한다.']],
  ['자연과 계절', ['가을엔 수확이 많고, 추운 곳은 겨울에 농사가 멈춘다.',
    '숲과 산에선 느려지고, 숲 속에선 화살을 덜 맞는다.',
    '겨울엔 언 바다를 걸어서 건널 수 있지만, 녹으면 빠진다.']],
  ['멀티 플레이와 대화', ['멀티 플레이에서 방을 만들고 입장 코드를 알려 주면 친구와 함께한다. 사람과 AI를 합쳐 8나라까지.',
    '대기실과 게임 중에 대화할 수 있다. PC는 Enter로 입력하고, 💬 빠른 대화로 정해 둔 말을 바로 보낸다. 입력바는 화면 왼쪽 아래 💬 버튼에 접혀 있고, 잠시 안 쓰면 다시 접힌다.',
    '모바일은 오른쪽 위 💬 버튼으로 대화창을 연다. 왼쪽의 빠른 대사를 누르면 바로 보낸다.']],
];

const FEEDBACK_URL = 'https://forms.gle/T2pcd9yCjqrEZGep8';

/** 말풍선 그림 (도트 느낌, 커피잔과 같은 결). */
function bubbleIcon(size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
    <path d="M2 2h12v1h1v7h-1v1H7l-3 3v-3H2v-1H1V3h1z" fill="rgb(250,244,228)"/>
    <path d="M4 5h8v1H4zM4 8h6v1H4z" fill="rgb(120,72,40)"/>
  </svg>`;
}

export class Lobby {
  readonly el = div('menu lobby');
  private help: HTMLDivElement | null = null;
  private coffee: HTMLDivElement | null = null;
  private busyOpen = false;

  constructor(onStart: () => void, onMulti: () => void, onTutorial: () => void) {
    this.el.appendChild(pixelTitle('Pixel Territory', 4));
    div('subtitle', this.el, '자연 속에서 플레이하는 실시간 전략 RTS');
    const col = div('lobby-buttons', this.el);
    button(col, '싱글 플레이', onStart, { size: 20, w: 260, h: 50 });
    button(col, '멀티 플레이', onMulti, { size: 20, w: 260, h: 50 });
    button(col, '튜토리얼', onTutorial, { size: 20, w: 260, h: 50 });
    button(col, '게임 방법', () => this.showHelp(), { size: 20, w: 260, h: 50 });
    // 모바일만 (CSS: body.touch), 앱으로 열었으면 숨김: 오른쪽 위 [앱 설치하기] (커피·피드백 버튼과 같은 모양, 주소창 없이 전체 화면)
    const ib = document.createElement('button');
    ib.className = 'feedback-btn install-btn';
    ib.textContent = '앱 설치하기';
    ib.addEventListener('click', () => void installApp());
    this.el.appendChild(ib);
    div('footer', this.el, '자원지를 차지하고, 병사와 건물로 지키세요.');
    const cb = document.createElement('button');            // 오른쪽 아래: 개발자에게 커피
    cb.className = 'coffee-btn';
    cb.title = '개발자에게 커피 한 잔';
    cb.innerHTML = cupIcon(26);
    cb.addEventListener('click', () => this.showCoffee());
    this.el.appendChild(cb);
    const fb = document.createElement('button');            // 커피 버튼 왼쪽: 피드백 → 소개 창 → 구글 폼 (새 탭)
    fb.className = 'feedback-btn';
    fb.innerHTML = `${bubbleIcon(22)}<span>피드백 하기</span>`;
    fb.addEventListener('click', () => this.showFeedback());
    this.el.appendChild(fb);
  }

  showCoffee() {
    if (this.coffee) return;
    const back = (this.coffee = div('modal-back', this.el));
    const box = div('modal coffee', back);
    div('coffee-icon', box).innerHTML = cupIcon(56);
    div('modal-title', box, '커피 한 잔 사주세요!');
    div('coffee-text', box, '재미있게 즐기셨다면 커피 한 잔으로 개발자를 응원해 주세요.\n더 좋은 게임을 만드는 데 큰 힘이 됩니다.');
    box.appendChild(coffeeLink('커피 사주러 가기', 'coffee-link', 22));
    button(box, '닫기', () => this.closeCoffee(), { w: 120, h: 38 }).classList.add('coffee-close');
    back.addEventListener('mousedown', (e) => { if (e.target === back) this.closeCoffee(); });
  }

  closeCoffee() { this.coffee?.remove(); this.coffee = null; }

  /** [피드백 하기]: 커피 창과 같은 모양의 소개 창. 안의 버튼을 눌러야 구글 폼으로 (새 탭). */
  showFeedback() {
    if (this.coffee) return;
    const back = (this.coffee = div('modal-back', this.el));   // 커피 창과 같은 자리 (한 번에 하나)
    const box = div('modal coffee', back);
    div('coffee-icon', box).innerHTML = bubbleIcon(52);
    div('modal-title', box, '의견을 들려주세요!');
    div('coffee-text', box, '버그, 불편한 점, 바라는 기능, 재미있었던 점까지 무엇이든 좋아요.\n짧은 설문으로 남겨 주시면 다음 업데이트에 반영할게요.');
    const a = document.createElement('a');
    a.className = 'coffee-link';
    a.href = FEEDBACK_URL;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.innerHTML = `${bubbleIcon(22)}<span>피드백 남기러 가기</span>`;
    a.addEventListener('click', () => this.closeCoffee());
    box.appendChild(a);
    button(box, '닫기', () => this.closeCoffee(), { w: 120, h: 38 }).classList.add('coffee-close');
    back.addEventListener('mousedown', (e) => { if (e.target === back) this.closeCoffee(); });
  }

  /** 서버 접속자가 꽉 찼으면 로비 위에 안내 ([다시 시도]: 자리가 났으면 닫힌다). */
  async checkBusy() {
    const busy = async () => { try { return !!(await (await fetch('/api/status')).json()).busy; } catch { return false; } };
    if (this.busyOpen || !(await busy())) return;
    this.busyOpen = true;
    const close = busyBox(this.el, '서버에 접속한 사람이 많아 지금은 게임을 열 수 없습니다. 잠시 뒤에 다시 시도해 주세요', [
      ['다시 시도', () => { void busy().then((b) => { if (!b) { close(); this.busyOpen = false; } }); return false; }],
      ['닫기', () => { this.busyOpen = false; }],
    ]);
  }

  showHelp() {
    if (this.help) return;
    const back = (this.help = div('modal-back', this.el));
    const box = div('modal howto', back);
    div('modal-title', box, '게임 방법');
    const body = div('howto-body', box);                     // 설명만 스크롤 (제목과 닫기 버튼은 그대로)
    const cols = div('howto-cols', body);                    // 두 단으로 고르게 (CSS columns)
    HOW_TO.forEach(([head, base]) => {
      const sec = div('howto-sec', cols);
      div('howto-head', sec, head);
      for (const line of base) div('howto-line', sec, line);
    });
    div('howto-divider', body);                              // 줄글 아래: 그림 조작법 (기기에 맞춰, 게임 안 설명 창과 같은 그림)
    div('howto-head howto-controls', body, '조작');
    if (touchMode()) fillTouchHelp(body, true, true); else fillHelp(body, true, true);
    const foot = div('modal-foot', box);
    button(foot, '닫기', () => this.closeHelp(), { w: 120, h: 40 });
    back.addEventListener('mousedown', (e) => { if (e.target === back) this.closeHelp(); });
  }

  closeHelp() { this.help?.remove(); this.help = null; }

  /** Esc: 게임 방법 창을 닫는다. */
  key(e: KeyboardEvent) { if (e.key === 'Escape') { this.closeHelp(); this.closeCoffee(); } }
}
