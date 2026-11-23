// 멀티 플레이 화면: 내 이름·색, 열린 방 목록 (몇 초마다 새로), 코드로 입장하기, 새 방 만들기.
// 방을 누르면 들어간다 (비밀번호가 있으면 그 줄에서 입력). 들어가기는 대기실(room.ts)이 연결을 열어 한다.

import type { LobbyInfo } from './lobbyArt.ts';
import { nameField, type Settings } from './setup.ts';
import { randomName } from './names.ts';
import { button, div, field } from './widgets.ts';
import { busyBox } from '../ui/coffee.ts';

interface RoomRow { id: string; name: string; host: string; humans: number; cap: number; bots: number; locked: boolean; map: string; start_mode: string }

/** 대기실에 들어갈 것 (server/app.py room_join). */
export interface JoinRequest { id?: string; code?: string; password?: string; player: { name: string; color: number } }

export class MultiMenu {
  readonly el = div('menu setup multi');
  private left = div('setup-left', this.el);
  private listEl!: HTMLDivElement;
  private msgEl = div('setup-msg', this.el);
  private rooms: RoomRow[] = [];
  private timer = 0;
  private asking: string | null = null;           // 비밀번호를 묻는 방
  private code = '';
  private codePw = '';

  constructor(private s: Settings, private lobby: LobbyInfo | null, private onBack: () => void,
              private onCreate: () => void, private onJoin: (req: JoinRequest) => void) {
    const foot = div('setup-foot', this.el);
    button(foot, '뒤로', () => this.onBack(), { size: 18, w: 140, h: 48 });
    button(foot, '새 방 만들기', () => this.onCreate(), { size: 20, w: 220, h: 48, selected: true, accent: true });
    foot.appendChild(this.msgEl);
    this.render();
  }

  attach(parent: HTMLElement = document.body) {
    parent.appendChild(this.el);
    void this.refresh();
    clearInterval(this.timer);
    this.timer = window.setInterval(() => void this.refresh(), 2500);
  }

  detach() { clearInterval(this.timer); this.el.remove(); }

  say(t: string) { this.msgEl.textContent = t; }

  /** 서버가 꽉 찼다 (방을 만들거나 들어가지 못했다): 반투명 배경 위 안내. */
  busy(t: string) { this.say(''); busyBox(this.el, t, [['닫기', () => {}]]); }

  key(e: KeyboardEvent) {
    if (e.key === 'Escape' && !(document.activeElement instanceof HTMLInputElement)) this.onBack();
  }

  private player() { return { name: this.s.multiName.trim() || randomName(), color: this.s.color }; }

  private async refresh() {
    try {
      this.rooms = await (await fetch('/api/rooms')).json();
    } catch {
      return;
    }
    if (this.asking && !this.rooms.some((r) => r.id === this.asking)) this.asking = null;
    if (!this.asking) this.renderList();                 // 비밀번호를 넣는 중에는 다시 그리지 않는다 (입력이 지워지지 않게)
  }

  private render() {
    const L = this.left, s = this.s;
    L.innerHTML = '';
    div('setup-title', L, '멀티 플레이');
    const row = (label: string) => { const r = div('setup-row', L); div('setup-label', r, label); return div('setup-ctl', r); };
    let r = row('내 이름');
    nameField(r, s);
    r = row('내 색');
    (this.lobby?.colors ?? []).forEach(([, col], i) => {
      const sw = div('swatch' + (s.color === i ? ' on' : ''), r);
      sw.style.background = `rgb(${col.join(',')})`;
      sw.addEventListener('click', () => { s.color = i; this.render(); });
    });
    div('note small', r, '겹치면 방에서 다른 색으로');
    div('gap', L);
    div('setup-head', L, '열린 방');
    this.listEl = div('room-list', L);
    this.renderList();
    div('gap', L);
    div('setup-head', L, '코드로 입장하기');
    r = div('setup-ctl', L);
    const f = field(r, this.code, 6, 160, (v) => { this.code = v.toUpperCase(); f.value = this.code; });
    f.placeholder = '6글자 코드';
    f.classList.add('code-field');
    f.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.joinCode(); });
    const pw = field(r, this.codePw, 16, 150, (v) => { this.codePw = v; });
    pw.type = 'password';
    pw.placeholder = '비밀번호 (있으면)';
    pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.joinCode(); });
    button(r, '입장', () => this.joinCode(), { size: 16, w: 90, h: 34 });
  }

  private joinCode() {
    const c = this.code.trim();
    if (c.length !== 6) { this.say('코드 6글자를 넣으세요'); return; }
    this.onJoin({ code: c, password: this.codePw, player: this.player() });
  }

  private renderList() {
    const el = this.listEl;
    if (!el) return;
    el.innerHTML = '';
    if (!this.rooms.length) { div('note small', el, '열린 방이 없습니다. 새 방을 만들어 보세요'); return; }
    for (const r of this.rooms) {
      const line = div('room-row', el);
      div('room-name', line, `${r.locked ? '🔒 ' : ''}${r.name}`);
      div('room-meta', line, `${r.host} · 사람 ${r.humans}/${r.cap}${r.bots ? ` · AI ${r.bots}` : ''} · 지도 ${r.map.split('-').at(-2) ?? ''} · ${r.start_mode === 'pick' ? '자리 고르기' : '무작위 자리'}`);
      const full = r.humans >= r.cap;
      if (this.asking === r.id) {                          // 비밀번호
        const pw = field(line, '', 16, 140, () => {});
        pw.type = 'password';
        pw.placeholder = '비밀번호';
        const go = () => this.onJoin({ id: r.id, password: pw.value, player: this.player() });
        pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
        button(line, '입장', go, { size: 15, w: 70, h: 30 });
        setTimeout(() => pw.focus(), 0);
      } else {
        const b = button(line, full ? '가득 참' : '입장', () => {
          if (r.locked) { this.asking = r.id; this.renderList(); } else this.onJoin({ id: r.id, player: this.player() });
        }, { size: 15, w: 90, h: 30 });
        b.disabled = full;
      }
    }
  }
}
