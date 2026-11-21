// 터치 화면 (body.touch일 때만 보인다): PC의 키보드 단축키를 손가락으로 누르는 버튼으로.
//   위 오른쪽   [⏸] [×1] [☰]      일시정지(P), 속도(.), 메뉴 (도움말, 같은 지도로 새 판 F5, 새 지도 F6, 로비로 F10)
//   왼쪽        [1] [2] [3]        부대: 탭 = 부르기, 길게 = 지정 (Shift+숫자 / Ctrl+숫자)
//   오른쪽      [⌂] [▣]            내 거점으로 (Space), 화면 안 내 병사 모두 고르기
//   아래        고른 것 한 줄 + [⚔ 공격이동] [■ 정지] [+ 더하기] [✕ 풀기]   (A, S, Shift, Esc)
//   건물 놓기   건물 그림 옆에 [✓ 짓기] [✕]  (그림을 가리지 않게 아래, 화면 아래쪽이면 위)
//   길게 누르기  그 자리 설명 카드 (손가락에 가리지 않게 위로)

import type { Camera } from '../sim/camera.ts';
import type { Controller } from './controller.ts';
import type { GameState } from './state.ts';
import { unitCounts } from './hud.ts';
import type { TouchInput } from './touch.ts';
import { addToHomeHint, canFullscreen, enterFullscreen, isStandalone } from '../ui/device.ts';

export interface TouchUiHooks {
  st(): GameState | null;
  ctl(): Controller | null;
  cam: Camera;
  touch: TouchInput;
  infoAt(mx: number, my: number): string | null;
  pause(): void;
  speed(): void;
  home(): void;
  restart(): void;
  newMap(): void;
  lobby(): void;
  changed(): void;
}

const HELP = [
  ['고르기', '내 병사·건물·배를 탭. 멀리서 보면 무리 배지를 탭하면 그 무리 전체'],
  ['여러 명', '길게 누른 채 끌어서 상자로 고르기, 또는 오른쪽 ▣ (화면 안 내 병사 모두)'],
  ['명령', '고른 뒤 땅을 탭하면 이동, 적을 탭하면 공격, 빈 자원지를 탭하면 짓기 (바다 건너면 배를 탄다)'],
  ['화면', '한 손가락으로 끌어 이동, 두 손가락으로 벌리고 오므려 확대'],
  ['건물', '아래 건물 버튼 → 그림을 탭이나 끌기로 옮기고 ✓. 고른 병사가 없으면 가까운 쉬는 병사가 짓는다'],
  ['훈련', '아래 보병·궁수·전함 버튼. 거점이나 항구를 골라 두면 그곳에서, 아니면 돌아가며'],
  ['부대', '왼쪽 1~3: 길게 누르면 지금 고른 병사를 부대로, 탭하면 부르기'],
  ['설명', '빈 땅을 길게 누르면 지형·자원지 설명'],
];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, parent: HTMLElement, text?: string) {
  const d = document.createElement(tag);
  d.className = cls;
  if (text !== undefined) d.textContent = text;
  parent.appendChild(d);
  return d;
}

export class TouchUi {
  readonly root = el('div', 't-root', document.body);
  private top = el('div', 't-top', this.root);
  private pauseBtn: HTMLButtonElement;
  private speedBtn: HTMLButtonElement;
  private groups = el('div', 't-groups', this.root);
  private side = el('div', 't-side', this.root);
  private selRow = el('div', 't-selrow', this.root);
  private selLabel = el('div', 't-sellabel', this.selRow);
  private atkBtn: HTMLButtonElement;
  private stopBtn: HTMLButtonElement;
  private addBtn: HTMLButtonElement;
  private confirm = el('div', 't-confirm', this.root);
  private okBtn: HTMLButtonElement;
  private info = el('div', 't-info', this.root);
  private infoUntil = 0;
  private menu: HTMLDivElement | null = null;
  private groupBtns: HTMLButtonElement[] = [];

  constructor(private h: TouchUiHooks) {
    const btn = (parent: HTMLElement, text: string, cls: string, fn: () => void) => {
      const b = el('button', `t-btn ${cls}`, parent, text);
      b.addEventListener('click', (e) => { e.stopPropagation(); fn(); this.h.changed(); });
      return b;
    };
    this.pauseBtn = btn(this.top, '⏸', '', () => h.pause());
    this.speedBtn = btn(this.top, '×1', '', () => h.speed());
    btn(this.top, '☰', '', () => this.openMenu());
    for (let n = 1; n <= 3; n++) this.groupBtns.push(this.groupButton(n));
    btn(this.side, '⌂', '', () => h.home()).title = '내 거점으로';
    btn(this.side, '▣', '', () => this.selectOnScreen()).title = '화면 안 내 병사 모두';
    this.atkBtn = btn(this.selRow, '⚔ 공격이동', 'warm', () => { const c = h.ctl(); if (c && c.sel.size) c.mode = c.mode === 'attack' ? null : 'attack'; });
    this.stopBtn = btn(this.selRow, '■ 정지', '', () => h.ctl()?.stop());
    this.addBtn = btn(this.selRow, '+ 더하기', '', () => { h.touch.add = !h.touch.add; });
    btn(this.selRow, '✕', '', () => { const c = h.ctl(); if (c) { c.sel.clear(); c.selShips.clear(); c.selB = null; c.mode = null; } h.touch.add = false; });
    this.okBtn = btn(this.confirm, '✓ 짓기', 'ok', () => this.build());
    btn(this.confirm, '✕', '', () => { const c = h.ctl(); if (c) c.mode = null; });
  }

  dispose() { this.root.remove(); this.menu?.remove(); }

  /** 부대 버튼: 탭 = 부르기, 길게 누르기 = 지금 고른 병사를 이 부대로. */
  private groupButton(n: number) {
    const b = el('button', 't-btn t-group', this.groups, String(n));
    let timer = 0, held = false;
    b.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      held = false;
      timer = window.setTimeout(() => {
        held = true;
        const c = this.h.ctl();
        if (c) { c.setGroup(n); navigator.vibrate?.(20); this.h.changed(); }
      }, 500);
    });
    const end = (recall: boolean) => {
      clearTimeout(timer);
      if (recall && !held) { this.h.ctl()?.recallGroup(n); this.h.changed(); }
    };
    b.addEventListener('pointerup', () => end(true));
    b.addEventListener('pointercancel', () => end(false));
    b.addEventListener('pointerleave', () => clearTimeout(timer));
    return b;
  }

  private selectOnScreen() {
    const c = this.h.ctl(), cam = this.h.cam;
    if (!c) return;
    const [vw, vh] = cam.view();
    c.selectBox(cam.x, cam.y, cam.x + vw, cam.y + vh, this.h.touch.add);
  }

  private build() {
    const c = this.h.ctl(), g = this.h.touch.ghost;
    if (!c || !g || typeof c.mode !== 'number') return;
    c.place(g[0], g[1], this.h.cam.zoom, false);
  }

  private openMenu() {
    if (this.menu) return;
    const back = (this.menu = el('div', 't-menu-back', document.body));
    const box = el('div', 't-menu', back);
    el('div', 't-menu-title', box, '메뉴');
    const row = el('div', 't-menu-row', box);
    const item = (text: string, fn: () => void) => {
      const b = el('button', 't-btn wide', row, text);
      b.addEventListener('click', () => { this.closeMenu(); fn(); });
    };
    item('같은 지도로 새 판', () => this.h.restart());
    item('새 지도', () => this.h.newMap());
    item('로비로', () => this.h.lobby());
    if (canFullscreen() && !isStandalone() && !document.fullscreenElement) item('전체 화면 (주소창 내리기)', () => void enterFullscreen());
    item('닫기', () => {});
    const hint = addToHomeHint();
    if (hint) el('div', 't-help', box, hint);
    el('div', 't-menu-head', box, '조작');
    for (const [k, v] of HELP) {
      const line = el('div', 't-help', box);
      el('b', '', line, k);
      line.append(` ${v}`);
    }
    back.addEventListener('click', (e) => { if (e.target === back) this.closeMenu(); });
  }

  private closeMenu() { this.menu?.remove(); this.menu = null; }

  /** 길게 누른 자리 설명 (sx < 0이면 닫기). 손가락에 가리지 않게 위쪽에. */
  showInfo(sx: number, sy: number) {
    const c = this.h.cam;
    const text = sx >= 0 ? this.h.infoAt(...c.toMap(sx, sy)) : null;
    if (!text) { this.info.style.display = 'none'; this.infoUntil = 0; return; }
    this.info.textContent = text;
    this.info.style.display = 'block';
    const w = Math.min(320, window.innerWidth - 24);
    this.info.style.maxWidth = `${w}px`;
    const rect = this.info.getBoundingClientRect();
    const x = Math.min(Math.max(sx - rect.width / 2, 12), window.innerWidth - rect.width - 12);
    const y = sy - rect.height - 56 >= 8 ? sy - rect.height - 56 : sy + 48;
    this.info.style.left = `${x}px`;
    this.info.style.top = `${y}px`;
    this.infoUntil = performance.now() + 3200;
  }

  /** 4번/초: 버튼 상태와 고른 것 한 줄. */
  update() {
    const st = this.h.st(), c = this.h.ctl();
    if (!st || !c) return;
    this.pauseBtn.textContent = st.paused ? '▶' : '⏸';
    this.speedBtn.textContent = `×${st.speed}`;
    this.groupBtns.forEach((b, i) => {
      const g = c.groups.get(i + 1);
      const n = g ? [...g].filter(([s, gen]) => st.units.get(s)?.gen === gen).length : 0;
      b.dataset.count = n ? String(n) : '';
    });
    c.prune();
    const has = c.sel.size > 0 || c.selShips.size > 0 || c.selB !== null;
    this.selRow.style.display = has ? '' : 'none';
    this.selLabel.textContent = this.selText(st, c);
    this.atkBtn.style.display = c.sel.size ? '' : 'none';
    this.atkBtn.classList.toggle('on', c.mode === 'attack');
    this.stopBtn.style.display = c.sel.size || c.selShips.size ? '' : 'none';
    this.addBtn.classList.toggle('on', this.h.touch.add);
    if (this.infoUntil && performance.now() > this.infoUntil) this.showInfo(-1, -1);
  }

  /** 매 프레임: 건물 놓기 ✓ 버튼을 그림 옆에 (그림을 가리지 않게). */
  frame() {
    const c = this.h.ctl(), g = this.h.touch.ghost, cam = this.h.cam;
    const placing = !!c && typeof c.mode === 'number' && !!g;
    this.confirm.style.display = placing ? 'flex' : 'none';
    if (!placing) return;
    const t = c!.placeTarget(c!.mode as number, g![0], g![1], cam.zoom);
    this.okBtn.disabled = !t.ok;
    const sx = (t.x - cam.x) * cam.zoom, sy = (t.y - cam.y) * cam.zoom;
    const r = this.h.st()!.info.rules.build[c!.mode as number].r * cam.zoom + 22;   // 건물 반지름 + 여유 (그림을 가리지 않게)
    const rect = this.confirm.getBoundingClientRect();
    const below = sy + r + rect.height < window.innerHeight - 150;          // 아래 막대와 겹치면 위로
    const x = Math.min(Math.max(sx - rect.width / 2, 8), window.innerWidth - rect.width - 8);
    this.confirm.style.left = `${x}px`;
    this.confirm.style.top = `${below ? sy + r : Math.max(sy - r - rect.height - 20, 60)}px`;
  }

  private selText(st: GameState, c: Controller): string {
    const R = st.info.rules, parts: string[] = [];
    if (c.sel.size) {
      parts.push(unitCounts(st, c.sel.keys(), ' · '));
    }
    if (c.selShips.size) {
      const boats = [...c.selShips].map((id) => st.boats.get(id)!).filter(Boolean);
      const war = boats.filter((b) => b.kind === 1).length, fer = boats.filter((b) => b.kind === 0);
      if (war) parts.push(`전함 ${war}`);
      if (fer.length) parts.push(`나룻배 ${fer.length} (병사 ${fer.reduce((s, b) => s + b.cargo, 0)})`);
    }
    const b = c.selB ? st.builds.get(c.selB[0]) : null;
    if (b) {
      let s = `${R.build_names[b.kind]} ${Math.round(b.hp * 100)}%`;
      if (b.prog < 1) s += ` · 짓는 중 ${Math.round(b.prog * 100)}%`;
      else if (b.qlen) s += ` · 대기 ${b.qlen}`;
      parts.push(s);
    }
    return parts.join('  ');
  }

  /** 가림 검사에 쓸 요소들. */
  panels(): HTMLElement[] { return [this.top, this.groups, this.side, this.selRow, this.info]; }
}
