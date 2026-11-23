// 대기실 (멀티): 서버에 room_create / room_join으로 접속해 방 상태(room)를 받아 그린다.
//   왼쪽: 방 이름, 입장 코드 (복사), 설정 (방장은 AI 수·난이도·계절·시작 방식을 바꿀 수 있다), 참가자 (색, 이름, 방장, 준비, 내보내기), 내 색.
//   오른쪽: 지도 약도 + 시작 자리 (무작위: 서버가 정한 배치 / 각자 고르기: 약도를 눌러 내 자리), 드래곤 둥지·유황 웅덩이.
//   아래: [나가기], [준비] (방장이 아니면) 또는 [시작] (방장).
// 방장이 시작하면 서버가 start를 보낸다: 연결을 그대로 게임 화면에 넘긴다 (Connection.hold → GameView가 이어받는다).
// 판이 끝나고 [대기실로]: 게임 화면이 연결을 돌려준다 → room_back을 보내 같은 방에 다시 들어간다.

import { Connection, type Handlers } from '../game/net.ts';
import { SpriteBank } from '../game/sprites.ts';
import type { LobbyInfo } from './lobbyArt.ts';
import { SEASONS } from './setup.ts';
import { busyBox } from '../ui/coffee.ts';
import { DIM, GOLD, INK, button, div, uiScale, previewReserve } from './widgets.ts';

interface Member { name: string; color: number; ready: boolean; spot: number[] | null }
interface RoomState {
  id: string; code: string; name: string; host: number; me: number; cap: number; bots: number; start_mode: 'random' | 'pick';
  setup: { map: string; difficulty?: string; season?: number }; locked: boolean; state: string; layout: number[][] | null;
  members: Member[]; map_status: { state?: string; progress?: string };
}

export interface RoomHooks {
  leave(msg?: string, busy?: boolean): void;         // 대기실을 나간다 (나감, 내보내짐, 들어가지 못함, 끊김). busy: 서버가 꽉 찼다
  start(conn: Connection, mapKey: string): void;     // 판이 시작됐다: 연결을 게임 화면에
}

export class RoomView {
  readonly el = div('menu setup room');
  private left = div('setup-left', this.el);
  private prevBox = div('preview', this.el);
  private prevImg = document.createElement('img');
  private prevCanvas = document.createElement('canvas');
  private foot = div('setup-foot', this.el);
  private msgEl = div('setup-msg', this.el);
  private conn: Connection;
  private room: RoomState | null = null;
  private bank: SpriteBank;
  private previewSize = 260;
  private raf = 0;
  private mouse: [number, number] | null = null;
  private extras: { key: string; lairs: number[][]; sulfur: number[][] } | null = null;
  private handed = false;                            // 연결을 게임 화면에 넘겼다 (닫지 않는다)
  private gone = false;

  /** first: 처음 보낼 것 (room_create / room_join), 또는 끝난 판의 연결 (대기실로 돌아간다). */
  constructor(first: Record<string, unknown> | Connection, private lobby: LobbyInfo | null, private hooks: RoomHooks) {
    this.bank = new SpriteBank((lobby?.colors ?? [['', [214, 70, 52], [0, 0, 0]]]).map((c) => c[1]));
    this.prevImg.className = 'preview-img';
    this.prevCanvas.className = 'preview-canvas';
    this.prevBox.prepend(this.prevImg, this.prevCanvas);
    this.prevBox.addEventListener('mousemove', (e) => {
      const r = this.prevBox.getBoundingClientRect(), k = this.previewSize / r.width;
      this.mouse = [(e.clientX - r.left) * k, (e.clientY - r.top) * k];
    });
    this.prevBox.addEventListener('mouseleave', () => { this.mouse = null; });
    this.prevBox.addEventListener('pointerdown', (e) => this.pick(e));
    const h: Handlers = {
      start: (info) => {                              // 판 시작: 연결을 넘긴다 (start와 그 뒤의 것은 게임 화면이 받는다)
        this.handed = true;
        this.conn.hold(info);
        this.hooks.start(this.conn, this.room?.setup.map ?? (info as any).map);
      },
      state: () => {}, msg: () => {}, over: () => {}, diplo: () => {},
      status: (t) => this.say(t),
      error: (text, fatal, busy) => { if (fatal) this.leave(text, busy); else this.say(text); },
      closed: () => this.leave('서버와 연결이 끊겼습니다'),
      other: (m) => this.onMessage(m),
    };
    if (first instanceof Connection) {
      this.conn = first;
      first.setHandlers(h);
      first.send({ t: 'room_back' });
    } else this.conn = Connection.open(first, h);
    this.say('방에 들어가는 중...');
    this.render();
  }

  private watch = new ResizeObserver(() => this.layoutPreview());   // 왼쪽 칸 너비가 바뀌면 미리보기 자리를 다시

  attach(parent: HTMLElement = document.body) {
    this.watch.observe(this.left);
    parent.appendChild(this.el);
    this.layoutPreview();
    cancelAnimationFrame(this.raf);
    const tick = () => { this.drawPreview(); this.raf = requestAnimationFrame(tick); };
    tick();
  }

  /** 화면에서 뗀다. 게임에 넘기지 않았으면 연결도 닫는다 (서버가 방에서 뺀다). */
  dispose() {
    cancelAnimationFrame(this.raf);
    this.el.remove();
    if (!this.handed) { this.gone = true; this.conn.close(); }
  }

  key(e: KeyboardEvent) { if (e.key === 'Escape' && !(document.activeElement instanceof HTMLInputElement)) this.leaveRoom(); }

  private say(t: string) { this.msgEl.textContent = t; }

  private leave(msg?: string, busy = false) {
    if (this.gone || this.handed) return;
    this.gone = true;
    this.hooks.leave(msg, busy);
  }

  private leaveRoom() { this.conn.send({ t: 'room_leave' }); this.leave(); }

  private send(m: Record<string, unknown>) { this.conn.send(m); }

  private onMessage(m: any) {
    if (m.t === 'room') {
      const keyChanged = m.setup?.map !== this.room?.setup.map;
      this.room = m as RoomState;
      if (keyChanged && this.room.setup.map) {
        this.prevImg.src = `/api/maps/${this.room.setup.map}/day.png`;
        void this.loadExtras(this.room.setup.map);
      }
      this.say(this.room.state === 'starting' ? '판을 준비하는 중...' : '');
      this.render();
    } else if (m.t === 'room_error') {
      if (m.fatal) this.leave(m.error, Boolean(m.busy));
      else if (m.busy) busyBox(this.el, m.error, [['닫기', () => {}]]);   // 시작하려는데 판이 꽉 찼다: 대기실에 남는다
      else this.say(m.error);
    } else if (m.t === 'room_kicked') this.leave('방에서 내보내졌습니다');
    else if (m.t === 'room_closed') this.leave();
  }

  /** 지도의 드래곤 둥지와 유황 웅덩이 (설정 화면과 같은 /layout에서). */
  private async loadExtras(key: string) {
    try {
      const r = await (await fetch(`/api/maps/${key}/layout?bots=1&color=0`)).json();
      this.extras = { key, lairs: r.lairs ?? [], sulfur: r.sulfur ?? [] };
    } catch { /* 없어도 된다 */ }
  }

  // ------------------------------------------------------------- 왼쪽
  private render() {
    const L = this.left, r = this.room;
    L.innerHTML = '';
    this.foot.innerHTML = '';
    if (!r) {
      div('setup-title', L, '대기실');
      button(this.foot, '나가기', () => this.leaveRoom(), { size: 18, w: 140, h: 48 });
      this.foot.appendChild(this.msgEl);
      return;
    }
    const host = r.me === r.host, me = r.members[r.me];
    div('setup-title', L, r.name);
    const row = (label: string) => { const x = div('setup-row', L); div('setup-label', x, label); return div('setup-ctl', x); };
    let x = row('입장 코드');
    div('room-code', x, r.code);
    button(x, '복사', () => { void navigator.clipboard?.writeText(r.code); this.say('코드를 복사했습니다'); }, { size: 15, w: 70, h: 32 });
    if (r.locked) div('note small', x, '비밀번호 있음');
    div('gap', L);
    div('setup-head', L, '설정');
    const size = r.setup.map.split('-').at(-2) ?? '';
    x = row('지도');
    div('note', x, `${r.setup.map.split('-')[0] === 'default' ? '기본' : r.setup.map.split('-')[0]} · ${size} · 시드 ${r.setup.map.split('-').at(-1)}`);
    const nMax = this.lobby?.colors.length ?? 8;
    x = row('AI 나라');
    if (host) button(x, '-', () => this.send({ t: 'room_setup', bots: Math.max(0, r.bots - 1) }), { size: 18, w: 36, h: 32 });
    div('count', x, `${r.bots}`);
    if (host) button(x, '+', () => this.send({ t: 'room_setup', bots: Math.min(nMax - r.cap, r.bots + 1) }), { size: 18, w: 36, h: 32 });
    div('note small', x, `사람 정원 ${r.cap}`);
    x = row('난이도');
    for (const d of this.lobby?.difficulty ?? ['쉬움', '보통', '어려움']) {
      const b = button(x, d, () => this.send({ t: 'room_setup', difficulty: d }), { selected: (r.setup.difficulty ?? '보통') === d, size: 15, w: 74, h: 32 });
      b.disabled = !host;
    }
    x = row('시작 계절');
    SEASONS.forEach((name, i) => {
      const b = button(x, name, () => this.send({ t: 'room_setup', season: i }), { selected: (r.setup.season ?? 0) === i, size: 15, w: 64, h: 32 });
      b.disabled = !host;
    });
    x = row('시작 자리');
    for (const [mode, label] of [['random', '무작위'], ['pick', '각자 고르기']] as const) {
      const b = button(x, label, () => this.send({ t: 'room_setup', start_mode: mode }), { selected: r.start_mode === mode, size: 15, w: 110, h: 32 });
      b.disabled = !host;
    }
    if (r.start_mode === 'pick') {
      const t = div('note', x, me?.spot ? '자리 정함' : '← 오른쪽 약도를 클릭');
      t.style.color = me?.spot ? DIM : GOLD;
    }
    div('gap', L);
    div('setup-head', L, `참가자 ${r.members.length}/${r.cap}`);
    const list = div('room-members', L);
    r.members.forEach((m, i) => {
      const line = div('room-member', list);
      const sw = div('swatch small', line);
      sw.style.background = `rgb(${(this.lobby?.colors[m.color]?.[1] ?? [128, 128, 128]).join(',')})`;
      div('room-mname', line, `${m.name}${i === r.me ? ' (나)' : ''}`);
      div('room-mtag', line, i === r.host ? '방장' : m.ready ? '준비 완료' : '준비 중');
      if (host && i !== r.me) button(line, '내보내기', () => this.send({ t: 'room_kick', member: i }), { size: 13, w: 80, h: 26 });
    });
    x = row('내 색');
    (this.lobby?.colors ?? []).forEach(([, col], i) => {
      const used = r.members.some((m, j) => j !== r.me && m.color === i);
      const sw = div('swatch' + (me?.color === i ? ' on' : '') + (used ? ' used' : ''), x);
      sw.style.background = `rgb(${col.join(',')})`;
      if (!used) sw.addEventListener('click', () => this.send({ t: 'room_color', color: i }));
    });
    // 아래
    button(this.foot, '나가기', () => this.leaveRoom(), { size: 18, w: 140, h: 48 });
    if (host) {
      const ready = r.members.every((m, i) => i === r.host || m.ready) && r.members.length >= 2;
      const b = button(this.foot, '시작', () => this.send({ t: 'room_start' }), { size: 20, w: 220, h: 48, selected: true, accent: true });
      b.disabled = !ready || r.state !== 'wait' || r.map_status?.state !== 'ready';
      if (r.members.length < 2) this.say('다른 사람이 들어오기를 기다립니다 (코드를 알려 주세요)');
      else if (!ready) this.say('모두 준비하면 시작할 수 있습니다');
    } else {
      button(this.foot, me?.ready ? '준비 취소' : '준비', () => this.send({ t: 'room_ready', on: !me?.ready }),
             { size: 20, w: 220, h: 48, selected: !me?.ready, accent: !me?.ready });
    }
    // 각자 고르기인데 자리를 안 골랐다: 준비했으면 (방장은 시작할 수 있으면) 무작위로 정해진다고 알린다
    const ready = host ? r.members.length >= 2 && r.members.every((m, i) => i === r.host || m.ready) : !!me?.ready;
    if (r.start_mode === 'pick' && me && !me.spot && ready) this.say('자리를 고르지 않아서 시작할 때 무작위로 정해집니다 (약도를 누르면 고를 수 있습니다)');
    if (r.map_status?.state && r.map_status.state !== 'ready') this.say(`지도 준비 중: ${r.map_status.progress ?? r.map_status.state}`);
    this.foot.appendChild(this.msgEl);
  }

  // ------------------------------------------------------------- 오른쪽 (약도)
  layoutPreview() {
    const ui = uiScale(), W = window.innerWidth / ui, H = window.innerHeight / ui;
    const size = Math.max(Math.min(W - previewReserve(this.left, ui), H - 150), 260);
    this.previewSize = size;
    Object.assign(this.prevBox.style, { width: `${size}px`, height: `${size}px`, left: `${W - size - 40}px`, top: '84px' });
    const px = (window.devicePixelRatio || 1) * ui;
    this.prevCanvas.width = Math.round(size * px);
    this.prevCanvas.height = Math.round(size * px);
  }

  private mapSize() { return Number(this.room?.setup.map.split('-').at(-2) ?? 512); }

  private pick(e: PointerEvent) {
    const r = this.room;
    if (!r || r.start_mode !== 'pick' || e.button !== 0) return;
    const b = this.prevBox.getBoundingClientRect(), n = this.mapSize();
    const x = Math.floor(((e.clientX - b.left) / b.width) * n), y = Math.floor(((e.clientY - b.top) / b.height) * n);
    this.send({ t: 'room_spot', y, x });
  }

  private drawPreview() {
    const g = this.prevCanvas.getContext('2d')!, size = this.previewSize, px = this.prevCanvas.width / size;
    g.setTransform(px, 0, 0, px, 0, 0);
    g.clearRect(0, 0, size, size);
    g.imageSmoothingEnabled = false;
    const r = this.room;
    if (!r) return;
    const n = this.mapSize(), at = (y: number, x: number) => [((x + 0.5) / n) * size, ((y + 0.5) / n) * size];
    const text = (t: string, x: number, y: number, col: string) => {
      g.font = "13px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";
      g.textAlign = 'center'; g.textBaseline = 'bottom';
      g.fillStyle = '#000'; g.fillText(t, x + 1, y + 2);
      g.fillStyle = col; g.fillText(t, x, y);
    };
    if (r.map_status?.state !== 'ready') {
      g.fillStyle = 'rgba(0,0,0,0.6)'; g.fillRect(0, 0, size, size);
      text(r.map_status?.progress ?? '지도 준비 중...', size / 2, size / 2, INK);
      return;
    }
    if (this.extras && this.extras.key === r.setup.map) {
      const sul = this.bank.site(3, 3);
      for (const [y, x] of this.extras.sulfur) { const [sx, sy] = at(y, x); g.drawImage(sul, Math.trunc(sx - sul.width / 2), Math.trunc(sy - sul.height / 2)); }
      for (const [y, x] of this.extras.lairs) {
        const [sx, sy] = at(y, x);
        g.fillStyle = 'rgba(10,12,22,0.55)'; g.beginPath(); g.arc(sx, sy, 9, 0, Math.PI * 2); g.fill();
        text('드래곤', sx, sy - 9, 'rgb(200,228,255)');
      }
    }
    const HALL = this.lobby?.rules.kinds.HALL ?? 0;
    const hall = (y: number, x: number, color: number | null, label: string, me: boolean) => {
      const [sx, sy] = at(y, x);
      if (color === null) {                                      // AI 자리: 색은 시작할 때 정해진다
        g.fillStyle = 'rgba(200,200,200,0.8)'; g.strokeStyle = '#000';
        g.beginPath(); g.arc(sx, sy, 5, 0, Math.PI * 2); g.fill(); g.stroke();
        text('AI', sx, sy - 7, DIM);
        return;
      }
      const img = this.bank.building(HALL, color, 2);
      g.drawImage(img, Math.trunc(sx - img.width / 2), Math.trunc(sy + 6 - img.height));
      if (me) { g.strokeStyle = '#fff'; g.lineWidth = 1; g.beginPath(); g.arc(Math.trunc(sx) + 0.5, Math.trunc(sy) + 0.5, 14, 0, Math.PI * 2); g.stroke(); }
      text(label, sx, sy - 18, me ? INK : DIM);
    };
    if (r.start_mode === 'random' && r.layout) {
      r.layout.forEach(([y, x], i) => {
        const m = r.members[i];
        hall(y, x, m ? m.color : null, m ? m.name : '', i === r.me);
      });
    } else if (r.start_mode === 'pick') {
      r.members.forEach((m, i) => { if (m.spot) hall(m.spot[0], m.spot[1], m.color, m.name, i === r.me); });
      if (this.mouse) {
        g.strokeStyle = GOLD; g.beginPath(); g.arc(this.mouse[0], this.mouse[1], 10, 0, Math.PI * 2); g.stroke();
      }
    }
  }
}
