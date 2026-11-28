// 내 부족 버튼 (sim/tribes.py): 왼쪽 위 자원 HUD 바로 오른쪽의 동그란 아이콘 버튼 (메뉴 버튼과 같은 빛깔).
// 누르면 버튼 아래에 말풍선 (외교 말풍선과 같은 모양): 부족 이름, 성격, 강점·약점, 적용 대상.
// 다른 곳을 누르거나 버튼을 다시 누르면 닫힌다. HUD 너비가 바뀌면 (유황 칩 등) 따라 옮긴다. 효과 수치는 docs/ECONOMY_PLAN.md 4장.
// 개척 (sim/tribes.py Pioneer): 다른 기후에 거점을 다 지으면 서버가 카드를 보낸다 ('tribe' 메시지) → 가운데에 카드 두 장
// (지금 부족 지키기 / 새 기후 부족으로 바꾸기). '나중에'로 닫으면 버튼에 느낌표가 남고, 버튼을 누르면 다시 연다.

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

const NAMES = ['온대', '설원', '사막'];

const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]!));

export class TribeButton {
  private btn = document.createElement('button');
  private bubble = document.createElement('div');
  private shown = -1;
  private cards = document.createElement('div');             // 개척 카드 (가운데)
  private seenOffer = '';                                       // 저절로 띄운 카드 (같은 카드를 다시 띄우지 않게)
  private onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && this.cardsOpen) { e.stopPropagation(); this.closeCards(); } };
  private onDoc = (e: PointerEvent) => {                       // 다른 곳을 누르면 닫는다
    const t = e.target as Node;
    if (!this.bubble.contains(t) && !this.btn.contains(t)) this.close();
  };

  constructor(private st: () => GameState | null, private hud: () => HTMLElement | null, private send: (accept: boolean) => void) {
    this.btn.className = 'tribe-btn';
    this.btn.style.display = 'none';
    this.btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.offer() >= 0) { this.close(); this.openCards(); return; }   // 기다리는 카드가 있으면 카드부터
      if (this.isOpen) this.close(); else this.open();
    });
    this.cards.className = 't-menu-back tribe-cards-back';
    this.cards.style.display = 'none';
    for (const ev of ['pointerdown', 'mousedown', 'wheel'] as const) this.cards.addEventListener(ev, (e) => e.stopPropagation());
    document.body.append(this.cards);
    document.addEventListener('keydown', this.onKey, true);
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
    const pend = this.offer() >= 0;
    if (t !== this.shown || pend !== this.btn.classList.contains('pending')) {
      this.shown = t;
      this.btn.innerHTML = icon(TRIBE_ICONS[t] ?? 'leaf', 18) + (pend ? '<span class="tribe-alert">!</span>' : '');
      this.btn.classList.toggle('pending', pend);
      this.btn.title = pend ? '새 기후의 부족을 고를 수 있습니다 (눌러서 카드 보기)' : `${TEXT[t]?.title ?? ''} (눌러서 효과 보기)`;
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
      + `<div class="tribe-note">시작 거점 둘레의 지형으로 정해진다. 다른 기후에 거점을 세우면 그 부족으로 바꿀 수 있다 `
      + `(스스로 버린 기후는 다시 못 고른다. 지금 부족 기후의 거점을 모두 잃으면 거점이 가장 많은 기후의 부족이 된다). `
      + `병사(보병·궁수·척탄병과 그 기병)만 받는다 (용기사·바위거북·배는 아니다). 추위·더위로는 체력이 30% 아래로 깎이지 않는다.`
      + (st?.tribe.dropped.length ? `<br><b>버린 기후:</b> ${st.tribe.dropped.map((c) => NAMES[c]).join(', ')}` : '') + `</div>`;
    this.bubble.style.display = '';
    this.btn.classList.add('on');
    this.place();
  }

  close() { this.bubble.style.display = 'none'; this.btn.classList.remove('on'); }

  /** 기다리는 카드의 기후 (없으면 -1). */
  private offer(): number { return this.st()?.tribe.offers[0] ?? -1; }
  get cardsOpen() { return this.cards.style.display !== 'none'; }

  /** 서버가 부족·카드를 보냈다: 새 카드면 저절로 띄우고, 카드가 없어졌으면 닫는다. */
  sync() {
    const st = this.st(), c = this.offer();
    const key = c >= 0 ? `${c}:${st?.tribe.offers.length}:${st?.tribe.dropped.join(',')}` : '';
    if (c < 0) this.closeCards();
    else if (key !== this.seenOffer) { this.seenOffer = key; this.openCards(); }
    else if (this.cardsOpen) this.openCards(false);              // 이미 떠 있으면 내용만 (애니메이션 없이)
    this.update();
  }

  /** 카드 두 장: 지금 부족 지키기 / 새 기후의 부족으로 바꾸기. 고르지 않은 쪽은 다시 고를 수 없다.
   *  anim: 뜰 때 애니메이션 (배경이 어두워지고 → 창이 튀어 오르고 → 카드가 차례로 뒤집혀 나타나고 → 새 부족 카드에 금빛이 스친다). */
  openCards(anim = true) {
    const st = this.st(), c = this.offer();
    if (!st || c < 0) return;
    const cur = st.info.nations[st.info.me]?.tribe ?? 0;
    const card = (t: number, tag: string, btn: string, accept: boolean) => {
      const x = TEXT[t] ?? TEXT[0];
      const rows = (cls: string, mark: string, items: string[]) =>
        `<div class="tribe-list ${cls}">${items.map((s) => `<div class="tribe-row"><span class="tribe-mark">${mark}</span><span>${esc(s)}</span></div>`).join('')}</div>`;
      return `<div class="tribe-card${accept ? ' new' : ''}"><div class="tribe-tag">${tag}</div>`
        + (accept ? '<div class="tribe-shine"></div>' : '')
        + `<div class="tribe-card-icon">${icon(TRIBE_ICONS[t] ?? 'leaf', 40)}</div>`
        + `<div class="tribe-card-title"><span class="tribe-mini">${icon(TRIBE_ICONS[t] ?? 'leaf', 20)}</span>${x.title}</div><div class="tribe-role">${x.role}</div>`
        + `<div class="tribe-card-body">${x.good.length ? rows('good', '▲', x.good) : ''}${rows('bad', '▼', x.bad)}</div>`
        + `<button class="t-btn tribe-pick" data-accept="${accept ? 1 : 0}">${btn}</button></div>`;
    };
    this.cards.innerHTML = `<div class="t-menu tribe-cards"><div class="t-menu-title">새 땅의 부족</div>`
      + `<div class="tribe-cards-sub">${NAMES[c]} 지역에 거점을 세웠다. 부족을 고르자. 고르지 않은 쪽의 기후 특성은 다시 고를 수 없다.</div>`
      + `<div class="tribe-card-row">${card(cur, '지금 부족', `${NAMES[cur]} 지키기`, false)}${card(c, '새 부족', `${NAMES[c]}으로 바꾸기`, true)}</div>`
      + (st.tribe.dropped.length ? `<div class="tribe-cards-note">이미 버린 기후: ${st.tribe.dropped.map((d) => NAMES[d]).join(', ')}</div>` : '')
      + `<button class="dbtn tribe-later">나중에 고르기</button></div>`;
    for (const b of this.cards.querySelectorAll<HTMLButtonElement>('.tribe-pick')) {
      b.addEventListener('click', () => { this.send(b.dataset.accept === '1'); this.closeCards(); });
    }
    this.cards.querySelector('.tribe-later')?.addEventListener('click', () => this.closeCards());
    this.cards.classList.toggle('anim', anim);
    this.cards.style.display = '';
  }

  closeCards() { this.cards.style.display = 'none'; }

  dispose() {
    document.removeEventListener('pointerdown', this.onDoc, true);
    document.removeEventListener('keydown', this.onKey, true);
    this.btn.remove();
    this.bubble.remove();
    this.cards.remove();
  }
}
