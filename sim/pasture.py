"""목장 (docs/PASTURE_PLAN.md): 말·순록 떼를 울타리 안에 들여 식량을 낸다.

흐름 (Pastures):
1. 목장을 고르고 동물 떼를 클릭 (place): 누른 자리 가까이의 야생 말·순록과 같은 무리(PASTURE_RULES['herd_r'] 안의 같은 종류)를 정한다.
   떼 가운데 둘레에서 울타리 자리와 모양을 먼저 고르고 (넓고 둥글게, 떼가 많이 들어가게), 헛간(목장 건물)은 울타리 바로 바깥
   오른쪽(동쪽)이나 왼쪽(서쪽)에 붙여 놓는다 (_best_spot). 울타리 안은 모두 동물 자리, 헛간 쪽 기둥 하나는 비워 문처럼.
   가까운 병사들이 헛간을 짓고, 울타리 기둥도 그만큼 둘레를 따라 선다 (화면). 정한 동물들은 이 목장의 몫 (Animal.pen = 헛간 번호).
2. 짓는 동안: 몫인 동물은 짓는 나라의 병사를 보고는 달아나지 않고 (다른 나라 병사·싸움에는 달아난다),
   울타리 안쪽을 거닐며 풀을 뜯는다 (sim/wildlife.py _move가 roam으로 울타리 안 자리를 고른다: 밖에 있으면 걸어 들어온다).
3. 다 지은 순간 울타리 안에 있는 몫인 동물만 목장에 든다 (야생 동물 목록에서 빠지고 마리 수와 자리만 남는다:
   화면은 같은 자리에서 같은 모델을 이어 그린다). 밖에 남은 동물은 야생으로 돌아간다.
4. 생산: 마리마다 PASTURE_RULES['food'] (겨울엔 PASTURE_RULES['winter']배), 봄·여름에 새끼가 는다 (PASTURE_RULES['cap']까지). 식량 한도 +STORE_SITE.
5. 헛간이 무너지면 안의 동물이 야생 무리로 풀려나 달아난다. 짓는 중에 무너지면 몫이 풀린다.
6. 말 목장의 말 꺼내기 (order_ride): 보병·궁수를 고르고 내 말 목장(헛간이나 울타리 안)을 오른쪽 클릭하면 병사마다 말 한 마리씩
   (PASTURE_RULES['keep']마리는 남기고: 새끼를 치게) 문(헛간 쪽 울타리)으로 가서 타고 나온다 → 창기병·기마궁수 (체력 비율은 그대로). 가는 중에 다른 명령을 받으면 그만.
다른 건물은 울타리 안에 지을 수 없다 (World.can_place가 covers를 본다), 새 야생 무리도 울타리 안에는 생기지 않는다.

울타리 모양 (fence_shape):

울타리는 헛간을 가운데 둔 둥그스름한 모양이다. 바탕 반지름부터 방향마다 조금씩 다르다 (자리로 정해지는 부드러운 물결 몇 겹:
완전한 원이 아니라 손으로 둘러친 듯 자연스럽게, 같은 자리면 늘 같은 모양). 그리고 장애물 앞에서 안으로 휜다:
가운데에서 방향마다 바깥으로 나가다가 물·걸을 수 없는 칸, 다른 건물(반지름 + MARGIN), 자원지, 용 둥지를 만나면 그 앞에서 멈춘다.
그 다음 이웃 방향과 고르게 펴되 (들쭉날쭉하지 않게) 막힌 반지름을 넘지 않는다 (장애물에 다시 걸치지 않게).
화면(web/src/game/fence.ts)은 이 방향마다 반지름으로 기둥과 가로대를 칸마다 그린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim import rules as R

DIRS = 64            # 방향 수
STEP = 0.5           # 바깥으로 나가며 보는 간격 (칸)
MARGIN = 3.0         # 다른 건물과의 여유 (칸): 건물 그림은 자리보다 커서 조금 넉넉히
SITE_R = 4.5         # 자원지는 이만큼 비워 둔다 (그 자리에 지을 자원 건물 반지름 + 여유)
LAIR_R = 16.0        # 용 둥지 둘레 (둥지 그림 반지름쯤)
SMOOTH = 2           # 고르게 펼 때 양옆으로 보는 방향 수
MIN_SHARE = 0.5      # 이 비율 넘는 방향이 최소 반지름보다 짧으면 지을 수 없다
WOBBLE = ((2, 0.10), (3, 0.07), (5, 0.04))   # 바탕 모양의 물결: (한 바퀴에 몇 번, 세기). 합쳐 반지름의 약 ±20%
PEN_MARGIN = 2.0     # 다른 목장 울타리와의 여유 (칸)


def fence_shape(world, cy: float, cx: float, radius: float, inner: float = 4.0, skip_building: int = -1):
    """(cy, cx)를 가운데로 한 울타리의 방향마다 반지름 (DIRS개, 칸) 또는 지을 수 없으면 None.
    inner: 이보다 짧은 방향은 '막혔다'로 친다 (헛간 둘레), skip_building: 이 건물은 장애물로 치지 않는다 (자기 헛간)."""
    m, b = world.map, world.builds
    ang = np.arange(DIRS) * (2 * np.pi / DIRS)
    rng = np.random.default_rng([int(round(cx)) & 0xFFFF, int(round(cy)) & 0xFFFF, 77])   # 자리로 정해지는 물결
    base = np.ones(DIRS)
    for k, amp in WOBBLE:
        base += amp * rng.uniform(0.6, 1.0) * np.sin(k * ang + rng.uniform(0, 2 * np.pi))
    lim = radius * base / base.max()                              # 가장 먼 방향이 radius (넘지 않게)
    rs = np.arange(STEP, radius + 1e-6, STEP)
    xs = cx + np.cos(ang)[:, None] * rs[None]                     # (방향, 거리)
    ys = cy + np.sin(ang)[:, None] * rs[None]
    inside = (xs >= 0) & (ys >= 0) & (xs < m.W) & (ys < m.H)
    xi = np.clip(xs.astype(np.int64), 0, m.W - 1)
    yi = np.clip(ys.astype(np.int64), 0, m.H - 1)
    bad = ~inside | ~m.walk_static[yi, xi] | m.water[yi, xi] | m.cliff[yi, xi] | (rs[None] > lim[:, None])   # 바탕 모양 밖도 막힌 것으로
    alive = np.flatnonzero(b.alive[:b.n])
    obst = [(float(b.x[i]), float(b.y[i]), float(b.r[i]) + MARGIN) for i in alive if i != skip_building]
    obst += [(float(s.x), float(s.y), SITE_R) for s in world.sites if s.building < 0]
    obst += [(float(a.hx), float(a.hy), LAIR_R) for a in world.wild.animals.values() if a.unit >= 0]
    for ox, oy, orad in obst:
        if np.hypot(ox - cx, oy - cy) - orad > radius:
            continue
        bad |= np.hypot(xs - ox, ys - oy) < orad
    pens = getattr(world, 'pastures', None)                       # 다른 목장의 울타리 안 (+ 여유)
    if pens is not None and pens.pens:
        bad |= pens.covers(xs.ravel(), ys.ravel(), PEN_MARGIN).reshape(xs.shape)
    first = np.where(bad.any(1), bad.argmax(1), len(rs))           # 방향마다 처음 막힌 자리
    raw = np.where(first > 0, rs[np.maximum(first - 1, 0)], 0.0)   # 막히기 바로 앞까지
    raw[first == len(rs)] = radius
    raw = np.minimum(raw, lim)
    if (raw < inner).mean() > MIN_SHARE or (raw < lim * 0.5).mean() > MIN_SHARE:
        return None
    k = np.ones(2 * SMOOTH + 1) / (2 * SMOOTH + 1)                 # 이웃 방향과 고르게 (둥글게 이어서), 막힌 반지름은 넘지 않는다
    pad = np.concatenate([raw[-SMOOTH:], raw, raw[:SMOOTH]])
    smooth = np.convolve(pad, k, mode='valid')
    out = np.floor(np.minimum(raw, smooth) * 2) / 2                 # 0.5칸 단위 (화면으로 보내기 쉽게, 안쪽으로 내림)
    # 이웃 방향의 점 사이를 잇는 선도 막힌 칸(좁은 물줄기·장애물 귀퉁이)을 지나지 않게: 걸리면 두 끝을 안으로 당긴다
    oxy = np.array([(ox, oy, orad) for ox, oy, orad in obst], float).reshape(-1, 3)

    def blocked(x, y):
        xi_, yi_ = np.clip(x.astype(np.int64), 0, m.W - 1), np.clip(y.astype(np.int64), 0, m.H - 1)
        hit = (x < 0) | (y < 0) | (x >= m.W) | (y >= m.H) | ~m.walk_static[yi_, xi_] | m.water[yi_, xi_] | m.cliff[yi_, xi_]
        if len(oxy):
            hit |= (np.hypot(x[:, None] - oxy[:, 0], y[:, None] - oxy[:, 1]) < oxy[:, 2]).any(1)
        if pens is not None and pens.pens:
            hit |= pens.covers(x, y, PEN_MARGIN)
        return hit

    ts = np.linspace(0, 1, 9)
    for _ in range(int(radius / STEP) * 2):
        px, py = cx + np.cos(ang) * out, cy + np.sin(ang) * out
        nx_, ny_ = np.roll(px, -1), np.roll(py, -1)
        sx = px[:, None] + (nx_ - px)[:, None] * ts[None]
        sy = py[:, None] + (ny_ - py)[:, None] * ts[None]
        seg = blocked(sx.ravel(), sy.ravel()).reshape(DIRS, len(ts)).any(1)
        if not seg.any():
            break
        shrink = seg | np.roll(seg, 1)                              # 막힌 선의 두 끝
        out = np.where(shrink, np.maximum(out - STEP, 0.0), out)
    else:
        return None
    if (out < inner).mean() > MIN_SHARE or (out < lim * 0.5).mean() > MIN_SHARE:
        return None
    return [float(r) for r in out]


def radius_at(radii, ang):
    """방향마다 반지름 사이를 이어 이 각도들의 반지름."""
    n = len(radii)
    t = (np.asarray(ang, float) % (2 * np.pi)) / (2 * np.pi) * n
    i0 = np.floor(t).astype(np.int64) % n
    f = t - np.floor(t)
    r = np.asarray(radii, float)
    return r[i0] * (1 - f) + r[(i0 + 1) % n] * f


@dataclass
class Pen:
    """목장 하나 (헛간 건물 번호 b, 울타리 가운데 cx·cy: 헛간은 울타리 바로 바깥 동·서쪽)."""
    b: int
    gen: int                      # 헛간 세대 (같은 칸에 새 건물이 서면 다른 목장)
    own: int
    kind: int                     # 들이는 동물 (rules.HORSE / REINDEER)
    cx: float
    cy: float
    radii: list
    claim: list = field(default_factory=list)     # 짓는 동안: 이 목장 몫인 야생 동물 번호
    n: int = 0                    # 든 동물 수
    spots: list = field(default_factory=list)     # 든 동물의 자리 (가운데에서, 칸): 화면이 이어 그린다
    breed: float = 0.0            # 새끼가 늘기까지 (0~1)
    done: bool = False


class Pastures:
    def __init__(self, world):
        self.w = world
        self.pens: dict[int, Pen] = {}
        self.version = 0                          # 바뀔 때마다 +1 (서버가 화면에 다시 보낸다)
        self.riders: dict[int, tuple] = {}        # 말을 꺼내러 가는 병사 → (헛간 번호, 병사 세대, 길 슬롯)

    # ------------------------------------------------------------- 자리
    def covers(self, x, y, margin: float = 0.0) -> np.ndarray:
        """이 점들이 어느 목장 울타리 안 (+ margin)에 드나."""
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        hit = np.zeros(x.shape, bool)
        for p in self.pens.values():
            dx, dy = x - p.cx, y - p.cy
            d = np.hypot(dx, dy)
            near = d < max(p.radii) + margin
            if near.any():
                hit[near] |= d[near] < radius_at(p.radii, np.arctan2(dy[near], dx[near])) + margin
        return hit

    def inside(self, p: Pen, x: float, y: float, shrink: float = 0.0) -> bool:
        d = float(np.hypot(x - p.cx, y - p.cy))
        return d < float(radius_at(p.radii, np.arctan2(y - p.cy, x - p.cx))) - shrink

    def roam(self, a, rng):
        """몫인 동물이 거닐 다음 자리: 울타리 안쪽 (헛간 둘레는 비우고). 몫이 아니면 None."""
        p = self.pens.get(a.pen) if a.pen >= 0 else None
        if p is None:
            return None
        ang = rng.uniform(0, 2 * np.pi)
        r = float(radius_at(p.radii, ang)) * rng.uniform(0.1, 0.8)
        return p.cx + np.cos(ang) * r, p.cy + np.sin(ang) * r

    def herd_at(self, y: float, x: float, r: float | None = None) -> list:
        """(y, x) 가까이 (PASTURE_RULES['find_r'] 안)의 들일 수 있는 야생 동물과 그 무리 (같은 종류, herd_r 안, 같은 땅, 다른 목장 몫이 아닌 것)."""
        from sim.wildlife import HELD, TAMING
        P = R.PASTURE_RULES
        w = self.w
        r = P['find_r'] if r is None else r
        free = [a for a in w.wild.animals.values() if a.kind in P['food'] and a.unit < 0 and a.pen < 0 and a.mode not in (HELD, TAMING)]
        if not free:
            return []
        a0 = min(free, key=lambda a: np.hypot(a.x - x, a.y - y))
        if np.hypot(a0.x - x, a0.y - y) > r:
            return []
        comp = w.map.comp
        c0 = comp[int(a0.y), int(a0.x)]
        herd = [a for a in free if a.kind == a0.kind and np.hypot(a.x - a0.x, a.y - a0.y) < P['herd_r'] and comp[int(a.y), int(a.x)] == c0]
        herd.sort(key=lambda a: np.hypot(a.x - a0.x, a.y - a0.y))
        return herd

    def _best_spot(self, herd):
        """울타리 자리와 모양을 먼저 (떼 가운데 둘레에서 넓고 둥글게, 떼가 많이 들어가게), 그 다음 헛간을 울타리 바로 바깥 동·서쪽에.
        반환 (울타리 가운데 y, x, 반지름들, 헛간 y, 헛간 x) 또는 None."""
        P, w = R.PASTURE_RULES, self.w
        hx, hy = float(np.mean([a.x for a in herd])), float(np.mean([a.y for a in herd]))
        cands = []
        span = P['search']
        for dy in np.arange(-span, span + 0.1, 2.0):
            for dx in np.arange(-span, span + 0.1, 2.0):
                if dx * dx + dy * dy > span * span:
                    continue
                cy, cx = int(hy + dy) + 0.5, int(hx + dx) + 0.5
                radii = fence_shape(w, cy, cx, P['radius'], inner=4.0)
                if radii is None:
                    continue
                rr = np.asarray(radii)
                if rr.min() < 4.0 or rr.mean() < P['radius'] * P['min_fill']:   # 너무 작거나 깊게 파인 울타리는 안 된다
                    continue
                got = sum(1 for a in herd if self._in(cx, cy, rr, a.x, a.y, 1.0))
                score = (float((rr ** 2).mean()) / P['radius'] ** 2 * 10 - float(rr.std()) / P['radius'] * 20
                         + got * 1.5 - float(np.hypot(dx, dy)) * 0.15)
                cands.append((score, cy, cx, radii))
        cands.sort(key=lambda c: -c[0])
        for _, cy, cx, radii in cands[:12]:                       # 좋은 울타리부터: 헛간을 붙일 자리가 있는 것
            shed = self._shed_spot(cy, cx, radii)
            if shed is not None:
                return cy, cx, radii, shed[0], shed[1]
        return None

    def _shed_spot(self, cy, cx, radii):
        """울타리 바로 바깥 오른쪽(동) 또는 왼쪽(서)에 헛간 자리 (조금 위아래로도 본다). (y, x) 정수 칸 또는 None."""
        w = self.w
        r0 = R.BUILD_STATS[R.PASTURE]['r']
        rr = np.asarray(radii)
        ring = np.linspace(0, 2 * np.pi, 12, endpoint=False)
        for base in (0.0, np.pi):
            for off in (0.0, 0.26, -0.26, 0.52, -0.52):
                a = base + off
                d = float(radius_at(rr, a)) + r0 + 1.0
                y, x = int(cy + np.sin(a) * d), int(cx + np.cos(a) * d)
                if not w.can_place(y, x, r0):
                    continue
                px, py = x + 0.5 + np.cos(ring) * (r0 + 0.5), y + 0.5 + np.sin(ring) * (r0 + 0.5)   # 헛간 둘레가 울타리 안에 들지 않게
                if any(self._in(cx, cy, rr, qx, qy) for qx, qy in zip(px, py)):
                    continue
                return y, x
        return None

    @staticmethod
    def _in(cx, cy, radii, x, y, shrink=0.0) -> bool:
        return float(np.hypot(x - cx, y - cy)) < float(radius_at(radii, np.arctan2(y - cy, x - cx))) - shrink

    def place(self, nid: int, ids, y: float, x: float, quiet: bool = False) -> int:
        """목장을 고르고 (y, x)를 눌렀다: 그 떼에 목장을 짓는다. 반환: 헛간 건물 번호 (못 지으면 -1)."""
        P, w = R.PASTURE_RULES, self.w
        herd = self.herd_at(y, x)
        if not herd:
            if not quiet:
                w.say('목장은 말이나 순록 떼를 눌러 지어야 합니다', to=nid)
            return -1
        name = R.WILDLIFE[herd[0].kind]['name']
        comp, u = w.map.comp, w.units
        ids = np.asarray(ids, np.int64)
        lands = {int(comp[int(u.y[i]), int(u.x[i])]) for i in ids} if len(ids) else set()
        dst = int(comp[int(herd[0].y), int(herd[0].x)])
        if lands and dst not in lands and not any(w.fleet.harbors_on(nid, c) for c in lands):   # 짓는 병사가 갈 수 없다 (몫을 묶어 두지 않게)
            if not quiet:
                w.say(f'바다 건너 {name} 떼에 지으려면 병사들이 있는 땅에 항구가 있어야 합니다', to=nid)
            return -1
        if len(herd) < P['min_herd']:
            if not quiet:
                w.say(f'{name} 무리가 너무 작습니다 ({P["min_herd"]}마리부터)', to=nid)
            return -1
        spot = self._best_spot(herd)
        if spot is None:
            if not quiet:
                w.say('여기에는 울타리를 두를 자리가 없습니다 (물·건물·자원지에서 떨어진 넓은 땅)', to=nid)
            return -1
        fy, fx, radii, sy, sx = spot
        b = w.place_building(nid, R.PASTURE, sy, sx, ids, quiet=quiet)
        if b < 0:
            return -1
        p = Pen(b, int(w.builds.gen[b]), nid, herd[0].kind, fx, fy, radii)
        self.pens[b] = p
        for a in herd[:P['cap']]:
            a.pen = b
            p.claim.append(a.id)
            self._send_in(a)
        self.version += 1
        if not quiet:
            w.say(f'{name} 목장을 짓습니다 ({len(p.claim)}마리: 다 지을 때 울타리 안에 있는 만큼 들어갑니다)', to=nid)
        return b

    def pen_at(self, y: float, x: float):
        """(y, x)가 헛간이거나 울타리 안인 목장 (없으면 None)."""
        b = self.w.building_at(y, x)
        if b >= 0 and b in self.pens:
            return self.pens[b]
        for p in self.pens.values():
            if self.inside(p, x, y):
                return p
        return None

    def gate(self, p: Pen):
        """문 자리 (헛간 쪽 울타리 바로 안): (y, x)."""
        b = self.w.builds
        a = float(np.arctan2(b.y[p.b] - p.cy, b.x[p.b] - p.cx))
        r = max(float(radius_at(p.radii, a)) - 1.5, 0.0)
        return p.cy + np.sin(a) * r, p.cx + np.cos(a) * r

    def spare(self, p: Pen) -> int:
        """꺼내 탈 수 있는 말 (keep마리는 남기고, 꺼내러 가는 중인 몫은 빼고)."""
        return p.n - R.PASTURE_RULES['keep'] - sum(1 for v in self.riders.values() if v[0] == p.b)

    def order_ride(self, nid: int, ids, b: int, quiet: bool = False) -> int:
        """보병·궁수가 내 말 목장에서 말을 꺼내 탄다 (병사마다 한 마리, 있는 만큼). 반환: 보낸 병사 수."""
        w, u = self.w, self.w.units
        p = self.pens.get(b)
        if p is None or p.own != nid or not p.done:
            return 0
        info = R.WILDLIFE[p.kind]
        mounts = info.get('mounts', {})
        if not mounts:
            if not quiet:
                w.say(f'{R.josa(info["name"], "은", "는")} 탈 수 없습니다', to=nid)
            return 0
        ids = [int(i) for i in np.atleast_1d(ids) if u.alive[i] and u.own[i] == nid and int(u.kind[i]) in mounts]
        keep = R.PASTURE_RULES['keep']
        left = self.spare(p)
        if not ids or left <= 0:
            if not quiet:
                w.say(f'목장의 {info["name"]}은 {keep}마리는 남깁니다 (새끼를 치게)' if left <= 0 else '보병·궁수만 말을 탈 수 있습니다', to=nid)
            return 0
        gy, gx = self.gate(p)
        ids.sort(key=lambda i: np.hypot(u.x[i] - gx, u.y[i] - gy))
        ids = np.array(ids[:left], np.int64)
        for i in ids:
            self.riders.pop(int(i), None)
        if not w.order_move(ids, gy, gx):
            return 0
        for i in ids:
            self.riders[int(i)] = (b, int(u.gen[i]), int(u.slot[i]))
        if not quiet:
            w.say(f'목장에서 {info["name"]} {len(ids)}마리를 꺼내 타러 갑니다', to=nid)
        return len(ids)

    def _ride(self) -> None:
        """말을 꺼내러 간 병사: 문에 닿으면 탄다. 다른 명령을 받았거나 죽었거나 목장이 없어졌으면 그만."""
        from sim.entities import IDLE, MOVE
        w, u = self.w, self.w.units
        for i, (b, gen, slot) in list(self.riders.items()):
            p = self.pens.get(b)
            if p is None or not u.alive[i] or int(u.gen[i]) != gen or u.aboard[i]:
                del self.riders[i]
                continue
            st = int(u.state[i])
            if st == MOVE and int(u.slot[i]) == slot:
                continue                                   # 아직 가는 중
            gy, gx = self.gate(p)
            if st not in (IDLE, MOVE) or (st == MOVE and int(u.slot[i]) != slot) or np.hypot(u.x[i] - gx, u.y[i] - gy) > 5.0:   # 여럿이면 문 앞에 퍼져 선다
                del self.riders[i]                         # 다른 명령을 받았거나 닿지 못했다
                continue
            del self.riders[i]
            if p.n <= R.PASTURE_RULES['keep']:
                continue
            old = int(u.kind[i])
            new = R.WILDLIFE[p.kind]['mounts'][old]
            ratio = float(u.hp[i]) / R.UNIT_STATS[old]['hp']
            u.kind[i] = new
            u.hp[i] = ratio * R.UNIT_STATS[new]['hp']
            u.cd[i] = 0.0
            k = int(np.argmin([np.hypot(p.cx + dx - gx, p.cy + dy - gy) for dx, dy in p.spots])) if p.spots else -1
            if k >= 0:
                p.spots.pop(k)                             # 문에 가장 가까운 말이 나간다
            p.n -= 1
            self.version += 1
            w.say(f'목장의 {R.josa(R.WILDLIFE[p.kind]["name"], "을", "를")} 탔습니다: '
                  f'{R.josa(R.UNIT_NAMES[old], "이", "가")} {R.josa(R.UNIT_NAMES[new], "이", "가")} 되었습니다', to=p.own)

    def _send_in(self, a) -> None:
        """몫인 동물을 울타리 안쪽 자리로 걸어가게 한다."""
        from sim.wildlife import WALK
        t = self.roam(a, self.w.wild.rng)
        if t is not None:
            a.hx, a.hy = t
            a.tx, a.ty = t
            a.mode, a.t = WALK, 8.0

    # ------------------------------------------------------------- 진행
    def update(self, dt: float) -> None:
        w, b = self.w, self.w.builds
        P = R.PASTURE_RULES
        if self.riders:
            self._ride()
        for k in list(self.pens):
            p = self.pens[k]
            if not b.alive[p.b] or int(b.gen[p.b]) != p.gen or b.kind[p.b] != R.PASTURE:
                self._lost(p)
                continue
            if not p.done:
                if b.prog[p.b] >= 1:
                    self._fill(p)
                continue
            if 2 <= p.n < P['cap']:                       # 봄·여름에 새끼 (둘 이상일 때)
                sw = w.season_w
                p.breed += dt * float(sw[0] + sw[1]) / P['breed']
                if p.breed >= 1.0:
                    p.breed = 0.0
                    p.n += 1
                    p.spots.append(self._spot_in(p))
                    self.version += 1

    def _spot_in(self, p: Pen):
        rng = self.w.wild.rng
        ang = rng.uniform(0, 2 * np.pi)
        r = float(radius_at(p.radii, ang)) * rng.uniform(0.1, 0.75)
        return (round(float(np.cos(ang) * r), 2), round(float(np.sin(ang) * r), 2))

    def _fill(self, p: Pen) -> None:
        """다 지었다: 울타리 안의 몫인 동물이 목장에 든다, 밖의 것은 야생으로."""
        w = self.w
        wild = w.wild
        name = R.WILDLIFE[p.kind]['name']
        for aid in p.claim:
            a = wild.animals.get(aid)
            if a is None or a.pen != p.b:
                continue
            if self.inside(p, a.x, a.y, 0.5) and p.n < R.PASTURE_RULES['cap']:
                p.n += 1
                p.spots.append((round(a.x - p.cx, 2), round(a.y - p.cy, 2)))
                del wild.animals[aid]
            else:
                a.pen = -1
                a.hx, a.hy = a.x, a.y
        p.claim = []
        p.done = True
        self.version += 1
        w.say(f'{name} 목장 완성 ({p.n}마리)' if p.n else f'{name} 목장 완성 (울타리 안에 든 {name}이 없습니다)', to=p.own)

    def _lost(self, p: Pen) -> None:
        """헛간이 무너졌다: 몫은 풀리고, 든 동물은 야생 무리로 달아난다."""
        w = self.w
        wild = w.wild
        for aid in p.claim:
            a = wild.animals.get(aid)
            if a is not None and a.pen == p.b:
                a.pen = -1
                a.hx, a.hy = a.x, a.y
        if p.n:
            from sim.wildlife import Animal
            for dx, dy in p.spots[:p.n]:
                an = Animal(wild._next, p.kind, float(p.cx + dx), float(p.cy + dy), wild.rng)
                wild._next += 1
                wild.animals[an.id] = an
                wild._flee(an, p.cx, p.cy)               # 헛간에서 멀어지게
        del self.pens[p.b]
        self.version += 1
        if p.n and p.own < len(w.nations) and p.done:
            w.say(f'목장이 무너져 {R.WILDLIFE[p.kind]["name"]} {p.n}마리가 달아났습니다', to=p.own)

    def food(self, nid: int, season_w) -> float:
        """이 나라 목장들이 1초에 내는 식량."""
        P = R.PASTURE_RULES
        tot = 0.0
        for p in self.pens.values():
            if p.own == nid and p.done and p.n:
                f = 1.0 - float(season_w[3]) * (1.0 - P['winter'][p.kind])
                tot += P['food'][p.kind] * p.n * f
        return tot

    def owner_calm(self, a) -> int:
        """이 동물이 놀라지 않는 나라 (몫인 목장을 짓는 나라), 없으면 -1."""
        p = self.pens.get(a.pen) if a.pen >= 0 else None
        return p.own if p is not None else -1
