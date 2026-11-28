"""배: 나룻배(병사를 실어 나름)와 전함(배끼리 싸움).

나룻배 (바다 건너로 명령받은 병사들은 알아서 배를 타고 건넌다)
  1. 병사들이 있는 땅의 내 항구 중 (걸어가는 거리 + 바닷길)이 가장 짧은 항구로 모두 모인다.
     그 땅에 항구가 없으면 건널 수 없다 (2: 항구 짓기).
  2. 항구 앞에 나룻배 한 척이 대어 있고, 도착한 병사가 한 명씩 차례로 탄다.
     한 척(BOAT_CAPACITY명)이 차면 앞바다로 조금 나가 기다리고, 다음 배가 항구에 댄다.
  3. 모두 타면 (또는 오던 병사가 한동안 아무도 안 오면) 모든 배가 함께 출발해 내릴 곳 둘레에 내리고,
     원래 명령(이동/공격/건설)을 이어서 한다. 다 내려 준 나룻배는 항구로 돌아간다.
- 바다 위에서 적 전함에 맞아 가라앉으면 탄 병사도 잃는다.
- 병사를 태운 나룻배는 골라서 다시 보낼 수 있다 (order_ferries): 물 → 그 자리로 가서 기다림,
  땅 → 그 땅의 가까운 해안에 내려 주고 병사들은 찍은 곳으로 걸어간다.

배끼리 겹치지 않게: 배는 '길 위의 자리'(by, bx)와 '비켜난 거리'(oy, ox)를 따로 갖고, 가까운 배끼리 서로 밀어낸다
(비켜난 자리가 배가 다닐 수 있는 물일 때만). 화면과 규칙은 둘을 더한 자리(y, x)를 쓴다.

전함
- 항구에서 만든다. 선택해서 물 위로 움직인다 (오른쪽 클릭: 물 → 이동, 적 배 → 쫓아가 공격,
  해안의 적 병사·건물 → 사거리 안까지 다가가 포격).
- 사거리 안의 다른 나라 나룻배와 전함을 자동으로 쏜다. 적 배가 없으면 해안의 적 병사·건물을 포격한다 (rules.SHORE).
- 포탄은 날아간다: 쏜 뒤 WARSHIP_FLY초 지나 떨어진 자리에서 맞는다 (화면의 포탄과 맞는 순간이 같게).
  배는 그대로 맞고, 노린 병사는 그새 WARSHIP_HIT_R칸 밖으로 달아났으면 빗나간다 (둘레 병사는 떨어진 자리 기준).
- 거리를 둔다: 적 전함이나 포격하는 목표가 사거리 × keep_min보다 가까우면 사거리 × keep_lo~keep_hi 떨어진 바다로
  물러나며 계속 쏜다 (이동 명령을 받은 동안은 빼고). 포격하러 갈 때도 그 거리까지만 다가간다.
- 땅의 원거리 병사·망루·화염탑도 칠 것이 없으면 사거리 안의 적 배를 쏜다 (shore_fire, 화염탑은 sim/firetower.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim import rules as R
from sim.kernels.flow import INF, sea_path
from sim.entities import AMOVE, ATTACK, IDLE, MOVE

FERRY, WARSHIP = 'ferry', 'warship'
BOARD_GAP = 0.25           # 항구에서 한 명이 타는 데 걸리는 시간 (초)
BOARD_NEAR = 7.0           # 모이는 곳에서 이만큼 안에 온 병사가 탄다 (칸)
SIZE = {'ferry': (3.9, 5.5), 'warship': (5.0, 8.3)}   # 화면에 그려지는 배 크기 (세로, 가로 칸): 이 사각형끼리 겹치지 않게
WAIT_LIMIT = 40.0          # 오던 병사가 이만큼 아무도 안 오면 탄 병사만 데리고 출발 (초)


@dataclass
class Boat:
    kind: str
    own: int
    y: float
    x: float
    hp: float
    state: str = 'idle'            # 나룻배: load(항구에서 태우는 중) / ahead(앞바다로) / anchor(기다림) / cross / return
                                   # 전함: idle / move / hunt
    home: int = -1                 # 나룻배가 출발한 항구
    path: np.ndarray | None = None  # 지금 따라가는 길 (N, 2) [y, x]
    pos: float = 0.0
    cargo: list = field(default_factory=list)
    assigned: list = field(default_factory=list)
    slot: int = -1                 # 타는 곳으로 걸어가는 병사들의 거리 지도
    embark: tuple = (0, 0)         # 타는 곳 (땅 칸)
    route: np.ndarray | None = None
    land: tuple = (0, 0)           # 내릴 곳 (땅 칸)
    then: tuple = ()               # 내린 뒤 할 일
    stop: float = 0.0              # ahead: 앞바다에서 멈출 길 위치
    wait_t: float = 0.0
    dir: float = 1.0               # 보는 방향 (왼쪽 -1 / 오른쪽 1)
    cd: float = 0.0
    target: object = None          # 전함이 쫓는 배
    tu: int = -1                   # 전함이 포격하라고 받은 땅의 적 병사 (칸, 세대 tg) / 건물 (tb)
    tg: int = 0
    tb: int = -1
    aim: tuple = ()                # 마지막으로 포격한 땅의 자리 (x, y, 반지름)와 시각 (거리 두기)
    aim_t: float = -1e9
    repath: float = 0.0
    backing: bool = False          # 거리를 두려고 물러나는 중
    alive: bool = True
    id: int = 0                    # 배 번호 (화면이 같은 배를 계속 따라가게)
    by: float = -1.0               # 길 위의 자리 (y, x는 여기에 비켜난 거리를 더한 것)
    bx: float = -1.0
    oy: float = 0.0                # 다른 배를 비켜난 거리
    ox: float = 0.0

    def __post_init__(self):
        self.by, self.bx = self.y, self.x

    @property
    def maxhp(self):
        return R.WARSHIP_HP if self.kind == WARSHIP else R.FERRY_HP


@dataclass
class Convoy:
    """한 번의 바다 건너기: 항구에 모이는 병사들과 그들을 태울 나룻배들."""
    own: int
    harbor: int                    # 모이는 항구 (건물 번호)
    gather: tuple                  # 병사들이 모이는 땅 칸 (항구 앞 물가)
    route: np.ndarray              # 항구 앞 물 칸 → 내릴 물 칸
    land: tuple                    # 내릴 곳 (땅 칸)
    then: tuple                    # 내린 뒤 할 일
    slot: int                      # 항구로 걸어가는 병사들의 거리 지도
    assigned: list                 # 아직 안 탄 병사
    planned: int                   # 처음 병사 수로 계산한 배 수 (앞바다 자리 나누기)
    ferries: list = field(default_factory=list)
    board_cd: float = 0.0
    idle_t: float = 0.0            # 마지막으로 누가 탄 뒤 지난 시간
    done: bool = False


def _neighbors(mask):
    """mask의 4방향 이웃인 칸."""
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def _ferry_eval(walk, cost, nav, ty, tx, here, land, landing, ports, n, speed):
    """(보조 스레드) 같은 땅에서 배로 가는 시간과 걸어가는 시간 (초): (배, 걷기) 또는 배로 갈 수 없으면 None.
    배 = 항구까지 걷기 + 한 명씩 타기 + 바닷길 + 내린 곳에서 목표까지 걷기 + 여유. 걷기는 길찾기(_flow, GIL을 놓는다) 두 번:
    목표에서 (병사 자리, 내릴 곳)까지, 병사 자리에서 모든 항구 모이는 곳까지 (걷는 비용은 오가는 쪽이 같다).
    ports: [(모이는 곳 (y, x), 항구 앞 물 (y, x))]. 판의 상태는 읽지 않는다 (넘겨받은 것만: 걸음과 함께 돌아도 된다)."""
    from sim.kernels.flow import _flow
    H, W = walk.shape
    nn = walk.size
    out = np.empty((H, W), np.float32)

    def costs(sy, sx, pts):
        _flow(walk, cost, sy, sx, np.array([p[0] for p in pts], np.int64), np.array([p[1] for p in pts], np.int64), out,
              np.zeros(nn, np.uint8), np.empty(nn * 3, np.float32), np.empty(nn * 3, np.int64))
        return [float(out[p]) for p in pts]

    walk_cost, after = costs(ty, tx, [here, land])
    if walk_cost >= INF or after >= INF:
        return None
    to_port = costs(here[0], here[1], [g for g, _ in ports])
    best = None
    for (g, d), c in zip(ports, to_port):
        if c >= INF:
            continue
        goal = np.zeros(nav.shape, np.bool_)
        goal[d[0], d[1]] = True
        route = sea_path(nav, goal & nav, landing[0], landing[1], 4 * max(H, W))
        if not len(route):
            continue
        t = c / speed + n * BOARD_GAP + len(route) / R.FERRY_SPEED + after / speed + 6.0
        best = t if best is None else min(best, t)
    return None if best is None else (best, walk_cost / speed)


class Fleet:
    def __init__(self, world):
        self.w = world
        self._shores: dict = {}                    # (땅 모양 판, 땅 번호) → 그 땅의 해안 물 칸 (땅 모양이 바뀌면 버린다)
        self._seas: dict = {}                      # (땅 모양 판, 시작, 목표) → 바닷길
        self.boats: list[Boat] = []
        self.convoys: list[Convoy] = []
        self.docks: dict[int, tuple] = {}
        self._next_id = 1
        self.want_harbor: dict[int, tuple] = {}     # 나라 → 항구가 있어야 할 해안 (나룻배를 못 띄웠을 때, AI가 참고)
        self.shells: list = []     # 날아가는 포탄: (맞는 시각, 쏜 나라, 'u'/'b'/'s', 목표, 병사 gen, 떨어질 x, y)
        self.log = {'ferries': 0, 'landed': 0, 'sunk_ferries': 0, 'sunk_warships': 0, 'drowned': 0}   # 기록 (시험용)

    # ------------------------------------------------------------- 항구
    def can_place_harbor(self, y: int, x: int) -> bool:
        """바다(호수 말고)에 맞닿은 해안 (절벽 아님, 땅이 반쯤은 있고, 다른 건물과 떨어진 곳)."""
        w, m = self.w, self.w.map
        r = R.BUILD_STATS[R.HARBOR]['r']
        if not (r + 3 <= y < m.H - r - 3 and r + 3 <= x < m.W - r - 3) or not m.land[y, x]:
            return False
        win = (slice(y - r - 2, y + r + 3), slice(x - r - 2, x + r + 3))
        if not m.ocean[win].any() or m.cliff[y - 2:y + 3, x - 2:x + 3].any():   # 호수가 아니라 바다에 맞닿아야
            return False
        if m.land[y - r:y + r + 1, x - r:x + r + 1].mean() < 0.4:
            return False
        b = w.builds
        alive = b.alive[:b.n]
        if alive.any():
            d = np.hypot(b.x[:b.n][alive] - x, b.y[:b.n][alive] - y) - b.r[:b.n][alive]
            if d.min() < r + 2:
                return False
        return True

    def dock_of(self, h: int):
        """항구 앞 물 칸 (전함이 생기는 곳)."""
        if h in self.docks:
            return self.docks[h]
        m, b = self.w.map, self.w.builds
        y, x, r = int(b.y[h]), int(b.x[h]), 9
        y0, x0 = max(y - r, 0), max(x - r, 0)
        sub = m.nav[y0:y + r + 1, x0:x + r + 1] & m.ocean[y0:y + r + 1, x0:x + r + 1]
        ys, xs = np.nonzero(sub)
        if len(ys) == 0:
            return None
        k = np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2)
        self.docks[h] = (int(ys[k] + y0), int(xs[k] + x0))
        return self.docks[h]

    def launch_warship(self, own: int, h: int) -> None:
        d = self.dock_of(h)
        if d is not None:
            self._add(Boat(WARSHIP, own, d[0] + 0.5, d[1] + 0.5, R.WARSHIP_HP))

    def _add(self, boat: Boat) -> Boat:
        boat.id = self._next_id
        self._next_id += 1
        self.boats.append(boat)
        return boat

    def boat_by_id(self, bid):
        return next((b for b in self.boats if b.id == bid and b.alive), None)

    def has_harbor(self, own) -> bool:
        return len(self.w.building_ids(own, R.HARBOR, done=True)) > 0

    def harbors_on(self, own, comp_id) -> list[int]:
        """comp_id 땅 위의 완성된 내 항구들."""
        w, m, b = self.w, self.w.map, self.w.builds
        return [int(h) for h in w.building_ids(own, R.HARBOR, done=True)
                if m.comp[int(b.y[h]), int(b.x[h])] == comp_id]

    def warships(self, own=None):
        return [b for b in self.boats if b.kind == WARSHIP and (own is None or b.own == own)]

    def boat_at(self, y, x, r=3.0, own=None):
        best, bd = None, r
        for b in self.boats:
            if own is not None and b.own != own:
                continue
            d = np.hypot(b.y - y, b.x - x)
            if d < bd:
                best, bd = b, d
        return best

    # ------------------------------------------------------------- 길
    @staticmethod
    def _set_path(b, path, state):
        b.by, b.bx, b.oy, b.ox = b.y, b.x, 0.0, 0.0
        b.path, b.pos, b.state = path, 0.0, state

    def _path(self, y, x, goal_mask):
        """(y, x)에서 goal 칸까지 배의 길 (지금 자리 → 목표)."""
        m = self.w.map
        y, x = int(y), int(x)
        if not (0 <= y < m.H and 0 <= x < m.W) or not m.nav[y, x]:
            return None
        p = sea_path(m.nav, goal_mask, y, x, 4 * max(m.H, m.W))
        return p[::-1].copy() if len(p) else None

    def _point_goal(self, y, x, r=2):
        m = self.w.map
        goal = np.zeros(m.nav.shape, bool)
        y, x = int(y), int(x)
        goal[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1] = True
        return goal & m.nav

    def _version(self) -> int:
        """땅 모양 판 (바다가 얼고 녹아 걸을 수 있는 칸이 바뀌면 올라간다): 해안·바닷길 기억은 판이 같을 때만 쓴다."""
        v = getattr(self.w.map, 'walk_version', 0)
        if self._shores and next(iter(self._shores))[0] != v:
            self._shores.clear()
            self._seas.clear()
        return v

    def _shore(self, comp_id):
        """comp_id 땅(절벽 제외)에 맞닿은, 배가 다닐 수 있는 물 칸 (땅 모양이 바뀔 때까지 기억해 둔다)."""
        key = (self._version(), int(comp_id))
        got = self._shores.get(key)
        if got is None:
            m = self.w.map
            got = self._shores[key] = m.nav & _neighbors((m.comp == comp_id) & m.land & ~m.cliff)
        return got

    def _sea(self, goal_key, goal_mask, sy, sx):
        """(sy, sx)에서 goal까지 바닷길 (기억해 둔다, 돌려줄 때는 복사본). goal_key: goal을 가리키는 이름."""
        m = self.w.map
        key = (self._version(), goal_key, int(sy), int(sx))
        got = self._seas.get(key)
        if got is None:
            if len(self._seas) > 512:
                self._seas.clear()
            got = self._seas[key] = sea_path(m.nav, goal_mask() if callable(goal_mask) else goal_mask, int(sy), int(sx), 4 * max(m.H, m.W))
        return got.copy()

    def ferry_prep(self, ids, ty, tx, comp):
        """같은 땅에서 배와 걷기를 견줄 준비 (가벼운 것만, 걸음 안에서): _ferry_eval에 넘길 것들 또는 배로 갈 수 없으면 None."""
        w, m, u = self.w, self.w.map, self.w.units
        own = int(u.own[ids[0]])
        harbors = self.harbors_on(own, comp)
        if not harbors:
            return None
        landing = self._landing(comp, ty, tx)
        if landing is None:
            return None
        land = self._land_next_to(landing[0], landing[1], comp, near=(ty, tx))
        if land is None:
            return None
        cy, cx = float(u.y[ids].mean()), float(u.x[ids].mean())
        near = int(ids[np.argmin(np.hypot(u.y[ids] - cy, u.x[ids] - cx))])   # 무리 한가운데 병사 (가운데 점은 물일 수도)
        here = w.fields.snap(float(u.y[near]), float(u.x[near]))
        tgt = w.fields.snap(ty, tx)
        if here is None or tgt is None:
            return None
        ports = []
        for h in harbors:
            d = self.dock_of(h)
            if d is None:
                continue
            g = self._land_next_to(d[0], d[1], comp, near=(w.builds.y[h], w.builds.x[h]))
            if g is not None:
                ports.append((g, (int(d[0]), int(d[1]))))
        if not ports:
            return None
        return dict(ty=tgt[0], tx=tgt[1], here=here, land=land, landing=landing, ports=ports, n=len(ids))

    def _land_next_to(self, wy, wx, comp_id, near=None):
        m = self.w.map
        best, bd = None, 1e18
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                yy, xx = wy + dy, wx + dx
                if (0 <= yy < m.H and 0 <= xx < m.W and m.comp[yy, xx] == comp_id and m.land[yy, xx]
                        and not m.cliff[yy, xx]):
                    d = 0 if near is None else (yy - near[0]) ** 2 + (xx - near[1]) ** 2
                    if d < bd:
                        best, bd = (yy, xx), d
        return best

    # ------------------------------------------------------------- 나룻길
    def _landing(self, comp, ty, tx):
        """목표 가까이의, comp 땅(절벽 제외)에 맞닿은 배가 다닐 수 있는 물 칸."""
        m = self.w.map
        shore = self._shore(comp)
        for r in (25, 50, 100, 250):
            y0, y1 = max(int(ty) - r, 0), min(int(ty) + r + 1, m.H)
            x0, x1 = max(int(tx) - r, 0), min(int(tx) + r + 1, m.W)
            ys, xs = np.nonzero(shore[y0:y1, x0:x1])
            if len(ys):
                k = np.argmin((ys + y0 - ty) ** 2 + (xs + x0 - tx) ** 2)
                return int(ys[k] + y0), int(xs[k] + x0)
        return None

    def ferry(self, ids, ty, tx, then, src_comp, dst_comp) -> bool:
        w, m, u = self.w, self.w.map, self.w.units
        own = int(u.own[ids[0]])
        quiet = False                                   # 알림은 그 나라에게 (누가 읽을지는 조종자가)
        big = 4 * max(m.H, m.W)
        # 1. 내릴 곳: 목표 가까이의 해안 물 칸
        shore_dst = self._shore(dst_comp)
        landing = None
        for r in (25, 50, 100, 250):
            y0, y1 = max(int(ty) - r, 0), min(int(ty) + r + 1, m.H)
            x0, x1 = max(int(tx) - r, 0), min(int(tx) + r + 1, m.W)
            ys, xs = np.nonzero(shore_dst[y0:y1, x0:x1])
            if len(ys):
                k = np.argmin((ys + y0 - ty) ** 2 + (xs + x0 - tx) ** 2)
                landing = (int(ys[k] + y0), int(xs[k] + x0))
                break
        if landing is None:
            if not quiet:
                w.say('그쪽에는 배를 댈 해안이 없습니다 (절벽은 안 됩니다)', to=own)
            return False
        land = self._land_next_to(landing[0], landing[1], dst_comp, near=(ty, tx))
        if land is None:
            return False
        # 2. 병사들이 있는 땅의 내 항구 중 (걸어가는 거리 + 바닷길)이 가장 짧은 곳
        cy, cx = float(u.y[ids].mean()), float(u.x[ids].mean())
        best = None
        for h in self.harbors_on(own, src_comp):
            d = self.dock_of(h)
            if d is None:
                continue
            route = self._sea(('dock', int(d[0]), int(d[1])), lambda: self._point_goal(d[0], d[1], 0), landing[0], landing[1])   # 항구 앞 → 내릴 곳 (기억)
            if len(route) == 0:
                continue
            gather = self._land_next_to(d[0], d[1], src_comp, near=(w.builds.y[h], w.builds.x[h]))
            if gather is None:
                continue
            cost = len(route) + float(np.hypot(gather[0] - cy, gather[1] - cx))
            if best is None or cost < best[0]:
                best = (cost, h, route, gather)
        if best is None:
            # AI가 참고할 해안: 내릴 곳에서 바닷길이 가장 짧은 우리 쪽 해안
            cross = self._sea(('shore', int(src_comp)), lambda: self._shore(src_comp), landing[0], landing[1])
            if len(cross):
                embark = self._land_next_to(int(cross[0, 0]), int(cross[0, 1]), src_comp, near=(cy, cx))
                if embark is not None:
                    self.want_harbor[own] = embark
            if not quiet:
                w.say('바다 건너로 가려면 병사들이 있는 땅에 항구가 있어야 합니다 (2: 항구 짓기)'
                      if not self.harbors_on(own, src_comp) else '이 땅의 항구에서 그쪽 바다로 갈 수 없습니다', to=own)
            return False
        _, h, route, gather = best
        # 3. 병사들은 항구로 모이고, 첫 나룻배가 항구 앞에 댄다
        ids = np.asarray(ids)
        if not w.order_move(ids, gather[0], gather[1], ferry=False):   # 항구로 모인다 (다시 나룻배를 부르지 않는다)
            return False
        c = Convoy(own, h, gather, route.copy(), land, then, int(u.slot[ids[0]]), list(map(int, ids)),
                   planned=int(np.ceil(len(ids) / R.BOAT_CAPACITY)))
        self.convoys.append(c)
        self._new_ferry(c)
        if not quiet:
            w.say(f'병사 {len(ids)}명이 항구에 모여 배를 탑니다', to=own)
        return True

    def _new_ferry(self, c):
        d = c.route[0]
        b = self._add(Boat(FERRY, c.own, d[0] + 0.5, d[1] + 0.5, R.FERRY_HP, state='load', home=c.harbor,
                           path=c.route, pos=0.0, land=c.land, then=c.then))
        c.ferries.append(b)
        self.log['ferries'] += 1
        return b

    # ------------------------------------------------------------- 진행
    def update(self, dt) -> None:
        self._land_shells()
        for c in self.convoys:
            self._gather(c, dt)
        self.convoys = [c for c in self.convoys if not c.done]
        for b in list(self.boats):
            if not b.alive:
                continue
            if b.kind == FERRY:
                if b.state == 'ahead':
                    if self._sail(b, dt, b.stop):
                        b.state = 'anchor'
                elif b.state == 'cross':
                    # 같은 바닷길을 가는 배는 줄을 선다: 앞 배와 길 위로 7칸 넘게 붙지 않는다
                    ahead = [o.pos for o in self.boats if o is not b and o.alive and o.path is b.path and o.pos > b.pos]
                    cap = min(ahead) - 7.0 if ahead else None
                    if cap is not None and cap <= b.pos:
                        pass
                    elif self._sail(b, dt, cap) and cap is None:
                        self._unload(b)
                elif b.state == 'move':                # 물 위 한 곳으로 다시 보냈다: 가서 기다린다
                    if self._sail(b, dt):
                        b.state, b.path = 'idle', None
                elif b.state == 'return':
                    if self._sail(b, dt):
                        b.alive = False                # 항구에 들어간다
            else:
                self._warship(b, dt)
        self.boats = [b for b in self.boats if b.alive]
        self._separate(dt)

    def _separate(self, dt):
        """배끼리 겹치지 않게 서로 밀어내고, 보이는 자리(y, x)와 탄 병사의 자리를 정한다."""
        m, u = self.w.map, self.w.units
        bs = self.boats
        k = min(1.0, 4.0 * dt)
        for b in bs:                                    # 붐비지 않으면 길 위로 천천히 돌아온다
            b.oy *= 1 - 0.3 * k
            b.ox *= 1 - 0.3 * k
        for _ in range(3):                              # 여러 척이 붙어 있어도 풀리게 몇 번
          for i in range(len(bs)):
            a = bs[i]
            ha, wa = SIZE[a.kind]
            for j in range(i + 1, len(bs)):
                c = bs[j]
                hc, wc = SIZE[c.kind]
                dy = (a.by + a.oy) - (c.by + c.oy)
                dx = (a.bx + a.ox) - (c.bx + c.ox)
                over_y = (ha + hc) / 2 - abs(dy)
                over_x = (wa + wc) / 2 - abs(dx)
                if over_y <= 0 or over_x <= 0:
                    continue
                # 겹친 폭이 작은 쪽으로 반씩 비켜난다 (같은 자리면 번호로 방향을 정한다)
                if over_y < over_x:
                    sgn = (1.0 if dy > 0 else -1.0) if abs(dy) > 1e-3 else (1.0 if a.id % 2 else -1.0)
                    a.oy += sgn * over_y / 2
                    c.oy -= sgn * over_y / 2
                else:
                    sgn = (1.0 if dx > 0 else -1.0) if abs(dx) > 1e-3 else (1.0 if a.id % 2 else -1.0)
                    a.ox += sgn * over_x / 2
                    c.ox -= sgn * over_x / 2
        for b in bs:
            n = float(np.hypot(b.oy, b.ox))
            if n > 9.0:
                b.oy, b.ox = b.oy * 9.0 / n, b.ox * 9.0 / n
            ny, nx = b.by + b.oy, b.bx + b.ox
            yi, xi = int(ny), int(nx)
            if not (0 <= yi < m.H and 0 <= xi < m.W and m.nav[yi, xi]):   # 물 밖이면 비켜나지 않는다
                b.oy *= 0.5
                b.ox *= 0.5
                ny, nx = b.by, b.bx
            b.y, b.x = ny, nx
            for i in b.cargo:                           # 탄 병사는 배와 함께
                u.y[i], u.x[i] = b.y, b.x

    # ------------------------------------------------------------- 나룻배 다시 보내기
    def order_ferries(self, ferries, y, x) -> bool:
        """병사를 태운 나룻배를 (y, x)로: 물이면 그 자리로 가서 기다리고, 땅이면 그 땅의 가까운 해안에 내려 준다."""
        w, m = self.w, self.w.map
        ferries = [b for b in ferries if b.kind == FERRY and b.cargo and b.alive]
        if not ferries:
            return False
        for c in self.convoys:                          # 항구에서 기다리던 배면 그 묶음에서 뺀다
            c.ferries = [b for b in c.ferries if b not in ferries]
        yi, xi = int(np.clip(y, 0, m.H - 1)), int(np.clip(x, 0, m.W - 1))
        ok = False
        if m.walk_static[yi, xi] and m.land[yi, xi]:     # 땅: 가까운 해안에 내려 준다
            comp = int(m.comp[yi, xi])
            shore = self._shore(comp)
            landing = None
            for r in (15, 40, 100, 250):
                y0, x0 = max(yi - r, 0), max(xi - r, 0)
                ys, xs = np.nonzero(shore[y0:yi + r + 1, x0:xi + r + 1])
                if len(ys):
                    q = int(np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2))
                    landing = (int(ys[q] + y0), int(xs[q] + x0))
                    break
            if landing is None:
                w.say('그쪽에는 배를 댈 해안이 없습니다 (절벽은 안 됩니다)', to=ferries[0].own)
                return False
            land = self._land_next_to(landing[0], landing[1], comp, near=(y, x))
            for b in ferries:
                p = self._path(b.y, b.x, self._point_goal(landing[0], landing[1], 1))
                if p is None or land is None:
                    continue
                self._set_path(b, p, 'cross')
                b.land, b.then = land, ('move', False, float(y), float(x))
                ok = True
        else:                                           # 물: 그 자리로 가서 기다린다
            goal = self._point_goal(y, x, 2)
            for b in ferries:
                p = self._path(b.y, b.x, goal)
                if p is not None:
                    self._set_path(b, p, 'move')
                    ok = True
        if not ok:
            w.say('배로 갈 수 없는 곳입니다', to=ferries[0].own)
        return ok

    def _gather(self, c, dt):
        """항구에서: 도착한 병사를 한 명씩 태우고, 배가 차면 앞바다로 보내고 다음 배를 대고, 다 타면 함께 출발."""
        w, u = self.w, self.w.units
        c.ferries = [b for b in c.ferries if b.alive]
        if not w.builds.alive[c.harbor]:                # 항구가 무너지면 탄 병사만 데리고 떠난다
            c.assigned = []
        gy, gx = c.gather[0] + 0.5, c.gather[1] + 0.5
        keep = []
        for i in c.assigned:                            # 아직 오는 중인 병사 (다른 명령을 받았으면 빠진다)
            if not u.alive[i] or u.aboard[i]:
                continue
            d = np.hypot(u.y[i] - gy, u.x[i] - gx)
            if (u.state[i] == MOVE and u.slot[i] == c.slot) or (u.state[i] == IDLE and d <= 8):
                keep.append(i)
        c.assigned = keep
        loader = next((b for b in c.ferries if b.state == 'load'), None)
        leaving = any(b.state == 'ahead' and b.pos < 6 for b in c.ferries)   # 앞 배가 비켜난 뒤에 다음 배를 댄다
        if loader is None and c.assigned and w.builds.alive[c.harbor] and not leaving:
            loader = self._new_ferry(c)
        c.board_cd -= dt
        c.idle_t += dt
        if loader is not None and c.board_cd <= 0:     # 한 명씩 차례로
            near = [i for i in c.assigned if np.hypot(u.y[i] - gy, u.x[i] - gx) <= BOARD_NEAR]
            if near:
                i = min(near, key=lambda j: np.hypot(u.y[j] - gy, u.x[j] - gx))
                u.aboard[i] = True
                u.state[i] = IDLE
                u.slot[i] = u.tgt[i] = u.tgb[i] = u.bld[i] = -1
                u.y[i], u.x[i] = loader.y, loader.x
                loader.cargo.append(i)
                c.assigned.remove(i)
                c.board_cd, c.idle_t = BOARD_GAP, 0.0
                if len(loader.cargo) >= R.BOAT_CAPACITY:    # 다 찼다: 앞바다로 나가 기다린다 (먼저 찬 배가 더 멀리)
                    k = sum(b.state in ('ahead', 'anchor') for b in c.ferries)
                    loader.stop = float(min(len(c.route) - 1, 6 * (max(c.planned, k + 1) - k)))
                    loader.state = 'ahead'
        loaded = [b for b in c.ferries if b.cargo]
        if not c.assigned or (c.idle_t > WAIT_LIMIT and loaded):   # 모두 탔다 (또는 한동안 아무도 안 온다): 함께 출발
            for b in c.ferries:
                if b.cargo:
                    b.state, b.path = 'cross', c.route
                else:
                    self._go_home(b)
            if c.assigned:                              # 끝내 안 온 병사는 그 자리에 둔다
                u.state[np.array(c.assigned)] = IDLE
            if loaded:
                n = sum(len(b.cargo) for b in loaded)
                w.say(f'나룻배 {len(loaded)}척 출발 (병사 {n}명)', to=c.own)
            c.done = True

    def _sail(self, b, dt, end=None) -> bool:
        """길을 따라 한 걸음 (end: 멈출 길 위치, 없으면 끝까지). 닿으면 True."""
        if b.path is None or len(b.path) == 0:
            return True
        last = len(b.path) - 1 if end is None else min(end, len(b.path) - 1)
        speed = R.WARSHIP_SPEED if b.kind == WARSHIP else R.FERRY_SPEED
        b.pos = min(b.pos + speed * dt, last)
        if b.pos < 0:                          # 아직 출발 전
            return False
        i = int(b.pos)
        j = min(i + 1, len(b.path) - 1)
        f = b.pos - i
        ny = b.path[i, 0] * (1 - f) + b.path[j, 0] * f + 0.5
        nx = b.path[i, 1] * (1 - f) + b.path[j, 1] * f + 0.5
        if abs(nx - b.bx) > 1e-3:
            b.dir = 1.0 if nx > b.bx else -1.0
        b.by, b.bx = ny, nx
        return b.pos >= last

    def _unload(self, b):
        w, m, u = self.w, self.w.map, self.w.units
        ly, lx = b.land
        landed = []
        for i in b.cargo:
            if not u.alive[i]:
                continue
            for _ in range(30):
                yy, xx = ly + w.rng.uniform(-3, 3), lx + w.rng.uniform(-3, 3)
                if (0 <= yy < m.H and 0 <= xx < m.W and m.walk[int(yy), int(xx)]
                        and m.comp[int(yy), int(xx)] == m.comp[ly, lx]):
                    break
            else:
                yy, xx = ly + 0.5, lx + 0.5
            u.y[i], u.x[i] = yy, xx
            u.aboard[i] = False
            landed.append(i)
        b.cargo = []
        self._go_home(b)                       # 다 내려 주고 항구로 돌아간다
        if not landed:
            return
        ids = np.array(landed)
        self.log['landed'] += len(landed)
        kind = b.then[0] if b.then else 'stay'
        if kind == 'move':
            w.order_move(ids, b.then[2], b.then[3], attack=b.then[1])
        elif kind == 'attack':
            unit, bld = b.then[1], b.then[2]
            if (unit >= 0 and u.alive[unit] and not u.aboard[unit]) or (bld >= 0 and w.builds.alive[bld]):
                w.order_attack(ids, unit=unit, building=bld)
        elif kind == 'build':
            bi = b.then[1]
            if w.builds.alive[bi] and w.builds.prog[bi] < 1:
                w.order_build(ids, bi)
        w.say(f'병사 {len(landed)}명 상륙', to=b.own)

    def _go_home(self, b):
        """나룻배를 출발한 항구로 (항구가 없어졌으면 그 자리에서 떠난다)."""
        w, m = self.w, self.w.map
        b.assigned = []
        d = self.dock_of(b.home) if b.home >= 0 and w.builds.alive[b.home] else None
        if d is not None:
            goal = np.zeros(m.nav.shape, bool)
            goal[d] = True
            p = self._path(b.y, b.x, goal)
            if p is not None and len(p) > 1:
                self._set_path(b, p, 'return')
                return
        b.alive = False

    # ------------------------------------------------------------- 전함
    def order_ships(self, ships, y, x) -> bool:
        """전함들을 물 위 (y, x)로."""
        goal = self._point_goal(y, x, 3)
        if not goal.any():
            return False
        ok = False
        for s in ships:
            p = self._path(s.y, s.x, goal)
            if p is not None:
                self._set_path(s, p, 'move')
                s.target = None
                ok = True
        return ok

    def hunt(self, ships, target) -> None:
        for s in ships:
            s.state, s.target, s.repath = 'hunt', target, 0.0
            s.tu = s.tb = -1

    def bombard(self, ships, unit=-1, building=-1) -> None:
        """전함들이 땅의 적 병사 (unit)나 건물 (building)을 포격하러 간다 (사거리 안의 바다까지)."""
        u = self.w.units
        for s in ships:
            s.state, s.target, s.repath = 'siege', None, 0.0
            s.tu, s.tb = int(unit), int(building)
            s.tg = int(u.gen[unit]) if unit >= 0 else 0

    def _siege_target(self, s):
        """포격하라고 받은 목표가 아직 있으면 그 자리 (x, y, 반지름), 없으면 None."""
        u, b = self.w.units, self.w.builds
        if s.tu >= 0:
            if u.alive[s.tu] and int(u.gen[s.tu]) == s.tg and not u.aboard[s.tu]:
                return float(u.x[s.tu]), float(u.y[s.tu]), 0.0
        elif s.tb >= 0 and b.alive[s.tb]:
            return float(b.x[s.tb]), float(b.y[s.tb]), float(b.r[s.tb])
        return None

    def _land_foe(self, s, r):
        """사거리 r 안의 가장 가까운 땅의 적: ('u', 병사) / ('b', 건물) / None. 날고 있는 병사는 빼고."""
        w, u, b = self.w, self.w.units, self.w.builds
        nn, best, bd = len(w.nations), None, r
        ids = w.unit_ids()
        if len(ids):
            ids = ids[(u.own[ids] < nn) & ~u.aboard[ids] & ~u.air[ids]]
            ids = ids[w.diplo.friend[s.own, u.own[ids]] == 0] if len(ids) else ids
            if len(ids):
                d = np.hypot(u.x[ids] - s.x, u.y[ids] - s.y)
                k = int(np.argmin(d))
                if d[k] <= bd:
                    best, bd = ('u', int(ids[k])), float(d[k])
        bs = np.flatnonzero(b.alive[:b.n])
        if len(bs):
            bs = bs[(b.own[bs] < nn) & (w.diplo.friend[s.own, b.own[bs]] == 0)]
            if len(bs):
                d = np.hypot(b.x[bs] - s.x, b.y[bs] - s.y) - b.r[bs]
                k = int(np.argmin(d))
                if d[k] < bd:
                    best = ('b', int(bs[k]))
        return best

    def _shell(self, s, kind, i) -> None:
        """전함이 땅의 적 병사 (kind 'u')나 건물 ('b') i를 쏜다: WARSHIP_FLY초 뒤 떨어진다 (_land_shells)."""
        w, u, b = self.w, self.w.units, self.w.builds
        if kind == 'u':
            tx, ty = float(u.x[i]), float(u.y[i])
            s.aim, s.aim_t = (tx, ty, 0.0), w.time
        else:
            tx, ty = float(b.x[i]), float(b.y[i])
            s.aim, s.aim_t = (tx, ty, float(b.r[i])), w.time
        self._launch(s, kind, i, tx, ty)

    def _launch(self, s, kind, tgt, tx, ty) -> None:
        """포탄을 쏜다: 화면에 그릴 기록 (2)과 맞을 때까지 날아가는 포탄."""
        w = self.w
        w.recent.append((w.time, s.x, s.y - 2, tx, ty, 2))
        gen = int(w.units.gen[tgt]) if kind == 'u' else 0
        self.shells.append((w.time + R.WARSHIP_FLY, s.own, kind, tgt, gen, tx, ty))

    def _land_shells(self) -> None:
        """때가 된 포탄이 떨어진다."""
        if not self.shells:
            return
        now, keep = self.w.time, []
        for sh in self.shells:
            if sh[0] > now + 1e-9:
                keep.append(sh)
            else:
                self._impact(*sh[1:])
        self.shells = keep

    def _impact(self, own, kind, i, gen, tx, ty) -> None:
        """포탄이 떨어졌다: 배 ('s')는 그대로 맞고, 땅이면 노린 병사·건물과 둘레의 적 병사 (덜)가 맞는다."""
        w, u, b, S = self.w, self.w.units, self.w.builds, R.SHORE
        if kind == 's':
            if i.alive:
                d = R.WARSHIP_DMG * w.diplo.hurt[i.own]
                i.hp -= d
                w.diplo.hits[own, i.own] += d
                if i.hp <= 0:
                    self._sink(i)
            return
        if kind == 'u':
            if u.alive[i] and int(u.gen[i]) == gen and not u.aboard[i] and np.hypot(u.x[i] - tx, u.y[i] - ty) <= R.WARSHIP_HIT_R:
                d = R.WARSHIP_DMG * w.diplo.hurt[u.own[i]] * u.fx_take[i]
                u.hp[i] -= d
                w.diplo.hits[own, u.own[i]] += d
                if u.hp[i] <= 0:
                    u.alive[i] = False
        elif b.alive[i]:
            d = R.WARSHIP_DMG * S['vs_build'] * w.diplo.hurt[b.own[i]]
            b.hp[i] -= d
            w.diplo.hits[own, b.own[i]] += d
            b.last[i] = own
        ids = w.unit_ids()
        if len(ids):
            near = ids[(np.hypot(u.x[ids] - tx, u.y[ids] - ty) <= S['splash']) & ~u.air[ids] & ~u.aboard[ids]
                       & (u.own[ids] < len(w.nations))]
            near = near[w.diplo.friend[own, u.own[near]] == 0] if len(near) else near
            for j in near:
                if kind == 'u' and j == i:
                    continue
                d = R.WARSHIP_DMG * S['splash_mul'] * w.diplo.hurt[u.own[j]] * u.fx_take[j]
                u.hp[j] -= d
                w.diplo.hits[own, u.own[j]] += d
                if u.hp[j] <= 0:
                    u.alive[j] = False

    def _range_goal(self, x, y, reach):
        """(x, y)에서 reach칸 안의 배가 다닐 바다 칸."""
        m = self.w.map
        goal = np.zeros(m.nav.shape, bool)
        r = int(reach) + 1
        y0, y1, x0, x1 = max(int(y) - r, 0), min(int(y) + r + 1, m.H), max(int(x) - r, 0), min(int(x) + r + 1, m.W)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        goal[y0:y1, x0:x1] = np.hypot(yy + 0.5 - y, xx + 0.5 - x) <= reach
        return goal & m.nav

    def _ring_goal(self, x, y, r0, r1):
        """(x, y)에서 r0~r1칸 떨어진 배가 다닐 바다 칸 (거리 두기)."""
        return self._range_goal(x, y, r1) & ~self._range_goal(x, y, r0)

    def foe_boat_near(self, own, x, y, r):
        """(x, y)에서 r 안의 가장 가까운 적 배 (나라 own에게)."""
        best, bd = None, r
        for o in self.boats:
            if o.alive and self.w.diplo.foe(own, o.own):
                d = float(np.hypot(o.x - x, o.y - y))
                if d <= bd:
                    best, bd = o, d
        return best

    def hit_boat(self, boat, dmg, by) -> None:
        """땅에서 배를 맞혔다 (by: 친 나라)."""
        d = dmg * self.w.diplo.hurt[boat.own]
        boat.hp -= d
        self.w.diplo.hits[by, boat.own] += d
        if boat.hp <= 0 and boat.alive:
            self._sink(boat)

    def kernel_arrays(self, dt) -> dict:
        """전투 커널 (sim/kernels/combat.py)에 넘길 살아 있는 배 배열과 병사마다 노리는 배 (배 id → 이번 걸음의 번호).
        배 공격 명령을 받은 병사는 배가 사거리 밖으로 가면 이따금 다시 길을 찾는다."""
        w, u = self.w, self.w.units
        live = [b for b in self.boats if b.alive]
        n = u.n
        ush = np.full(max(n, 1), -1, np.int32)
        pos = {b.id: k for k, b in enumerate(live)}
        has = np.flatnonzero(u.alive[:n] & (u.ship[:n] >= 0))
        for i in has:
            k = pos.get(int(u.ship[i]), -1)
            ush[i] = k
            if k < 0:
                u.ship[i] = -1
        order = has[(ush[has] >= 0) & (u.state[has] == ATTACK) & ~u.air[has] & ~u.aboard[has]] if len(has) else has
        if len(order):                                  # 배 공격 명령: 배가 사거리 밖이면 다시 길을 찾는다
            u.ship_t[order] -= dt
            for k in np.unique(ush[order]):
                g = order[(ush[order] == k) & (u.ship_t[order] <= 0)]
                b = live[k]
                g = g[np.hypot(u.x[g] - b.x, u.y[g] - b.y) > w.k_range[u.kind[g]]]
                if len(g):
                    u.ship_t[g] = 2.0
                    w.ship_route(g, b)
        return dict(ush=ush, n=len(live), live=live,
                    x=np.array([b.x for b in live] or [0.0], np.float32), y=np.array([b.y for b in live] or [0.0], np.float32),
                    own=np.array([b.own for b in live] or [0], np.int16), hp=np.array([b.hp for b in live] or [0.0], np.float32),
                    alive=np.ones(max(len(live), 1), np.bool_) & (len(live) > 0))

    def kernel_back(self, sb) -> None:
        """커널이 깎은 배 체력을 돌려받아 가라앉히고, 노리는 배를 배 id로 적는다."""
        u, live, n = self.w.units, sb['live'], self.w.units.n
        for k, b in enumerate(live):
            if sb['hp'][k] < np.float32(b.hp) - 1e-6:
                b.hp = float(sb['hp'][k])
                if b.hp <= 0 and b.alive:
                    self._sink(b)
        ush = sb['ush'][:n]
        ids = np.array([b.id for b in live] or [-1], np.int32)
        u.ship[:n] = np.where(ush >= 0, ids[np.maximum(ush, 0)], -1)

    def shore_fire(self) -> None:
        """땅에서 배로 (걸음마다, 커널 다음): 칠 병사가 없는 망루가 사거리 안의 적 배를 쏜다 (원거리 병사는 커널이 배도 표적으로 견준다)."""
        w, bl = self.w, self.w.builds
        foes = [o for o in self.boats if o.alive]
        if not foes:
            return
        nn = len(w.nations)
        for o in foes:
            for t in np.flatnonzero(bl.alive[:bl.n] & (bl.kind[:bl.n] == R.TOWER) & (bl.prog[:bl.n] >= 1) & (bl.cd[:bl.n] <= 0)):
                if bl.own[t] >= nn or w.diplo.friend[bl.own[t], o.own] or np.hypot(bl.x[t] - o.x, bl.y[t] - o.y) > R.TOWER_RANGE:
                    continue
                bl.cd[t] = R.TOWER_CD
                w.recent.append((w.time, float(bl.x[t]), float(bl.y[t]) - 3, o.x, o.y, 1))
                self.hit_boat(o, R.TOWER_DMG, int(bl.own[t]))
                if not o.alive:
                    break

    def _warship(self, s, dt):
        s.cd -= dt
        # 사거리 안의 가장 가까운 적 배를 쏜다
        foe, fd = None, R.WARSHIP_RANGE
        if s.target is not None and s.target.alive:
            d = np.hypot(s.target.y - s.y, s.target.x - s.x)
            if d <= R.WARSHIP_RANGE:
                foe, fd = s.target, d
        if foe is None:
            for o in self.boats:
                if o.alive and self.w.diplo.foe(s.own, o.own):
                    d = np.hypot(o.y - s.y, o.x - s.x)
                    if d < fd:
                        foe, fd = o, d
        if foe is not None and s.cd <= 0:
            s.cd = R.WARSHIP_CD
            self._launch(s, 's', foe, foe.x, foe.y)     # WARSHIP_FLY초 뒤 맞는다
        elif foe is None and s.cd <= 0:                 # 적 배가 없으면 땅을 포격: 받은 목표가 사거리 안이면 그것, 아니면 가장 가까운 적
            tgt = None
            st = self._siege_target(s) if s.state == 'siege' else None
            if st is not None and np.hypot(st[0] - s.x, st[1] - s.y) - st[2] <= R.WARSHIP_RANGE:
                tgt = ('u', s.tu) if s.tu >= 0 else ('b', s.tb)
            if tgt is None:
                tgt = self._land_foe(s, R.WARSHIP_RANGE)
            if tgt is not None:
                s.cd = R.WARSHIP_CD
                self._shell(s, *tgt)
        # 거리 두기: 상대 전함이나 포격하는 목표가 너무 가까우면 물러나며 쏜다 (이동 명령 중은 빼고)
        S, RG = R.SHORE, R.WARSHIP_RANGE
        eng = None
        if foe is not None and foe.kind == WARSHIP:
            eng = (foe.x, foe.y, 0.0)
        elif s.state == 'siege':
            eng = self._siege_target(s)
        if eng is None and s.aim and self.w.time - s.aim_t < 3.0:
            eng = s.aim
        if eng is not None and s.state in ('idle', 'hunt', 'siege') \
                and np.hypot(eng[0] - s.x, eng[1] - s.y) - eng[2] < RG * S['keep_min']:
            s.repath -= dt
            if s.repath <= 0 or s.path is None or not s.backing:
                s.repath = 1.0
                p = self._path(s.y, s.x, self._ring_goal(eng[0], eng[1], RG * S['keep_lo'] + eng[2], RG * S['keep_hi'] + eng[2]))
                if p is not None:
                    self._set_path(s, p, s.state)
                    s.backing = True
            if s.path is not None and s.backing and self._sail(s, dt):
                s.path, s.backing = None, False
            return
        if s.backing:                                   # 충분히 물러났다
            s.path, s.backing = None, False
        # 움직임
        if s.state == 'hunt':
            t = s.target
            if t is None or not t.alive:
                s.state, s.target, s.path = 'idle', None, None
            elif np.hypot(t.y - s.y, t.x - s.x) > R.WARSHIP_RANGE * 0.7:
                s.repath -= dt
                if s.repath <= 0 or s.path is None:
                    s.repath = 1.0
                    p = self._path(s.y, s.x, self._point_goal(t.y, t.x, 2))
                    if p is not None:
                        self._set_path(s, p, 'hunt')
                if s.path is not None:
                    self._sail(s, dt)
        elif s.state == 'move':
            if self._sail(s, dt):
                s.state, s.path = 'idle', None
        elif s.state == 'siege':                       # 땅의 목표를 포격하러: 사거리 안의 바다까지 간다
            st = self._siege_target(s)
            if st is None:
                s.state, s.path, s.tu, s.tb = 'idle', None, -1, -1
            elif np.hypot(st[0] - s.x, st[1] - s.y) - st[2] > R.WARSHIP_RANGE * 0.85:
                s.repath -= dt
                if s.repath <= 0 or s.path is None:
                    s.repath = 1.5
                    p = self._path(s.y, s.x, self._ring_goal(st[0], st[1], RG * S['keep_lo'] + st[2], RG * S['keep_hi'] + st[2]))   # 거리를 두고
                    if p is not None:
                        self._set_path(s, p, 'siege')
                    elif s.path is None:                # 닿을 바다가 없다
                        s.state, s.tu, s.tb = 'idle', -1, -1
                if s.path is not None:
                    self._sail(s, dt)
            else:
                s.path = None

    def _sink(self, b):
        w, u = self.w, self.w.units
        b.alive = False
        lost = [i for i in b.cargo if u.alive[i]]
        self.log['sunk_warships' if b.kind == WARSHIP else 'sunk_ferries'] += 1
        self.log['drowned'] += len(lost)
        if lost:
            u.alive[lost] = False
            u.aboard[lost] = False
        w.say('전함이 가라앉았습니다' if b.kind == WARSHIP else
              f'나룻배가 가라앉았습니다' + (f' (병사 {len(lost)}명을 잃었습니다)' if lost else ''), to=b.own)
        for o in self.boats:
            if o.target is b:
                o.target = None

    def harbor_lost(self, h) -> None:
        self.docks.pop(h, None)
