// 생명: 바닷새와 물고기 떼 (보이드), 물보라와 파문, 마우스 상호작용 — 최상위 viewer/life.py를 옮겼다.
// - 바닷새: 무리마다 해안의 목적지를 향해 날며 해안선 근처에 머문다. 흰 날개 + 어두운 날개 끝, 날갯짓, 지면 그림자.
//   해 질 녘엔 하나둘 사라진다.
// - 물고기: 얕은 물에서 떼 지어 다닌다 (물색보다 어두운 1칸). 가끔 뛰어올라 물보라와 파문. 밤에는 안 보인다.
// - 마우스 가까이에서 흩어지고, 물을 클릭하면 파문이 생기며 물고기가 달아난다.
// - 물고기 자원지(게임): 그 앞바다(반지름 9칸)를 큰 물고기 떼가 자유롭게 헤엄친다 (BaitBalls).
// 그리기는 지도 칸 단위 연산 목록(곱하기/덮어쓰기/밝히기)으로 만들고, render/lifeDraw.ts가 GPU로 그린다.

import type { Bundle } from '../bundle/tsb.ts';
import type { DayNightCycle } from '../sim/clock.ts';
import { Rng, edt, gaussian, gradient } from './grid.ts';

export interface LifeOps {
  mul: number[];        // x, y, k        (색 × k)
  set: number[];        // x, y, r, g, b  (덮어쓰기)
  brighten: number[];   // x, y           (색 × 1.25 + 18)
}

type V2 = [number, number];
const BODY = [206, 210, 220], WING = [244, 246, 248], TIP = [62, 66, 78];

class Flock {
  pos: V2[];
  vel: V2[];
  constructor(pos: V2[], readonly group: number[], readonly speed: [number, number], rng: Rng) {
    this.pos = pos;
    this.vel = pos.map(() => { const a = rng.uniform(0, 2 * Math.PI); return [Math.cos(a) * speed[0], Math.sin(a) * speed[0]] as V2; });
  }

  boidForces(sepR: number, viewR: number, wSep: number, wAli: number, wCoh: number): V2[] {
    const n = this.pos.length, out: V2[] = [];
    for (let i = 0; i < n; i++) {
      let sx = 0, sy = 0, ax = 0, ay = 0, cx = 0, cy = 0, cnt = 0;
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const dx = this.pos[i][0] - this.pos[j][0], dy = this.pos[i][1] - this.pos[j][1];
        const dist = Math.hypot(dx, dy) + 1e-9;
        if (dist <= 1e-6) continue;
        if (dist < sepR) { sx += dx / (dist * dist); sy += dy / (dist * dist); }
        if (this.group[i] === this.group[j] && dist < viewR) {
          cnt++; ax += this.vel[j][0]; ay += this.vel[j][1]; cx += this.pos[j][0]; cy += this.pos[j][1];
        }
      }
      let fx = wSep * sx, fy = wSep * sy;
      if (cnt > 0) {
        fx += wAli * (ax / cnt - this.vel[i][0]) + wCoh * (cx / cnt - this.pos[i][0]);
        fy += wAli * (ay / cnt - this.vel[i][1]) + wCoh * (cy / cnt - this.pos[i][1]);
      }
      out.push([fx, fy]);
    }
    return out;
  }
}

function flee(p: V2, point: V2 | null, radius: number, strength: number): V2 {
  if (!point) return [0, 0];
  const dx = p[0] - point[0], dy = p[1] - point[1];
  const dist = Math.hypot(dx, dy) + 1e-9;
  const k = Math.min(Math.max(1 - dist / radius, 0), 1) ** 2;
  return [(dx / dist) * k * strength, (dy / dist) * k * strength];
}

function limit(v: V2, lo: number, hi: number): V2 {
  const sp = Math.hypot(v[0], v[1]) + 1e-9;
  const s = Math.min(Math.max(sp, lo), hi) / sp;
  return [v[0] * s, v[1] * s];
}

/** 칸마다 2D 벡터장 (끌어당기는 방향). */
function pullField(pot: Float64Array, W: number, H: number, scale: number): Float32Array {
  const [gy, gx] = gradient(pot, W, H);
  const out = new Float32Array(W * H * 2);
  for (let i = 0; i < W * H; i++) {
    const n = Math.hypot(gx[i], gy[i]) + 1e-6, k = Math.min(Math.max(pot[i] / scale, 0), 1);
    out[i * 2] = (-gx[i] / n) * k;
    out[i * 2 + 1] = (-gy[i] / n) * k;
  }
  return out;
}

class SeaBirds {
  flock: Flock;
  targets: V2[];
  timers: number[];
  phase: number[];
  fear: number[];
  private pull: Float32Array;
  private coastPts: V2[];
  constructor(water: Uint8Array, private W: number, private H: number, private rng: Rng) {
    const land = water.map((w) => (w ? 0 : 1));
    const dW = edt(water, W, H), dL = edt(land, W, H);
    const pot = new Float64Array(W * H), coast: V2[] = [];
    for (let i = 0; i < W * H; i++) {
      const signed = dW[i] - dL[i];
      pot[i] = Math.abs(signed - 4.0);
      if (Math.abs(signed - 4.0) < 2.0) coast.push([i % W, Math.floor(i / W)]);
    }
    this.pull = pullField(gaussian(pot, W, H, 3.0), W, H, 6.0);
    this.coastPts = coast.length ? coast : [[W / 2, H / 2]];
    const nF = rng.int(3, 5), pos: V2[] = [], group: number[] = [];
    for (let f = 0; f < nF; f++) {
      const c = this.coastPts[rng.int(0, this.coastPts.length)], k = rng.int(5, 13);
      for (let i = 0; i < k; i++) { pos.push([c[0] + rng.normal(0, 3), c[1] + rng.normal(0, 3)]); group.push(f); }
    }
    this.flock = new Flock(pos, group, [14.0, 26.0], rng);
    this.targets = Array.from({ length: nF }, () => [...this.coastPts[rng.int(0, this.coastPts.length)]] as V2);
    this.timers = Array.from({ length: nF }, () => rng.uniform(4, 12));
    this.phase = pos.map(() => rng.uniform(0, 1));
    this.fear = pos.map(() => 0);
  }

  update(dt: number, mouse: V2 | null, burst: boolean) {
    const fl = this.flock, rng = this.rng;
    this.timers = this.timers.map((t, f) => {
      t -= dt;
      if (t <= 0) { this.targets[f] = [...this.coastPts[rng.int(0, this.coastPts.length)]] as V2; return rng.uniform(6, 16); }
      return t;
    });
    const boid = fl.boidForces(6.0, 70.0, 40.0, 1.0, 1.0);
    for (let i = 0; i < fl.pos.length; i++) {
      const calm = 1 - this.fear[i], p = fl.pos[i];
      let ax = boid[i][0] * (0.3 + 0.7 * calm), ay = boid[i][1] * (0.3 + 0.7 * calm);
      const t = this.targets[fl.group[i]], tx = t[0] - p[0], ty = t[1] - p[1], tn = Math.hypot(tx, ty) + 1e-6;
      ax += (tx / tn) * 9.0 * calm; ay += (ty / tn) * 9.0 * calm;
      const sx = Math.min(Math.max(p[0] | 0, 0), this.W - 1), sy = Math.min(Math.max(p[1] | 0, 0), this.H - 1);
      ax += this.pull[(sy * this.W + sx) * 2] * 14.0 * calm; ay += this.pull[(sy * this.W + sx) * 2 + 1] * 14.0 * calm;
      ax += rng.normal(0, 6.0); ay += rng.normal(0, 6.0);
      const m = 8.0;
      ax += (p[0] < m ? 30 : 0) - (p[0] > this.W - m ? 30 : 0);
      ay += (p[1] < m ? 30 : 0) - (p[1] > this.H - m ? 30 : 0);
      const push = flee(p, mouse, burst ? 50.0 : 30.0, burst ? 900.0 : 450.0);
      this.fear[i] = Math.hypot(push[0], push[1]) > 20.0 ? 1.0 : Math.max(this.fear[i] - dt * 0.7, 0);
      ax += push[0]; ay += push[1];
      fl.vel[i] = limit([fl.vel[i][0] + ax * dt, fl.vel[i][1] + ay * dt], fl.speed[0], fl.speed[1] * (1 + 0.8 * this.fear[i]));
      fl.pos[i] = [p[0] + fl.vel[i][0] * dt, p[1] + fl.vel[i][1] * dt];
      this.phase[i] = (this.phase[i] + dt * (3.0 + 4.0 * this.fear[i])) % 1.0;
    }
  }

  draw(ops: LifeOps, tint: number[], alive: number) {
    const n = this.flock.pos.length, show = Math.round(n * alive);
    const shadow: number[] = [], parts: number[] = [];
    for (let i = 0; i < show; i++) {
      const p = this.flock.pos[i], v = this.flock.vel[i];
      const x = Math.trunc(p[0]), y = Math.trunc(p[1]);
      const vn = Math.hypot(v[0], v[1]) + 1e-9;
      const dx = Math.round(v[0] / vn), dy = Math.round(v[1] / vn);
      const px = -dy, py = dx, back = this.phase[i] < 0.5 ? 0 : 1;
      const list: [number, number, number[]][] = [[x, y, BODY]];
      for (const s of [1, -1]) {
        list.push([x + s * px - back * dx, y + s * py - back * dy, WING]);
        list.push([x + 2 * s * px - 2 * back * dx, y + 2 * s * py - 2 * back * dy, TIP]);
      }
      for (const [bx, by] of list) shadow.push(bx + 3, by + 3, 0.62);         // 그림자: 햇빛 반대쪽 지면에
      for (const [bx, by, c] of list) parts.push(bx, by, ...c.map((v2, k) => Math.min(Math.max(v2 * tint[k], 0), 255)));
    }
    ops.mul.push(...shadow);
    ops.set.push(...parts);
  }
}

class FishSchools {
  flock: Flock | null = null;
  targets: V2[] = [];
  timers: number[] = [];
  jumpTimers: number[] = [];
  fear: number[] = [];
  splashes: [number, number, number, number][] = [];
  private pull: Float32Array;
  private habitat: V2[];
  private scarePoint: V2 | null = null;
  private scareT = 0;
  constructor(private water: Uint8Array, private W: number, private H: number, private rng: Rng) {
    const dLand = edt(water, W, H);
    const pot = new Float64Array(W * H), hab: V2[] = [];
    for (let i = 0; i < W * H; i++) {
      pot[i] = Math.abs(dLand[i] - 7.0);
      if (water[i] && dLand[i] >= 3 && dLand[i] <= 12) hab.push([i % W, Math.floor(i / W)]);
    }
    this.pull = pullField(gaussian(pot, W, H, 2.0), W, H, 4.0);
    if (!hab.length) for (let i = 0; i < W * H; i++) if (water[i]) hab.push([i % W, Math.floor(i / W)]);
    this.habitat = hab;
    if (!hab.length) return;
    const nS = rng.int(6, 11), pos: V2[] = [], group: number[] = [];
    for (let s = 0; s < nS; s++) {
      const c = hab[rng.int(0, hab.length)], k = rng.int(5, 11);
      for (let i = 0; i < k; i++) { pos.push([c[0] + rng.normal(0, 1.5), c[1] + rng.normal(0, 1.5)]); group.push(s); }
    }
    this.flock = new Flock(pos, group, [3.0, 9.0], rng);
    this.targets = Array.from({ length: nS }, () => [...hab[rng.int(0, hab.length)]] as V2);
    this.timers = Array.from({ length: nS }, () => rng.uniform(3, 9));
    this.jumpTimers = Array.from({ length: nS }, () => rng.uniform(4, 14));
    this.fear = pos.map(() => 0);
  }

  private isWater(x: number, y: number) {
    return x >= 0 && x < this.W && y >= 0 && y < this.H && this.water[(y | 0) * this.W + (x | 0)] > 0;
  }

  splash(x: number, y: number, big = false) {
    if (this.isWater(Math.trunc(x), Math.trunc(y))) this.splashes.push([x, y, 0, big ? 1.6 : 1.0]);
  }

  update(dt: number, mouse: V2 | null, click: V2 | null) {
    for (const s of this.splashes) s[2] += dt;
    this.splashes = this.splashes.filter((s) => s[2] < 0.9 * s[3]);
    if (click) this.splash(click[0], click[1], true);
    const fl = this.flock;
    if (!fl) return;
    const rng = this.rng;
    this.timers = this.timers.map((t, s) => {
      t -= dt;
      if (t > 0) return t;
      let hx = 0, hy = 0, c = 0;
      fl.pos.forEach((p, i) => { if (fl.group[i] === s) { hx += p[0]; hy += p[1]; c++; } });
      hx /= c; hy /= c;
      const near = this.habitat.filter((h) => Math.hypot(h[0] - hx, h[1] - hy) < 40);
      const pool = near.length ? near : this.habitat;
      this.targets[s] = [...pool[rng.int(0, pool.length)]] as V2;
      return rng.uniform(4, 10);
    });
    if (click) {
      this.scarePoint = click; this.scareT = 1.0;
      fl.pos.forEach((p, i) => { if (Math.hypot(p[0] - click[0], p[1] - click[1]) < 32.0) this.fear[i] = 1.0; });
    }
    this.scareT = Math.max(this.scareT - dt, 0);
    const boid = fl.boidForces(1.5, 8.0, 6.0, 1.2, 0.8);
    for (let i = 0; i < fl.pos.length; i++) {
      const calm = 1 - this.fear[i], p = fl.pos[i];
      let ax = boid[i][0] * (0.3 + 0.7 * calm), ay = boid[i][1] * (0.3 + 0.7 * calm);
      const t = this.targets[fl.group[i]], tx = t[0] - p[0], ty = t[1] - p[1], tn = Math.hypot(tx, ty) + 1e-6;
      ax += (tx / tn) * 2.5 * calm; ay += (ty / tn) * 2.5 * calm;
      const sx = Math.min(Math.max(p[0] | 0, 0), this.W - 1), sy = Math.min(Math.max(p[1] | 0, 0), this.H - 1);
      ax += this.pull[(sy * this.W + sx) * 2] * 4.0; ay += this.pull[(sy * this.W + sx) * 2 + 1] * 4.0;
      ax += rng.normal(0, 4.0); ay += rng.normal(0, 4.0);
      const f1 = flee(p, mouse, 18.0, 90.0);
      ax += f1[0]; ay += f1[1];
      if (this.scareT > 0) { const f2 = flee(p, this.scarePoint, 36.0, 600.0 * this.scareT); ax += f2[0]; ay += f2[1]; }
      this.fear[i] = Math.max(this.fear[i] - dt * 0.9, 0);
      const v = limit([fl.vel[i][0] + ax * dt, fl.vel[i][1] + ay * dt], fl.speed[0], fl.speed[1] * (2.5 + 3.0 * this.fear[i]));
      const nx = p[0] + v[0] * dt, ny = p[1] + v[1] * dt;
      const sx2 = Math.min(Math.max(nx | 0, 0), this.W - 1), sy2 = Math.min(Math.max(ny | 0, 0), this.H - 1);
      if (this.water[sy2 * this.W + sx2]) { fl.pos[i] = [nx, ny]; fl.vel[i] = v; }       // 땅으로는 못 간다
      else fl.vel[i] = [-v[0] * 0.6 + rng.normal(0, 2), -v[1] * 0.6 + rng.normal(0, 2)];
    }
    this.jumpTimers = this.jumpTimers.map((t, s) => {
      t -= dt;
      if (t > 0) return t;
      const idx = fl.group.map((g, i) => (g === s ? i : -1)).filter((i) => i >= 0);
      const p = fl.pos[idx[rng.int(0, idx.length)]];
      this.splash(p[0], p[1]);
      return rng.uniform(6, 18);
    });
  }

  draw(ops: LifeOps, foamColor: number[], tint: number[], visible: number) {
    if (this.flock && visible > 0) {
      const k = 1.0 - 0.3 * visible;
      for (const p of this.flock.pos) {
        const x = Math.min(Math.max(Math.trunc(p[0]), 0), this.W - 1), y = Math.min(Math.max(Math.trunc(p[1]), 0), this.H - 1);
        if (this.water[y * this.W + x]) ops.mul.push(x, y, k);
      }
    }
    const foam = foamColor.map((c, k) => Math.trunc(Math.min(Math.max(c * tint[k], 0), 255)));
    for (const [sx, sy, t, size] of this.splashes) {
      const u = t / (0.9 * size), cx = Math.trunc(sx), cy = Math.trunc(sy);
      if (u < 0.18) {
        const pts = size > 1 ? [[0, 0], [1, 0], [-1, 0], [0, -1], [0, -2]] : [[0, 0], [0, -1]];
        for (const [dx, dy] of pts) ops.set.push(cx + dx, cy + dy, ...foam);
      } else {
        const r = 1.0 + u * 4.0 * size, n = Math.max(8, Math.trunc(r * 6));
        for (let i = 0; i < n; i++) {
          if (u > 0.6 && i % 2 !== 0) continue;                  // 사라질수록 듬성듬성
          const a = (2 * Math.PI * i) / n;
          const x = Math.round(cx + Math.cos(a) * r), y = Math.round(cy + Math.sin(a) * r * 0.75);
          if (this.isWater(x, y)) ops.brighten.push(x, y);
        }
      }
    }
  }
}

/** 물고기 자원지마다 그 앞바다(반지름 BALL_R칸)를 자유롭게 헤엄치는 무리: 보이드(떨어지기·나란히·모이기)
 *  + 작은 무리 셋이 저마다 영역 안의 목표를 몇 초마다 바꾸며 따라가기 + 영역 밖이면 되돌아오기 + 흔들림.
 *  바다 물고기보다 크게: 가는 쪽으로 머리 한 칸 + 몸 + 옅은 꼬리. */
const BALL_R = 9;
const BALL_GROUPS = 3;        // 작은 무리 수 (저마다 다른 곳으로)
const SCARE_R = 4.5;          // 커서가 이만큼 가까이 오면 놀란다 (칸)
const SCARE_PUSH = 0.6;       // 숨기 전에 튀어나가는 동안 (초)
class BaitBalls {
  private balls: { c: V2; flock: Flock; targets: V2[]; timers: number[]; scare: number[]; push: number[]; depth: number[] }[] = [];

  constructor(private water: Uint8Array, private W: number, private H: number, private rng: Rng) {}

  set(centers: V2[]) {
    const rng = this.rng;
    this.balls = centers.map((c) => {
      const n = rng.int(18, 24), pos: V2[] = [], group: number[] = [];
      for (let i = 0; i < n; i++) {                                              // 작은 무리 셋으로 흩어져 시작
        const a = rng.uniform(0, 2 * Math.PI), r = rng.uniform(0, BALL_R * 0.7);
        pos.push([c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * r]);
        group.push(i % BALL_GROUPS);
      }
      return { c, flock: new Flock(pos, group, [1.0, 3.6], rng),
               targets: Array.from({ length: BALL_GROUPS }, () => this.pick(c)), timers: Array.from({ length: BALL_GROUPS }, () => rng.uniform(1, 5)),
               scare: pos.map(() => 0), push: pos.map(() => 0), depth: pos.map(() => 0) };
    });
  }

  /** 영역 안의 바다 칸 하나 (못 찾으면 가운데). */
  private pick(c: V2): V2 {
    for (let k = 0; k < 20; k++) {
      const a = this.rng.uniform(0, 2 * Math.PI), r = Math.sqrt(this.rng.uniform(0, 1)) * BALL_R * 0.8;
      const x = c[0] + Math.cos(a) * r, y = c[1] + Math.sin(a) * r;
      if (this.isWater(x, y)) return [x, y];
    }
    return [c[0], c[1]];
  }

  private isWater(x: number, y: number) {
    return x >= 0 && x < this.W && y >= 0 && y < this.H && this.water[(y | 0) * this.W + (x | 0)] > 0;
  }

  /** mouse: 커서 (지도 칸). 가까운 물고기는 조금 밀려나다가 아래로 숨고 (흐려짐), 커서가 떠나고 잠시 뒤 다시 떠오른다. */
  update(dt: number, mouse: V2 | null) {
    const rng = this.rng;
    for (const b of this.balls) {
      const fl = b.flock;
      for (let g = 0; g < BALL_GROUPS; g++) {
        b.timers[g] -= dt;
        if (b.timers[g] <= 0) { b.targets[g] = this.pick(b.c); b.timers[g] = rng.uniform(3, 7); }
      }
      const boid = fl.boidForces(2.6, 4.0, 7.0, 0.7, 0.12);                     // 떨어지기 강하게, 모이기 약하게 (덩어리가 되지 않게)
      for (let i = 0; i < fl.pos.length; i++) {
        const p = fl.pos[i];
        const t = b.targets[fl.group[i]], tx = t[0] - p[0], ty = t[1] - p[1], tn = Math.hypot(tx, ty) + 1e-6;
        let ax = boid[i][0] + (tx / tn) * 1.4 + rng.normal(0, 3.5);
        let ay = boid[i][1] + (ty / tn) * 1.4 + rng.normal(0, 3.5);
        const rx = p[0] - b.c[0], ry = p[1] - b.c[1], d = Math.hypot(rx, ry) + 1e-6;
        if (d > BALL_R) { ax -= (rx / d) * (d - BALL_R) * 4.0; ay -= (ry / d) * (d - BALL_R) * 4.0; }   // 영역 밖: 되돌아온다
        if (mouse && Math.hypot(p[0] - mouse[0], p[1] - mouse[1]) < SCARE_R) {
          if (b.scare[i] <= 0) { b.scare[i] = rng.uniform(2.5, 4.0); b.push[i] = SCARE_PUSH; }   // 놀랐다: 밀려나기 → 숨기 → 잠시 뒤 떠오르기
          else b.scare[i] = Math.max(b.scare[i], 2.0);                          // 커서가 머물면 더 숨어 있는다
          const f = flee(p, mouse, SCARE_R, 160.0);
          ax += f[0]; ay += f[1];
        }
        const pushing = b.push[i] > 0;                                          // 밀려나는 동안은 그대로 보이고, 그 뒤 아래로
        if (pushing) b.push[i] = Math.max(b.push[i] - dt, 0);
        else b.scare[i] = Math.max(b.scare[i] - dt, 0);
        b.depth[i] = Math.min(Math.max(b.depth[i] + (pushing ? 0 : b.scare[i] > 0 ? dt * 2.2 : -dt * 0.7), 0), 1);
        const v = limit([fl.vel[i][0] + ax * dt, fl.vel[i][1] + ay * dt], fl.speed[0], fl.speed[1] * (pushing ? 3.5 : 1));
        const nx = p[0] + v[0] * dt, ny = p[1] + v[1] * dt;
        if (this.isWater(nx, ny)) { fl.pos[i] = [nx, ny]; fl.vel[i] = v; }        // 땅으로는 못 간다
        else fl.vel[i] = [-v[0] * 0.5 + rng.normal(0, 1), -v[1] * 0.5 + rng.normal(0, 1)];
      }
    }
  }

  draw(ops: LifeOps, visible: number) {
    if (visible <= 0) return;
    for (const b of this.balls) {
      const fl = b.flock;
      fl.pos.forEach((p, i) => {
        const vis = visible * (1 - b.depth[i]);                                 // 숨을수록 흐려진다
        if (vis <= 0.04) return;
        const head = 1.0 - 0.42 * vis, body = 1.0 - 0.36 * vis, tail = 1.0 - 0.2 * vis;
        const v = fl.vel[i], n = Math.hypot(v[0], v[1]) + 1e-6, ux = v[0] / n, uy = v[1] / n;
        const cells: [number, number, number][] = [[p[0] + ux * 0.6, p[1] + uy * 0.6, head], [p[0] - ux * 0.4, p[1] - uy * 0.4, body],
                                                   [p[0] - ux * 1.4, p[1] - uy * 1.4, tail]];
        const seen = new Set<number>();
        for (const [x0, y0, k] of cells) {
          const x = Math.trunc(x0), y = Math.trunc(y0), key = y * this.W + x;
          if (seen.has(key) || !this.isWater(x, y)) continue;
          seen.add(key);
          ops.mul.push(x, y, k);
        }
      });
    }
  }
}

export class Life {
  readonly birds: SeaBirds;
  readonly fish: FishSchools;
  readonly balls: BaitBalls;
  private water: Uint8Array;
  private W: number;
  private H: number;
  private foam: number[];

  constructor(bundle: Bundle, seed = 0) {
    const m = bundle.meta, fl = bundle.arrays.flags.data as Uint8Array;
    this.W = m.W; this.H = m.H;
    this.water = new Uint8Array(this.W * this.H);
    for (let i = 0; i < this.water.length; i++) this.water[i] = fl[i] & m.flags.surf_water ? 1 : 0;
    this.foam = m.shader.foam_color;
    this.birds = new SeaBirds(this.water, this.W, this.H, new Rng(seed + 101));
    this.fish = new FishSchools(this.water, this.W, this.H, new Rng(seed + 202));
    this.balls = new BaitBalls(this.water, this.W, this.H, new Rng(seed + 303));
  }

  /** 물고기 자원지의 무리 자리 (지도 칸 [x, y]...). 게임이 판을 열 때 넘긴다. */
  setBaitBalls(centers: V2[]) { this.balls.set(centers); }

  update(dt: number, mouse: V2 | null, click: V2 | null) {
    const onWater = !!click && click[0] >= 0 && click[0] < this.W && click[1] >= 0 && click[1] < this.H &&
      this.water[Math.trunc(click[1]) * this.W + Math.trunc(click[0])] > 0;
    this.birds.update(dt, mouse, !!click);
    this.fish.update(dt, mouse, onWater ? click : null);
    this.balls.update(dt, mouse);
  }

  /** 그릴 것: [물고기(곱하기 → 물보라 → 파문), 새(그림자 → 몸)] 순서. */
  ops(cycle: DayNightCycle): LifeOps[] {
    const { light } = cycle.keyframe(), sun = cycle.sunAlt();
    const birdsAlive = Math.min(Math.max((sun + 2.0) / 6.0, 0), 1);       // 해 질 녘에 하나둘 사라진다
    const fishVisible = Math.min(Math.max((sun + 4.0) / 8.0, 0), 1);      // 밤에는 안 보인다
    const fish: LifeOps = { mul: [], set: [], brighten: [] };
    const birds: LifeOps = { mul: [], set: [], brighten: [] };
    this.balls.draw(fish, fishVisible);
    this.fish.draw(fish, this.foam, light, fishVisible);
    this.birds.draw(birds, light, birdsAlive);
    return [fish, birds];
  }
}
