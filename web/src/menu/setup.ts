// 시작 전 설정 (데스크톱 game/menu.py의 Setup):
//   지도(지형 프리셋, 크기, 시드, 무작위, 지도 만들기 + 오른쪽 미리보기), 내 나라(이름, 색), 시작 자리(무작위/지도에서 고르기),
//   상대(AI 나라 수, 난이도), 시작 계절. '게임 시작'은 지도가 없으면 만들고 바로 시작한다.
// 무작위 배치를 미리보기에서 봤으면 게임도 그 배치 그대로 시작한다 (서버 /layout → join의 starts, colors).
// '고급 설정': 지형 세부 값 창 (advanced.ts). 고친 값은 여기서 기억해 다시 열면 그대로, 지도 만들기에 실어 보낸다.
// 방 만들기 (멀티, mode 'room'): 같은 화면에 방 항목(방 이름, 사람 정원, 비밀번호, 시작 자리 방식)을 더하고 '방 만들기'.
//   시작 자리는 대기실에서 정하므로 여기에는 없다. AI 수는 0부터 (사람 정원 + AI ≤ 나라 수).

import { randomName } from './names.ts';
import { SpriteBank } from '../game/sprites.ts';
import { AdvancedDialog, AdvancedState } from './advanced.ts';
import type { LobbyInfo } from './lobbyArt.ts';
import { DIM, GOLD, INK, button, div, field, uiScale, previewReserve } from './widgets.ts';

export const SEASONS = ['봄', '여름', '가을', '겨울'];

export interface Settings {
  preset: string | null; size: number; seed: string;
  name: string; color: number;
  spotMode: 'random' | 'pick'; spot: [number, number] | null;
  bots: number; difficulty: string; season: number;
  // 방 만들기 (멀티)
  roomName: string; cap: number; password: string; roomStart: 'random' | 'pick';
  multiName: string;            // 멀티에서 쓰는 내 이름 (처음엔 무작위 '형용사 명사', 싱글의 name과 따로)
}

export const defaultSettings = (): Settings => ({
  preset: null, size: 512, seed: '8767564', name: '나', color: 0, spotMode: 'random', spot: null,
  bots: 4, difficulty: '보통', season: 0,
  roomName: '같이 해요', cap: 4, password: '', roomStart: 'random', multiName: randomName(),
});

/** 방 만들기에 넘길 것 (server/app.py room_create). */
export interface RoomRequest {
  name: string; password: string; cap: number; bots: number; start_mode: 'random' | 'pick';
  setup: { map: string; difficulty: string; season: number };
  player: { name: string; color: number };
}

/** 게임 시작에 넘길 것. */
export interface PlayRequest {
  key: string;
  options: { bots: number; color: number; name: string; difficulty: string; season: number;
    spot?: [number, number] | null; starts?: number[][] | null; colors?: number[] | null };
}

interface Listing { presets: { key: string; name: string }[]; sizes: number[] }
interface Layout { key: string; starts: number[][]; colors: number[]; lairs: number[][]; sulfur: number[][] }

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class Setup {
  readonly el = div('menu setup');
  private left = div('setup-left', this.el);
  private prevBox = div('preview', this.el);
  private prevImg = document.createElement('img');
  private prevCanvas = document.createElement('canvas');
  private prevCfg = div('preview-cfg', this.el);
  private msgEl: HTMLDivElement;
  private bank: SpriteBank;
  private presets: [string | null, string][];
  private sizes: number[];
  // 지도
  private builtSettings: string | null = null;    // 마지막으로 만든 지도의 (프리셋, 크기, 시드)
  private builtKey: string | null = null;         // 그 지도 키 (서버)
  private building = false;
  private buildStatus = '';
  private buildStart = 0;
  private startAfterBuild = false;
  private layout: Layout | null = null;
  private layoutFetching = '';
  private mouse: [number, number] | null = null;
  private previewSize = 260;
  private raf = 0;
  private adv: AdvancedState | null = null;       // 고급 설정 (그 프리셋에서 고친 값)
  private dialog: AdvancedDialog | null = null;

  constructor(readonly s: Settings, private lobby: LobbyInfo | null, listing: Listing,
              private onBack: () => void, private onPlay: (req: PlayRequest) => void,
              readonly mode: 'single' | 'room' = 'single', private onRoom: ((req: RoomRequest) => void) | null = null) {
    this.presets = [[null, '기본'], ...listing.presets.map((p) => [p.key, p.name] as [string, string])];
    this.sizes = listing.sizes;
    if (!this.sizes.includes(s.size)) s.size = this.sizes[this.sizes.length - 1];
    this.bank = new SpriteBank((lobby?.colors ?? [['', [214, 70, 52], [0, 0, 0]]]).map((c) => c[1]));
    this.prevImg.className = 'preview-img';
    this.prevCanvas.className = 'preview-canvas';
    this.prevBox.prepend(this.prevImg, this.prevCanvas);
    this.msgEl = div('setup-msg', this.el);
    const foot = div('setup-foot', this.el);
    button(foot, '뒤로', () => this.onBack(), { size: 18, w: 140, h: 48 });
    button(foot, this.mode === 'room' ? '방 만들기' : '게임 시작', () => this.start(), { size: 20, w: 220, h: 48, selected: true, accent: true });
    foot.appendChild(this.msgEl);
    this.prevBox.addEventListener('mousemove', (e) => {          // 화면 픽셀 → 메뉴 픽셀
      const r = this.prevBox.getBoundingClientRect(), k = this.previewSize / r.width;
      this.mouse = [(e.clientX - r.left) * k, (e.clientY - r.top) * k];
    });
    this.prevBox.addEventListener('mouseleave', () => { this.mouse = null; });
    this.prevBox.addEventListener('mousedown', (e) => { if (e.button === 0 && this.mode === 'single' && this.s.spotMode === 'pick') void this.pickSpot(e); });
    this.render();
  }

  /** 화면에 붙인다 (데스크톱처럼 설정 화면은 한 번 만들어 두고, 로비에 다녀와도 만든 지도와 배치가 남는다). */
  private watch = new ResizeObserver(() => this.layoutPreview());   // 왼쪽 칸 너비가 바뀌면 미리보기 자리를 다시

  attach(parent: HTMLElement = document.body) {
    this.watch.observe(this.left);
    parent.appendChild(this.el);
    this.layoutPreview();
    cancelAnimationFrame(this.raf);
    const tick = () => { this.drawPreview(); this.raf = requestAnimationFrame(tick); };
    tick();
  }

  detach() { cancelAnimationFrame(this.raf); this.el.remove(); }

  get mapReady() { return !this.building && this.builtKey !== null && this.builtSettings === this.settingsKey(); }

  /** 지금 프리셋에 맞는 고급 설정에서 바꾼 값 (없으면 빈 것). */
  private overrides(): Record<string, any> {
    return this.adv && this.adv.preset === this.s.preset ? this.adv.overrides().config : {};
  }

  private settingsKey() { return JSON.stringify([this.s.preset, this.s.size, this.s.seed, this.overrides()]); }

  /** Esc: 고급 설정 창이 열려 있으면 닫고, 입력 칸에 있으면 빠져나오고, 아니면 로비로. */
  key(e: KeyboardEvent) {
    if (e.key !== 'Escape') return;
    if (this.dialog) { this.dialog.close(); return; }
    if (!(document.activeElement instanceof HTMLInputElement)) this.onBack();
  }

  private async openAdvanced() {
    if (this.dialog) return;
    try {
      if (!this.adv || this.adv.preset !== this.s.preset) this.adv = await AdvancedState.load(this.s.preset);
    } catch (e) {
      this.say((e as Error).message);
      return;
    }
    const name = this.presets.find(([k]) => k === this.s.preset)?.[1] ?? '기본';
    this.dialog = new AdvancedDialog(this.el, this.adv, `${name} · ${this.s.size} · 시드 ${this.s.seed}`,
      () => { this.dialog = null; this.render(); },
      () => { this.dialog = null; this.render(); void this.build(); });
  }

  // ------------------------------------------------------------- 왼쪽 패널
  private render() {
    const s = this.s, L = this.left;
    L.innerHTML = '';
    div('setup-title', L, this.mode === 'room' ? '새 방 만들기' : '새 게임 설정');
    const head = (t: string) => div('setup-head', L, t);
    const row = (label: string) => { const r = div('setup-row', L); div('setup-label', r, label); return div('setup-ctl', r); };
    const set = (f: () => void) => () => { f(); this.render(); };

    head('지도');
    let r = row('지형');
    r.classList.add('wrap');
    for (const [key, name] of this.presets) button(r, name, set(() => { s.preset = key; }), { selected: s.preset === key, size: 15, h: 32 });
    r = row('크기');
    for (const sz of this.sizes) button(r, `${sz}`, set(() => { s.size = sz; }), { selected: s.size === sz, size: 15, w: 84, h: 32 });
    r = row('시드');
    field(r, s.seed, 12, 170, (v) => { s.seed = v; this.refreshPreview(); });
    button(r, '무작위', set(() => { s.seed = String(Math.floor(Math.random() * 2 ** 31)); }), { size: 15, w: 90, h: 32 });
    button(r, '고급 설정', () => void this.openAdvanced(), { size: 15, w: 110, h: 32 });
    r = row('');
    const b = button(r, '지도 만들기', () => void this.build(), { size: 16, w: 170, h: 34 });
    b.classList.add('build');                     // 눈에 띄게 (청록)
    b.disabled = this.building;
    const nAdv = this.adv && this.adv.preset === s.preset ? this.adv.count() : 0;
    if (nAdv) div('note small', r, `지형 세부 ${nAdv}개 바꿈`).style.color = GOLD;
    div('gap', L);

    head('내 나라');
    r = row('이름');
    if (this.mode === 'room') nameField(r, s);           // 멀티: 무작위 이름 + 다시 뽑기
    else field(r, s.name, 10, 200, (v) => { s.name = v; });
    r = row('색');
    (this.lobby?.colors ?? []).forEach(([, col], i) => {
      const sw = div('swatch' + (s.color === i ? ' on' : ''), r);
      sw.style.background = `rgb(${col.join(',')})`;
      sw.addEventListener('click', set(() => { s.color = i; }));
    });
    if (this.lobby) {
      const unit = this.bank.unit(0, s.color, 0, 3), hall = this.bank.building(this.lobby.rules.kinds.HALL, s.color, 2);
      unit.className = 'sprite-unit'; hall.className = 'sprite-hall';
      r.append(unit, hall);
    }
    div('gap', L);

    if (this.mode === 'room') this.renderRoom(L, head, row, set);
    else {
    head('시작 자리');
    r = row('');
    button(r, '무작위', set(() => {
      const again = s.spotMode === 'random';
      s.spot = null; s.spotMode = 'random';
      if (again) this.layout = null;                     // 다시 누르면 새로 뽑는다
    }), { selected: s.spotMode === 'random', size: 15, w: 110, h: 32 });
    button(r, '지도에서 고르기', set(() => { s.spotMode = 'pick'; }), { selected: s.spotMode === 'pick', size: 15, w: 150, h: 32 });
    if (s.spotMode === 'pick') {
      const t = div('note', r, s.spot === null ? '← 오른쪽 미리보기를 클릭' : '자리 정함');
      t.style.color = s.spot === null ? GOLD : DIM;
    } else if (this.mapReady) div('note small', r, '다시 누르면 새 배치');
    div('gap', L);
    }

    head('상대');
    r = row('AI 나라');
    const nMax = this.lobby?.colors.length ?? 8;
    const minBots = this.mode === 'room' ? 0 : 1, maxBots = this.mode === 'room' ? nMax - s.cap : nMax - 1;
    s.bots = Math.min(Math.max(s.bots, minBots), maxBots);
    button(r, '-', set(() => { s.bots = Math.min(Math.max(s.bots - 1, minBots), maxBots); }), { size: 18, w: 36, h: 32 });
    div('count', r, `${s.bots}`);
    button(r, '+', set(() => { s.bots = Math.min(Math.max(s.bots + 1, minBots), maxBots); }), { size: 18, w: 36, h: 32 });
    div('setup-label inline', r, '난이도');
    for (const d of this.lobby?.difficulty ?? ['쉬움', '보통', '어려움']) {
      button(r, d, set(() => { s.difficulty = d; }), { selected: s.difficulty === d, size: 15, w: 74, h: 32 });
    }
    r = row('시작 계절');
    SEASONS.forEach((name, i) => button(r, name, set(() => { s.season = i; }), { selected: s.season === i, size: 15, w: 64, h: 32 }));
    this.refreshPreview();
  }

  /** 방 만들기의 방 항목: 방 이름, 사람 정원, 비밀번호, 시작 자리 방식. */
  private renderRoom(L: HTMLElement, head: (t: string) => HTMLElement, row: (label: string) => HTMLElement, set: (f: () => void) => () => void) {
    const s = this.s, nMax = this.lobby?.colors.length ?? 8;
    head('방');
    let r = row('방 이름');
    field(r, s.roomName, 24, 260, (v) => { s.roomName = v; });
    r = row('사람 정원');
    button(r, '-', set(() => { s.cap = Math.max(2, s.cap - 1); }), { size: 18, w: 36, h: 32 });
    div('count', r, `${s.cap}`);
    button(r, '+', set(() => { s.cap = Math.min(nMax, s.cap + 1); s.bots = Math.min(s.bots, nMax - s.cap); }), { size: 18, w: 36, h: 32 });
    div('note small', r, `사람 + AI ≤ ${nMax}나라`);
    r = row('비밀번호');
    field(r, s.password, 16, 200, (v) => { s.password = v; });
    div('note small', r, '비우면 누구나 들어온다');
    r = row('시작 자리');
    button(r, '무작위', set(() => { s.roomStart = 'random'; }), { selected: s.roomStart === 'random', size: 15, w: 110, h: 32 });
    button(r, '각자 고르기', set(() => { s.roomStart = 'pick'; }), { selected: s.roomStart === 'pick', size: 15, w: 130, h: 32 });
    div('gap', L);
  }

  private say(t: string) { this.msgEl.textContent = t; }

  // ------------------------------------------------------------- 지도 만들기
  private async build() {
    if (this.building) return;
    const s = this.s, want = this.settingsKey();
    this.building = true;
    this.buildStart = performance.now();
    this.buildStatus = '준비 중...';
    this.builtSettings = want;
    this.builtKey = null;
    s.spot = null;
    this.layout = null;
    this.render();
    try {
      let st = await (await fetch('/api/maps', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: s.preset, size: s.size, seed: s.seed, config: this.overrides() }) })).json();
      const key: string = st.key;
      while (st.state !== 'ready') {
        if (st.state === 'error' || !key) throw new Error(st.error ?? '지도를 만들지 못했습니다');
        this.buildStatus = st.progress ?? '지도 만드는 중...';
        await sleep(500);
        st = await (await fetch(`/api/maps/${key}/status`)).json();
      }
      this.builtKey = key;
      this.prevImg.src = `/api/maps/${key}/day.png`;
    } catch (e) {
      this.builtSettings = null;
      this.startAfterBuild = false;
      this.say(`지도 만들기 실패: ${(e as Error).message}`);
    } finally {
      this.building = false;
      this.render();
    }
    if (this.startAfterBuild && this.mapReady) { this.startAfterBuild = false; this.start(); }
  }

  // ------------------------------------------------------------- 시작 자리
  /** 지도 키 '<프리셋>-<크기>-<시드>'의 크기 (정사각형 지도). */
  private mapSize() { return Number(this.builtKey!.split('-').at(-2)); }

  private layoutWant() { return JSON.stringify([this.builtKey, this.s.bots, this.s.color]); }

  /** 모든 나라의 거점 자리('무작위'일 때 그대로 쓴다)와 드래곤 둥지를 미리 받아 둔다 (서버가 게임과 같은 규칙으로). */
  private async ensureLayout() {
    if (!this.mapReady) return;                           // 고르기 모드에서도 받는다 (드래곤 둥지 표시)
    const want = this.layoutWant();
    if ((this.layout && this.layout.key === want) || this.layoutFetching === want) return;
    this.layoutFetching = want;
    try {
      const r = await (await fetch(`/api/maps/${this.builtKey}/layout?bots=${this.s.bots}&color=${this.s.color}`)).json();
      if (this.layoutFetching === want) this.layout = { key: want, starts: r.starts, colors: r.colors, lairs: r.lairs ?? [], sulfur: r.sulfur ?? [] };
    } finally {
      if (this.layoutFetching === want) this.layoutFetching = '';
    }
  }

  private async pickSpot(e: MouseEvent) {
    if (!this.mapReady) { this.say('먼저 지도를 만드세요'); return; }
    const r = this.prevBox.getBoundingClientRect();
    const n = this.mapSize();
    const x = Math.floor(((e.clientX - r.left) / r.width) * n), y = Math.floor(((e.clientY - r.top) / r.height) * n);
    const res = await fetch(`/api/maps/${this.builtKey}/layout?bots=${this.s.bots}&color=${this.s.color}&spot=${y},${x}`);
    const j = await res.json();
    if (!res.ok) { this.say(j.error ?? '그 자리는 고를 수 없습니다'); return; }
    this.s.spot = [y, x];
    this.say('시작 자리를 정했습니다');
    this.render();
  }

  // ------------------------------------------------------------- 시작
  private start() {
    const s = this.s;
    if (this.mode === 'room') {                                    // 방 만들기: 지도가 없으면 만들고 나서
      if (!this.mapReady) { this.startAfterBuild = true; void this.build(); return; }
      this.onRoom?.({ name: s.roomName.trim() || '같이 해요', password: s.password, cap: s.cap, bots: s.bots, start_mode: s.roomStart,
        setup: { map: this.builtKey!, difficulty: s.difficulty, season: s.season },
        player: { name: s.multiName.trim() || randomName(), color: s.color } });
      return;
    }
    if (s.spotMode === 'pick' && (s.spot === null || !this.mapReady)) {
      this.say('지도를 만들고, 미리보기에서 시작할 자리를 클릭하세요');
      return;
    }
    if (!this.mapReady) { this.startAfterBuild = true; void this.build(); return; }
    const options: PlayRequest['options'] = { bots: s.bots, color: s.color, name: s.name.trim() || '나',
      difficulty: s.difficulty, season: s.season, spot: s.spotMode === 'pick' ? s.spot : null };
    if (s.spotMode === 'random' && this.layout && this.layout.key === this.layoutWant()) {
      options.starts = this.layout.starts;                // 무작위 배치를 미리보기에서 봤으면 그대로
      options.colors = this.layout.colors;
    }
    this.onPlay({ key: this.builtKey!, options });
  }

  // ------------------------------------------------------------- 미리보기 (오른쪽)
  /** 화면 크기에 맞춰 미리보기 자리 (한 변 = max(260, min(W - 왼쪽 칸이 차지하는 폭, H-150)), 오른쪽 위). */
  layoutPreview() {
    const ui = uiScale(), W = window.innerWidth / ui, H = window.innerHeight / ui;     // 메뉴 픽셀
    const size = Math.max(Math.min(W - previewReserve(this.left, ui), H - 150), 260);
    this.previewSize = size;
    Object.assign(this.prevBox.style, { width: `${size}px`, height: `${size}px`, left: `${W - size - 40}px`, top: '84px' });
    Object.assign(this.prevCfg.style, { left: `${W - size - 40}px`, top: `${84 + size + 12}px` });
    const px = (window.devicePixelRatio || 1) * ui;               // 실제 화면 픽셀로 또렷하게
    this.prevCanvas.width = Math.round(size * px);
    this.prevCanvas.height = Math.round(size * px);
  }

  private refreshPreview() {
    const name = this.presets.find(([k]) => k === this.s.preset)?.[1] ?? '기본';
    const n = this.adv && this.adv.preset === this.s.preset ? this.adv.count() : 0;
    this.prevCfg.textContent = `${name}${n ? ` (세부 ${n}개 바꿈)` : ''} · ${this.s.size} · 시드 ${this.s.seed}`;
  }

  private lairImg: HTMLCanvasElement | null = null;
  /** 미리보기의 드래곤 표시: 둥지에서 잠든 드래곤 (게임 화면과 같은 그림, 정오 빛). */
  private lairIcon(): HTMLCanvasElement {
    if (this.lairImg) return this.lairImg;
    const nest = this.bank.stack.icon('lair', 0, 1, { dirs: 1 }), drg = this.bank.stack.icon('dragon', 0, 1, { frame: 3, dir: 1 });
    const c = document.createElement('canvas');
    c.width = nest.width; c.height = nest.height;
    const g = c.getContext('2d')!;
    g.drawImage(nest, 0, 0);
    g.drawImage(drg, Math.round((nest.width - drg.width) / 2), Math.round((nest.height - drg.height) / 2 - nest.height * 0.08));
    return (this.lairImg = c);
  }

  private drawPreview() {
    const g = this.prevCanvas.getContext('2d')!, size = this.previewSize, px = this.prevCanvas.width / size;
    g.setTransform(px, 0, 0, px, 0, 0);
    g.clearRect(0, 0, size, size);
    g.imageSmoothingEnabled = false;
    const showImg = !this.building && this.builtKey !== null;
    this.prevImg.style.display = showImg ? '' : 'none';
    const text = (t: string, x: number, y: number, px: number, col: string, base: CanvasTextBaseline = 'middle') => {
      g.font = `${px}px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif`;
      g.textAlign = 'center';
      g.textBaseline = base;
      g.fillStyle = '#000';
      g.fillText(t, x + 1, y + 2);
      g.fillStyle = col;
      g.fillText(t, x, y);
    };
    const c = size / 2;
    if (this.building) {                                  // 도는 점 10개 + 진행 문구 + 지난 시간
      const t = (performance.now() / 1000) * 4;
      for (let k = 0; k < 10; k++) {
        const a = t - k * 0.35, v = 230 - k * 18;
        g.fillStyle = `rgb(${v},${v},${Math.min(255, v + 20)})`;
        g.beginPath();
        g.arc(c + Math.trunc(Math.cos(a) * 22), c - 20 + Math.trunc(Math.sin(a) * 22), Math.max(1, 4 - Math.floor(k / 3)), 0, Math.PI * 2);
        g.fill();
      }
      text(this.buildStatus || '지도 만드는 중...', c, c + 30, 17, INK);
      const sec = (performance.now() - this.buildStart) / 1000;
      text(`${Math.round(sec)}초`, c, c + 56, 14, DIM);
      if (sec > 15) {                                     // 오래 걸린다: 서버가 붐빈다고 알린다
        text('지금 접속자가 많아', c, c + 88, 14, GOLD);
        text('요청이 제때 처리되지 못하고 있습니다', c, c + 108, 14, GOLD);
        text('조금만 더 기다려 주세요', c, c + 132, 13, DIM);
      }
      return;
    }
    if (!showImg) {
      text('지도 만들기를 누르면', c, c - 12, 18, INK);
      text('여기에 미리보기가 나옵니다', c, c + 14, 15, DIM);
      return;
    }
    if (!this.mapReady) {
      g.fillStyle = 'rgba(0,0,0,0.59)';
      g.fillRect(0, 0, size, size);
      text('설정이 바뀌었습니다', c, c - 12, 18, GOLD);
      text('지도 만들기를 누르세요', c, c + 14, 15, INK);
      return;
    }
    const n = this.mapSize();
    const hallKind = this.lobby?.rules.kinds.HALL ?? 0;
    const hall = (y: number, x: number, color: number, me: boolean, label?: string) => {
      const sx = ((x + 0.5) / n) * size, sy = ((y + 0.5) / n) * size;
      const img = this.bank.building(hallKind, color, 2);
      g.drawImage(img, Math.trunc(sx - img.width / 2), Math.trunc(sy + 6 - img.height));
      if (me) {
        g.strokeStyle = '#fff';
        g.lineWidth = 1;
        g.beginPath();
        g.arc(Math.trunc(sx) + 0.5, Math.trunc(sy) + 0.5, 14, 0, Math.PI * 2);
        g.stroke();
        if (label) text(label, sx, sy - 20, 13, INK, 'bottom');
      }
    };
    void this.ensureLayout();
    if (this.layout && this.layout.key === this.layoutWant()) {      // 드래곤 둥지 (설원의 가장 높은 곳)
      const sul = this.bank.site(3, 3);                              // 유황 웅덩이 (사막)
      for (const [y, x] of this.layout.sulfur) {
        const sx = ((x + 0.5) / n) * size, sy = ((y + 0.5) / n) * size;
        g.drawImage(sul, Math.trunc(sx - sul.width / 2), Math.trunc(sy - sul.height / 2));
      }
      const img = this.lairIcon();
      for (const [y, x] of this.layout.lairs) {
        const sx = ((x + 0.5) / n) * size, sy = ((y + 0.5) / n) * size;
        const w = 40, f = w / img.width, h = img.height * f, r = w * 0.75;
        const glow = g.createRadialGradient(sx, sy, 0, sx, sy, r);        // 눈 위에서도 보이게 은은한 그늘 (가장자리는 투명)
        glow.addColorStop(0, 'rgba(10,12,22,0.55)'); glow.addColorStop(1, 'rgba(10,12,22,0)');
        g.fillStyle = glow; g.beginPath(); g.arc(sx, sy, r, 0, Math.PI * 2); g.fill();
        g.imageSmoothingEnabled = true;
        g.drawImage(img, sx - w / 2, sy - h / 2, w, h);
        g.imageSmoothingEnabled = false;
        text('드래곤', sx, sy - h / 2 - 1, 12, 'rgb(200,228,255)', 'bottom');
      }
    }
    if (this.mode === 'room') {
      // 방 만들기: 시작 자리는 대기실에서
    } else if (this.s.spotMode === 'random') {
      if (this.layout && this.layout.key === this.layoutWant()) {
        this.layout.starts.forEach(([y, x], i) => hall(y, x, this.layout!.colors[i], i === 0, this.s.name.trim() || '나'));
      }
    } else if (this.s.spot) hall(this.s.spot[0], this.s.spot[1], this.s.color, true);
    if (this.mode === 'single' && this.s.spotMode === 'pick' && this.mouse) {
      g.strokeStyle = GOLD;
      g.beginPath();
      g.arc(this.mouse[0], this.mouse[1], 10, 0, Math.PI * 2);
      g.stroke();
    }
  }
}

/** 멀티 이름 칸: 입력 + [🎲] (다시 뽑기). 멀티 화면과 방 만들기가 함께 쓴다. */
export function nameField(parent: HTMLElement, s: Settings) {
  const f = field(parent, s.multiName, 10, 200, (v) => { s.multiName = v; });
  const b = button(parent, '🎲', () => { s.multiName = randomName(); f.value = s.multiName; }, { size: 16, w: 40, h: 32 });
  b.title = '다른 이름';
}
