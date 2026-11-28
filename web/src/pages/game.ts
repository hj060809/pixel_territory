// 게임 페이지: 로비 → [싱글] 설정 → 게임, [멀티] 방 목록 → (새 방: 방 설정) → 대기실 → 게임. 게임에서 F10·끝난 뒤 Enter → 로비.
// 주소에 map= 또는 quick= 가 있으면 메뉴 없이 바로 판을 연다 (개발·시험용):
//   /?quick=1&bots=4&color=0&name=나&difficulty=보통&season=0&fog=1&starts=y,x;y,x...     /?map=<지도 키>&...

import '../ui/style.css';
import { GameView, clearResume, loadResume } from '../game/view.ts';
import { Connection, type JoinOptions } from '../game/net.ts';
import { Lobby } from '../menu/lobby.ts';
import { LobbyArt, type LobbyInfo } from '../menu/lobbyArt.ts';
import { Setup, defaultSettings, type PlayRequest, type RoomRequest, type Settings } from '../menu/setup.ts';
import { MultiMenu, type JoinRequest } from '../menu/multi.ts';
import { RoomView } from '../menu/room.ts';
import { applyUiScale, shadeLeft, uiScale } from '../menu/widgets.ts';
import { enterFullscreen, isStandalone, isTouchDevice, setTouchMode, touchMode } from '../ui/device.ts';
import { registerServiceWorker, showFullscreenNote } from '../ui/install.ts';
import { startVis, visPref } from '../game/visibility.ts';

type Screen = 'lobby' | 'setup' | 'multi' | 'roomsetup' | 'room' | 'game';

class App {
  private art = new LobbyArt();
  private artCanvas = document.createElement('canvas');
  private screen: Screen = 'lobby';
  private lobby: Lobby;
  private setup: Setup | null = null;
  private roomSetup: Setup | null = null;       // 새 방 만들기 (같은 설정 화면, 방 항목을 더해)
  private multi: MultiMenu | null = null;
  private room: RoomView | null = null;
  private game: GameView | null = null;
  private settings: Settings = defaultSettings();
  private lobbyInfo: LobbyInfo | null = null;
  private listing: any = null;
  private raf = 0;
  private artLoad: Promise<void>;

  constructor() {
    setTouchMode(isTouchDevice());
    document.body.classList.toggle('standalone', isStandalone());   // 앱으로 열었으면 [앱으로 설치]를 숨긴다              // 처음엔 기기에 맞춰. 게임 중에는 마지막으로 쓴 입력(터치 / 마우스)으로 바뀐다
    const rotate = document.createElement('div');   // 터치 기기를 세로로 들면 (CSS로만 보인다)
    rotate.className = 'rotate-notice';
    rotate.innerHTML = '<div>화면을 가로로 돌려 주세요<div class="dim">Pixel Territory는 가로 화면에서 플레이합니다</div></div>';
    document.body.appendChild(rotate);
    this.artLoad = this.art.load().then((info) => { this.lobbyInfo = info; });
    this.artCanvas.id = 'menu-art';
    document.body.appendChild(this.artCanvas);
    this.lobby = new Lobby(() => {
      if (touchMode()) void enterFullscreen();     // 모바일: '싱글 플레이'를 누르는 순간 주소창을 내린다 (누른 순간에만 허용된다)
      void this.show('setup');
    }, () => {
      if (touchMode()) void enterFullscreen();
      void this.show('multi');
    }, () => {
      if (touchMode()) void enterFullscreen();
      void this.startTutorial();
    });
    window.addEventListener('resize', () => {
      applyUiScale(); this.resizeArt(); this.setup?.layoutPreview(); this.roomSetup?.layoutPreview(); this.room?.layoutPreview();
    });
    applyUiScale();
    window.addEventListener('keydown', (e) => {
      if (this.screen === 'lobby') this.lobby.key(e);
      else if (this.screen === 'setup' && this.setup?.el.isConnected) this.setup.key(e);
      else if (this.screen === 'roomsetup' && this.roomSetup?.el.isConnected) this.roomSetup.key(e);
      else if (this.screen === 'multi') this.multi?.key(e);
      else if (this.screen === 'room') this.room?.key(e);
    });
    this.resizeArt();
  }

  async boot() {
    const p = new URLSearchParams(location.search);
    registerServiceWorker();
    // 터치 기기로 알아보지 못했으면 (PC처럼 보이는 기기): 처음 터치하는 순간 터치 화면으로 (게임 시작 → 전체 화면도 걸리게)
    const firstTouch = (e: PointerEvent) => {
      if (e.pointerType !== 'touch') return;
      window.removeEventListener('pointerdown', firstTouch, true);
      setTouchMode(true);
    };
    if (!touchMode()) window.addEventListener('pointerdown', firstTouch, true);
    if (p.has('map') || p.has('quick')) {
      const key = p.get('map') ?? (await (await fetch('/api/maps')).json()).demo[0].key;
      this.play({ key, options: {
        bots: Number(p.get('bots') ?? 4), color: Number(p.get('color') ?? 0), name: p.get('name') ?? '나',
        difficulty: p.get('difficulty') ?? '보통', season: Number(p.get('season') ?? 0), fog: p.get('fog') === '1',
        starts: p.get('starts') ? p.get('starts')!.split(';').map((q) => q.split(',').map(Number)) : null } });   // starts=y,x;y,x (사람 다음 AI)
      return;
    }
    if (await this.resumeGame()) return;
    await this.show('lobby');
    if (touchMode()) showFullscreenNote();       // 모바일: 처음 한 번 '게임 시작을 누르면 전체 화면' 안내
  }

  private async show(screen: Screen, msg?: string, busy = false) {
    this.screen = screen;
    this.game?.dispose();
    this.game = null;
    this.setup?.detach();
    this.roomSetup?.detach();
    this.multi?.detach();
    if (screen !== 'room') { this.room?.dispose(); this.room = null; }
    this.lobby.closeHelp();
    this.lobby.el.remove();
    if (screen === 'game') return;            // 메뉴 배경은 게임이 첫 장면을 그릴 때까지 남겨 둔다 (hideArt)
    this.artCanvas.style.display = '';
    this.startArt();
    if (screen === 'lobby') { document.body.appendChild(this.lobby.el); void this.lobby.checkBusy(); this.lobby.maybeShowPatch(); return; }   // 패치노트: 페이지를 열고 처음 한 번
    await this.artLoad;
    if (screen === 'multi') {
      this.multi ??= new MultiMenu(this.settings, this.lobbyInfo, () => void this.show('lobby'),
        () => void this.show('roomsetup'), (req) => this.enterRoom(req));
      this.multi.attach();
      if (busy && msg) this.multi.busy(msg); else this.multi.say(msg ?? '');
      return;
    }
    if (screen === 'room') return;                 // enterRoom이 붙인다
    this.listing ??= await (await fetch('/api/maps')).json();
    if (this.screen !== screen) return;
    if (screen === 'setup') {
      this.setup ??= new Setup(this.settings, this.lobbyInfo, this.listing, () => void this.show('lobby'), (req) => this.play(req));
      this.setup.attach();
    } else if (screen === 'roomsetup') {
      this.roomSetup ??= new Setup(this.settings, this.lobbyInfo, this.listing, () => void this.show('multi'), () => {}, 'room',
        (req) => this.enterRoom(req));
      this.roomSetup.attach();
    }
  }

  /** 대기실로: 새 방 만들기 (RoomRequest) 또는 들어가기 (JoinRequest). 연결은 대기실이 연다. */
  private enterRoom(req: RoomRequest | JoinRequest) {
    void this.show('room');
    const first = 'setup' in req ? { t: 'room_create', ...req } : { t: 'room_join', ...req };
    this.room = new RoomView(first, this.lobbyInfo, {
      leave: (msg, busy) => void this.show('multi', msg, busy),
      start: (conn, key, vis) => this.playRoom(conn, key, vis),
    });
    this.room.attach();
  }

  /** 방장이 시작했다: 대기실의 연결을 그대로 게임 화면에. */
  private playRoom(conn: Connection, key: string, vis: boolean) {
    startVis(vis);                                   // 방 기본값으로 시작 (게임 중 메뉴에서 각자 바꾼다)
    this.room?.dispose();                            // 연결은 넘겼으니 닫지 않는다
    this.room = null;
    void this.show('game');
    this.game = new GameView(key, {}, this.roomHooks(), this.artCanvas.style.display !== 'none', conn);
  }

  private roomHooks() {
    return {
      lobby: () => void this.show('lobby'),
      newMap: () => void this.show('setup'),         // 사람이 여럿인 판에는 없다 (다시 연 싱글 판이면 설정 화면으로)
      ready: () => this.hideArt(),
      single: () => void this.show('setup'),
      room: (conn: Connection) => this.backToRoom(conn),
    };
  }

  /** 판이 끝났다: 그 연결로 같은 방의 대기실에 다시 들어간다. */
  private backToRoom(conn: Connection) {
    void this.show('room');                          // 게임 화면을 치운다 (연결은 넘겨받았으니 닫히지 않는다)
    this.room = new RoomView(conn, this.lobbyInfo, {
      leave: (msg, busy) => void this.show('multi', msg, busy),
      start: (c, key, vis) => this.playRoom(c, key, vis),
    });
    this.room.attach();
  }

  /** 브라우저를 다시 열었다: 끊긴 채 기다리는 내 자리가 있으면 그 판으로 (없으면 false). */
  private async resumeGame(): Promise<boolean> {
    const r = loadResume();
    if (!r) return false;
    let ok = false;
    try {
      const q = await (await fetch(`/api/resume?sid=${encodeURIComponent(r.sid)}&token=${encodeURIComponent(r.token)}`)).json();
      ok = !!q.ok && q.map === r.map;
    } catch { /* 서버에 못 닿으면 로비로 */ }
    if (!ok) { clearResume(r.token); return false; }
    await this.artLoad;
    void this.show('game');
    const conn = Connection.open({ t: 'resume', sid: r.sid, token: r.token }, null);
    this.game = new GameView(r.map, {}, this.roomHooks(), true, conn);
    return true;
  }

  /** 로비 '튜토리얼': 데모 지도로 튜토리얼 판 (sim/tutorial.py, game/tutorial.ts). */
  private async startTutorial() {
    this.listing ??= await (await fetch('/api/maps')).json();
    const key = this.listing.demo[0].key;
    this.play({ key, options: { tutorial: true, bots: 1, color: this.settings.color, name: this.settings.name.trim() || '나',
      difficulty: '보통', season: 0 } });
  }

  private play(req: PlayRequest) {
    startVis(visPref());                             // 싱글: 설정 화면에서 고른 값
    void this.show('game');
    const start = (key: string, options: JoinOptions, overMenu: boolean) => {
      this.game?.dispose();
      this.game = new GameView(key, options, {
        lobby: () => void this.show('lobby'),
        // 새 지도: 고른 시작 자리와 미리보기 배치는 그 지도에서만 맞으니 버린다
        newMap: (next) => start(next, { ...options, spot: null, starts: null, colors: null }, false),
        ready: () => this.hideArt(),
        single: () => void this.show('setup'),
      }, overMenu);
    };
    start(req.key, req.options, this.artCanvas.style.display !== 'none');
  }

  /** 게임 화면이 첫 장면을 그렸으면 메뉴 배경을 멈추고 치운다. */
  private hideArt() {
    if (this.screen !== 'game') return;
    this.artCanvas.style.display = 'none';
    cancelAnimationFrame(this.raf);
  }

  // ---- 메뉴 배경 (로비: 왼쪽 그늘, 설정: 전체를 어둡게)
  private resizeArt() {
    const dpr = window.devicePixelRatio || 1;
    this.artCanvas.width = Math.round(window.innerWidth * dpr);
    this.artCanvas.height = Math.round(window.innerHeight * dpr);
  }

  private startArt() {
    cancelAnimationFrame(this.raf);
    const g = this.artCanvas.getContext('2d')!;
    const tick = () => {
      const W = window.innerWidth, H = window.innerHeight, dpr = window.devicePixelRatio || 1;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.art.draw(g, W, H);
      if (this.screen === 'lobby') shadeLeft(g, Math.min(620 * uiScale(), Math.floor(W / 2) + 80), H);
      else { g.fillStyle = 'rgba(8,10,14,0.588)'; g.fillRect(0, 0, W, H); }
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  /** 시험용 */
  get debug() { return { screen: this.screen, setup: this.setup, game: this.game, settings: this.settings }; }
}

const app = new App();
(window as any).__app = app;
app.boot().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML('beforeend', `<div class="hud">오류: ${String(e)}</div>`);
});
