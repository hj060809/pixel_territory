// 게임 화면 하나: 지도 준비 → 지형 장면 → 서버와 판 → 매 프레임 그리기와 입력.
// 로비로 나가거나(F10, 끝난 뒤 Enter) 새 지도로 바꾸면(F6) dispose()로 연결·워커·GL·이벤트를 모두 정리한다.
// 연결이 끊기면 같은 판에 자동으로 다시 접속한다 (서버가 RESUME_SECONDS 동안 판을 멈춘 채 기다린다).
// 탭을 숨기면 일시정지하고, 돌아오면 이어 간다 (내가 멈춘 경우만 다시 푼다).

import { Life } from '../life/life.ts';
import { Camera } from '../sim/camera.ts';
import { TerrainScene } from '../terrain/scene.ts';
import { Loading } from '../ui/loading.ts';
import { ActionBar, TRAIN_KEYS } from './actionBar.ts';
import { Controller } from './controller.ts';
import { Overlay } from './draw.ts';
import { Hud } from './hud.ts';
import { Connection, type JoinOptions } from './net.ts';
import { SpriteBank } from './sprites.ts';
import { GameState, type StartInfo } from './state.ts';
import { F_OCEAN, TerrainRules } from './terrainRules.ts';
import { fadeCovered } from './occlude.ts';
import { TouchInput } from './touch.ts';
import { TouchUi } from './touchUi.ts';
import { DevConsole } from './devConsole.ts';
import { DiploUi } from './diplomacy.ts';
import { setTouchMode, touchMode } from '../ui/device.ts';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 지도 키 '<프리셋>-<크기>-<시드>'에서 시드만 바꾼 키 (F6: 새 지도). */
export function nextSeedKey(key: string): string {
  const parts = key.split('-');
  parts[parts.length - 1] = String((Number(parts[parts.length - 1]) + 1) % 2 ** 31);
  return parts.join('-');
}

/** 지도가 준비될 때까지 (없으면 서버에 만들기를 부탁하고 진행 상황을 보여 준다). */
export async function ensureMap(key: string, progress: (t: string) => void, alive: () => boolean = () => true) {
  while (alive()) {
    const st = await (await fetch(`/api/maps/${key}/status`)).json();
    if (st.state === 'ready') return;
    if (st.state === 'error') throw new Error(st.error);
    if (st.state === 'missing') {
      const [preset, size, seed] = key.split('-');
      await fetch('/api/maps', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: preset === 'default' ? null : preset, size: Number(size), seed }) });
    }
    progress(`지도 만드는 중: ${st.progress ?? '대기 중...'}`);
    await sleep(500);
  }
}

export interface ViewHooks {
  lobby(): void;                 // F10, 끝난 뒤 Enter
  newMap(key: string): void;     // F6
  ready?(): void;                // 첫 장면을 그렸다 (메뉴 배경을 치워도 된다)
}

export class GameView {
  private ac = new AbortController();
  private canvas = document.createElement('canvas');
  private overlay = document.createElement('canvas');
  private loading = new Loading();
  private gl: WebGL2RenderingContext | null = null;
  private scene: TerrainScene | null = null;
  private net: Connection | null = null;
  private hud: Hud | null = null;
  private bar: ActionBar | null = null;
  private dev: DevConsole | null = null;          // 개발용 숨은 콘솔 (서버 --dev)
  private diplo: DiploUi | null = null;           // 외교 말풍선과 동맹 요청 알림
  private tui: TouchUi | null = null;
  private raf = 0;
  private disposed = false;

  /** overMenu: 메뉴 배경 위에서 시작 (로딩 화면을 반투명하게, 첫 장면이 그려질 때까지 게임 화면을 숨긴다). */
  constructor(readonly key: string, readonly opts: JoinOptions, private hooks: ViewHooks, overMenu = false) {
    this.canvas.id = 'view';
    this.overlay.id = 'overlay';
    for (const c of [this.canvas, this.overlay]) c.style.visibility = 'hidden';   // 첫 장면 전의 검은 화면을 숨긴다
    document.body.append(this.canvas, this.overlay);
    this.loading.soft(overMenu);
    this.loading.show('지도 준비 중...');
    this.run().catch((e) => {
      if (this.disposed) return;
      console.error(e);
      this.stuck(`오류: ${String((e as Error).message ?? e)}`, false);
      this.listen(window, 'keydown', (ev: KeyboardEvent) => { if (ev.key === 'F10') { ev.preventDefault(); this.hooks.lobby(); } });
    });
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ac.abort();
    this.net?.close();
    this.scene?.dispose();
    this.hud?.dispose();
    this.bar?.dispose();
    this.dev?.dispose();
    this.diplo?.dispose();
    this.tui?.dispose();
    this.loading.dispose();
    this.gl?.getExtension('WEBGL_lose_context')?.loseContext();     // GPU 메모리를 바로 돌려준다
    this.canvas.remove();
    this.overlay.remove();
    delete (window as any).__game;
  }

  /** 더 이어 갈 수 없는 화면: 알림과 '로비로' 버튼 (키보드면 F10 안내도). show: 로딩 화면을 새로 띄운다. */
  private stuck(text: string, show = true) {
    const t = touchMode() ? text : `${text}  (F10: 로비로)`;
    if (show) this.loading.show(t); else this.loading.set(t);
    this.loading.soft(false);                          // 뒤의 게임 화면·버튼이 비치지 않게
    this.loading.action('로비로', () => this.hooks.lobby());
  }

  private listen<K extends keyof WindowEventMap>(target: Window | Document | HTMLElement, type: K | string,
                                                  fn: (e: any) => void, opts: AddEventListenerOptions = {}) {
    target.addEventListener(type, fn, { ...opts, signal: this.ac.signal });
  }

  private async run() {
    const { canvas, overlay, loading, key } = this;
    const gl = (this.gl = canvas.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: true }));
    if (!gl) { loading.set('이 브라우저는 WebGL2를 지원하지 않습니다'); return; }
    const g = overlay.getContext('2d')!;
    await ensureMap(key, (t) => loading.set(t), () => !this.disposed);
    if (this.disposed) return;
    const scene = await TerrainScene.load(gl, `/api/maps/${key}/bundle.tsb`, {}, (t) => loading.set(t));
    if (this.disposed) { scene.dispose(); return; }
    this.scene = scene;
    scene.cycle.auto = false;                 // 시계는 서버가 정한다
    scene.season.auto = false;
    const life = new Life(scene.bundle, 0);
    const cam = new Camera(scene.W, scene.H);
    cam.overscroll = true;                    // 지도 가장자리도 화면 가운데까지 끌어올 수 있게
    const dpr = () => Math.min(window.devicePixelRatio || 1, touchMode() ? 2 : 8);   // 터치 기기는 2로 제한
    const waveHz = scene.updateHz;
    const resize = () => {
      scene.updateHz = touchMode() ? Math.min(waveHz, 6) : waveHz;    // 모바일: 물결 그림 갱신을 낮춰 배터리·발열을 줄인다
      for (const c of [canvas, overlay]) { c.width = Math.round(window.innerWidth * dpr()); c.height = Math.round(window.innerHeight * dpr()); }
      cam.resize(window.innerWidth, window.innerHeight);
    };
    resize();
    cam.fit();
    this.listen(window, 'resize', resize);

    let st: GameState | null = null, ctl: Controller | null = null, draw: Overlay | null = null;
    let rules: TerrainRules | null = null;
    loading.set('판 준비 중...');
    const stuck = (text: string, show = true) => this.stuck(text, show);
    const net = (this.net = new Connection(key, this.opts, {
      start: async (info: StartInfo) => {
        const first = !st;
        sid = info.sid ?? sid;
        if (info.resumed && reconnecting) {               // 다시 접속: 화면 자리는 그대로, 전체 상태가 곧 온다
          reconnecting = false;
          loading.fadeOut();
        }
        st = new GameState(info);
        rules ??= await TerrainRules.load(`/api/maps/${key}/rules.bin`, info.rules);
        if (this.disposed) return;
        ctl = new Controller(st, net, rules);
        const FISH = info.rules.kinds?.FISH;                // 물고기 자원지: 그 앞바다를 헤엄치는 물고기 떼
        const balls: [number, number][] = [];
        for (const s of info.sites) {
          const f = s.kind === FISH ? ctl.fishSpot(s) : null;
          if (!f) continue;
          // 무리 가운데는 표시에서 바다 쪽으로 조금 더 (물가에 걸려 반쪽이 되지 않게, 표시는 무리 안쪽에)
          const dx = f.x - s.x, dy = f.y - s.y, n = Math.hypot(dx, dy) || 1;
          let cx = f.x, cy = f.y;
          for (let t = 3; t >= 0.5; t -= 0.5) {
            const x = Math.round(f.x + (dx / n) * t), y = Math.round(f.y + (dy / n) * t);
            if (x >= 0 && y >= 0 && x < rules.W && y < rules.H && rules.at(y, x) & F_OCEAN) { cx = x; cy = y; break; }
          }
          balls.push([cx + 0.5, cy + 0.5]);
        }
        life.setBaitBalls(balls);
        const bank = new SpriteBank(info.nations.map((n) => n.color));
        draw = new Overlay(g, bank, st, ctl, scene);
        if (!this.diplo) this.diplo = new DiploUi(st, ctl, net);
        else this.diplo.reset(st, ctl);
        const dui = this.diplo;
        ctl.onForeignHall = (b) => dui.openFor(b);
        this.bar?.dispose();
        this.bar = new ActionBar(st, ctl, bank);          // 하단 버튼 (건물 1~, 병종 QWE)
        if (!this.hud) this.hud = new Hud(st, ctl, scene, rules);
        else this.hud.reset(st, ctl);
        if (!first && !info.resumed) loading.hide();
        if (!info.resumed) waitHome = true;   // 첫 상태가 오면 내 거점으로 (그리고 두 프레임 뒤에 화면을 보인다)
      },
      state(m) {
        if (!st) return;
        st.apply(m, performance.now());
        if (waitHome) { waitHome = false; centerHome(4.0); revealAt = 2; }
      },
      msg(items) { for (const t of items) st?.say(t); hudWait = 1; },
      over(result) { if (st) st.over = result; hudWait = 1; },
      diplo: (m) => { if (st) { st.diplo = m; this.diplo?.render(); } },
      status(text) { loading.set(text); },
      error(text, fatal) {
        if (fatal) {                          // 판을 이어 갈 수 없다: 다시 접속하지 않는다
          gaveUp = true;
          stuck(text);
        } else if (st) st.say(text);
        else stuck(`오류: ${text}`, false);
      },
      closed: () => {
        if (this.disposed || gaveUp) return;
        if (!st || !sid) { this.stuck('서버와 연결이 끊겼습니다'); return; }
        if (!reconnecting) {                  // 처음 끊긴 순간
          reconnecting = true;
          lostAt = performance.now();
          loading.soft(true);
          loading.show('서버와 연결이 끊겼습니다. 다시 연결하는 중...');
        }
        if (performance.now() - lostAt > 55000) {
          gaveUp = true;
          this.stuck('다시 연결하지 못했습니다', false);
          return;
        }
        setTimeout(() => { if (!this.disposed && reconnecting) net.resume(sid!); }, 1500);
      },
    }));
    let waitHome = false, revealAt = -1;
    let sid: string | null = null, reconnecting = false, gaveUp = false, lostAt = 0, autoPaused = false;
    this.listen(document, 'visibilitychange', () => {   // 탭을 숨기면 일시정지, 돌아오면 이어 간다
      if (!st || st.over) return;
      if (document.hidden && !st.paused) { autoPaused = true; net.send({ t: 'pause', on: true }); }
      else if (!document.hidden && autoPaused) { autoPaused = false; net.send({ t: 'pause', on: false }); }
    });

    const centerHome = (zoom?: number) => {
      if (!st || !ctl) return;
      let x = 0, y = 0, n = 0;
      for (const s of ctl.sel.keys()) { const u = st.units.get(s); if (u) { x += u.x; y += u.y; n++; } }
      if (!n) {
        const hall = [...st.builds.values()].find((b) => b.own === st!.info.me && b.kind === st!.info.rules.kinds.HALL);
        const u = [...st.units.values()].find((v) => v.own === st!.info.me);
        const src = hall ?? u;
        if (!src) return;
        x = src.x; y = src.y; n = 1;
      }
      if (zoom) cam.zoom = cam.zoomTarget = zoom;
      const [vw, vh] = cam.view();
      cam.x = x / n - vw / 2; cam.y = y / n - vh / 2;
      cam.clamp();
    };

    // ---- 입력
    const keys = new Set<string>();
    let mouse: [number, number] | null = null, box: [number, number, number, number] | null = null;
    let midDrag = false, lifeClick: [number, number] | null = null, hudWait = 1;
    const pending = { speed: 1, speedAt: -1e9, pause: false, pauseAt: -1e9 };   // 방금 보낸 속도/일시정지 (답이 오기 전)
    const togglePause = () => {               // 서버 답을 기다리지 않고 마지막으로 요청한 값 기준으로
      if (!st) return;
      const cur = performance.now() - pending.pauseAt < 1000 ? pending.pause : st.paused;
      pending.pause = !cur; pending.pauseAt = performance.now();
      net.send({ t: 'pause', on: pending.pause });
    };
    const cycleSpeed = () => {
      if (!st) return;
      const cur = performance.now() - pending.speedAt < 1000 ? pending.speed : st.speed;
      pending.speed = cur === 1 ? 2 : cur === 2 ? 4 : 1; pending.speedAt = performance.now();
      net.send({ t: 'speed', value: pending.speed });
    };
    // ---- 터치 (손가락 동작 → 같은 행동, 터치용 버튼). 마지막으로 쓴 입력에 따라 화면이 바뀐다
    const touch = new TouchInput(cam, {
      ctl: () => ctl,
      box: (b) => { box = b; },
      info: (sx, sy) => this.tui?.showInfo(sx, sy),
      commanded: (mx, my) => { lifeClick = [mx, my]; },
      changed: () => { hudWait = 1; },
    });
    this.tui = new TouchUi({
      st: () => st, ctl: () => ctl, cam, touch,
      infoAt: (mx, my) => this.hud?.infoAt(mx, my, cam.zoom) ?? null,
      pause: togglePause, speed: cycleSpeed, home: () => centerHome(),
      restart: () => net.send({ t: 'restart' }), newMap: () => this.hooks.newMap(nextSeedKey(key)), lobby: () => this.hooks.lobby(),
      changed: () => { hudWait = 1; },
    });
    let lastTouch = -1e9;                     // 터치 뒤 브라우저가 흉내 내 보내는 마우스 이벤트는 무시한다
    const fromTouch = () => performance.now() - lastTouch < 800;
    this.listen(canvas, 'pointerdown', (e: PointerEvent) => {
      if (e.pointerType === 'mouse') { if (touchMode()) { setTouchMode(false); resize(); } return; }
      e.preventDefault();
      lastTouch = performance.now();
      if (!touchMode()) { setTouchMode(true); resize(); }
      mouse = null;
      canvas.setPointerCapture?.(e.pointerId);
      touch.down(e);
      hudWait = 1;
    });
    for (const [type, fn] of [['pointermove', (e: PointerEvent) => touch.move(e)], ['pointerup', (e: PointerEvent) => touch.up(e)],
                              ['pointercancel', (e: PointerEvent) => touch.cancel(e)]] as const) {
      this.listen(canvas, type, (e: PointerEvent) => {
        if (e.pointerType === 'mouse') return;
        lastTouch = performance.now();
        fn(e);
      });
    }
    overlay.style.pointerEvents = 'none';
    this.listen(canvas, 'contextmenu', (e) => e.preventDefault());
    this.listen(canvas, 'wheel', (e: WheelEvent) => { e.preventDefault(); cam.zoomTo(1.15 ** (-e.deltaY / 100), [e.clientX, e.clientY]); }, { passive: false });
    this.listen(canvas, 'mousedown', (e: MouseEvent) => {
      if (!ctl || fromTouch()) return;
      const [mx, my] = cam.toMap(e.clientX, e.clientY);
      if (e.button === 0) {
        if (ctl.mode === 'attack') { ctl.command(mx, my, cam.zoom, true); ctl.mode = null; }
        else if (typeof ctl.mode === 'number') { ctl.place(mx, my, cam.zoom, e.shiftKey); this.bar?.update(); }
        else box = [e.clientX, e.clientY, e.clientX, e.clientY];
      } else if (e.button === 2) {
        if (ctl.mode !== null) { ctl.mode = null; this.bar?.update(); }
        else { ctl.command(mx, my, cam.zoom, false); lifeClick = [mx, my]; }
      } else if (e.button === 1) { midDrag = true; e.preventDefault(); }
      hudWait = 1;
    });
    this.listen(window, 'mouseup', (e: MouseEvent) => {
      if (fromTouch()) return;
      if (e.button === 0 && box && ctl) {
        const [ax, ay, bx, by] = box;
        box = null;
        if (Math.abs(ax - bx) + Math.abs(ay - by) < 6) ctl.selectPoint(...cam.toMap(bx, by), cam.zoom, e.shiftKey);
        else {
          const [x0, y0] = cam.toMap(Math.min(ax, bx), Math.min(ay, by)), [x1, y1] = cam.toMap(Math.max(ax, bx), Math.max(ay, by));
          ctl.selectBox(x0, y0, x1, y1, e.shiftKey);
        }
        hudWait = 1;
      }
      if (e.button === 1) midDrag = false;
    });
    this.listen(window, 'mousemove', (e: MouseEvent) => {
      if (fromTouch()) return;
      mouse = [e.clientX, e.clientY];
      if (box) { box[2] = e.clientX; box[3] = e.clientY; }
      if (midDrag) cam.pan(e.movementX, e.movementY);
    });
    this.listen(document, 'mouseleave', () => { mouse = null; });
    this.listen(window, 'keyup', (e: KeyboardEvent) => keys.delete(e.key));
    this.listen(window, 'keydown', (e: KeyboardEvent) => {
      if (e.code === 'Backquote' && st?.info.dev) {     // 개발용 숨은 콘솔 (서버 --dev일 때만)
        e.preventDefault();
        this.dev ??= new DevConsole(net, (t) => st?.say(t));
        this.dev.toggle();
        return;
      }
      keys.add(e.key);
      const k = e.key.toLowerCase();
      const digit = /^Digit[1-9]$/.test(e.code) ? Number(e.code.slice(5)) : 0;   // Shift를 눌러도 숫자 (e.key는 '!' 등)
      if (['f1', 'f5', 'f6', 'f10', 'f12', ' ', 'tab'].includes(k) || (digit && (e.ctrlKey || e.shiftKey))) e.preventDefault();
      if (k === 'f10' || (k === 'enter' && st?.over)) { this.hooks.lobby(); return; }
      if (k === 'f6') { this.hooks.newMap(nextSeedKey(key)); return; }
      const hud = this.hud;
      if (!ctl || !st || !hud) return;
      hudWait = 1;
      if (digit) {                            // 숫자: 건물 버튼 / Ctrl+숫자: 부대 지정 / Shift+숫자: 부대 부르기
        if (e.ctrlKey) ctl.setGroup(digit);
        else if (e.shiftKey) ctl.recallGroup(digit);
        else this.bar?.buildKey(digit);
        return;
      }
      const train = TRAIN_KEYS.find(([key]) => key === k);
      if (train && !e.ctrlKey) { ctl.train(train[1]); this.bar?.update(); return; }   // Q 보병, W 궁수, E 전함
      switch (k) {
        case 'escape':
          if (this.diplo?.isOpen) this.diplo.close();
          else if (ctl.mode !== null) ctl.mode = null; else { ctl.sel.clear(); ctl.selB = null; ctl.selShips.clear(); }
          break;
        case 'a': if (ctl.sel.size) ctl.mode = 'attack'; break;
        case 's': ctl.stop(); break;
        case ' ': centerHome(); break;
        case 'p': togglePause(); break;
        case '.': cycleSpeed(); break;
        case 'f1': hud.showHelp = !hud.showHelp; break;
        case 'f5': net.send({ t: 'restart' }); break;
        case 'f12': screenshot(canvas, overlay); break;
      }
    });

    // ---- 루프
    let last = performance.now();
    const frame = (now: number) => {
      if (this.disposed) return;
      this.raf = requestAnimationFrame(frame);           // 먼저 다음 프레임을 잡는다: 그리다 오류가 나도 게임이 멈추지 않게
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      cam.ease(dt);
      const step = (600 * dt) / cam.zoom;
      let dx = (+keys.has('ArrowRight') - +keys.has('ArrowLeft')) * step;
      let dy = (+keys.has('ArrowDown') - +keys.has('ArrowUp')) * step;
      if (mouse && document.hasFocus() && !box) {           // 화면 가장자리
        dx += (+(mouse[0] >= window.innerWidth - 4) - +(mouse[0] <= 3)) * step;
        dy += (+(mouse[1] >= window.innerHeight - 4) - +(mouse[1] <= 3)) * step;
      }
      if (dx || dy) { cam.x += dx; cam.y += dy; cam.clamp(); }
      if (st) {
        scene.cycle.hour = st.hour;
        scene.season.year = st.year;
      }
      scene.update(0, dt);
      const mm = mouse ? cam.toMap(mouse[0], mouse[1]) : null;
      life.update(dt, mm, lifeClick);
      lifeClick = null;
      scene.draw(canvas.width, canvas.height, cam.x, cam.y, cam.zoom * dpr(), life);
      g.setTransform(dpr(), 0, 0, dpr(), 0, 0);
      g.clearRect(0, 0, window.innerWidth, window.innerHeight);
      let pointer = mouse;
      if (touchMode()) {                                  // 터치: 건물 그림은 손가락으로 옮긴 자리 (처음엔 화면 가운데)
        if (ctl && typeof ctl.mode === 'number') touch.ghost ??= cam.toMap(window.innerWidth / 2, window.innerHeight / 2 - 30);
        else touch.ghost = null;
        pointer = touch.ghost ? [(touch.ghost[0] - cam.x) * cam.zoom, (touch.ghost[1] - cam.y) * cam.zoom] : null;
      }
      if (st && draw) draw.draw(cam, now, pointer, box);
      this.diplo?.frame(cam);
      this.tui?.frame();
      hudWait += dt;
      if (this.hud && hudWait >= 0.25) {
        hudWait = 0;
        this.hud.update(cam, touchMode() ? null : mouse);
        this.diplo?.render();
        this.bar?.update();
        this.tui?.update();
        if (st) fadeCovered([...this.hud.panels(), ...(this.bar ? [this.bar.el] : []), ...(this.tui?.panels() ?? [])],
                            onScreen(st, cam, pointer));
      }
      if (revealAt > 0 && --revealAt === 0) {            // 첫 장면이 그려졌다: 보이고, 로딩 화면은 천천히 사라진다
        for (const c of [canvas, overlay]) c.style.visibility = '';
        loading.set('');
        loading.fadeOut();
        this.hooks.ready?.();
      }
    };
    this.raf = requestAnimationFrame(frame);
    (window as any).__game = { get st() { return st; }, get ctl() { return ctl; }, cam, scene, net, key, life };
  }
}

/** 화면에 보이는 병사·배·건물(과 놓을 건물 그림)의 화면 자리: 이것들을 가리는 상자는 반투명하게. */
function onScreen(st: GameState, cam: Camera, pointer: [number, number] | null): [number, number][] {
  const out: [number, number][] = [], W = window.innerWidth, H = window.innerHeight, z = cam.zoom;
  const add = (x: number, y: number) => {
    const sx = (x - cam.x) * z, sy = (y - cam.y) * z;
    if (sx >= 0 && sx <= W && sy >= 0 && sy <= H) out.push([sx, sy]);
  };
  for (const u of st.units.values()) if (!(u.bits & 2)) add(u.x, u.y - 0.6);
  for (const b of st.boats.values()) add(b.x, b.y);
  for (const b of st.builds.values()) add(b.x, b.y);
  if (pointer) out.push(pointer);
  return out;
}

function screenshot(a: HTMLCanvasElement, b: HTMLCanvasElement) {
  const c = document.createElement('canvas');
  c.width = a.width; c.height = a.height;
  const g = c.getContext('2d')!;
  g.drawImage(a, 0, 0);
  g.drawImage(b, 0, 0);
  const link = document.createElement('a');
  link.download = `game_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
  link.href = c.toDataURL('image/png');
  link.click();
}
