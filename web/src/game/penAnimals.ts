// 목장 안의 동물 (화면만의 꾸밈, docs/PASTURE_PLAN.md 2-5). 서버(sim/pasture.py)는 마리 수와 자리만 안다.
// 목장에 든 순간 서버가 넘긴 자리(울타리 안에 걸어 들어온 야생 동물의 마지막 자리)에서 같은 모델로 이어 그린다
// → 야생 동물이 사라지고 다른 그림이 나타나는 것이 아니라, 같은 동물이 그 자리에서 계속 풀을 뜯는다.
// 그 뒤 울타리 안을 느리게 거닐고 서서 풀을 뜯는다 (헛간은 울타리 바로 바깥). 화면을 연 뒤 새로 는 새끼는 조금 작게.

import type { PenRec } from './protocol.ts';
import { radiusAt } from './fence.ts';
import type { Light, StackRenderer } from './stack.ts';

const NAMES = ['horse', 'dragon', 'tortoise', 'reindeer'];     // 동물 종류 → 모델 (rules.WILDLIFE 순서, wildlife.ts와 같다)
const SPEED = 0.45;                                          // 거니는 빠르기 (칸/초)
const DIRS = 16, TAU = Math.PI * 2;

interface Beast { x: number; y: number; tx: number; ty: number; walk: boolean; t: number; ang: number; calf: boolean; seed: number }

export class PenAnimals {
  private herds = new Map<number, { gen: number; list: Beast[] }>();
  private rng = 1;

  private rand() { this.rng = (this.rng * 16807) % 2147483647; return this.rng / 2147483647; }

  /** 서버의 목장 목록에 맞춘다 (처음 본 목장은 받은 자리에서, 늘어난 만큼 새끼). */
  sync(pens: Map<number, PenRec>) {
    for (const k of [...this.herds.keys()]) if (!pens.has(k) || !pens.get(k)!.done) this.herds.delete(k);
    for (const p of pens.values()) {
      if (!p.done) continue;
      let h = this.herds.get(p.b);
      if (h && h.gen !== p.gen) { this.herds.delete(p.b); h = undefined; }
      const fresh = !h;
      if (!h) { h = { gen: p.gen, list: [] }; this.herds.set(p.b, h); }
      while (h.list.length < p.spots.length) {
        const [dx, dy] = p.spots[h.list.length], x = p.cx + dx, y = p.cy + dy;
        h.list.push({ x, y, tx: x, ty: y, walk: false, t: 1 + this.rand() * 4, ang: this.rand() * TAU, calf: !fresh, seed: this.rand() * 10 });
      }
      if (h.list.length > p.spots.length) h.list.length = p.spots.length;
    }
  }

  /** 거닐기 (프레임마다): 울타리 안 어디든 (헛간은 울타리 바깥에 있다). */
  update(dt: number, pens: Map<number, PenRec>) {
    for (const [k, h] of this.herds) {
      const p = pens.get(k);
      if (!p) continue;
      for (const b of h.list) {
        b.t -= dt;
        if (b.t <= 0) {
          if (!b.walk && this.rand() < 0.55) {                  // 다른 자리로 거닌다 (울타리 안쪽)
            const a = this.rand() * TAU, r = radiusAt(p.radii, a) * (0.1 + this.rand() * 0.7);
            b.tx = p.cx + Math.cos(a) * r; b.ty = p.cy + Math.sin(a) * r;
            b.walk = true; b.t = 12;
          } else { b.walk = false; b.t = 2 + this.rand() * 5; }   // 서서 풀을 뜯는다
        }
        if (b.walk) {
          const dx = b.tx - b.x, dy = b.ty - b.y, d = Math.hypot(dx, dy);
          if (d < 0.1) { b.walk = false; b.t = 2 + this.rand() * 4; continue; }
          const s = Math.min(SPEED * (b.calf ? 1.15 : 1) * dt, d);
          b.x += (dx / d) * s; b.y += (dy / d) * s;
          let da = (Math.atan2(dy, dx) - b.ang) % TAU;           // 가는 쪽으로 천천히 돈다
          if (da > Math.PI) da -= TAU;
          if (da < -Math.PI) da += TAU;
          b.ang += da * Math.min(dt * 4, 1);
        }
      }
    }
  }

  /** 그릴 조각들 (건물·울타리 목록에 섞어 y 순서로). */
  items(g: CanvasRenderingContext2D, stack: StackRenderer, L: Light, K: number, t: number,
        sx: (x: number) => number, sy: (y: number) => number, vis: (x: number, y: number, pad?: number) => boolean,
        torch: (x: number, y: number) => number, pens: Map<number, PenRec>): { y: number; f: () => void }[] {
    const out: { y: number; f: () => void }[] = [];
    for (const [k, h] of this.herds) {
      const p = pens.get(k);
      if (!p) continue;
      const name = NAMES[p.kind] ?? 'horse';
      for (const b of h.list) {
        const x = sx(b.x), y = sy(b.y);
        if (!vis(x, y, 40)) continue;
        out.push({ y: b.y, f: () => {
          const frame = b.walk ? Math.trunc(t * 3 + b.seed) % 2 : Math.sin(t * 0.8 + b.seed) > -0.2 ? 2 : 0;
          const dir = ((Math.round(b.ang / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
          const k = b.calf ? Math.max(K * 0.7, 0.7) : K;
          g.imageSmoothingEnabled = k < 1 || b.calf;
          stack.draw(g, name, 0, L, Math.round(x), Math.round(y), k, { frame, dir, torch: torch(b.x, b.y) });
          g.imageSmoothingEnabled = false;
        } });
      }
    }
    return out;
  }
}
