// 밤의 횃불: 해가 지면 다 지은 건물 둘레(모서리 바깥 땅)에 횃불이 선다.
// 빛은 지형 빛 단계에 넘기고 (render/terrain.ts setTorches: 반지름 TORCH_R칸만, 디더로 섞임),
// 같은 빛을 유닛·건물 칠하기에도 쓴다 (at). 불꽃은 조금씩 일렁인다 (횃불마다 다르게).

import { TORCH_R } from '../render/terrain.ts';
import type { GameState } from './state.ts';
import { F_LAND, F_WATER, type TerrainRules } from './terrainRules.ts';

export interface Torch { x: number; y: number; s: number; id: number }

const hash = (a: number) => { let h = Math.imul(a ^ (a >>> 15), 2246822519); h = Math.imul(h ^ (h >>> 13), 3266489917); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

/** 해 고도 → 밤 정도 (해가 지평선 조금 위에서 켜기 시작해 -6°에 다 켜진다). */
export function nightAmount(sunAlt: number) { return Math.min(Math.max((1 - sunAlt) / 7, 0), 1); }

export class Torches {
  list: Torch[] = [];
  private spots = new Map<string, [number, number][]>();

  constructor(private rules: TerrainRules) {}

  private land(x: number, y: number) {
    const m = this.rules, xi = Math.floor(x), yi = Math.floor(y);
    return xi >= 0 && yi >= 0 && xi < m.W && yi < m.H && (m.at(yi, xi) & F_LAND) !== 0 && !(m.at(yi, xi) & F_WATER);
  }

  /** 건물 하나의 횃불 자리: 거점 4, 망루 1, 나머지 2. 건물 그림에 가리지 않게 앞 모서리와 양옆에
   *  (그림은 위아래가 눌려 있어 앞뒤로는 가깝게), 물이면 다음 자리. */
  private spotsFor(kind: number, x: number, y: number, r: number, seed: number, R: any): [number, number][] {
    const n = kind === R.kinds.HALL ? 4 : kind === R.kinds.TOWER ? 1 : 2;
    const hx = r + 0.5, hy = r * 0.6 + 0.6;
    const order: [number, number][] = kind === R.kinds.TOWER ? [[0, r + 0.8], [r + 0.8, 0], [-r - 0.8, 0]]
      : [[hx, hy], [-hx, hy], [hx + 0.3, -hy * 0.2], [-hx - 0.3, -hy * 0.2], [0, hy + 0.6]];
    const out: [number, number][] = [];
    for (const [dx, dy] of order) {
      if (out.length >= n) break;
      const j = (hash(seed + out.length) - 0.5) * 0.6;
      const tx = x + dx + j, ty = y + dy + j * 0.5;
      if (this.land(tx, ty)) out.push([tx, ty]);
    }
    return out;
  }

  /** 지금 켜진 횃불 (밤이 아니면 빈 목록). t: 화면 시각(초). */
  update(st: GameState, night: number, t: number): Torch[] {
    this.list = [];
    if (night <= 0) return this.list;
    const R = st.info.rules;
    for (const b of st.builds.values()) {
      if (b.prog < 1) continue;
      const key = `${b.slot},${b.gen}`;
      let sp = this.spots.get(key);
      if (!sp) { sp = this.spotsFor(b.kind, b.x, b.y, R.build[b.kind].r, b.slot * 131 + b.gen * 7, R); this.spots.set(key, sp); }
      sp.forEach(([x, y], i) => {
        const id = b.slot * 8 + i;
        const fl = 0.86 + 0.14 * Math.sin(t * 7.3 + id * 1.9) * Math.sin(t * 2.9 + id * 0.7 + 1.3);   // 일렁임
        this.list.push({ x, y, s: night * fl, id });
      });
    }
    return this.list;
  }

  /** 지형에 넘길 [x, y, 세기]... */
  points(): Float32Array {
    const a = new Float32Array(this.list.length * 3);
    this.list.forEach((p, i) => { a[i * 3] = p.x; a[i * 3 + 1] = p.y; a[i * 3 + 2] = p.s; });
    return a;
  }

  /** (x, y)에 닿는 횃불 빛 (0~1). */
  at(x: number, y: number): number {
    let v = 0;
    for (const p of this.list) {
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < TORCH_R) v += p.s * Math.pow(1 - d / TORCH_R, 0.9);
    }
    return Math.min(v, 1);
  }
}

/** 불꽃 (화면 점, 그림자·빛 표와 상관없이 스스로 빛난다). (x, y): 횃대 꼭대기, k: 점 크기. */
export function drawFlame(g: CanvasRenderingContext2D, x: number, y: number, k: number, t: number, id: number, a: number) {
  g.globalAlpha = a;
  const f = Math.floor(t * 9 + id * 3.7) % 3;
  g.fillStyle = 'rgb(224,98,45)'; g.fillRect(x - k, y - k, 2 * k, k);
  g.fillStyle = 'rgb(255,178,72)'; g.fillRect(x - k + (f === 1 ? k : 0), y - 2 * k, k, k);
  g.fillStyle = 'rgb(255,226,150)'; g.fillRect(x - (f === 2 ? k : 0), y - 2 * k, k, k);
  if (f !== 0) { g.fillStyle = 'rgb(255,178,72)'; g.fillRect(x - k + (f === 2 ? k : 0), y - 3 * k, k, k); }
  g.globalAlpha = 1;
}
