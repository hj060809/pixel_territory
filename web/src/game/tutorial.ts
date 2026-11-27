// 튜토리얼 안내 (로비 '튜토리얼' → 서버의 튜토리얼 판, sim/tutorial.py): 화면에 '지금 할 일'을 띄우고,
// 게임 상태를 보고 해냈으면 '잘했어요'와 [다음 단계] 버튼 (넘어가기는 사람이 누른다). PC는 마우스·키캡 그림, 터치는 손가락·화면 버튼 그림 (help.ts와 같은 그림).
// 단계마다 [위치 보기] (그곳으로 화면 이동), [건너뛰기], [끝내기] (한 번 더 묻고 로비로).
// 모바일: 창은 화면 가운데에 잠시 떴다가 (AUTO_DOCK) 왼쪽 아래 동그란 버튼으로 빨려 들어간다 (접힘). 버튼을 누르면 다시 가운데,
// 창의 [접기]로 다시 접는다. 단계를 해내면 1초 뒤 [다음 단계]와 함께 가운데에 다시 뜬다. 마지막에 완료 창 (싱글 플레이 / 로비로).

import type { Camera } from '../sim/camera.ts';
import type { Controller } from './controller.ts';
import type { GameState } from './state.ts';
import { gesture, kbd, mouse, tbtn } from './help.ts';
import { confirmBox } from './gameMenu.ts';
import { touchMode } from '../ui/device.ts';

export interface TutorialHooks {
  st(): GameState | null;
  ctl(): Controller | null;
  cam: Camera;
  center(x: number, y: number): void;     // 그 자리로 화면 옮기기
  home(): void;                           // 내 거점으로
  lobby(): void;
  single(): void;                         // 튜토리얼을 마치고 싱글 플레이 설정으로
}

interface Step {
  title: string;
  pc: string;                             // 설명 (HTML: 그림 포함)
  touch: string;
  enter?(): void;                         // 이 단계에 들어올 때 (기준 값 기억)
  target?(): [number, number] | null;     // [위치 보기]로 갈 곳
  done(): boolean;
  progress?(): string;                    // 진행 중 한 줄 (예: 길들이는 중)
  manual?: string;                        // 버튼으로 넘어가는 단계 (그 버튼 이름)
}

const AUTO_DOCK = 3500;                  // 모바일: 단계가 시작되고 이만큼(ms) 보인 뒤 접힌다
const REOPEN = 1000;                     // 모바일: 해내고 이만큼(ms) 뒤 다시 펼친다

const plus = '<span class="help-plus">+</span>';
const then = '<span class="help-plus">→</span>';

export class Tutorial {
  private el = document.createElement('div');
  private idx = 0;
  private okAt = 0;                       // 이 단계를 해낸 시각 ('잘했어요' + [다음 단계]: 넘어가기는 사람이 누른다)
  private steps: Step[];
  private sig = '';
  private base: any = {};
  private dockBtn = document.createElement('button');   // 모바일: 접힌 창 (왼쪽 아래 동그란 버튼)
  private docked = false;
  private timer = 0;

  constructor(private h: TutorialHooks) {
    this.el.className = 'tutorial';
    document.body.appendChild(this.el);
    this.dockBtn.className = 'tut-dock';
    this.dockBtn.title = '튜토리얼';
    this.dockBtn.addEventListener('click', (e) => { e.stopPropagation(); this.open(false); });
    document.body.appendChild(this.dockBtn);
    this.steps = this.makeSteps();
    this.go(0);
  }

  dispose() { clearTimeout(this.timer); this.el.remove(); this.dockBtn.remove(); }

  // ------------------------------------------------------------- 모바일: 펼치기 · 접기
  /** 가운데에 펼친다. auto: 잠시 뒤 저절로 접는다 (단계가 막 시작됐을 때). */
  private open(auto: boolean) {
    clearTimeout(this.timer);
    this.docked = false;
    this.el.classList.remove('docked');
    this.el.style.transform = '';
    this.dockBtn.classList.remove('show');
    const s = this.steps[this.idx], last = this.idx === this.steps.length - 1;
    if (auto && touchMode() && !s.manual && !last && !this.okAt) this.timer = window.setTimeout(() => this.dock(), AUTO_DOCK);
  }

  /** 왼쪽 아래 버튼으로 빨려 들어간다 (창이 버튼 자리로 작아지며 사라진다). */
  private dock() {
    clearTimeout(this.timer);
    if (!touchMode()) return;
    const r = this.dockBtn.getBoundingClientRect();
    const dx = r.left + r.width / 2 - window.innerWidth / 2, dy = r.top + r.height / 2 - window.innerHeight / 2;
    this.docked = true;
    this.el.style.transform = `translate(-50%, -50%) translate(${dx}px, ${dy}px) scale(0.06)`;
    this.el.classList.add('docked');
    this.dockBtn.classList.add('show');
  }

  // ------------------------------------------------------------- 게임 상태 읽기
  private mine(kind?: number[]) {
    const st = this.h.st();
    if (!st) return [];
    return [...st.units.values()].filter((u) => u.own === st.info.me && (!kind || kind.includes(u.kind)));
  }

  private myBuilds(kinds: number[]) {
    const st = this.h.st();
    if (!st) return [];
    return [...st.builds.values()].filter((b) => b.own === st.info.me && kinds.includes(b.kind));
  }

  private hall(own: 'me' | 'foe') {
    const st = this.h.st();
    if (!st) return null;
    const me = st.info.me, H = st.info.rules.kinds.HALL;
    return [...st.builds.values()].find((b) => b.kind === H && (own === 'me' ? b.own === me : b.own !== me)) ?? null;
  }

  private near<T extends { x: number; y: number }>(list: T[]): T | null {
    const h = this.hall('me');
    if (!h || !list.length) return list[0] ?? null;
    return list.reduce((a, b) => (Math.hypot(a.x - h.x, a.y - h.y) <= Math.hypot(b.x - h.x, b.y - h.y) ? a : b));
  }

  private makeSteps(): Step[] {
    const R = () => this.h.st()!.info.rules;
    const K = () => R().kinds;
    return [
      {
        title: '환영합니다!',
        pc: '자연 속에서 나라를 키우는 실시간 전략 게임입니다. 몇 단계로 기본 조작을 해 봅니다.<br>오른쪽 위 목록에서 <b>내 나라</b>와 가까이 있는 <b>적 나라</b>를 볼 수 있어요.',
        touch: '자연 속에서 나라를 키우는 실시간 전략 게임입니다. 몇 단계로 기본 조작을 해 봅니다.',
        manual: '시작하기',
        done: () => false,
      },
      {
        title: '화면 둘러보기',
        pc: `${mouse('wheel')} 휠로 확대·축소, ${kbd('←')}${kbd('↑')}${kbd('↓')}${kbd('→')} 또는 마우스를 화면 끝에 대어 화면을 옮겨 보세요.`,
        touch: `${gesture('drag')} 한 손가락으로 끌어 옮기고, ${gesture('pinch')} 두 손가락으로 확대·축소해 보세요.`,
        enter: () => { const c = this.h.cam; this.base = { x: c.x, y: c.y, z: c.zoom }; },
        done: () => {
          const c = this.h.cam, b = this.base;
          return Math.hypot(c.x - b.x, c.y - b.y) > 25 || Math.abs(Math.log(c.zoom / b.z)) > 0.35;
        },
      },
      {
        title: '병사 고르기',
        pc: `${mouse('left')} 내 병사를 클릭하거나, 왼쪽 버튼을 누른 채 끌어 네모로 여러 명을 고르세요.`,
        touch: `${gesture('tap')} 내 병사를 탭하거나, ${gesture('box')} 길게 누른 채 끌어 여러 명을 고르세요. ${tbtn('▣')}는 화면 안 병사 모두.`,
        enter: () => this.h.home(),
        target: () => { const h = this.hall('me'); return h ? [h.x, h.y] : null; },
        done: () => (this.h.ctl()?.sel.size ?? 0) > 0,
      },
      {
        title: '이동하기',
        pc: `병사를 고른 채 ${mouse('right')} 땅을 오른쪽 클릭하면 그곳으로 갑니다.`,
        touch: `병사를 고른 채 ${gesture('tap')} 땅을 탭하면 그곳으로 갑니다.`,
        enter: () => { this.base = new Map(this.mine().map((u) => [u.slot, [u.x, u.y]])); },
        done: () => this.mine().some((u) => { const p = this.base.get(u.slot); return p && Math.hypot(u.x - p[0], u.y - p[1]) > 5; }),
      },
      {
        title: '진형 서기',
        pc: `병사를 둘 이상 고르고 ${mouse('right')} 오른쪽 버튼을 누른 채 끌어 선을 그어 보세요. 그 선을 따라 <b>보병은 앞</b>, <b>궁수는 뒤</b>에 고르게 섭니다. 끝을 시작점 가까이로 닫으면 둘레 방어선이 돼요.`,
        touch: `병사를 둘 이상 고르고 ${tbtn('▦ 진형')}을 켠 뒤 ${gesture('drag')} 한 손가락으로 선을 그어 보세요. 그 선을 따라 <b>보병은 앞</b>, <b>궁수는 뒤</b>에 섭니다. 켜 둔 동안 화면 이동은 두 손가락이에요.`,
        enter: () => { this.base = this.h.ctl()?.formSent ?? 0; },
        done: () => (this.h.ctl()?.formSent ?? 0) > this.base,
      },
      {
        title: '자원지에 짓기',
        pc: `병사를 고르고 ${mouse('right')} 빈 <b>식량 자원지</b>(이삭 표시)를 오른쪽 클릭하면 농장을 짓습니다. 목재·석재 자원지도 같은 방법이에요.`,
        touch: `병사를 고르고 ${gesture('tap')} 빈 <b>식량 자원지</b>(이삭 표시)를 탭하면 농장을 짓습니다. 목재·석재 자원지도 같은 방법이에요.`,
        enter: () => { this.base = this.myBuilds([K().FARM, K().LUMBER, K().QUARRY]).length; },
        target: () => {
          const st = this.h.st()!, taken = st.siteTaken();
          const s = this.near(st.info.sites.filter((x) => x.kind === 0 && !taken.has(x.id)));
          return s ? [s.x + 0.5, s.y + 0.5] : null;
        },
        done: () => this.myBuilds([K().FARM, K().LUMBER, K().QUARRY]).length > this.base,
      },
      {
        title: '건물 짓기',
        pc: `아래 막대의 <b>망루</b>를 누르거나 ${kbd('7')}을 누른 뒤 ${mouse('left')} 땅을 클릭하세요. 망루는 다가오는 적을 쏩니다.`,
        touch: `아래 막대의 <b>망루</b> 버튼 ${then} 그림을 끌어 자리에 놓고 ${tbtn('✓ 짓기', 'ok')}. 망루는 다가오는 적을 쏩니다.`,
        enter: () => { this.base = this.myBuilds([K().TOWER]).length; },
        target: () => { const h = this.hall('me'); return h ? [h.x, h.y] : null; },
        done: () => this.myBuilds([K().TOWER]).length > this.base,
      },
      {
        title: '병사 만들기',
        pc: `${kbd('Q')} 보병, ${kbd('W')} 궁수. 아래 막대의 병사 버튼을 눌러도 됩니다. 거점에서 훈련합니다.`,
        touch: `아래 막대의 ${tbtn('보병')} ${tbtn('궁수')} 버튼을 누르세요. 거점에서 훈련합니다.`,
        enter: () => { this.base = this.mine().length; },
        done: () => this.mine().length > this.base || this.myBuilds([K().HALL]).some((b) => b.qlen > 0),
      },
      {
        title: '야생말 길들이기',
        pc: `병사를 고르고 ${mouse('right')} 야생말을 오른쪽 클릭하면 다가가 길들입니다. 길들이면 빠른 <b>기병</b>이 돼요.`,
        touch: `병사를 고르고 ${gesture('tap')} 야생말을 탭하면 다가가 길들입니다. 길들이면 빠른 <b>기병</b>이 돼요.`,
        target: () => {
          const st = this.h.st()!;
          const a = this.near([...st.animals.values()].filter((x) => x.kind === 0));
          return a ? [a.x, a.y] : null;
        },
        progress: () => {
          const st = this.h.st()!;
          const t = [...st.animals.values()].find((a) => a.kind === 0 && a.state === 4);
          if (t) return `길들이는 중... ${Math.round(t.prog * 100)}%`;
          return [...st.animals.values()].some((a) => a.kind === 0 && a.state === 3) ? '병사가 말에게 가는 중...' : '';
        },
        done: () => this.mine([2, 3]).length > 0,
      },
      {
        title: '적 거점 공격',
        pc: `병사를 모두 고르고 ${kbd('A')} ${plus} ${mouse('left')} 적 거점을 클릭하면 가는 길의 적과 싸우며 쳐들어갑니다. 적의 거점과 병사를 모두 없애면 승리!`,
        touch: `병사를 모두 고르고 ${tbtn('⚔ 공격이동', 'warm')} ${then} 적 거점을 탭하면 쳐들어갑니다. 적의 거점과 병사를 모두 없애면 승리!`,
        target: () => { const h = this.hall('foe'); return h ? [h.x, h.y] : null; },
        progress: () => {
          const h = this.hall('foe');
          return h ? `적 거점 체력 ${Math.round(h.hp * 100)}%` : '적 거점을 무너뜨렸습니다! 남은 적 병사도 물리치세요';
        },
        done: () => { const st = this.h.st()!; return st.over === '승리'; },
      },
      {
        title: '튜토리얼 완료!',
        pc: '기본은 모두 익혔어요. 이 밖에도 항구와 배, 드래곤과 바위거북 길들이기, 동맹과 외교, 계절과 날씨가 기다립니다.<br>이제 싱글 플레이에서 AI와, 멀티 플레이에서 친구와 겨뤄 보세요!',
        touch: '기본은 모두 익혔어요. 이 밖에도 항구와 배, 드래곤과 바위거북 길들이기, 동맹과 외교, 계절과 날씨가 기다립니다.<br>이제 싱글 플레이에서 AI와, 멀티 플레이에서 친구와 겨뤄 보세요!',
        done: () => false,
      },
    ];
  }

  // ------------------------------------------------------------- 진행
  private go(i: number) {
    this.idx = Math.min(i, this.steps.length - 1);
    this.okAt = 0;
    this.base = {};
    if (this.h.st()) this.steps[this.idx].enter?.();
    else this.pendingEnter = true;
    this.sig = '';
    this.render();
    this.open(true);
  }

  private pendingEnter = false;

  /** 0.25초마다 (게임 화면 HUD와 함께): 해냈는지 보고 다음 단계로. */
  update() {
    const st = this.h.st();
    if (!st) return;
    if (this.pendingEnter) { this.pendingEnter = false; this.steps[this.idx].enter?.(); }
    const s = this.steps[this.idx];
    const last = this.idx === this.steps.length - 1;
    if (!last && st.over === '승리' && this.idx < this.steps.length - 2) { this.go(this.steps.length - 1); return; }   // 먼저 이겨 버렸다
    if (!this.okAt && !s.manual && !last && s.done()) {
      this.okAt = performance.now();
      if (touchMode()) {                                      // 모바일: 1초 뒤 [다음 단계]와 함께 다시 가운데로
        clearTimeout(this.timer);
        this.timer = window.setTimeout(() => this.open(false), REOPEN);
      }
    }
    if (!touchMode() && this.docked) this.open(false);       // 터치 → 마우스로 바뀌었다: 접지 않는다
    this.render();
  }

  private render() {
    const s = this.steps[this.idx], touch = touchMode(), last = this.idx === this.steps.length - 1;
    const prog = this.okAt ? '✓ 잘했어요!' : this.h.st() && s.progress ? s.progress() : '';
    const sig = `${this.idx}|${touch}|${prog}`;
    if (sig === this.sig) return;
    this.sig = sig;
    const n = this.steps.length - 2;                          // 환영·완료를 빼고 센 단계
    this.dockBtn.innerHTML = `<span class="tut-q">?</span><span class="tut-badge${this.okAt ? ' ok' : ''}">${
      this.okAt ? '✓' : this.idx === 0 ? '!' : last ? '✓' : `${this.idx}/${n}`}</span>`;
    const el = this.el;
    el.classList.toggle('done', last);
    el.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'tut-head';
    head.textContent = this.idx === 0 ? '튜토리얼' : last ? '튜토리얼' : `튜토리얼 ${this.idx} / ${n}`;
    const dots = document.createElement('span');
    dots.className = 'tut-dots';
    for (let k = 1; k <= n; k++) {
      const d = document.createElement('i');
      if (k < this.idx || last || (k === this.idx && this.okAt)) d.className = 'on';
      else if (k === this.idx) d.className = 'now';
      dots.appendChild(d);
    }
    head.appendChild(dots);
    const title = document.createElement('div');
    title.className = 'tut-title';
    title.textContent = s.title;
    const body = document.createElement('div');
    body.className = 'tut-body';
    body.innerHTML = touch ? s.touch : s.pc;
    el.append(head, title, body);
    if (prog) {
      const p = document.createElement('div');
      p.className = 'tut-prog' + (this.okAt ? ' ok' : '');
      p.textContent = prog;
      el.appendChild(p);
    }
    const row = document.createElement('div');
    row.className = 'tut-btns';
    const quit = () => confirmBox('튜토리얼 끝내기', '튜토리얼을 끝내고 로비로 나갈까요?', '로비로 나가기', () => this.h.lobby());
    const b = (label: string, fn: () => void, cls = '') => {
      const e = document.createElement('button');
      e.className = 'dbtn ' + cls;
      e.textContent = label;
      e.addEventListener('click', (ev) => { ev.stopPropagation(); fn(); });
      row.appendChild(e);
    };
    const fold = () => { if (touch) b('접기', () => this.dock(), 'tut-fold'); };   // 모바일: 왼쪽 아래 버튼으로
    if (last) {
      b('싱글 플레이 하러 가기', () => this.h.single(), 'tut-main');
      b('로비로', () => this.h.lobby());
    } else if (this.okAt) {                                  // 해냈다: 사람이 [다음 단계]를 눌러 넘어간다
      b('다음 단계 ▶', () => this.go(this.idx + 1), 'tut-main');
      fold();
      b('끝내기', quit);
    } else if (s.manual) {
      b(s.manual, () => this.go(this.idx + 1), 'tut-main');
      b('튜토리얼 끝내기', quit);
    } else {
      const t = s.target?.();
      if (t) b('📍 위치 보기', () => { const p = s.target?.(); if (p) this.h.center(p[0], p[1]); if (touch) this.dock(); });
      fold();
      b('건너뛰기', () => this.go(this.idx + 1));
      b('끝내기', quit);
    }
    el.appendChild(row);
  }
}
