// 대화 (사람이 여럿인 판): 서버 server/session.py의 chat을 판의 모든 사람이 받는다. 화면 왼쪽 아래 알림 줄(hud-msgs)에 함께 보인다.
// PC: 알림 줄 아래 [입력바][보내기][💬 빠른 대화]. Enter로 입력, Esc로 빠져나온다.
//     처음엔 접혀 있다 (화면 왼쪽 아래 동그란 💬 버튼). 펼친 뒤 IDLE ms 동안 쓰지 않으면 입력바가 그 버튼으로 빨려 들어간다
//     (알림·대화 줄은 그대로).
//     그 버튼이나 Enter로 다시 펼친다 (펼치면 버튼은 사라진다). 입력 중·마우스를 올린 동안·빠른 대화를 연 동안은 접지 않는다.
//     빠른 대화: 원을 같은 간격으로 나눈 선택판 (가운데 ✕) — 칸을 누르면 그 대사를 보낸다.
// 모바일: 오른쪽 위 버튼 줄에 💬 (읽지 않은 수). 누르면 큰 대화창: 위 오른쪽 ✕, 아래 입력, 창 왼쪽 바깥에 빠른 대사 버튼 세로로.

import type { Connection } from './net.ts';
import type { GameState } from './state.ts';
import { touchMode } from '../ui/device.ts';

export const QUICK = ['안녕하세요!', '준비됐어요', '동맹할래요?', '같이 쳐요!', '도와주세요!', '잠깐만요', '고마워요', '좋은 판이었어요'];
const MAX = 80;                                         // server/session.py CHAT_MAX
const IDLE = 5000;                                      // PC: 이만큼(ms) 안 쓰면 입력바를 접는다

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls: string, parent?: HTMLElement, text?: string) {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  parent?.appendChild(e);
  return e;
}

/** 이름 (나라 색) + 글 한 줄. */
export function chatLine(st: GameState, from: number, text: string, cls = 'chat-line'): HTMLDivElement {
  const d = el('div', cls);
  const n = st.info.nations[from];
  const name = el('b', 'chat-name', d, `${n?.name ?? '?'}: `);
  if (n) name.style.color = `rgb(${n.light.join(',')})`;
  d.append(text);
  return d;
}

export class Chat {
  private bar = el('div', 'chat-bar');                 // PC
  private input: HTMLInputElement;
  private wheel: HTMLDivElement | null = null;
  private mbtn: HTMLButtonElement | null = null;       // 모바일: 오른쪽 위 💬
  private badge: HTMLSpanElement | null = null;
  private dlg: HTMLDivElement | null = null;           // 모바일 대화창
  private log: HTMLDivElement | null = null;
  private unread = 0;
  private dock = el('button', 'chat-dock');            // PC: 접힌 입력바 (동그란 💬)
  private timer = 0;
  private hover = false;

  constructor(private st: () => GameState | null, private net: Connection, private changed: () => void) {
    this.input = el('input', 'chat-input', this.bar);
    this.input.maxLength = MAX;
    this.input.placeholder = 'Enter: 대화';
    this.input.addEventListener('keydown', (e) => {
      e.stopPropagation();                             // 게임 단축키로 가지 않게
      if (e.key === 'Enter' && !e.isComposing) { this.send(this.input.value); this.input.value = ''; this.input.blur(); }
      else if (e.key === 'Escape') this.input.blur();
    });
    this.input.addEventListener('focus', () => { document.body.classList.add('chat-typing'); clearTimeout(this.timer); this.changed(); });
    this.input.addEventListener('blur', () => { document.body.classList.remove('chat-typing'); this.idle(); this.changed(); });
    this.bar.addEventListener('mouseenter', () => { this.hover = true; clearTimeout(this.timer); });
    this.bar.addEventListener('mouseleave', () => { this.hover = false; this.idle(); });
    const send = el('button', 'dbtn', this.bar, '보내기');
    send.addEventListener('click', () => { this.send(this.input.value); this.input.value = ''; });
    const q = el('button', 'dbtn chat-quick-btn', this.bar, '💬 빠른 대화');
    q.addEventListener('click', () => this.openWheel());
    document.body.appendChild(this.bar);
    this.dock.textContent = '💬';
    this.dock.title = '대화 (Enter)';
    this.dock.addEventListener('click', (e) => { e.stopPropagation(); this.wake(true); });
    document.body.appendChild(this.dock);
    this.fold(true);                                     // 처음엔 접힌 채로
    // 모바일: 오른쪽 위 버튼 줄(touchUi의 .t-top) 맨 앞에
    const top = document.querySelector('.t-top');
    if (top) {
      this.mbtn = el('button', 't-btn chat-mbtn', undefined, '💬');
      this.badge = el('span', 'chat-badge', this.mbtn);
      this.mbtn.addEventListener('click', (e) => { e.stopPropagation(); this.openDialog(); });
      top.prepend(this.mbtn);
    }
    this.setBadge();
  }

  dispose() { clearTimeout(this.timer); this.bar.remove(); this.dock.remove(); this.mbtn?.remove(); this.closeWheel(); this.closeDialog(); }

  // ------------------------------------------------------------- PC: 입력바 접기 · 펼치기
  /** IDLE 뒤에 접기 (그때도 쓰는 중이면 다시 기다린다). */
  private idle() {
    clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      if (this.typing || this.hover || this.wheel) this.idle();
      else this.fold();
    }, IDLE);
  }

  /** 입력바가 왼쪽 아래 동그란 버튼으로 빨려 들어간다 (now: 움직임 없이 바로, 처음 한 번). */
  private fold(now = false) {
    clearTimeout(this.timer);
    const b = this.bar.getBoundingClientRect(), d = this.dock.getBoundingClientRect();
    const dx = d.left + d.width / 2 - b.left, dy = d.top + d.height / 2 - (b.top + b.height / 2);   // 입력바 왼쪽 끝 → 버튼 가운데
    if (now) this.bar.classList.add('instant');
    this.bar.style.transform = `translate(${dx}px, ${dy}px) scale(0.06)`;
    this.bar.classList.add('docked');
    this.dock.classList.add('show');
    if (now) requestAnimationFrame(() => requestAnimationFrame(() => this.bar.classList.remove('instant')));
  }

  /** 다시 펼친다 (focus: 바로 입력). 버튼은 사라진다. */
  private wake(focus: boolean) {
    this.bar.style.transform = '';
    this.bar.classList.remove('docked');
    this.dock.classList.remove('show');
    if (focus) this.input.focus(); else this.idle();
  }

  get typing() { return document.activeElement === this.input; }

  /** PC: Enter로 입력 칸에 (접혀 있으면 펼치고). */
  focus() { if (!touchMode()) this.wake(true); }

  /** 무언가 열려 있으면 닫는다 (Esc). */
  close(): boolean {
    if (this.wheel) { this.closeWheel(); return true; }
    if (this.dlg) { this.closeDialog(); return true; }
    return false;
  }

  private send(text: string) {
    const t = text.trim().slice(0, MAX);
    if (t) this.net.send({ t: 'chat', text: t });
  }

  /** 서버에서 대화가 왔다 (state에는 이미 쌓였다). */
  received(from: number, text: string) {
    const st = this.st();
    if (!st) return;
    if (this.log) { this.log.appendChild(chatLine(st, from, text)); this.log.scrollTop = this.log.scrollHeight; }
    else if (from !== st.info.me) { this.unread++; this.setBadge(); }
  }

  private setBadge() {
    if (!this.badge) return;
    this.badge.textContent = this.unread > 9 ? '9+' : String(this.unread);
    this.badge.style.display = this.unread ? '' : 'none';
  }

  // ------------------------------------------------------------- PC: 빠른 대화 선택판 (원을 같은 간격으로)
  openWheel() {
    if (this.wheel) return;
    const back = (this.wheel = el('div', 'chat-wheel-back', document.body));
    const S = 420, c = S / 2, r0 = 66, r1 = 196, n = QUICK.length, gap = 0.035;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${S} ${S}`);
    svg.setAttribute('class', 'chat-wheel');
    const pt = (r: number, a: number) => `${(c + r * Math.cos(a)).toFixed(1)} ${(c + r * Math.sin(a)).toFixed(1)}`;
    QUICK.forEach((text, i) => {
      const a0 = -Math.PI / 2 - Math.PI / n + (i * 2 * Math.PI) / n + gap, a1 = a0 + (2 * Math.PI) / n - 2 * gap;
      const g = document.createElementNS(ns, 'g');
      g.setAttribute('class', 'chat-sector');
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', `M${pt(r0, a0)} L${pt(r1, a0)} A${r1} ${r1} 0 0 1 ${pt(r1, a1)} L${pt(r0, a1)} A${r0} ${r0} 0 0 0 ${pt(r0, a0)} Z`);
      g.appendChild(p);
      const am = (a0 + a1) / 2, rm = (r0 + r1) / 2 + 4;
      const lines = text.length > 6 && text.includes(' ') ? [text.slice(0, text.indexOf(' ')), text.slice(text.indexOf(' ') + 1)] : [text];
      lines.forEach((ln, k) => {
        const t = document.createElementNS(ns, 'text');
        t.setAttribute('x', (c + rm * Math.cos(am)).toFixed(1));
        t.setAttribute('y', (c + rm * Math.sin(am) + (k - (lines.length - 1) / 2) * 18).toFixed(1));
        t.textContent = ln;
        g.appendChild(t);
      });
      const num = document.createElementNS(ns, 'text');
      num.setAttribute('class', 'chat-num');
      num.setAttribute('x', (c + rm * Math.cos(am)).toFixed(1));                       // 번호: 대사 바로 위
      num.setAttribute('y', (c + rm * Math.sin(am) - (lines.length - 1) * 9 - 22).toFixed(1));
      num.textContent = String(i + 1);
      g.appendChild(num);
      g.addEventListener('click', (e) => { e.stopPropagation(); this.send(text); this.closeWheel(); });
      svg.appendChild(g);
    });
    const mid = document.createElementNS(ns, 'g');
    mid.setAttribute('class', 'chat-center');
    const cc = document.createElementNS(ns, 'circle');
    cc.setAttribute('cx', String(c)); cc.setAttribute('cy', String(c)); cc.setAttribute('r', String(r0 - 10));
    const ct = document.createElementNS(ns, 'text');
    ct.setAttribute('x', String(c)); ct.setAttribute('y', String(c));
    ct.textContent = '✕';
    mid.append(cc, ct);
    mid.addEventListener('click', (e) => { e.stopPropagation(); this.closeWheel(); });
    svg.appendChild(mid);
    back.appendChild(svg);
    el('div', 'chat-wheel-hint', back, '대사를 누르면 바로 보냅니다 · 숫자 키 1~8 · Esc: 닫기');
    back.addEventListener('click', () => this.closeWheel());
    back.tabIndex = -1;
    back.addEventListener('keydown', (e) => {
      e.stopPropagation();
      const k = Number(e.key);
      if (k >= 1 && k <= n) { this.send(QUICK[k - 1]); this.closeWheel(); }
      else if (e.key === 'Escape') this.closeWheel();
    });
    back.focus();
  }

  private closeWheel() { if (!this.wheel) return; this.wheel.remove(); this.wheel = null; this.idle(); }

  // ------------------------------------------------------------- 모바일: 큰 대화창
  openDialog() {
    const st = this.st();
    if (this.dlg || !st) return;
    const back = (this.dlg = el('div', 'chat-dlg-back', document.body));
    const quick = el('div', 'chat-mquick', back);           // 창 왼쪽 바깥: 빠른 대사 (세로)
    for (const q of QUICK) {
      const b = el('button', 't-btn', quick, q);
      b.addEventListener('click', (e) => { e.stopPropagation(); this.send(q); });
    }
    const box = el('div', 'chat-dlg', back);
    const head = el('div', 'chat-dlg-head', box);
    el('div', 'chat-dlg-title', head, '대화');
    const x = el('button', 'chat-dlg-x', head, '✕');
    x.addEventListener('click', () => this.closeDialog());
    this.log = el('div', 'chat-dlg-log', box);
    for (const m of st.chatLog) this.log.appendChild(chatLine(st, m.from, m.text));
    if (!st.chatLog.length) el('div', 'chat-empty', this.log, '아직 대화가 없습니다. 왼쪽 빠른 대사나 아래 입력창으로 말해 보세요');
    const foot = el('div', 'chat-dlg-foot', box);
    const inp = el('input', 'chat-input', foot);
    inp.maxLength = MAX;
    inp.placeholder = '할 말을 입력하세요';
    const go = () => { this.send(inp.value); inp.value = ''; };
    inp.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter' && !e.isComposing) go(); });
    el('button', 't-btn ok', foot, '보내기').addEventListener('click', go);
    back.addEventListener('click', (e) => { if (e.target === back) this.closeDialog(); });
    requestAnimationFrame(() => { if (this.log) this.log.scrollTop = this.log.scrollHeight; });
    this.unread = 0;
    this.setBadge();
  }

  private closeDialog() { this.dlg?.remove(); this.dlg = null; this.log = null; }
}
