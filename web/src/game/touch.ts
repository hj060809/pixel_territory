// 터치 입력: 손가락 동작을 PC와 같은 행동(고르기, 명령, 화면 이동, 확대, 건물 놓기)으로 바꾼다.
// 규칙과 서버 명령은 Controller 그대로 쓴다 (PC 입력은 view.ts의 마우스 처리 그대로).
//
//   탭                  내 병사·배·건물이면 고르기 / 고른 게 있으면 그곳으로 명령 (이동·공격·짓기) / 아무것도 없으면 설명
//   한 손가락 끌기       화면 이동
//   두 손가락            벌리고 오므려 확대, 함께 움직여 화면 이동
//   길게 누르기          그 자리 설명 카드 (지형, 자원지, 배)
//   길게 누른 뒤 끌기     선택 상자 (여러 명)
//   건물 놓는 중         탭한 곳으로 건물 그림을 옮기고, 그림을 끌어서 옮기고, ✓ 로 짓는다 (touchUi)

import type { Camera } from '../sim/camera.ts';
import type { Controller } from './controller.ts';

export const TOUCH_PX = 18;         // 손가락으로 고르는 반경 (화면 픽셀)
const MOVE_PX = 10;                 // 이만큼 움직이면 탭이 아니라 끌기
const LONG_MS = 420;                // 이만큼 누르고 있으면 길게 누르기

export interface TouchHooks {
  ctl(): Controller | null;
  box(b: [number, number, number, number] | null): void;   // 선택 상자 그리기
  info(sx: number, sy: number): void;                       // 설명 카드
  commanded(mx: number, my: number): void;                  // 명령을 내렸다 (새와 물고기가 놀라 흩어지게)
  changed(): void;                                          // 화면 정보를 바로 갱신
}

type Mode = 'none' | 'pending' | 'pan' | 'long' | 'box' | 'pinch' | 'ghost';

export class TouchInput {
  /** 놓을 건물 그림 자리 (지도 좌표). 건물 놓기를 시작하면 화면 가운데에 생긴다. */
  ghost: [number, number] | null = null;
  /** [+]를 켜면 고른 것에 더한다 (PC의 Shift). */
  add = false;
  private pts = new Map<number, [number, number]>();
  private mode: Mode = 'none';
  private start: [number, number] = [0, 0];
  private timer = 0;
  private pinch = { d: 1, mx: 0, my: 0 };

  constructor(private cam: Camera, private h: TouchHooks) {}

  down(e: PointerEvent) {
    this.pts.set(e.pointerId, [e.clientX, e.clientY]);
    clearTimeout(this.timer);
    if (this.pts.size === 1) {
      this.start = [e.clientX, e.clientY];
      if (this.nearGhost(e.clientX, e.clientY)) { this.mode = 'ghost'; return; }
      this.mode = 'pending';
      this.timer = window.setTimeout(() => this.long(), LONG_MS);
    } else if (this.pts.size === 2) {
      this.mode = 'pinch';
      this.h.box(null);
      const [a, b] = [...this.pts.values()];
      this.pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, mx: (a[0] + b[0]) / 2, my: (a[1] + b[1]) / 2 };
    }
  }

  move(e: PointerEvent) {
    const prev = this.pts.get(e.pointerId);
    if (!prev) return;
    const cur: [number, number] = [e.clientX, e.clientY];
    this.pts.set(e.pointerId, cur);
    const moved = Math.hypot(cur[0] - this.start[0], cur[1] - this.start[1]) > MOVE_PX;
    switch (this.mode) {
      case 'pending':
        if (moved) { clearTimeout(this.timer); this.mode = 'pan'; this.cam.pan(cur[0] - prev[0], cur[1] - prev[1]); }
        break;
      case 'pan': this.cam.pan(cur[0] - prev[0], cur[1] - prev[1]); break;
      case 'long': if (moved) { this.mode = 'box'; this.h.info(-1, -1); this.h.box([...this.start, ...cur]); } break;
      case 'box': this.h.box([...this.start, ...cur]); break;
      case 'ghost': this.ghost = this.cam.toMap(cur[0], cur[1]); break;
      case 'pinch': {
        if (this.pts.size < 2) break;
        const [a, b] = [...this.pts.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
        const cam = this.cam;
        cam.setZoom(cam.zoom * (d / this.pinch.d), [mx, my]);
        cam.zoomTarget = cam.zoom;
        cam.pan(mx - this.pinch.mx, my - this.pinch.my);
        this.pinch = { d, mx, my };
        break;
      }
    }
  }

  up(e: PointerEvent) {
    const p = this.pts.get(e.pointerId);
    this.pts.delete(e.pointerId);
    clearTimeout(this.timer);
    if (this.mode === 'pinch') { if (!this.pts.size) this.mode = 'none'; return; }   // 두 손가락을 다 뗄 때까지 아무것도
    if (this.pts.size || !p) return;
    const mode = this.mode;
    this.mode = 'none';
    if (mode === 'pending') this.tap(p[0], p[1]);
    else if (mode === 'box') {
      this.h.box(null);
      const ctl = this.h.ctl();
      if (ctl) {
        const [ax, ay] = this.start;
        const [x0, y0] = this.cam.toMap(Math.min(ax, p[0]), Math.min(ay, p[1]));
        const [x1, y1] = this.cam.toMap(Math.max(ax, p[0]), Math.max(ay, p[1]));
        ctl.selectBox(x0, y0, x1, y1, this.add);
        this.h.changed();
      }
    }
  }

  cancel(e: PointerEvent) {
    this.pts.delete(e.pointerId);
    clearTimeout(this.timer);
    if (!this.pts.size) { this.mode = 'none'; this.h.box(null); }
  }

  private long() {
    if (this.mode !== 'pending') return;
    this.mode = 'long';
    navigator.vibrate?.(12);
    this.h.info(this.start[0], this.start[1]);
  }

  private nearGhost(sx: number, sy: number) {
    if (!this.ghost) return false;
    const c = this.cam, gx = (this.ghost[0] - c.x) * c.zoom, gy = (this.ghost[1] - c.y) * c.zoom;
    return Math.hypot(sx - gx, sy - gy) < 40;
  }

  /** 탭: PC의 왼쪽 클릭(고르기)과 오른쪽 클릭(명령)을 상황에 맞게 하나로. */
  private tap(sx: number, sy: number) {
    const ctl = this.h.ctl();
    if (!ctl) return;
    const cam = this.cam, z = cam.zoom, [mx, my] = cam.toMap(sx, sy);
    if (ctl.mode === 'attack') { ctl.command(mx, my, z, true, TOUCH_PX); ctl.mode = null; this.h.commanded(mx, my); this.h.changed(); return; }
    if (typeof ctl.mode === 'number') { this.ghost = [mx, my]; return; }      // 건물 그림을 그곳으로
    const me = ctl.me, commanding = ctl.sel.size > 0 || ctl.selShips.size > 0;
    if (commanding) {
      // 고른 게 있으면 명령이 먼저: 적 → 공격, 빈 자원지 → 짓기. 손가락 바로 밑의 (아직 안 고른) 내 병사·배를 탭하면 그것을 고른다
      const r = Math.max(2.0, TOUCH_PX / z);
      const foe = ctl.unitAt(mx, my, r);
      const foeB = ctl.buildingAt(mx, my);
      const site = ctl.siteAt(mx, my, Math.max(4.0, r * 1.25));
      const target = (foe && foe.own !== me) || (foeB && (foeB.own !== me || foeB.prog < 1)) || (site && !ctl.st_siteTaken().has(site.id));
      const mine = ctl.unitAt(mx, my, Math.max(0.8, 10 / z), me);
      const myBoat = ctl.boatAt(mx, my, Math.max(2.0, 12 / z), me);
      const pickBoat = myBoat && (myBoat.kind === 1 || myBoat.cargo > 0) && !ctl.selShips.has(myBoat.id);
      const myB = foeB && foeB.own === me && foeB.prog >= 1 ? foeB : null;
      if (!target && ((mine && !ctl.sel.has(mine.slot)) || pickBoat)) ctl.selectPoint(mx, my, z, this.add, 10);
      else if (!target && myB && !mine) ctl.selectPoint(mx, my, z, this.add, 10);   // 다 지은 내 건물: 고르기
      else { ctl.command(mx, my, z, false, TOUCH_PX); this.h.commanded(mx, my); }
    } else {
      // 아무것도 안 골랐으면: 손가락 둘레의 내 병사·배·건물을 고른다 (멀리서는 그 무리 전체). 없으면 그 자리 설명
      const unit = ctl.unitAt(mx, my, Math.max(1.5, TOUCH_PX / z), me);
      const boat = ctl.boatAt(mx, my, Math.max(3.0, (TOUCH_PX + 2) / z), me);
      const bld = ctl.buildingAt(mx, my, me);
      if (unit || (boat && (boat.kind === 1 || boat.cargo > 0)) || bld) ctl.selectPoint(mx, my, z, this.add, TOUCH_PX);
      else { ctl.selB = null; this.h.info(sx, sy); }
    }
    this.h.changed();
  }
}

