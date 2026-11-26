// 울타리 그리기 (목장, docs/PASTURE_PLAN.md 2-4).
// 큰 울타리를 그림 하나로 그리면 땅과 어긋난다. 그래서 서버가 정한 모양(sim/pasture.py fence_shape: 가운데 + 방향마다 반지름)을 따라
// 기둥을 SPACING칸마다 그 땅 위에 세우고, 이웃 기둥 사이에 가로대 둘을 건다.
// - 지형은 위에서 내려다본 그림 (높이로 화면이 어긋나지 않는다): 기둥은 그 칸의 바닥 점에 서서 위로 솟는다 (스프라이트와 같다).
// - 빛: 스프라이트(stack.ts shade)와 같은 색표·같은 해/달 빛. 그 칸이 산 그림자에 가렸으면 (지형의 지평선 높이, 지형 그리기와 같은 판정)
//   그 해/달 빛을 받지 않는다 → 언덕 그늘 쪽 울타리는 땅과 함께 어둡다. 횃불도 받는다.
// - 물·절벽·땅이 아닌 칸에는 기둥을 세우지 않고, 그 양옆 가로대도 끊는다.
// - 그림자: 해 반대쪽 바닥에 (스프라이트와 같은 방향·진하기). 모든 울타리 그림자를 건물보다 먼저 깐다 (기둥 위에 그림자가 덮이지 않게).
// - 그리는 순서: 기둥 사이 한 칸(가로대 + 앞 기둥)이 한 조각, 조각마다 제 y로 건물들과 함께 앞뒤를 정한다.
// - 화면 점은 정수 (그림 한 점 = P 화면 픽셀): 움직여도 자글거리지 않게.
// - 시인성 강조(visOn)를 켜면 밝은 테두리: 울타리 윤곽의 위쪽만 (기둥 꼭대기 테두리 바깥, 위 가로대 위 한 줄).
//   가는 기둥을 스프라이트처럼 사방으로 두르면 테두리가 기둥보다 굵어져 흰 상자처럼 보이고, 두 가로대 사이까지 칠하면 널빤지처럼 메워진다.
//   나라색 바닥 고리는 울타리가 아니라 목장 건물(헛간)에만.

import { type Light, OUTLINE, REF, RIM, WARM } from './stack.ts';
import { F_CLIFF, F_LAND, F_WATER, type TerrainRules } from './terrainRules.ts';
import { visOn } from './visibility.ts';
import { Mat, RAMPS } from './voxel.ts';

/** 울타리 모양: 가운데 (지도 칸)와 방향마다 반지름 (방향 i = 각도 2πi/n, 0은 +x). prog: 짓는 중이면 0~1 (그만큼의 기둥만 섰다). */
export interface FenceShape { x: number; y: number; radii: number[]; prog?: number; gate?: number }   // gate: 문 방향 (헛간 쪽, 라디안): 그 기둥 하나를 비운다

/** 방향마다 반지름 사이를 이어 이 각도의 반지름 (서버 sim/pasture.py radius_at과 같다). */
export function radiusAt(radii: number[], ang: number): number {
  const n = radii.length, t = ((((ang % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2)) * n;
  const i0 = Math.floor(t) % n, f = t - Math.floor(t);
  return radii[i0] * (1 - f) + radii[(i0 + 1) % n] * f;
}

const SPACING = 2.4;              // 기둥 사이 (칸)
const POST_H = 5;                 // 기둥 높이 (그림 점: 0..POST_H, 말 등 높이쯤)
const RAILS = [2, 4];             // 가로대 높이 (그림 점: 사이 한 점이 비어 땅이 비친다)
const SHADOW = [14, 12, 26];      // 그림자 색 (stack.ts와 같다)
const JITTER = 0.5;               // 기둥 자리를 둘레에서 안팎으로 흔드는 폭 (칸)

interface Post { x: number; y: number; ok: boolean; seed: number }

export class FenceDrawer {
  private cache = new Map<string, Post[]>();
  private readonly hz: Float32Array;

  constructor(private rules: TerrainRules, bundle: { arrays: any }) {
    this.hz = bundle.arrays.horizon.data as Float32Array;
  }

  /** 기둥 자리 (모양마다 한 번 계산해 둔다). 닫힌 둘레를 따라 SPACING칸마다. */
  posts(f: FenceShape): Post[] {
    const key = `${f.x},${f.y},${f.gate ?? ''},${f.radii.join(',')}`;
    let ps = this.cache.get(key);
    if (ps) return ps;
    const n = f.radii.length, pts: [number, number][] = [];
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      pts.push([f.x + Math.cos(a) * f.radii[i], f.y + Math.sin(a) * f.radii[i]]);
    }
    let per = 0;
    for (let i = 0; i < n; i++) { const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % n]; per += Math.hypot(x1 - x0, y1 - y0); }
    const count = Math.max(8, Math.round(per / SPACING)), step = per / count;
    ps = [];
    let seg = 0, along = 0;                                  // 둘레를 고른 간격으로 걷는다
    for (let k = 0; k < count; k++) {
      let want = k * step - along;
      for (;;) {
        const [x0, y0] = pts[seg % n], [x1, y1] = pts[(seg + 1) % n], len = Math.hypot(x1 - x0, y1 - y0);
        if (want <= len || seg >= n * 2) {
          const t = len > 0 ? Math.min(want / len, 1) : 0;
          const j = (((k * 0.754877 + f.x * 0.13 + f.y * 0.29) % 1) - 0.5) * JITTER;   // 손으로 박은 듯 안팎으로 조금씩 (자리마다 같다)
          const nx = len > 0 ? (y1 - y0) / len : 0, ny = len > 0 ? -(x1 - x0) / len : 0;
          const x = x0 + (x1 - x0) * t + nx * j, y = y0 + (y1 - y0) * t + ny * j;
          ps.push({ x, y, ok: this.ground(x, y), seed: ((k * 0.618034) % 1) - 0.5 });
          break;
        }
        want -= len; along += len; seg++;
      }
    }
    if (f.gate !== undefined && ps.length) {                 // 문: 헛간 쪽에 가장 가까운 기둥 하나를 비운다 (양옆 가로대도 끊긴다)
      let gi = 0, gd = Infinity;
      ps.forEach((p, i) => {
        let d = Math.abs(Math.atan2(p.y - f.y, p.x - f.x) - f.gate!) % (Math.PI * 2);
        if (d > Math.PI) d = Math.PI * 2 - d;
        if (d < gd) { gd = d; gi = i; }
      });
      ps[gi].ok = false;
    }
    if (this.cache.size > 64) this.cache.clear();
    this.cache.set(key, ps);
    return ps;
  }

  /** 기둥을 세울 수 있는 칸: 땅이고 물·절벽이 아니다. */
  private ground(x: number, y: number) {
    const r = this.rules, xi = Math.floor(x), yi = Math.floor(y);
    if (xi < 0 || yi < 0 || xi >= r.W || yi >= r.H) return false;
    const fl = r.at(yi, xi);
    return (fl & F_LAND) !== 0 && (fl & (F_CLIFF | F_WATER)) === 0;
  }

  /** 이 칸에서 해/달마다 하늘이 트였나 (1) 산에 가렸나 (0): 지형 그리기(render/terrain.ts LIGHT_FS)와 같은 판정. */
  private open(x: number, y: number, L: Light): number[] {
    const r = this.rules, xi = Math.min(Math.max(Math.floor(x), 0), r.W - 1), yi = Math.min(Math.max(Math.floor(y), 0), r.H - 1);
    const h = this.hz[yi * r.W + xi];
    return L.src.map((s) => {
      const tan = s.z / Math.max(Math.hypot(s.x, s.y), 1e-6);
      return h < tan ? 1 : 0;
    });
  }

  /** 나무 한 점의 색 (stack.ts shade와 같은 계산: 낮 그림 5단계 → 지금 시각 빛표·그늘표, 산 그림자, 횃불). */
  private wood(nx: number, ny: number, nz: number, seed: number, L: Light, open: number[], torch: number, m: number = Mat.WOOD) {
    const ref = nx * REF[0] + ny * REF[1] + nz * REF[2];
    const step = Math.min(4, Math.max(0, Math.round(2.05 + ref * 1.35 + seed * 0.6)));
    const base = RAMPS[m][step], T = L.table;
    let lit = 0;
    L.src.forEach((s, k) => { lit += s.w * open[k] * Math.min(Math.max((nx * s.x + ny * s.y + nz * s.z) / s.div, 0), 1); });
    lit = Math.min(lit, 1);
    const c = [0, 1, 2].map((k) => T[base[k] * 4 + k] * (1 - lit) + T[1024 + base[k] * 4 + k] * lit);
    if (torch > 0) {
      const a = Math.min(Math.max(torch * 1.2 - 0.1, 0), 1);
      for (let k = 0; k < 3; k++) c[k] = Math.max(c[k], c[k] + (base[k] * WARM[k] - c[k]) * a);
    }
    return `rgb(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])})`;
  }

  /** 지금 선 기둥 수 (짓는 중이면 그만큼만: 둘레를 따라 하나씩 선다). */
  private built(f: FenceShape, n: number) { return f.prog === undefined || f.prog >= 1 ? n : Math.floor(Math.max(f.prog, 0) * n); }

  /** 이어진 두 기둥 사이에 가로대를 걸까 (둘 다 섰고, 사이가 너무 멀지 않다). */
  private linked(a: Post, b: Post) { return a.ok && b.ok && Math.hypot(b.x - a.x, b.y - a.y) < SPACING * 1.7; }

  /** 모든 울타리의 그림자 (건물보다 먼저). */
  drawShadows(g: CanvasRenderingContext2D, fences: FenceShape[], L: Light, K: number,
              sx: (x: number) => number, sy: (y: number) => number, vis: (x: number, y: number, pad?: number) => boolean) {
    if (!L.shadow) return;
    const P = Math.max(1, Math.round(K)), { dx, dy, a } = L.shadow;
    g.fillStyle = `rgba(${SHADOW[0]},${SHADOW[1]},${SHADOW[2]},${a})`;
    for (const f of fences) {
      const ps = this.posts(f), up = this.built(f, ps.length);
      for (let i = 0; i < up; i++) {
        const p = ps[i], q = ps[(i + 1) % ps.length];
        if (!p.ok) continue;
        const bx = Math.round(sx(p.x)), by = Math.round(sy(p.y));
        if (!vis(bx, by, 60)) continue;
        for (let z = 0; z <= POST_H; z++) g.fillRect(Math.round(bx + dx * (z + 0.5) * P), Math.round(by + dy * (z + 0.5) * P), P, P);
        if (!this.linked(p, q) || i + 1 >= up && up < ps.length) continue;
        const cx = Math.round(sx(q.x)), cy = Math.round(sy(q.y));
        g.globalAlpha = 0.75;                                 // 가로대 그림자는 조금 옅게 (가는 줄이 또 하나의 울타리처럼 보이지 않게)
        for (const z of RAILS) this.line(g, bx + dx * z * P, by + dy * z * P, cx + dx * z * P, cy + dy * z * P, P);
        g.globalAlpha = 1;
      }
    }
  }

  /** 울타리 조각들 (건물 목록에 섞어 y 순서로 그린다): 기둥 i와 그 다음 기둥까지의 가로대. */
  pieces(fences: FenceShape[], g: CanvasRenderingContext2D, L: Light, K: number,
         sx: (x: number) => number, sy: (y: number) => number, vis: (x: number, y: number, pad?: number) => boolean,
         torch: (x: number, y: number) => number): { y: number; f: () => void }[] {
    const out: { y: number; f: () => void }[] = [];
    const P = Math.max(1, Math.round(K)), half = Math.floor(P / 2);
    const ol = `rgba(${OUTLINE[0]},${OUTLINE[1]},${OUTLINE[2]},0.92)`;
    const rim = visOn() ? `rgba(${RIM[0]},${RIM[1]},${RIM[2]},0.5)` : null;      // 밝은 테두리 (stack.ts와 같은 색)
    const hi = Math.max(...RAILS) + 1;
    for (const f of fences) {
      const ps = this.posts(f), up = this.built(f, ps.length);
      for (let i = 0; i < up; i++) {
        const p = ps[i], q = ps[(i + 1) % ps.length];
        if (!p.ok) continue;
        const bx = Math.round(sx(p.x)), by = Math.round(sy(p.y));
        if (!vis(bx, by, 60)) continue;
        const link = this.linked(p, q) && (i + 1 < up || up === ps.length);   // 짓는 중: 선 기둥 사이에만 가로대
        out.push({ y: link ? Math.max(p.y, q.y) : p.y, f: () => {
          const open = this.open(p.x, p.y, L), tch = torch(p.x, p.y);
          if (link) {                                        // 가로대: 기둥 사이 (앞을 보며 조금 위를 향한 면의 빛: 밝은 나무)
            const cx = Math.round(sx(q.x)), cy = Math.round(sy(q.y));
            let ux = q.x - p.x, uy = q.y - p.y;
            const l = Math.hypot(ux, uy) || 1; ux /= l; uy /= l;
            let nx = -uy, ny = ux;
            if (ny < 0 || (ny === 0 && nx < 0)) { nx = -nx; ny = -ny; }   // 보는 쪽(화면 아래)을 향한 면
            const open2 = this.open(q.x, q.y, L).map((v, k) => (v + open[k]) / 2), t2 = (tch + torch(q.x, q.y)) / 2;
            const sl = Math.hypot(cx - bx, cy - by);
            if (sl > P * 2) {                                  // 두 끝을 기둥 너비만큼 줄인다 (다음 기둥을 덮지 않게)
              const ex = ((cx - bx) / sl) * P, ey = ((cy - by) / sl) * P;
              const ax = bx + ex, ay = by + ey, zx = cx - ex, zy = cy - ey;
              if (rim) { g.fillStyle = rim; this.line(g, ax, ay - hi * P, zx, zy - hi * P, P); }   // 밝은 테두리: 위 가로대 위 한 줄
              g.fillStyle = this.wood(nx * 0.8, ny * 0.8, 0.6, p.seed + 0.3, L, open2, t2);
              for (const z of RAILS) this.line(g, ax, ay - z * P, zx, zy - z * P, P);
            }
          }
          // 기둥: 테두리, 앞면, 꼭대기 (기둥은 이 조각에서 마지막에: 제 가로대 끝을 덮는다)
          const x0 = bx - half, top = by - POST_H * P;
          if (rim) { g.fillStyle = rim; g.fillRect(x0 - 2 * P, top - 2 * P, P * 5, P); g.fillRect(x0 - 2 * P, top - P, P, 2 * P); g.fillRect(x0 + 2 * P, top - P, P, 2 * P); }   // 꼭대기 테두리 바깥 (위와 위쪽 옆)
          g.fillStyle = ol;
          g.fillRect(x0 - P, top - P, P * 3, (POST_H + 2) * P);
          g.fillStyle = this.wood(0, 0.9, 0.3, p.seed, L, open, tch, Mat.WOOD);
          g.fillRect(x0, top + P, P, POST_H * P);
          g.fillStyle = this.wood(0, 0, 1, p.seed, L, open, tch, Mat.WOOD);
          g.fillRect(x0, top, P, P);
        } });
      }
    }
    return out;
  }

  /** 정수 점 선 (점 크기 P): 두 끝을 잇는 가장 가까운 점들. */
  private line(g: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, P: number) {
    const n = Math.max(1, Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) / P));
    for (let k = 0; k <= n; k++) {
      const t = k / n;
      g.fillRect(Math.round(x0 + (x1 - x0) * t - P / 2), Math.round(y0 + (y1 - y0) * t - P / 2), P, P);
    }
  }
}
