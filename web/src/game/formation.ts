// 진형 자리 계산 (미리보기와 서버로 보내는 자리가 같게, 여기 한 곳에서). 서버는 받은 자리를 걸을 수 있는 칸으로 맞춰
// 병사마다 제 자리로 보낸다 (sim/world.py order_formation).
// - 선 (오른쪽 드래그로 그은 직선·곡선): 근접 병사가 선 위에, 원거리 병사는 그 뒤에. 줄마다 선 처음부터 끝까지 고르게 퍼진다.
//   한 줄에 다 서면 간격이 SPACING보다 좁아질 만큼 많으면 여러 줄.
//   정면은 병사들이 지금 있는 쪽의 반대편 (적 쪽으로 선을 긋는다).
// - 닫힌 곡선 (끝이 시작 가까이): 둘레 방어선. 정면은 바깥, 원거리는 안쪽.
// PC는 오른쪽 드래그 (A 다음 왼쪽 드래그는 공격 이동), 모바일은 진형 그리기를 켜고 한 손가락 끌기.
// 나는 병사 (용기사)는 진형에 서지 않고 진형 가운데로 간다.

export interface FUnit { slot: number; gen: number; kind: number; x: number; y: number }
/** role: 0 근접 (앞줄), 1 원거리 (뒷줄), 2 나는 병사 (진형 가운데로). */
export interface Spot { slot: number; gen: number; x: number; y: number; role: number }
type P = [number, number];

export const SPACING = 2.0;      // 옆·앞뒤 병사와의 가장 좁은 간격 (칸): 서로 밀어내는 거리 (1.48칸, sim/kernels/combat.py)보다 넉넉히
const GAP = 2.0;                 // 근접 줄과 원거리 줄 사이

const roleOf = (R: any, kind: number) => (R.unit_fly?.[kind] ? 2 : R.unit_ranged?.[kind] ? 1 : 0);

/** 꺾은선의 길이 누적. */
function cumul(pts: P[]): number[] {
  const c = [0];
  for (let i = 1; i < pts.length; i++) c.push(c[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return c;
}

/** 꺾은선 위 길이 a의 자리와 진행 방향 (단위). */
function at(pts: P[], cum: number[], a: number): [number, number, number, number] {
  const L = cum[cum.length - 1];
  a = Math.min(Math.max(a, 0), L);
  let i = 1;
  while (i < cum.length - 1 && cum[i] < a) i++;
  const seg = Math.max(cum[i] - cum[i - 1], 1e-9), t = (a - cum[i - 1]) / seg;
  const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, (x1 - x0) / seg, (y1 - y0) / seg];
}

/** 너무 촘촘한 점은 걸러 낸다 (마우스가 그린 선). */
function clean(pts: P[], step = 0.4): P[] {
  const out: P[] = [];
  for (const p of pts) if (!out.length || Math.hypot(p[0] - out[out.length - 1][0], p[1] - out[out.length - 1][1]) >= step) out.push(p);
  if (pts.length && out.length && out[out.length - 1] !== pts[pts.length - 1] && pts.length > 1) out.push(pts[pts.length - 1]);
  return out;
}

const centroid = (us: { x: number; y: number }[]): P => us.length
  ? [us.reduce((s, u) => s + u.x, 0) / us.length, us.reduce((s, u) => s + u.y, 0) / us.length] : [0, 0];

/** 선 (pts)을 따라 진형 자리. closed: 닫힌 곡선 (둘레 방어선). front: 정면 방향을 정해 줄 때, 없으면 병사들 반대편 (닫히면 바깥).
 *  반환은 선을 따라가는 차례 (서버가 가까운 자리끼리 토막으로 묶어 길을 찾는다). */
export function layout(R: any, units: FUnit[], raw: P[], closed: boolean, front?: P): Spot[] {
  if (!units.length || !raw.length) return [];
  let pts = clean(raw);
  if (closed && pts.length >= 3) pts = [...pts, pts[0]];
  if (pts.length < 2) pts = [raw[0], [raw[0][0] + 1e-3, raw[0][1]]];
  const cum = cumul(pts), L = cum[cum.length - 1];
  const C = centroid(units);
  const melee = units.filter((u) => roleOf(R, u.kind) === 0), ranged = units.filter((u) => roleOf(R, u.kind) === 1);
  const fly = units.filter((u) => roleOf(R, u.kind) === 2);
  // 정면 (선의 법선 쪽 부호)
  let sign = 1;
  if (closed) {                                                   // 바깥: 법선이 곡선 가운데에서 멀어지는 쪽
    const pc = centroid(pts.map(([x, y]) => ({ x, y })));
    let s = 0;
    for (let k = 0; k < 24; k++) { const [x, y, tx, ty] = at(pts, cum, (k + 0.5) / 24 * L); s += (-ty) * (x - pc[0]) + tx * (y - pc[1]); }
    sign = s >= 0 ? 1 : -1;
  } else {
    const [mx, my, tx, ty] = at(pts, cum, L / 2);
    const dir = front ?? [mx - C[0], my - C[1]];
    sign = (-ty) * dir[0] + tx * dir[1] >= 0 ? 1 : -1;
  }
  const out: (Spot & { a: number })[] = [];
  const place = (list: FUnit[], base: number, role: number) => {   // 한 역할: 줄마다 cap명, 첫 줄이 base만큼 (뒤로 음수) 떨어져
    if (!list.length) return 0;
    const cap = closed ? Math.max(1, Math.floor(L / SPACING)) : Math.max(1, Math.floor(L / SPACING + 1e-6) + 1);
    const ranks = Math.ceil(list.length / cap);
    // 선을 따라 정렬: 열린 선은 선 방향으로, 닫힌 곡선은 가운데를 도는 각도로 (자리도 같은 차례: 서로 엇갈리지 않게)
    const [fx, fy] = pts[0], [lx, ly] = pts[pts.length - 1];
    const dl = Math.hypot(lx - fx, ly - fy) || 1;
    const pc = centroid(pts.map(([x, y]) => ({ x, y })));
    const key = (u: FUnit) => closed ? Math.atan2(u.y - pc[1], u.x - pc[0]) : ((u.x - fx) * (lx - fx) + (u.y - fy) * (ly - fy)) / dl;
    const sorted = [...list].sort((p, q) => key(p) - key(q));
    let k = 0;
    for (let r = 0; r < ranks; r++) {
      const m = Math.min(cap, sorted.length - k), off = base - r * SPACING;
      const spots: [number, number, number][] = [];
      for (let j = 0; j < m; j++) {
        const a = closed ? (j + 0.5) * L / m : m === 1 ? L / 2 : j * L / (m - 1);   // 그은 선 처음부터 끝까지 고르게 (닫힌 곡선은 한 바퀴 고르게)
        const [x, y, tx, ty] = at(pts, cum, a);
        spots.push([x + (-ty) * sign * off, y + tx * sign * off, a]);
      }
      if (closed) spots.sort((p, q) => Math.atan2(p[1] - pc[1], p[0] - pc[0]) - Math.atan2(q[1] - pc[1], q[0] - pc[0]));
      for (const [x, y, a] of spots) { const u = sorted[k++]; out.push({ slot: u.slot, gen: u.gen, x, y, role, a }); }
    }
    return ranks;
  };
  const mr = place(melee, 0, 0);
  place(ranged, mr ? -((mr - 1) * SPACING + GAP) : 0, 1);
  out.sort((p, q) => p.a - q.a);
  const mid = centroid(out.length ? out : units);
  for (const u of fly) out.push({ slot: u.slot, gen: u.gen, x: mid[0], y: mid[1], role: 2, a: L });
  return out.map(({ slot, gen, x, y, role }) => ({ slot, gen, x, y, role }));
}

/** 닫혔나: 길이가 8칸 넘고 끝이 시작 가까이 (2.5칸이나 길이의 15% 안). */
export function isClosed(pts: P[]): boolean {
  if (pts.length < 4) return false;
  const L = cumul(pts).pop()!;
  const [x0, y0] = pts[0], [x1, y1] = pts[pts.length - 1];
  return L > 8 && Math.hypot(x1 - x0, y1 - y0) < Math.max(2.5, L * 0.15);
}

/** 선 길이 (칸). */
export const pathLength = (pts: P[]) => (pts.length ? cumul(pts).pop()! : 0);
