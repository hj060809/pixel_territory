// 게임 페이지: 로비 → 설정 → 게임 → (F10, 끝난 뒤 Enter) 로비. 데스크톱 game/app.py의 화면 흐름과 같다.
// 주소에 map= 또는 quick= 가 있으면 메뉴 없이 바로 판을 연다 (개발·시험용):
//   /?quick=1&bots=4&color=0&name=나&difficulty=보통&season=0     /?map=<지도 키>&...

import '../ui/style.css';
import { GameView } from '../game/view.ts';
import type { JoinOptions } from '../game/net.ts';
import { Lobby } from '../menu/lobby.ts';
import { LobbyArt, type LobbyInfo } from '../menu/lobbyArt.ts';
import { Setup, defaultSettings, type PlayRequest, type Settings } from '../menu/setup.ts';
import { applyUiScale, shadeLeft, uiScale } from '../menu/widgets.ts';

type Screen = 'lobby' | 'setup' | 'game';

class App {
  private art = new LobbyArt();
  private artCanvas = document.createElement('canvas');
  private screen: Screen = 'lobby';
  private lobby: Lobby;
  private setup: Setup | null = null;
  private game: GameView | null = null;
  private settings: Settings = defaultSettings();
  private lobbyInfo: LobbyInfo | null = null;
  private listing: any = null;
  private raf = 0;
  private artLoad: Promise<void>;

  constructor() {
    this.artLoad = this.art.load().then((info) => { this.lobbyInfo = info; });
    this.artCanvas.id = 'menu-art';
    document.body.appendChild(this.artCanvas);
    this.lobby = new Lobby(() => void this.show('setup'));
    window.addEventListener('resize', () => { applyUiScale(); this.resizeArt(); this.setup?.layoutPreview(); });
    applyUiScale();
    window.addEventListener('keydown', (e) => {
      if (this.screen === 'lobby') this.lobby.key(e);
      else if (this.screen === 'setup' && this.setup?.el.isConnected) this.setup.key(e);
    });
    this.resizeArt();
  }

  async boot() {
    const p = new URLSearchParams(location.search);
    if (p.has('map') || p.has('quick')) {
      const key = p.get('map') ?? (await (await fetch('/api/maps')).json()).demo[0].key;
      this.play({ key, options: {
        bots: Number(p.get('bots') ?? 4), color: Number(p.get('color') ?? 0), name: p.get('name') ?? '나',
        difficulty: p.get('difficulty') ?? '보통', season: Number(p.get('season') ?? 0) } });
      return;
    }
    await this.show('lobby');
  }

  private async show(screen: Screen) {
    this.screen = screen;
    this.game?.dispose();
    this.game = null;
    this.setup?.detach();
    this.lobby.closeHelp();
    this.lobby.el.remove();
    if (screen === 'game') return;            // 메뉴 배경은 게임이 첫 장면을 그릴 때까지 남겨 둔다 (hideArt)
    this.artCanvas.style.display = '';
    this.startArt();
    if (screen === 'lobby') document.body.appendChild(this.lobby.el);
    else {
      this.listing ??= await (await fetch('/api/maps')).json();
      await this.artLoad;
      if (this.screen !== 'setup') return;
      this.setup ??= new Setup(this.settings, this.lobbyInfo, this.listing, () => void this.show('lobby'), (req) => this.play(req));
      this.setup.attach();
    }
  }

  private play(req: PlayRequest) {
    void this.show('game');
    const start = (key: string, options: JoinOptions, overMenu: boolean) => {
      this.game?.dispose();
      this.game = new GameView(key, options, {
        lobby: () => void this.show('lobby'),
        // 새 지도: 고른 시작 자리와 미리보기 배치는 그 지도에서만 맞으니 버린다
        newMap: (next) => start(next, { ...options, spot: null, starts: null, colors: null }, false),
        ready: () => this.hideArt(),
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
