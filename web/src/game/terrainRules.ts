// 게임 규칙 지형 (서버 /api/maps/<키>/rules.bin): 마우스 아래 설명과 건물 자리 미리보기를 브라우저가 바로 계산한다.
// 규칙은 서버(sim/world.py can_place, sim/boats.py can_place_harbor)와 같다. 실제로 지을지는 서버가 정한다.

import { gunzip } from '../bundle/tsb.ts';
import type { BuildRec } from './protocol.ts';

export const F_LAND = 1, F_FORD = 2, F_CLIFF = 4, F_OCEAN = 8, F_WATER = 16;

export class TerrainRules {
  constructor(readonly W: number, readonly H: number, readonly flags: Uint8Array,
              readonly cost: Uint16Array, readonly cover: Uint8Array, private rules: any) {}

  static async load(url: string, rules: any): Promise<TerrainRules> {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`게임 규칙 지형을 받지 못했습니다 (${r.status})`);
    const buf = await gunzip(await r.arrayBuffer());
    const v = new DataView(buf);
    const W = v.getUint16(4, true), H = v.getUint16(6, true), N = W * H;
    let o = 8;
    const flags = new Uint8Array(buf.slice(o, o + N)); o += N;
    const cost = new Uint16Array(buf.slice(o, o + N * 2)); o += N * 2;
    const cover = new Uint8Array(buf.slice(o, o + N));
    return new TerrainRules(W, H, flags, cost, cover, rules);
  }

  at(y: number, x: number) { return this.flags[y * this.W + x]; }
  land(y: number, x: number) { return (this.at(y, x) & F_LAND) !== 0; }

  private farFromBuildings(y: number, x: number, r: number, builds: Iterable<BuildRec>) {
    for (const b of builds) {
      const br = this.rules.build[b.kind].r;
      if (Math.hypot(b.x - x, b.y - y) - br < r + 2) return false;
    }
    return true;
  }

  /** world.can_place: 반지름 r 안이 모두 땅이고 다른 건물과 떨어진 곳. */
  canPlace(y: number, x: number, r: number, builds: Iterable<BuildRec>): boolean {
    if (!(r <= y && y < this.H - r && r <= x && x < this.W - r)) return false;
    for (let yy = y - r; yy <= y + r; yy++) for (let xx = x - r; xx <= x + r; xx++) if (!this.land(yy, xx)) return false;
    return this.farFromBuildings(y, x, r, builds);
  }

  /** fleet.can_place_harbor: 바다(호수 말고)에 맞닿은 해안, 절벽 아님, 땅이 반쯤은 있고, 다른 건물과 떨어진 곳. */
  canPlaceHarbor(y: number, x: number, builds: Iterable<BuildRec>): boolean {
    const r = this.rules.build[this.rules.kinds.HARBOR].r;
    if (!(r + 3 <= y && y < this.H - r - 3 && r + 3 <= x && x < this.W - r - 3) || !this.land(y, x)) return false;
    let ocean = false;
    for (let yy = y - r - 2; yy < y + r + 3; yy++) for (let xx = x - r - 2; xx < x + r + 3; xx++) if (this.at(yy, xx) & F_OCEAN) ocean = true;
    if (!ocean) return false;
    for (let yy = y - 2; yy < y + 3; yy++) for (let xx = x - 2; xx < x + 3; xx++) if (this.at(yy, xx) & F_CLIFF) return false;
    let land = 0;
    for (let yy = y - r; yy <= y + r; yy++) for (let xx = x - r; xx <= x + r; xx++) land += this.land(yy, xx) ? 1 : 0;
    if (land / ((2 * r + 1) ** 2) < 0.4) return false;
    return this.farFromBuildings(y, x, r, builds);
  }

  /** 걷는 속도 배율 (눈 덮이면 느리다, 얼어붙은 바다는 2.2). mat: 지금 재질, ice: 바다 얼음. */
  speed(y: number, x: number, mat: number, ice: boolean): number {
    const i = y * this.W + x;
    let c = this.cost[i] / 1000;
    if (ice) c = this.rules.sea_ice_cost;
    else if (this.flags[i] & F_LAND && this.rules.snowy.includes(mat)) c = Math.max(c * 1.6, 3.0);
    return Math.fround(1 / Math.fround(c));
  }
}
