// 내 부족 버튼 (sim/tribes.py): 왼쪽 위 자원 HUD 바로 오른쪽의 동그란 아이콘 버튼 (메뉴 버튼과 같은 빛깔).
// 누르면 버튼 아래에 말풍선 (외교 말풍선과 같은 모양): 부족 이름, 성격, 강점·약점, 적용 대상.
// 다른 곳을 누르거나 버튼을 다시 누르면 닫힌다. HUD 너비가 바뀌면 (유황 칩 등) 따라 옮긴다. 효과 수치는 docs/ECONOMY_PLAN.md 4장.

import { TRIBE_ICONS, icon } from '../ui/icons.ts';
import type { GameState } from './state.ts';

interface TribeText { title: string; role: string; good: string[]; bad: string[] }

/** 부족마다 설명 (sim/tribes.py 번호 순서: 온대, 설원, 사막). */
const TEXT: TribeText[] = [
  { title: '온대 부족', role: '병력을 빨리 모은다',
    good: ['병사 훈련 시간 ×0.85 (15% 빠르게)'],
    bad: ['설원에서: 이동 ×0.85, 추위에 체력이 조금씩 깎인다', '사막에서: 이동 ×0.85, 더위에 체력이 조금씩 깎이고, 갈증으로 먹는 식량 ×1.2'] },
  { title: '설원 부족', role: '지키기에 강하다',
    good: ['설원에서 받는 피해 ×0.85', '설원에서 눈 때문에 느려지지 않는다'],
    bad: ['사막에서: 이동 ×0.85, 더위에 체력이 조금씩 깎이고, 갈증으로 먹는 식량 ×1.2', '바위거북 길들이는 시간 ×1.5'] },
  { title: '사막 부족', role: '빠른 공격에 강하다',
    good: ['설원이 아닌 곳에서 공격력 ×1.2', '사막의 더위를 받지 않는다'],
    bad: ['설원에서: 이동 ×0.85, 추위에 체력이 조금씩 깎인다', '사막에서도 갈증으로 먹는 식량 ×1.2 (모든 부족 같다)', '드래곤 길들이는 시간 ×1.25'] },
];

const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]!));

export class TribeButton {
  private btn = document.createElement('button');
  private bubble = document.createElement('div');
  private shown = -1;
  private onDoc = (e: PointerEvent) => {                       // 다른 곳을 누르면 닫는다
    const t = e.target as Node;
    if (!this.bubble.contains(t) && !this.btn.contains(t)) this.close();
  };

  constructor(private st: () => GameState | null, private hud: () => HTMLElement | null) {
    this.btn.className = 'tribe-btn';
    this.btn.style.display = 'none';
    this.btn.addEventListener('click', (e) => { e.stopPropagation(); if (this.isOpen) this.close(); else this.open(); });
    this.btn.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.btn.addEventListener('mousedown', (e) => e.stopPropagation());
    this.bubble.className = 'diplo-bubble tribe-bubble';
    this.bubble.style.display = 'none';
    for (const ev of ['pointerdown', 'mousedown'] as const) this.bubble.addEventListener(ev, (e) => e.stopPropagation());
    document.body.append(this.btn, this.bubble);
    document.addEventListener('pointerdown', this.onDoc, true);
  }

  get isOpen() { return this.bubble.style.display !== 'none'; }

  /** 아이콘과 자리를 맞춘다 (HUD를 고칠 때마다). */
  update() {
    const st = this.st(), hud = this.hud();
    const t = st?.info.nations[st.info.me]?.tribe;
    if (t === undefined || t === null || !hud) { this.btn.style.display = 'none'; this.close(); this.shown = -1; return; }
    if (t !== this.shown) {
      this.shown = t;
      this.btn.innerHTML = icon(TRIBE_ICONS[t] ?? 'leaf', 18);
      this.btn.title = `${TEXT[t]?.title ?? ''} (눌러서 효과 보기)`;
    }
    this.btn.style.display = '';
    const r = hud.getBoundingClientRect();                       // 자원 HUD 바로 오른쪽, 위를 맞춘다
    this.btn.style.left = `${Math.round(r.right + 6)}px`;
    this.btn.style.top = `${Math.round(r.top + 2)}px`;
    if (this.isOpen) this.place();
  }

  private place() {
    const b = this.btn.getBoundingClientRect();
    this.bubble.style.left = `${Math.round(b.left + b.width / 2)}px`;
    this.bubble.style.top = `${Math.round(b.bottom + 10)}px`;
  }

  open() {
    const st = this.st();
    const t = st?.info.nations[st.info.me]?.tribe ?? 0;
    const x = TEXT[t] ?? TEXT[0];
    const rows = (cls: string, mark: string, items: string[]) =>
      `<div class="tribe-list ${cls}">${items.map((s) => `<div class="tribe-row"><span class="tribe-mark">${mark}</span><span>${esc(s)}</span></div>`).join('')}</div>`;
    this.bubble.innerHTML = `<div class="dhead tribe-title">${icon(TRIBE_ICONS[t] ?? 'leaf', 20)}<span>${x.title}</span>`
      + `<span class="tribe-role">${x.role}</span></div>`
      + (x.good.length ? rows('good', '▲', x.good) : '') + rows('bad', '▼', x.bad)
      + `<div class="tribe-note">시작 거점 둘레의 지형으로 정해진다. 병사(보병·궁수·창기병·기마궁수)만 받는다 (용기사·바위거북·배는 아니다). `
      + `추위·더위로는 체력이 30% 아래로 깎이지 않는다.</div>`;
    this.bubble.style.display = '';
    this.btn.classList.add('on');
    this.place();
  }

  close() { this.bubble.style.display = 'none'; this.btn.classList.remove('on'); }

  dispose() {
    document.removeEventListener('pointerdown', this.onDoc, true);
    this.btn.remove();
    this.bubble.remove();
  }
}
