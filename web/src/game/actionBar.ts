// 하단 버튼 막대: 건물(숫자 키)과 병종(QWERTY). 버튼 왼쪽 위에 키, 가운데에 내 나라 색 아이콘.
// 건물 버튼(또는 숫자 키)을 누르면 반투명 건물 그림이 커서에 붙고, 땅을 클릭하면 놓인다 (controller.place).
// 병종 버튼(또는 키)을 누르면 고른 건물, 아니면 내 건물들에서 돌아가며 만든다 (controller.train).
// 마우스를 올리면 이름과 비용, 자원이 모자라거나 만들 건물이 없으면 흐리게.

import type { Controller, TrainKind } from './controller.ts';
import type { SpriteBank } from './sprites.ts';
import type { GameState } from './state.ts';

/** 버튼 순서 = 숫자 키 1~9 → 건물 종류 번호 (sim/rules.py: 거점 0, 농장 1, 벌목장 2, 채석장 3, 망루 4, 항구 5, 유황 채취장 6,
 *  화염탑 7, 목장 8). 거점, 자원 건물, 공격 건물, 항구 순:
 *  1 거점, 2 농장, 3 벌목장, 4 채석장, 5 유황 채취장, 6 목장, 7 망루, 8 화염탑, 9 항구. */
export const BUILD_KEYS = [0, 1, 2, 3, 6, 8, 4, 7, 5];
/** 건물 버튼 i번째의 키 글자 (1~9). */
export const buildKeyLabel = (i: number) => String(i + 1);
/** Q W E (R T Y는 나중 병종용). 기병(창기병, 기마궁수)은 버튼이 없다: 병사로 야생말을 길들인다. */
export const TRAIN_KEYS: [string, TrainKind][] = [['q', 'infantry'], ['w', 'archer'], ['e', 'warship']];
const UNIT_OF: Record<string, number> = { infantry: 0, archer: 1 };

const ICON = 40;      // 아이콘 칸 (CSS 픽셀)

function icon(src: HTMLCanvasElement): HTMLCanvasElement {
  const c = document.createElement('canvas');
  const k = Math.max(1, Math.floor(ICON / Math.max(src.width, src.height)));
  c.width = src.width * k; c.height = src.height * k;
  const g = c.getContext('2d')!;
  g.imageSmoothingEnabled = false;
  g.drawImage(src, 0, 0, c.width, c.height);
  c.className = 'act-icon';
  return c;
}

interface Btn { el: HTMLButtonElement; cost: number[]; build?: number; train?: TrainKind; sulfur?: number }

export class ActionBar {
  readonly el = document.createElement('div');
  private btns: Btn[] = [];

  constructor(private st: GameState, private ctl: Controller, bank: SpriteBank) {
    const R = st.info.rules, me = st.info.me;
    this.el.className = 'action-bar';
    const group = () => { const d = document.createElement('div'); d.className = 'act-group'; this.el.appendChild(d); return d; };
    const make = (parent: HTMLElement, key: string, img: HTMLCanvasElement, name: string, cost: number[], extra = '') => {
      const b = document.createElement('button');
      b.className = 'act-btn';
      const k = document.createElement('div');
      k.className = 'act-key';
      k.textContent = key.toUpperCase();
      b.append(k, icon(img));
      const c = cost.map((v, i) => (v ? `${R.res_names[i]} ${v}` : '')).filter(Boolean).join(', ');
      b.title = `${name}  [${key.toUpperCase()}]${c || extra ? `\n${[c, extra].filter(Boolean).join(', ')}` : ''}`;
      b.addEventListener('mousedown', (e) => e.stopPropagation());
      parent.appendChild(b);
      return b;
    };
    const gb = group();
    BUILD_KEYS.forEach((kind, i) => {
      const sul = R.build[kind].sulfur ?? 0;
      const el = make(gb, buildKeyLabel(i), bank.building(kind, me, 1), R.build_names[kind], R.build[kind].cost, sul ? `유황 ${sul}` : '');
      el.addEventListener('click', () => this.pickBuild(kind));
      this.btns.push({ el, cost: R.build[kind].cost, build: kind, sulfur: sul });
    });
    const gu = group();
    for (const [key, what] of TRAIN_KEYS) {
      const ui = UNIT_OF[what];
      const img = what === 'warship' ? bank.ship('warship', me, 1) : bank.unit(ui, me, 0, 1);
      const cost = what === 'warship' ? R.warship_cost : R.unit_cost[ui];
      const name = what === 'warship' ? '전함' : R.unit_names[ui];
      const el = make(gu, key, img, name, cost);
      el.addEventListener('click', () => this.ctl.train(what));
      this.btns.push({ el, cost, train: what });
    }
    document.body.appendChild(this.el);
  }

  /** 건물 버튼: 같은 건물을 다시 누르면 놓기를 그만둔다. */
  pickBuild(kind: number) { this.ctl.mode = this.ctl.mode === kind ? null : kind; this.update(); }

  /** 숫자 키 n (1~9) → 건물. 없는 번호면 false. */
  buildKey(n: number): boolean {
    const kind = n >= 1 ? BUILD_KEYS[n - 1] : undefined;
    if (kind === undefined) return false;
    this.pickBuild(kind);
    return true;
  }

  update() {
    const st = this.st, me = st.nations[st.info.me];
    const res = me?.res ?? [0, 0, 0];
    for (const b of this.btns) {
      const afford = b.cost.every((v, i) => res[i] >= v) && (me?.sulfur ?? 0) >= (b.sulfur ?? 0);
      let ok = afford;
      if (b.train) ok &&= this.ctl.producers(b.train).length > 0;
      b.el.classList.toggle('off', !ok);
      b.el.classList.toggle('on', b.build !== undefined && this.ctl.mode === b.build);
    }
  }

  dispose() { this.el.remove(); }
}
