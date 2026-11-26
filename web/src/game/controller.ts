// 선택과 명령 (데스크톱 game/app.py의 _select_point / _select_box / _command / _place / _train과 같은 규칙).
// 명령은 서버로 보내고(서버가 sim/commands.py로 처리), 화면 표시(명령 동그라미)는 같은 판단을 여기서 해서 바로 그린다.

import { radiusAt } from './fence.ts';
import type { Connection } from './net.ts';
import type { GameState, Unit, Boat } from './state.ts';
import type { BuildRec } from './protocol.ts';
import { type TerrainRules } from './terrainRules.ts';
import { josa } from '../ui/device.ts';
import { animalAt } from './wildlife.ts';

export const UNIT_ZOOM = 2.6;        // 이보다 가까이 보면 병사 하나하나, 멀면 무리 배지
const FLY_CELLS = 18 / 2.4;           // 날고 있는 병종이 떠 있는 높이 (지도 칸, draw.ts FLY_LIFT와 같다)
/** null / 'attack'(A 다음 클릭) / 숫자 = 놓을 건물 종류 (하단 버튼, 숫자 키) */
export type Mode = null | 'attack' | number;
/** 건물 버튼 (숫자 키 1~): 서버 이름 */
export const BUILD_NAMES_EN = ['hall', 'farm', 'lumber', 'quarry', 'tower', 'harbor', 'sulfur', 'fire', 'pasture'];   // 건물 종류 번호 순서 (sim/rules.py)
export type TrainKind = 'infantry' | 'archer' | 'warship';
export interface Ping { t0: number; x: number; y: number; col: string }

const PING = { attack: 'rgb(255,110,90)', build: 'rgb(140,200,255)', move: 'rgb(170,240,170)',
               amove: 'rgb(255,170,120)', ship: 'rgb(170,220,255)', tame: 'rgb(240,200,90)' };

export class Controller {
  sel = new Map<number, number>();        // 병사 칸 → 세대
  selB: [number, number] | null = null;   // 건물 (칸, 세대)
  selShips = new Set<number>();           // 배 번호 (전함, 병사를 태운 나룻배)
  groups = new Map<number, Map<number, number>>();
  mode: Mode = null;
  pings: Ping[] = [];
  private turn: Record<string, number> = {};      // 훈련을 맡길 건물 차례 (종류마다)

  constructor(private st: GameState, private net: Connection, readonly rules: TerrainRules) {}

  get me() { return this.st.info.me; }
  onForeignHall: ((b: BuildRec) => void) | null = null;     // 다른 나라의 거점을 눌렀다 (외교 말풍선)
  onPickElse: (() => void) | null = null;                   // 다른 나라의 거점이 아닌 곳을 눌렀다 (외교 말풍선을 닫는다)
  /** 살펴보는 다른 나라의 건물 (거점 말고): 건물 말풍선 (buildInfo.ts). */
  inspect: [number, number] | null = null;
  rules_kinds() { return this.R().kinds; }
  /** 내 동맹인가 (외교 상태). */
  isAlly(nid: number) { return !!this.st.diplo && String(nid) in this.st.diplo.allies; }
  private R() { return this.st.info.rules; }

  // ------------------------------------------------------------- 찾기 (서버 sim/world.py와 같은 규칙)
  /** ground: 날고 있는 병사도 땅 위치로 (아니면 그림이 떠 있는 자리로 찾는다). */
  unitAt(x: number, y: number, r: number, own?: number, ground = false): Unit | null {
    let best: Unit | null = null, bd = r;
    for (const u of this.st.units.values()) {
      if (u.bits & 2 || (own !== undefined && u.own !== own)) continue;
      const d = Math.hypot(u.x - x, this.drawnY(u, ground) - y);
      if (d <= bd) { best = u; bd = d; }
    }
    return best;
  }

  buildingAt(x: number, y: number, own?: number): BuildRec | null {
    let best: BuildRec | null = null, bd = Infinity;
    for (const b of this.st.builds.values()) {
      if (own !== undefined && b.own !== own) continue;
      const d = Math.hypot(b.x - x, b.y - y) - this.R().build[b.kind].r;
      if (d < bd) { best = b; bd = d; }
    }
    return best && bd <= 1.0 ? best : null;
  }

  siteAt(x: number, y: number, r: number) {
    let best = null as StartSite | null, bd = r;
    for (const s of this.st.info.sites) {
      const d = Math.hypot(s.x - x, s.y - y);
      if (d < bd) { best = s; bd = d; }
    }
    return best;
  }

  boatAt(x: number, y: number, r: number, own?: number): Boat | null {
    let best: Boat | null = null, bd = r;
    for (const b of this.st.boats.values()) {
      if (own !== undefined && b.own !== own) continue;
      const d = Math.hypot(b.x - x, b.y - y);
      if (d < bd) { best = b; bd = d; }
    }
    return best;
  }

  // ------------------------------------------------------------- 고른 것
  /** 살아 있는 선택만 남긴다 (죽은 병사, 무너진 건물, 가라앉은 배). */
  prune() {
    for (const [s, g] of this.sel) { const u = this.st.units.get(s); if (!u || u.gen !== g || u.bits & 2) this.sel.delete(s); }
    if (this.selB) { const b = this.st.builds.get(this.selB[0]); if (!b || b.gen !== this.selB[1]) this.selB = null; }
    for (const id of this.selShips) { const b = this.st.boats.get(id); if (!b || !pickable(b)) this.selShips.delete(id); }
  }

  /** 건물이 선 자원지 번호들 (터치 탭 판단에). */
  st_siteTaken() { return this.st.siteTaken(); }

  refs(): number[][] { return [...this.sel].map(([s, g]) => [s, g]); }
  hasSelection() { return this.sel.size > 0 || this.selB !== null || this.selShips.size > 0; }

  /** 화면에 그려진 높이 (날고 있으면 떠 있는 만큼 위). */
  drawnY(u: Unit, ground = false) { return !ground && u.bits & 4 ? u.y - FLY_CELLS : u.y; }

  selectBox(x0: number, y0: number, x1: number, y1: number, add: boolean) {
    this.inspect = null;
    this.onPickElse?.();
    if (!add) { this.sel.clear(); this.selShips.clear(); this.selB = null; }
    for (const u of this.st.units.values()) {
      const uy = this.drawnY(u);
      if (u.own === this.me && !(u.bits & 2) && u.x >= x0 && u.x <= x1 && uy >= y0 && uy <= y1) this.sel.set(u.slot, u.gen);
    }
    for (const b of this.st.boats.values()) {
      if (b.own === this.me && pickable(b) && b.x >= x0 && b.x <= x1 && b.y >= y0 && b.y <= y1) this.selShips.add(b.id);
    }
  }

  /** px: 고르는 반경 (화면 픽셀, 터치는 손가락 크기만큼 넓게). */
  selectPoint(x: number, y: number, zoom: number, add: boolean, px = 8) {
    this.inspect = null;                                       // 말풍선은 누를 때마다 새로 (땅·다른 것을 누르면 꺼진다)
    const fb0 = this.buildingAt(x, y);
    if (!(fb0 && fb0.own !== this.me && fb0.kind === this.R().kinds.HALL)) this.onPickElse?.();
    const u = this.unitAt(x, y, Math.max(1.5, px / zoom), this.me);
    if (u) {
      if (!add) { this.sel.clear(); this.selB = null; this.selShips.clear(); }
      if (zoom < UNIT_ZOOM) {                    // 멀리서는 배지 하나 = 그 무리 전체
        for (const v of this.st.units.values()) {
          if (v.own === this.me && !(v.bits & 2) && Math.hypot(v.x - u.x, v.y - u.y) < 34 / zoom) this.sel.set(v.slot, v.gen);
        }
      } else this.sel.set(u.slot, u.gen);
      return;
    }
    const ship = this.boatAt(x, y, Math.max(3.0, (px + 2) / zoom), this.me);
    if (ship && pickable(ship)) {
      if (!add) { this.sel.clear(); this.selB = null; this.selShips.clear(); }
      this.selShips.add(ship.id);
      return;
    }
    const b = this.buildingAt(x, y, this.me);
    if (b) {
      if (!add) { this.sel.clear(); this.selShips.clear(); }
      this.selB = [b.slot, b.gen];
      return;
    }
    const fb = this.buildingAt(x, y);                        // 다른 나라의 거점: 외교 말풍선 (고른 병사는 그대로)
    if (fb && fb.own !== this.me && fb.kind === this.R().kinds.HALL && this.onForeignHall) {
      this.selB = null;                                      // 건물 말풍선은 닫고 외교 말풍선 (고른 병사는 그대로)
      this.onForeignHall(fb);
      return;
    }
    if (fb && fb.own !== this.me) {                          // 다른 나라의 다른 건물: 살펴보기 말풍선 (고른 병사는 그대로)
      this.selB = null;
      this.inspect = [fb.slot, fb.gen];
      return;
    }
    if (!add) { this.sel.clear(); this.selB = null; this.selShips.clear(); }
  }

  // ------------------------------------------------------------- 명령
  private ping(x: number, y: number, col: string) { this.pings.push({ t0: performance.now(), x, y, col }); }

  /** 오른쪽 클릭 (attack: A 다음 클릭). 서버로 보내고, 같은 판단으로 명령 표시를 바로 그린다. */
  command(x: number, y: number, zoom: number, attack: boolean, px = 8) {
    this.prune();
    const r = Math.max(2.0, px / zoom);
    if (this.selShips.size) {
      const foe = this.boatAt(x, y, Math.max(3.0, r * 1.25));
      if (foe && foe.own !== this.me) this.ping(x, y, PING.attack);
      else if (this.rules.at(Math.floor(y), Math.floor(x)) & 16) this.ping(x, y, PING.ship);
      else if ([...this.selShips].some((id) => this.st.boats.get(id)?.kind === 0)) this.ping(x, y, PING.move);   // 나룻배: 해안에 내려 줌
    }
    if (this.sel.size || this.selShips.size) {
      this.net.command(this.refs(), [...this.selShips], x, y, attack, r);
    }
    if (!this.sel.size) return;
    const foe = this.unitAt(x, y, Math.max(2.0, r));
    if (foe && foe.own !== this.me) return this.ping(x, y, PING.attack);
    const an = animalAt(this.st, x, y, Math.max(1.8, r));      // 야생 동물: 길들이러 (깨어 있거나 잠든 드래곤은 친다)
    if (an && (an.state === 5 || an.state === 6)) return this.ping(an.x, an.y - 1, PING.attack);
    if (an && !attack && this.R().wildlife?.[an.kind]?.tamers?.length) return this.ping(an.x, an.y - 0.4, PING.tame);   // 길들이지 않는 동물(순록)은 그냥 그 자리로
    const b = this.buildingAt(x, y);
    if (b && b.own !== this.me) return this.ping(x, y, PING.attack);
    if (b && b.prog < 1) return this.ping(x, y, PING.build);
    const pen = this.penAt(x, y);                              // 내 말 목장: 말을 꺼내 탄다 (서버 sim/pasture.py order_ride)
    if (pen && pen.own === this.me && pen.done && !attack && Object.keys(this.R().wildlife?.[pen.kind]?.mounts ?? {}).length) return this.ping(x, y, PING.tame);
    const s = this.siteAt(x, y, Math.max(4.0, r * 1.25));
    if (s && !this.st.siteTaken().has(s.id) && !attack) return this.ping(s.x, s.y, PING.build);
    this.ping(x, y, attack ? PING.amove : PING.move);
  }

  /** 자원지에 짓는 건물이면 그 자원 종류 (아니면 -1). */
  siteRes(kind: number): number {
    const sb = this.R().site_building;
    for (const k of Object.keys(sb)) if (sb[k] === kind) return Number(k);
    return -1;
  }

  /** (x, y)가 헛간이거나 울타리 안인 목장. */
  penAt(x: number, y: number) {
    const b = this.buildingAt(x, y);
    if (b && this.st.pens.has(b.slot)) return this.st.pens.get(b.slot)!;
    for (const p of this.st.pens.values()) {
      const d = Math.hypot(x - p.cx, y - p.cy);
      if (d < radiusAt(p.radii, Math.atan2(y - p.cy, x - p.cx))) return p;
    }
    return null;
  }

  /** 목장: 커서 가까이의 말·순록 떼 (같은 종류, herd_r 안). 반환: 누른 동물과 떼 가운데, 마리 수. 서버 sim/pasture.py herd_at과 같다
   *  (짓는 중인 다른 목장 몫은 화면이 몰라 서버가 다시 고른다). */
  herdAt(x: number, y: number, zoom: number) {
    const P = this.R().pasture;
    if (!P) return null;
    const ok = (k: number) => P.food[String(k)] !== undefined;
    let a0 = null as null | { x: number; y: number; kind: number }, bd = Math.max(P.find_r, 30 / zoom);
    for (const an of this.st.animals.values()) {
      if (!ok(an.kind) || an.state === 3 || an.state === 4) continue;      // 길들이는 중은 빼고
      const d = Math.hypot(an.x - x, an.y - y);
      if (d < bd) { a0 = an; bd = d; }
    }
    if (!a0) return null;
    const herd = [...this.st.animals.values()].filter((an) => an.kind === a0!.kind && an.state !== 3 && an.state !== 4
      && Math.hypot(an.x - a0!.x, an.y - a0!.y) < P.herd_r);
    const cx = herd.reduce((s, a) => s + a.x, 0) / herd.length, cy = herd.reduce((s, a) => s + a.y, 0) / herd.length;
    return { ax: a0.x, ay: a0.y, cx, cy, n: herd.length, kind: a0.kind };
  }

  /** 건물을 놓을 자리: 자원지 건물은 커서 가까이의 빈 자원지에 붙는다, 목장은 떼 가운데에. 반환 {x, y, ok}. */
  placeTarget(kind: number, x: number, y: number, zoom: number): { x: number; y: number; ok: boolean } {
    if (kind === this.R().kinds.PASTURE) {
      const h = this.herdAt(x, y, zoom);
      return h ? { x: h.cx, y: h.cy, ok: h.n >= this.R().pasture.min_herd } : { x, y, ok: false };
    }
    const res = this.siteRes(kind);
    if (res >= 0) {
      const taken = this.st.siteTaken();
      let best = null as StartSite | null, bd = Math.max(6, 40 / zoom);
      for (const s of this.st.info.sites) {
        if (s.kind !== res || taken.has(s.id)) continue;
        const d = Math.hypot(s.x - x, s.y - y);
        if (d < bd) { best = s; bd = d; }
      }
      return best ? { x: best.x + 0.5, y: best.y + 0.5, ok: true } : { x, y, ok: false };   // 건물은 칸 가운데에 선다
    }
    return { x, y, ok: this.canPlace(kind, Math.floor(y), Math.floor(x)) };
  }

  /** 건물 자리를 클릭했다 (keep: Shift를 누른 채면 이어서 더 놓는다). 고른 병사가 없으면 서버가 가까운 쉬는 병사를 고른다. */
  place(x: number, y: number, zoom: number, keep = false) {
    if (typeof this.mode !== 'number') return;
    const kind = this.mode, R = this.R();
    const t = this.placeTarget(kind, x, y, zoom);
    if (kind === R.kinds.PASTURE) {                            // 목장: 누른 동물 자리를 보낸다 (헛간 자리와 울타리는 서버가 고른다)
      const h = this.herdAt(x, y, zoom);
      if (!h) { this.st.say('목장은 말이나 순록 떼를 눌러 지어야 합니다'); return; }
      if (h.n < R.pasture.min_herd) { this.st.say(`${R.wildlife[h.kind].name} 무리가 너무 작습니다 (${R.pasture.min_herd}마리부터)`); return; }
      this.net.send({ t: 'place', kind: BUILD_NAMES_EN[kind], units: this.refs(), x: h.ax, y: h.ay });
      this.ping(h.cx, h.cy, PING.build);
      if (!keep) this.mode = null;
      return;
    }
    if (!t.ok) {
      const res = this.siteRes(kind);
      this.st.say(res >= 0 ? `${josa(R.build_names[kind], '은', '는')} 빈 ${R.site_names[res]} 자리에 지어야 합니다`
        : '여기에는 지을 수 없습니다 (평평한 땅, 다른 건물과 떨어진 곳' + (kind === R.kinds.HARBOR ? ', 바다에 맞닿은 해안)' : ')'));
      return;
    }
    this.net.send({ t: 'place', kind: BUILD_NAMES_EN[kind], units: this.refs(), x: t.x, y: t.y });
    this.ping(t.x, t.y, PING.build);
    if (!keep) this.mode = null;
  }

  canPlace(kind: number, y: number, x: number) {
    const R = this.R(), builds = this.st.builds.values();
    if (kind === R.kinds.HARBOR) return this.rules.canPlaceHarbor(y, x, builds);
    return this.rules.canPlace(y, x, R.build[kind].r, builds);
  }

  /** 이 병종을 만드는 건물 (완성된 내 것). 고른 건물이 그 종류면 그것만. */
  producers(what: TrainKind): BuildRec[] {
    const R = this.R(), want = what === 'warship' ? R.kinds.HARBOR : R.kinds.HALL;
    const sel = this.selB ? this.st.builds.get(this.selB[0]) : null;
    if (sel && sel.kind === want && sel.prog >= 1 && sel.own === this.me) return [sel];
    return [...this.st.builds.values()].filter((b) => b.own === this.me && b.kind === want && b.prog >= 1)
      .sort((a, b) => a.slot - b.slot);
  }

  /** Q 보병 / W 궁수 / E 전함: 고른 건물, 아니면 내 건물들에서 돌아가며 (대기열이 찬 곳은 건너뛴다). */
  train(what: TrainKind) {
    const list = this.producers(what);
    if (!list.length) { this.st.say(what === 'warship' ? '전함을 만들 항구가 없습니다' : '훈련할 거점이 없습니다'); return; }
    const n = list.length, start = (this.turn[what] ?? -1) + 1;
    for (let k = 0; k < n; k++) {
      const b = list[(start + k) % n];
      if (b.qlen >= 5) continue;
      this.turn[what] = (start + k) % n;
      this.net.send({ t: 'train', kind: what, buildings: [[b.slot, b.gen]] });
      return;
    }
    this.st.say('훈련 대기열이 가득 찼습니다');
  }

  stop() { this.net.send({ t: 'stop', units: this.refs() }); }

  setGroup(n: number) {
    this.groups.set(n, new Map(this.sel));
    this.st.say(`${n}번 부대 지정 (${this.sel.size}명)`);
  }

  recallGroup(n: number) {
    const g = this.groups.get(n);
    if (!g) return;
    this.sel = new Map(g);
    this.prune();
  }
}

/** 고를 수 있는 배: 전함, 병사를 태운 나룻배 (빈 나룻배는 항구로 돌아가는 중). */
const pickable = (b: Boat) => b.kind === 1 || (b.kind === 0 && b.cargo > 0);

interface StartSite { id: number; kind: number; x: number; y: number; rich: number; snow?: boolean }
