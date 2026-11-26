// 외교 화면 (서버 sim/diplomacy.py): 다른 나라의 거점을 누르면 그 위에 말풍선 (동맹 요청, 동맹끼리 할 일, 공격 요청),
// 위 가운데에는 들어온 동맹 요청과 연장 물음 (수락 · 거절). 상태는 서버가 바뀔 때마다 보내는 'diplo' 메시지.
// 동맹끼리 (말풍선 안): 자원 보내기 (보낼 자원을 여럿 고르고 (처음엔 모두) 슬라이더 하나로 가진 것의 몇 %, 유황도),
// 병력 보내기 (고른 병사가 동맹의 가장 가까운 거점으로 가서 닿으면 합류).

import type { Camera } from '../sim/camera.ts';
import type { Controller } from './controller.ts';
import type { Connection } from './net.ts';
import type { BuildRec } from './protocol.ts';
import type { GameState } from './state.ts';

export interface DiploState {
  allies: Record<string, number>;          // 동맹 나라 → 남은 초
  extend: number[];                        // 연장을 물을 동맹
  incoming: number[];                      // 나에게 동맹을 청한 나라
  outgoing: number[];                      // 내가 청한 나라
  cooldown: Record<string, number>;        // 거절당해 다시 청하기까지 남은 초
  pairs: number[][];                       // 모든 동맹 [a, b]
  traitors: Record<string, number>;        // 배신자 → 남은 초
  theirs: number[];                        // 그 나라가 나를 보는 눈 (0 적대 · 1 경계 · 2 보통 · 3 우호)
  mine: number[];
  targets: number[][];                     // [요청한 나라, 칠 나라, 남은 초] (나와 내 동맹의 것)
  donate_cd: number;                       // 자원 보내기까지 남은 초
  troop_cd: number;                        // 병력 보내기까지 남은 초
  donate_max: number;                      // 한 번에 보낼 수 있는 비율
  ally_time: number; extend_prompt: number; traitor_time: number;
}

export const LEVELS = ['적대', '경계', '보통', '우호'];
export const LEVEL_COLORS = ['rgb(255,120,110)', 'rgb(255,200,120)', 'rgb(220,220,220)', 'rgb(150,230,150)'];
const mmss = (s: number) => `${Math.floor(Math.max(s, 0) / 60)}:${String(Math.max(s, 0) % 60).padStart(2, '0')}`;

export class DiploUi {
  private bubble = document.createElement('div');
  private prompts = document.createElement('div');
  private open: { nid: number; slot: number; gen: number } | null = null;
  private confirmBreak = false;
  private sig = '';                        // 버튼을 다시 만들지 (할 수 있는 일이 바뀌었을 때만)
  private psig = '';
  private head = document.createElement('div');
  private info = document.createElement('div');
  private body = document.createElement('div');
  // 자원 보내기 (동맹 말풍선 안): 보낼 자원 (여럿) + 슬라이더 하나 (고른 값은 다시 열어도 남는다)
  private resPick = [true, true, true, true];   // 식량 · 목재 · 석재 · 유황 (처음엔 모두)
  private resPct = 20;
  private amountEl: HTMLElement | null = null;
  private sendBtn: HTMLButtonElement | null = null;
  private troopBtn: HTMLButtonElement | null = null;

  constructor(private st: GameState, private ctl: Controller, private net: Connection) {
    this.bubble.className = 'diplo-bubble';
    this.bubble.style.display = 'none';
    this.prompts.className = 'diplo-prompts';
    this.head.className = 'dhead';
    this.info.className = 'dinfo';
    this.bubble.append(this.head, this.info, this.body);
    document.body.append(this.bubble, this.prompts);
    for (const el of [this.bubble, this.prompts]) {          // 말풍선을 눌러도 땅을 누른 것으로 치지 않게
      el.addEventListener('pointerdown', (e) => e.stopPropagation());
      el.addEventListener('mousedown', (e) => e.stopPropagation());
      el.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });
    }
  }

  reset(st: GameState, ctl: Controller) { this.st = st; this.ctl = ctl; this.closeBubble(); }

  get isOpen() { return this.open !== null; }

  /** 다른 나라의 거점을 눌렀다: 그 위에 말풍선. */
  openFor(b: BuildRec) {
    this.open = { nid: b.own, slot: b.slot, gen: b.gen };
    this.confirmBreak = false;
    this.sig = '';
    this.render();
  }

  /** Esc: 말풍선을 닫는다. */
  close() { this.closeBubble(); }

  private closeBubble() { this.open = null; this.sig = ''; this.bubble.style.display = 'none'; }

  private have(k: number): number {
    const me = this.st.nations[this.st.info.me];
    return !me ? 0 : k < 3 ? me.res[k] : me.sulfur;
  }

  /** 자원 보내기의 보낼 양 (가진 자원이 바뀌니 매번). */
  private fillRes() {
    const d = this.st.diplo, R = this.st.info.rules;
    if (!d || !this.amountEl) return;
    const names = [...R.res_names, '유황'];
    const parts: string[] = [];
    let total = 0;
    for (let k = 0; k < 4; k++) {
      if (!this.resPick[k]) continue;
      const v = Math.floor(this.have(k) * this.resPct / 100);
      total += v;
      parts.push(`${names[k]} ${v}`);
    }
    if (this.amountEl) this.amountEl.textContent = parts.length ? `${this.resPct}% → ${parts.join(' · ')}` : `${this.resPct}% (보낼 자원을 고르세요)`;
    if (this.sendBtn) {
      this.sendBtn.disabled = total <= 0 || d.donate_cd > 0;
      this.sendBtn.textContent = d.donate_cd > 0 ? `자원 보내기 (${d.donate_cd}초)` : '자원 보내기';
    }
  }

  private send(act: string, to: number, extra: Record<string, unknown> = {}) {
    this.net.send({ t: 'diplo', act, to, ...extra });
  }

  private btn(parent: HTMLElement, label: string, fn: () => void, opts: { off?: boolean; warm?: boolean; on?: boolean; title?: string } = {}) {
    const b = document.createElement('button');
    b.className = 'dbtn' + (opts.warm ? ' warm' : '') + (opts.on ? ' on' : '');
    b.textContent = label;
    b.disabled = !!opts.off;
    if (opts.title) b.title = opts.title;
    b.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
    parent.appendChild(b);
    return b;
  }

  private row(parent: HTMLElement, label?: string) {
    const r = document.createElement('div');
    r.className = 'drow';
    if (label) {
      const t = document.createElement('span');
      t.className = 'dlabel';
      t.textContent = label;
      r.appendChild(t);
    }
    parent.appendChild(r);
    return r;
  }

  /** 말풍선과 알림을 지금 상태로 (외교 상태가 오거나 0.25초마다). 글과 보낼 양은 매번,
   *  버튼은 할 수 있는 일이 바뀔 때만 다시 만든다 (누르는 사이에 버튼이 바뀌어 눌림이 사라지지 않게). */
  render() {
    this.renderPrompts();
    const o = this.open, d = this.st.diplo;
    if (!o || !d) { this.bubble.style.display = 'none'; return; }
    const hall = this.st.builds.get(o.slot);
    if (!hall || hall.gen !== o.gen || !this.st.nations[o.nid]?.alive) { this.closeBubble(); return; }
    const info = this.st.info.nations[o.nid], key = String(o.nid), me = this.st.info.me;
    const ally = key in d.allies, traitor = key in d.traitors;
    this.bubble.style.display = '';
    // 머리줄
    this.head.innerHTML = '';
    const sw = document.createElement('span');
    sw.className = 'swatch';
    sw.style.background = `rgb(${info.color.join(',')})`;
    const x = document.createElement('button');
    x.className = 'dclose';
    x.textContent = '×';
    x.title = '닫기 (Esc)';
    x.addEventListener('click', (e) => { e.stopPropagation(); this.closeBubble(); });
    const name = document.createElement('span');
    name.textContent = info.name;
    this.head.append(sw, name, x);
    // 글
    this.info.innerHTML = '';
    const line = (text: string, color?: string) => {
      const t = document.createElement('div');
      t.textContent = text;
      if (color) t.style.color = color;
      this.info.appendChild(t);
    };
    const tribes = this.st.info.rules.tribe_names ?? ['온대', '설원', '사막'];
    if (info.tribe !== undefined) line(`${tribes[info.tribe]} 부족`, 'rgb(230,220,190)');   // 시작 거점 둘레 지형 (sim/tribes.py)
    const lv = d.theirs[o.nid] ?? 2;
    line(`우리를 보는 눈: ${LEVELS[lv]}`, LEVEL_COLORS[lv]);
    if (ally) line(`동맹 · 남은 기간 ${mmss(d.allies[key])}`, LEVEL_COLORS[3]);
    if (traitor) line(`배신자 (${mmss(d.traitors[key])})`, LEVEL_COLORS[0]);
    if (d.cooldown[key]) line(`거절당함: ${d.cooldown[key]}초 뒤에 다시 청할 수 있다`);
    if (ally && this.ctl.sel.size === 0) line('병력을 보내려면 병사를 먼저 고르세요');
    this.fillAmounts();
    // 버튼
    const out = d.outgoing.includes(o.nid), cool = !!d.cooldown[key], incoming = d.incoming.includes(o.nid);
    const marked = d.targets.some(([a, t]) => a === me && t === o.nid), hasAlly = Object.keys(d.allies).length > 0;
    const ext = d.extend.includes(o.nid), rcd = d.donate_cd > 0, tcd = d.troop_cd > 0;
    const sig = [o.nid, ally, out, cool, incoming, marked, hasAlly, ext, rcd, tcd, this.confirmBreak].join(',');
    if (sig === this.sig) return;
    this.sig = sig;
    const body = this.body;
    body.innerHTML = '';
    this.troopBtn = this.sendBtn = null;
    this.amountEl = null;
    if (ally) {                                                // 자원 보내기: 보낼 자원 (여럿), 슬라이더, 보낼 양, 보내기
      const R = this.st.info.rules, max = Math.round(d.donate_max * 100);
      const box = document.createElement('div');
      box.className = 'dres';
      const kinds = document.createElement('div');
      kinds.className = 'dkinds';
      [...R.res_names, '유황'].forEach((nm: string, k: number) => {
        const b = this.btn(kinds, nm, () => { this.resPick[k] = !this.resPick[k]; b.classList.toggle('on', this.resPick[k]); this.fillRes(); },
                           { on: this.resPick[k], title: '보낼 자원 (여럿 고를 수 있다)' });
      });
      const slider = document.createElement('input');
      slider.type = 'range';
      slider.min = "0"; slider.max = String(max); slider.step = "5";
      slider.value = String(Math.min(this.resPct, max));
      slider.addEventListener('input', () => { this.resPct = Number(slider.value); this.fillRes(); });
      const amt = document.createElement('div');
      amt.className = 'damt';
      this.amountEl = amt;
      box.append(kinds, slider, amt);
      body.appendChild(box);
      const rs = this.row(body);
      this.sendBtn = this.btn(rs, '자원 보내기', () => this.send('give', o.nid, { pct: this.resPick.map((on) => (on ? this.resPct / 100 : 0)) }));
      this.sendBtn.classList.add('wide');
    }
    const r = this.row(body);                                  // 버튼은 같은 너비의 2열 (홀로 남는 버튼은 한 줄 전체)
    if (ally) {
      this.troopBtn = this.btn(r, '병력 보내기', () => { this.send('units', o.nid, { units: this.ctl.refs() }); this.ctl.sel.clear(); },
                               { title: '고른 병사가 이 나라의 가장 가까운 거점으로 가서, 닿으면 동맹의 병사가 된다 (바다 건너면 항구가 있어야)' });
      if (ext) this.btn(r, '동맹 연장', () => this.send('extend', o.nid));
      this.btn(r, this.confirmBreak ? '정말 깰까요?' : '동맹 깨기', () => {
        if (!this.confirmBreak) { this.confirmBreak = true; this.render(); return; }
        this.send('break', o.nid); this.confirmBreak = false;
      }, { warm: true, title: '기간 중에 깨면 배신자가 된다 (받는 피해 증가, 모든 나라의 관계 하락)' });
      this.fillAmounts();
    } else {
      if (incoming) {
        this.btn(r, '동맹 수락', () => this.send('reply', o.nid, { accept: true }));
        this.btn(r, '거절', () => this.send('reply', o.nid, { accept: false }));
      } else {
        this.btn(r, out ? '동맹 요청 보냄' : '동맹 요청', () => this.send('request', o.nid), { off: out || cool });
      }
      if (hasAlly) this.btn(r, marked ? '공격 요청함' : '동맹에게 공격 요청', () => this.send('target', o.nid),
                            { off: marked, title: '동맹들에게 이 나라를 함께 치자고 한다' });
    }
    if (r.childElementCount % 2 === 1) (r.lastElementChild as HTMLElement).classList.add('wide');   // 홀로 남는 버튼
  }

  /** 동맹 버튼의 글 (남은 대기 시간, 고른 병사 수)과 보낼 자원의 양: 매번. */
  private fillAmounts() {
    const d = this.st.diplo;
    if (!d) return;
    if (this.troopBtn) {
      const n = this.ctl.sel.size;
      this.troopBtn.textContent = d.troop_cd > 0 ? `병력 보내기 (${d.troop_cd}초)` : n ? `병사 ${n}명 보내기` : '병력 보내기';
      this.troopBtn.disabled = d.troop_cd > 0 || n === 0;
    }
    this.fillRes();
  }

  private renderPrompts() {
    const d = this.st.diplo, el = this.prompts;
    const sig = d ? `${d.incoming.join(',')}|${d.extend.join(',')}` : '';
    if (sig === this.psig) return;
    this.psig = sig;
    el.innerHTML = '';
    if (!d) { el.style.display = 'none'; return; }
    const names = this.st.info.nations;
    const row = (text: string) => {
      const r = document.createElement('div');
      r.className = 'dprompt';
      const t = document.createElement('span');
      t.textContent = text;
      r.appendChild(t);
      el.appendChild(r);
      return r;
    };
    for (const a of d.incoming) {
      const r = row(`${names[a].name}: 동맹을 청합니다`);
      this.btn(r, '수락', () => this.send('reply', a, { accept: true }));
      this.btn(r, '거절', () => this.send('reply', a, { accept: false }));
    }
    for (const a of d.extend) {
      const r = row(`${names[a].name}와(과)의 동맹이 곧 끝납니다`);
      this.btn(r, '연장', () => this.send('extend', a));
    }
    el.style.display = el.childElementCount ? '' : 'none';
  }

  /** 말풍선을 거점 위에 (매 프레임). */
  frame(cam: Camera) {
    const o = this.open;
    if (!o) return;
    const hall = this.st.builds.get(o.slot);
    if (!hall) return;
    const x = (hall.x - cam.x) * cam.zoom, y = (hall.y - 5 - cam.y) * cam.zoom;
    this.bubble.style.left = `${Math.round(x)}px`;
    this.bubble.style.top = `${Math.round(y)}px`;
  }

  dispose() { this.bubble.remove(); this.prompts.remove(); }
}
