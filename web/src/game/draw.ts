// 지도 위 물체 그리기 (Canvas 2D, 화면 픽셀). 위치는 상태 사이를 보간한 값.
// 유닛·건물·배·동물은 스프라이트 스태킹 (stack.ts): 지형과 같은 해 방향·낮밤 색표로 칠하고, 유닛과 배는 가는 쪽으로 돈다.
// 밤에는 건물 둘레에 횃불 (torches.ts): 빛은 지형 빛 단계와 유닛·건물 칠하기에 함께 들어간다.
// 그림 한 점의 화면 크기는 모두 같다 (spriteK): 유닛과 건물의 점 크기가 섞이지 않게.

import type { Camera } from '../sim/camera.ts';
import type { TerrainScene } from '../terrain/scene.ts';
import { type Controller, UNIT_ZOOM } from './controller.ts';
import { F_OCEAN } from './terrainRules.ts';
import type { BuildRec } from './protocol.ts';
import { animalSpots, drawAnimals } from './wildlife.ts';
import type { SpriteBank } from './sprites.ts';
import { type Light, lightFrom } from './stack.ts';
import { Torches, drawFlame, nightAmount } from './torches.ts';
import { type GameState, lerp } from './state.ts';

const DIRS = 16;
const TAU = Math.PI * 2;
/** 그림 한 점의 화면 크기 (확대에 따라). 건물 모델 너비가 2r × 2.4 점이라 땅 넓이와 맞는다. */
export const spriteK = (z: number) => Math.max(1, Math.round(z / 2.4));
/** 각도 → 방향 번호 (16방향). */
export const dirOf = (a: number) => ((Math.round(a / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
/** a를 b 쪽으로 돌린다 (짧은 쪽으로, 비율 f). */
export function turn(a: number, b: number, f: number) {
  let d = (b - a) % TAU;
  if (d > Math.PI) d -= TAU;
  if (d < -Math.PI) d += TAU;
  return a + d * Math.min(f, 1);
}

const WAKE = 'rgb(236,244,248)';
const SEL = 'rgb(240,250,240)';
const MOVING_BOAT = new Set([1, 2, 3, 5, 6, 8]);     // move hunt pickup cross return ahead

export class Overlay {
  constructor(private g: CanvasRenderingContext2D, private bank: SpriteBank, private st: GameState,
              private ctl: Controller, private scene: TerrainScene) {
    this.torches = new Torches(ctl.rules);
  }
  private torches: Torches;
  private light: Light | null = null;
  private lightKey = 0;
  private hourKey = NaN;
  private lastNow = 0;
  private ang = new Map<number, number>();        // 병사가 보는 방향 (라디안)
  private boatAng = new Map<number, number>();

  /** 지금 빛 (시각이 1/12시간 움직일 때마다 새로). */
  private lightNow(): Light {
    const c = this.scene.cycle, hk = Math.round(c.hour * 12);
    if (!this.light || hk !== this.hourKey) {
      this.hourKey = hk;
      this.light = lightFrom(c, this.scene.bundle.meta.light.light_xy, ++this.lightKey);
    }
    return this.light;
  }

  /** 건물이 서는 방향 (4방향): 항구는 부두가 바다 쪽, 나머지는 자리마다 (뒤를 보는 일은 드물게). */
  private bdir(b: BuildRec): number {
    if (b.kind === this.st.info.rules.kinds.HARBOR) {
      const d = this.dock(b);
      if (d) return ((Math.round(Math.atan2(-(d[1] + 0.5 - b.x), d[0] + 0.5 - b.y) / (Math.PI / 2)) % 4) + 4) % 4;
    }
    return [0, 0, 1, 3][(b.slot * 7 + b.gen * 3) % 4];
  }

  private text(s: string, x: number, y: number, size: number, col: string, bold = false,
               align: CanvasTextAlign = 'left', base: CanvasTextBaseline = 'middle') {
    const g = this.g;
    g.font = `${bold ? 'bold ' : ''}${size}px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif`;
    g.textAlign = align; g.textBaseline = base;
    g.lineWidth = 2; g.strokeStyle = 'black'; g.strokeText(s, x, y);
    g.fillStyle = col; g.fillText(s, x, y);
  }

  private bar(cx: number, y: number, w: number, frac: number, col?: string) {
    frac = Math.min(Math.max(frac, 0), 1);
    col ??= `rgb(${Math.trunc(230 - 150 * frac)},${Math.trunc(70 + 160 * frac)},60)`;
    const x0 = Math.trunc(cx - w / 2), g = this.g;
    g.fillStyle = 'rgb(20,20,24)'; g.fillRect(x0 - 1, y - 1, w + 2, 4);
    g.fillStyle = col; g.fillRect(x0, y, Math.trunc(w * frac), 2);
  }

  /** 픽셀 말풍선: 어두운 1칸 테두리, 밝은 바탕, 아래로 계단 꼬리. 안에 대기열 병사 아이콘 (최대 5). */
  private bubble(b: BuildRec, cx: number, top: number, z: number) {
    const g = this.g, R = this.st.info.rules;
    const items: number[] = [];
    for (let k = 0; k < 5; k++) { const c = (b.qbits >> (3 * k)) & 7; if (c) items.push(c - 1); }   // 대기열 번호: 0 보병, 1 궁수, 2 전함
    if (!items.length) return;
    const p = Math.max(1, Math.round(z / 2.6));                 // 말풍선 픽셀 한 칸
    const unitOf = (q: number) => (q === 2 ? 0 : q);                                 // 대기열 번호 → 병종 그림
    const icons = items.map((q) => this.bank.unit(unitOf(q), b.own, 0, p));
    const iw = icons[0].width, ih = icons[0].height, gap = p;
    const w = icons.length * iw + (icons.length - 1) * gap + 4 * p, h = ih + 6 * p;
    const x0 = Math.round(cx - w / 2), y0 = Math.round(top - h - 4 * p);
    const ink = 'rgb(26,24,30)', paper = 'rgb(244,238,222)';
    g.fillStyle = ink;                                           // 테두리 (모서리는 한 칸 깎는다)
    g.fillRect(x0 + p, y0, w - 2 * p, h);
    g.fillRect(x0, y0 + p, w, h - 2 * p);
    g.fillStyle = paper;
    g.fillRect(x0 + p, y0 + p, w - 2 * p, h - 2 * p);
    const tx = Math.round(cx - p);                               // 꼬리: 두 계단
    g.fillStyle = ink; g.fillRect(tx - p, y0 + h - p, 4 * p, p); g.fillRect(tx, y0 + h, 2 * p, p); g.fillRect(tx + p, y0 + h + p, p, p);
    g.fillStyle = paper; g.fillRect(tx, y0 + h - p, 2 * p, p); g.fillRect(tx + p, y0 + h, p, p);
    icons.forEach((img, i) => g.drawImage(img, x0 + 2 * p + i * (iw + gap), y0 + 2 * p));
    const total = items[0] === 2 ? R.warship_time : R.unit_time[unitOf(items[0])];   // 맨 앞: 훈련 진행 막대
    const f = Math.min(Math.max(1 - b.qtime / total, 0), 1);
    g.fillStyle = 'rgb(200,192,170)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, iw, p);
    g.fillStyle = 'rgb(90,170,90)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, Math.max(p, Math.round(iw * f)), p);
  }

  private docks = new Map<number, [number, number] | null>();

  /** 전함을 짓는 자리: 항구 앞 물 칸(서버 Fleet.dock_of와 같은 규칙: 9칸 안의 가장 가까운 바다)에서
   *  바다 쪽으로 몇 칸 더 나간 곳 (항구 그림과 겹치지 않게). */
  private dock(b: BuildRec): [number, number] | null {
    const key = b.slot * 65536 + b.gen;
    if (this.docks.has(key)) return this.docks.get(key)!;
    const m = this.ctl.rules, y = Math.floor(b.y), x = Math.floor(b.x), r = 9;
    let best: [number, number] | null = null, bd = Infinity;
    for (let yy = Math.max(y - r, 0); yy <= Math.min(y + r, m.H - 1); yy++) {
      for (let xx = Math.max(x - r, 0); xx <= Math.min(x + r, m.W - 1); xx++) {
        if (!(m.at(yy, xx) & F_OCEAN)) continue;
        const d = (yy - y) ** 2 + (xx - x) ** 2;
        if (d < bd) { bd = d; best = [yy, xx]; }
      }
    }
    if (best) {                                                  // 항구 → 물 칸 방향으로 더 나가 바다인 곳
      const r0 = this.st.info.rules.build[b.kind].r, dy = best[0] - y, dx = best[1] - x, n = Math.hypot(dy, dx) || 1;
      for (let t = r0 + 6; t >= Math.hypot(dy, dx); t--) {
        const yy = Math.round(y + (dy / n) * t), xx = Math.round(x + (dx / n) * t);
        if (yy >= 0 && yy < m.H && xx >= 0 && xx < m.W && m.at(yy, xx) & F_OCEAN) { best = [yy, xx]; break; }
      }
    }
    this.docks.set(key, best);
    return best;
  }

  /** 항구 앞 바다에서 전함을 짓는 중: 흐린 윤곽 위로 아래부터 차오르는 배, 비계, 반짝이는 망치질. */
  private shipyard(b: BuildRec, sx: (x: number) => number, sy: (y: number) => number, z: number, now: number) {
    const d = this.dock(b);
    if (!d) return;
    const g = this.g, R = this.st.info.rules;
    const f = Math.min(Math.max(1 - b.qtime / R.warship_time, 0), 1);
    const k = spriteK(z);
    const { cv, ax, ay, p } = this.bank.stack.sprite('warship', b.own, this.lightNow(), { dir: 0, shadow: false });
    const img = { width: p.bw * k, height: p.bh * k };
    const x = Math.round(sx(d[1] + 0.5) - ax * k) + p.bx * k, y = Math.round(sy(d[0] + 0.5) - ay * k) + p.by * k;
    g.globalAlpha = 0.28;                                        // 다 지은 모습의 흐린 윤곽
    g.drawImage(cv, p.bx, p.by, p.bw, p.bh, x, y, img.width, img.height);
    g.globalAlpha = 1;
    const fs = Math.max(1, Math.round(p.bh * (0.15 + 0.85 * f)));   // 아래(배 밑)부터 차오른다
    g.drawImage(cv, p.bx, p.by + p.bh - fs, p.bw, fs, x, y + (p.bh - fs) * k, img.width, fs * k);
    const fill = fs * k;
    g.fillStyle = 'rgb(150,112,70)';                             // 비계: 양옆 기둥과 짓는 높이의 가로대
    const line = y + img.height - fill;
    g.fillRect(x - k, line, k, img.height - (line - y));
    g.fillRect(x + img.width, line, k, img.height - (line - y));
    g.fillRect(x - k, line, img.width + 2 * k, k);
    if (Math.floor(now / 180) % 3 !== 0) {                       // 망치질 반짝임
      const sxp = x + ((Math.floor(now / 540) * 7) % Math.max(1, img.width - k));
      g.fillStyle = 'rgb(255,236,170)';
      g.fillRect(sxp, line - k, k, k);
    }
    if (b.qlen > 1) this.text(`+${b.qlen - 1}`, x + img.width + 2 * k, y + 2, 11, 'rgb(255,240,200)');
  }

  draw(cam: Camera, now: number, mouse: [number, number] | null, box: [number, number, number, number] | null) {
    const g = this.g, st = this.st, z = cam.zoom, R = st.info.rules, me = st.info.me;
    const W = cam.viewW, H = cam.viewH;
    const sx = (x: number) => (x - cam.x) * z, sy = (y: number) => (y - cam.y) * z;
    const vis = (x: number, y: number, pad = 40) => x >= -pad && x <= W + pad && y >= -pad && y <= H + pad;
    const a = st.alpha(now), t = st.smoothTime(now);
    const dt = this.lastNow ? Math.min((now - this.lastNow) / 1000, 0.1) : 0;
    this.lastNow = now;
    g.imageSmoothingEnabled = false;
    this.ctl.prune();
    const L = this.lightNow(), K = spriteK(z), stack = this.bank.stack;
    // 밤의 횃불: 지형에 빛을 넘기고, 유닛·건물 칠하기에도 쓴다
    const night = nightAmount(this.scene.cycle.sunAlt());
    const torches = this.torches.update(st, night, now / 1000);
    this.scene.setTorches(this.torches.points());
    const tl = (x: number, y: number) => (torches.length ? this.torches.at(x, y) : 0);

    // 자원지 (확대할수록 커진다. 멀리서도 2배 아래로는 줄지 않는다)
    const taken = st.siteTaken(), ks = Math.max(2, Math.round(z * 0.6));
    for (const s of st.info.sites) {
      if (taken.has(s.id)) continue;
      const x = sx(s.x), y = sy(s.y);
      if (!vis(x, y)) continue;
      const img = this.bank.site(s.kind, ks);
      g.drawImage(img, Math.round(x - img.width / 2), Math.round(y - img.height / 2));
    }
    // 건물
    const selB = this.ctl.selB;
    const bubbles: [BuildRec, number, number][] = [];       // 말풍선 (병사들 위에 그리려고 나중에)
    const yards: BuildRec[] = [];
    const items: { y: number; f: () => void }[] = [];      // 건물과 횃불: 아래(앞)에 있는 것을 나중에
    for (const b of st.builds.values()) {
      const x = sx(b.x), y = sy(b.y);
      if (!vis(x, y, 120)) continue;
      items.push({ y: b.y, f: () => {
        const done = b.prog >= 1, name = `b${b.kind}`, dir = this.bdir(b);
        let box;
        if (!done) {                                           // 짓는 중: 흐린 다 지은 모습 위로 아래부터 쌓여 올라간다
          g.globalAlpha = 0.3;
          box = stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, shadow: false });
          g.globalAlpha = 1;
          stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, cut: Math.max(b.prog, 0.06), shadow: false });
        } else box = stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, torch: Math.max(tl(b.x, b.y), night * 0.45) });   // 제 횃불이 비춘다
        if (selB && selB[0] === b.slot) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(box.x - 2.5, box.y - 2.5, box.w + 4, box.h + 4); }
        const bw = Math.max(box.w, 14);
        if (!done) this.bar(box.x + box.w / 2, box.y + box.h + 3, bw, b.prog, 'rgb(120,200,255)');
        else if (b.hp < 0.999) this.bar(box.x + box.w / 2, box.y - 4, bw, b.hp);
        if (done && b.kind === R.kinds.HALL && b.qlen && b.own === me) {
          if (z >= UNIT_ZOOM) bubbles.push([b, box.x + box.w / 2, box.y]);   // 가까이: 말풍선에 대기열 병사 아이콘
          else this.text(`${b.qlen}`, box.x + box.w + 2, box.y + 4, 12, 'rgb(255,240,200)');
        }
        if (done && b.kind === R.kinds.HARBOR && b.qlen && b.qkind === 2) yards.push(b);
      } });
    }
    for (const p of torches) {                                // 횃불: 횃대와 일렁이는 불꽃
      const x = sx(p.x), y = sy(p.y);
      if (!vis(x, y)) continue;
      items.push({ y: p.y, f: () => {
        const al = Math.min(1, night * 1.5);
        g.globalAlpha = al;
        stack.draw(g, 'torch', 0, L, x, y, K, { dirs: 1, torch: 1 });
        g.globalAlpha = 1;
        drawFlame(g, Math.round(x), Math.round(y - 5 * K), K, now / 1000, p.id, al);
      } });
    }
    items.sort((p, q) => p.y - q.y);
    for (const it of items) it.f();
    for (const b of yards) this.shipyard(b, sx, sy, z, now);    // 항구 앞바다의 전함 건조 (건물에 가리지 않게 나중에)
    // 배
    for (const b of st.boats.values()) {
      if (b.bits & 1) continue;                                     // 아직 항구에서 출발 전
      const bx = lerp(b.px, b.x, a), by = lerp(b.py, b.y, a), x = sx(bx), y = sy(by);
      if (!vis(x, y, 60)) continue;
      const ferry = b.kind === 0;
      const mx = b.x - b.px, my = b.y - b.py;                        // 가는 쪽으로 뱃머리를 돌린다
      let ang = this.boatAng.get(b.id) ?? (b.dir < 0 ? Math.PI : 0);
      if (Math.hypot(mx, my) > 0.01) ang = turn(ang, Math.atan2(my, mx), dt * 4);
      this.boatAng.set(b.id, ang);
      const bob = ferry && Math.trunc(t * 2 + bx) % 2 ? 1 : 0;      // 살짝 출렁인다
      if (MOVING_BOAT.has(b.state)) {                                // 지나간 물보라 (고물 쪽)
        g.fillStyle = WAKE;
        const c = Math.cos(ang), s = Math.sin(ang), back = (ferry ? 6 : 11) * K;
        for (const k of [1, 2]) g.fillRect(Math.round(x - c * (back + k * 3 * K)), Math.round(y - s * (back + k * 3 * K)), K, K);
      }
      const rc = stack.draw(g, ferry ? 'ferry' : 'warship', b.own, L, x, y + bob * K, K, { dir: dirOf(ang), torch: tl(bx, by) });
      if (this.ctl.selShips.has(b.id)) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(rc.x - 2.5, rc.y - 2.5, rc.w + 4, rc.h + 4); }
      if (b.hp < 0.999) this.bar(rc.x + rc.w / 2, rc.y - 4, Math.max(rc.w, 12), b.hp);
      if (ferry && b.cargo) this.text(`${b.cargo}`, rc.x + rc.w + 2, rc.y + rc.h / 2, 12, 'white', true);
    }
    // 야생 동물 (멀리서는 작게)
    const tameBars = z >= 1.2 ? drawAnimals(g, stack, L, animalSpots(st, a, sx, sy), K, t, W, H, dt, tl) : [];
    // 병사: 가까이서는 하나하나, 멀리서는 무리 배지
    const units = [...st.units.values()].filter((u) => !(u.bits & 2));
    if (z >= UNIT_ZOOM) {
      for (const s of st.shots) {                                 // 치는 병사는 맞는 쪽을 본다
        if (t - s.t0 > 0.12) continue;
        const u = this.ctl.unitAt(s.x0, s.y0, 0.7);
        if (u) this.ang.set(u.slot, Math.atan2(s.y1 - s.y0, s.x1 - s.x0));
      }
      const list = units.map((u) => ({ u, x: sx(lerp(u.px, u.x, a)), y: sy(lerp(u.py, u.y, a)) }))
        .filter((p) => p.x > -40 && p.x < W + 40 && p.y > -40 && p.y < H + 40).sort((p, q) => p.y - q.y);
      for (const { u, x, y } of list) {
        const frame = u.bits & 1 ? Math.trunc(t * 4.5 * 1.2 + u.slot * 0.37) % 2 : 0;   // 걸을 때 다리
        const mx = u.x - u.px, my = u.y - u.py;                    // 가는 쪽으로 몸을 돌린다
        let ang = this.ang.get(u.slot) ?? (u.slot % 2 ? Math.PI * 0.5 : Math.PI * 0.25);
        if (Math.hypot(mx, my) > 0.01) ang = turn(ang, Math.atan2(my, mx), dt * 10);
        this.ang.set(u.slot, ang);
        const rc = stack.draw(g, `u${u.kind}`, u.own, L, x, y, K, { frame, dir: dirOf(ang), torch: tl(lerp(u.px, u.x, a), lerp(u.py, u.y, a)) });
        if (this.ctl.sel.has(u.slot)) { g.strokeStyle = 'rgb(235,250,235)'; g.lineWidth = 1; g.beginPath(); g.moveTo(rc.x, rc.y + rc.h + 1.5); g.lineTo(rc.x + rc.w, rc.y + rc.h + 1.5); g.stroke(); }
        if (u.hp < 0.99) this.bar(rc.x + rc.w / 2, rc.y - 3, Math.max(rc.w - 2, 8), u.hp);
      }
    } else {
      const cell = 34, groups = new Map<string, { own: number; n: number; x: number; y: number; sel: boolean }>();
      for (const u of units) {
        const x = sx(lerp(u.px, u.x, a)), y = sy(lerp(u.py, u.y, a));
        const key = `${u.own},${Math.floor(y / cell)},${Math.floor(x / cell)}`;
        const e = groups.get(key) ?? { own: u.own, n: 0, x: 0, y: 0, sel: false };
        e.n++; e.x += x; e.y += y; e.sel ||= this.ctl.sel.has(u.slot);
        groups.set(key, e);
      }
      const list = [...groups.values()].map((e) => ({ ...e, x: e.x / e.n, y: e.y / e.n })).sort((p, q) => p.y - q.y);
      for (const e of list) {
        if (!vis(e.x, e.y)) continue;
        g.font = `bold 12px 'Malgun Gothic', sans-serif`;
        const w = Math.max(g.measureText(`${e.n}`).width + 8, 16), h = 15;
        const x0 = e.x - w / 2, y0 = e.y - h / 2;
        g.fillStyle = 'rgb(20,18,24)'; roundRect(g, x0 - 1, y0 - 1, w + 2, h + 2, 4); g.fill();
        const c = st.info.nations[e.own].color;
        g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; roundRect(g, x0, y0, w, h, 4); g.fill();
        if (e.sel) { g.strokeStyle = 'rgb(240,255,240)'; g.lineWidth = 1; roundRect(g, x0 - 2.5, y0 - 2.5, w + 5, h + 5, 5); g.stroke(); }
        this.text(`${e.n}`, e.x, e.y + 1, 12, 'white', true, 'center');
      }
    }
    // 공격: 화살(날아가는 짧은 선), 포탄(검은 점 → 물보라), 칼부림(반짝)
    for (const s of st.shots) {
      const age = (t - s.t0) / 0.3;
      const ax = sx(s.x0), ay = sy(s.y0), bx = sx(s.x1), by = sy(s.y1);
      if (s.kind >= 2) {
        const f = Math.min(age * 1.3, 1.0);
        if (f < 1) {
          g.fillStyle = 'rgb(30,28,34)'; g.beginPath();
          g.arc(ax + (bx - ax) * f, ay + (by - ay) * f - 6 * z * f * (1 - f), Math.max(1, Math.trunc(z * 0.45)), 0, 7); g.fill();
        } else { g.strokeStyle = WAKE; g.lineWidth = 1; g.beginPath(); g.arc(bx, by, Math.max(2, Math.trunc(z)), 0, 7); g.stroke(); }
      } else if (s.kind >= 1) {
        const f = Math.min(Math.max(age, 0) * 1.6, 1.0), h = Math.max(f - 0.15, 0.0);
        g.strokeStyle = 'rgb(236,226,196)'; g.lineWidth = 1; g.beginPath();
        g.moveTo(ax + (bx - ax) * h, ay + (by - ay) * h); g.lineTo(ax + (bx - ax) * f, ay + (by - ay) * f); g.stroke();
      } else if (age < 0.5) {
        g.fillStyle = 'rgb(255,250,230)'; g.beginPath(); g.arc(bx, by - 2 * z, Math.max(1, Math.trunc(z * 0.5)), 0, 7); g.fill();
      }
    }
    for (const p of tameBars) this.bar(p.x, p.y, p.w, p.prog, 'rgb(240,200,90)');   // 길들이기 진행 (병사에 가리지 않게 나중에)
    // 거점 위 말풍선: 대기열에 있는 병사 아이콘 (맨 앞은 훈련 진행 막대)
    for (const [b, cx, top] of bubbles) this.bubble(b, cx, top, z);
    // 명령 표시
    this.ctl.pings = this.ctl.pings.filter((p) => now - p.t0 < 600);
    for (const p of this.ctl.pings) {
      const f = (now - p.t0) / 600;
      g.strokeStyle = p.col; g.lineWidth = 1; g.beginPath(); g.arc(Math.trunc(sx(p.x)), Math.trunc(sy(p.y)), Math.trunc(4 + 10 * f), 0, 7); g.stroke();
    }
    // 드래그 상자
    if (box) { g.strokeStyle = 'rgb(230,240,230)'; g.lineWidth = 1; g.strokeRect(Math.min(box[0], box[2]) + 0.5, Math.min(box[1], box[3]) + 0.5, Math.abs(box[2] - box[0]), Math.abs(box[3] - box[1])); }
    // 건물 자리 미리보기
    const mode = this.ctl.mode;
    if (mouse && typeof mode === 'number') {                     // 놓을 건물이 커서에 (자원지 건물은 빈 자원지에 붙는다)
      const kind = mode;
      const [mx, my] = cam.toMap(mouse[0], mouse[1]);
      const t = this.ctl.placeTarget(kind, mx, my, z);
      const ok = t.ok;
      const px = t.ok ? sx(t.x) : mouse[0], py = t.ok ? sy(t.y) : mouse[1];
      g.globalAlpha = 0.55;
      const rc = stack.draw(g, `b${kind}`, me, L, px, py, K, { dirs: 4, shadow: false });
      g.globalAlpha = 1;
      g.strokeStyle = ok ? 'rgb(120,230,120)' : 'rgb(230,90,80)'; g.lineWidth = 1; g.strokeRect(rc.x - 2.5, rc.y - 2.5, rc.w + 4, rc.h + 4);
    }
  }
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}
