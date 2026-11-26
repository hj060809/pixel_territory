"""무역 (docs/ECONOMY_PLAN.md 3장): 무역소와 무역 행렬.

나뉜 부분 (규칙을 바꿀 때 한 곳만 고치게):
- pick_exchange: 무엇을 얼마나 바꿀지 (교환 규칙). 지금: 채움 비율(가진 양 / 한도)이 높은 것을 내주고 낮은 것을 받는 1:1 교환.
- Trade.allowed: 두 나라 사이에 무역이 되나 (켜고 끄기, 적대면 자동으로 멈춤).
- Caravan + Trade.update: 행렬이 길을 따라 오가고, 상대 무역소에서 짐을 바꾼다.
- 호위 (assign, _escorts): 무역소에 배치한 병사들이 떠나는 행렬을 escort명까지 따라간다 (남으면 다음 행렬). 바다에서는 상선에 함께 탄다.
- 약탈 (raid, _combat, _lost): 행렬은 반격하지 않는다. 명령받은 병사만 친다 (저절로 치는 병사·망루·전함은 없다).
  무너지면 실은 짐을 마지막으로 친 나라가 가져가고, 그 나라는 약탈 단계가 오른다: 모든 나라가 그 나라와의 행렬을
  raid_mul배 덜 보내고, raid_stop단계면 무역을 멈춘다 (raid_forget초마다 한 단계씩 내려간다).
- 무역하는 나라끼리는 덜 싸운다: 행렬이 무사히 다녀오면 두 나라의 관계가 rel만큼 오른다 (AI도 칠 곳을 고를 때 덜 고른다).
수치는 rules.TRADE 한 곳에.

흐름: 다 지은 무역소마다 행렬 하나. 쉬는 시간(every)이 지나면 무역할 수 있는 상대 무역소 중 바꿀 것이 가장 많은 곳을 골라
내줄 짐을 싣고 떠난다 → 상대 무역소에서 wait초 동안 짐을 바꾼다 (그때 상대가 줄 수 있는 만큼만, 못 바꾼 짐은 도로 가져온다)
→ 돌아와 받은 짐을 내린다. 길은 떠날 때 재고 (거리 지도의 내리막), 지형 빠르기대로 걷는다.

바닷길 (route): 걸어서만 가는 길과, 상선을 타고 건너는 길 중 빠른 쪽. 항구는 필요 없다:
  출발 쪽 해안 중 (걸어가는 시간 + 상대까지 바다 거리)가 가장 짧은 곳에서 상선을 타고, 상대 무역소 가까운 해안 중 가장 빠른 곳에 내린다.
  배는 그 앞바다에서 기다렸다가 돌아올 때 같은 길로 데려온다. 타고 내리는 데 board초. 길은 칸 목록 하나 (path)와 칸마다 바다인지 (sea).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sim import rules as R
from sim.entities import IDLE
from sim.kernels.flow import INF, _flow

T = R.TRADE
NRES = 4                                    # 식량, 목재, 석재, 유황
SHIP_SPEED = R.FERRY_SPEED                  # 상선 빠르기 (칸/초, 나룻배와 같다)
HOLD = 20                                   # 호위병은 상대 무역소 이만큼 앞에서 기다린다 (칸)
COLUMN = tuple(i * R.CARAVAN_GAP for i in range(len(R.CARAVAN_MEMBERS)))   # 행렬 줄: 맨 앞에서 뒤로 구성원까지의 거리 (호위 대형)
SIDE = 4.0                                  # 호위병이 상인 줄 양옆으로 떨어진 거리 (칸)
ALERT = 12.0                                # 행렬이나 호위병이 맞으면 이 시간 동안 호위병이 싸운다 (초)
FAR = 18.0                                  # 대형에서 이보다 멀면 길찾기로 돌아온다 (칸, 가까우면 곧장 따라잡는다)
AHEAD = 10                                  # 그때 가는 곳: 행렬 길 위로 이만큼 앞 (칸)


def _slot(x: float, y: float, ang: float, k: int, n: int, side_f: float = 1.0) -> tuple[float, float]:
    """호위병 k (n명 중)의 대형 자리 (y, x): 상인 줄의 양옆에 번갈아 (왼, 오른), 줄 앞에서 끝까지 같은 간격.
    앞뒤로는 줄 맨 앞보다 조금 앞에서 맨 뒤보다 조금 뒤까지 고르게 (한쪽에 ceil(n/2)명)."""
    per = (n + 1) // 2
    row, side = k // 2, (1 if k % 2 == 0 else -1)
    front, back = -1.0, COLUMN[-1] + 1.0                         # 줄보다 한 칸 앞에서 한 칸 뒤까지
    t = front + (back - front) * (row / (per - 1) if per > 1 else 0.5)
    cx, cy = np.cos(ang), np.sin(ang)
    sd = SIDE * side * side_f
    return y - cy * t + cx * sd, x - cx * t - cy * sd


# ------------------------------------------------------------- 교환 규칙
def have(nat, k: int) -> float:
    return nat.res[k] if k < 3 else nat.sulfur


def fill(nat) -> list[float]:
    """자원마다 채움 비율 (가진 양 / 한도)."""
    return [have(nat, k) / max(nat.caps[k], 1.0) for k in range(NRES)]


def pick_exchange(a, b, load: float | None = None):
    """a가 b에게 무엇을 주고 무엇을 받을지: (줄 자원, 받을 자원, 양) 또는 None.
    a에서 많고 b에서 적은 자원 x를 주고, b에서 많고 a에서 적은 자원 y를 받는다 (두 나라 모두 나아질 때만).
    양은 1:1, 한 번에 load까지 (주지 않으면 a의 그 자원 한도 × TRADE['load']: 한도가 클수록 많이 싣는다), 각자 그 자원 한도의 keep만큼은 남기고, 받는 쪽 한도의 남은 자리까지."""
    fa, fb = fill(a), fill(b)
    best, score = None, 0.0
    for x in range(NRES):
        for y in range(NRES):
            if x == y:
                continue
            gain_a, gain_b = fa[x] - fa[y], fb[y] - fb[x]         # a: x가 y보다 많다, b: y가 x보다 많다
            if gain_a <= 0 or gain_b <= 0:
                continue
            amt = min(load if load is not None else a.caps[x] * T['load'],
                      have(a, x) - a.caps[x] * T['keep'], have(b, y) - b.caps[y] * T['keep'],   # 남겨 둘 몫
                      b.caps[x] - have(b, x), a.caps[y] - have(a, y))                            # 받을 자리
            if amt < T['least']:
                continue
            s = (gain_a + gain_b) * amt
            if s > score:
                best, score = (x, y, float(amt)), s
    return best


def _take(nat, k: int, amt: float) -> None:
    if k < 3:
        nat.res[k] -= amt
    else:
        nat.sulfur -= amt


def _give(nat, k: int, amt: float) -> float:
    """받는다 (한도까지). 반환: 실제로 받은 양."""
    got = max(0.0, min(amt, nat.caps[k] - have(nat, k)))
    if k < 3:
        nat.res[k] += got
    else:
        nat.sulfur += got
    return got


# ------------------------------------------------------------- 행렬
@dataclass
class Caravan:
    id: int
    own: int
    home: int                    # 출발 무역소 (건물 번호)
    dest: int                    # 상대 무역소
    partner: int                 # 상대 나라
    path: np.ndarray             # 길 [(y, x), ...] 출발 → 상대
    sea: np.ndarray              # 칸마다 바다인지 (상선을 타고 간다)
    give: int                    # 내줄 자원
    want: int                    # 받을 자원
    cargo: list = field(default_factory=lambda: [0.0] * NRES)
    pos: float = 0.0             # 길 위 자리 (칸 수, 0 = 출발)
    back: bool = False           # 돌아오는 중
    wait: float = 0.0            # 상대 무역소에서 짐 바꾸는 남은 시간
    board: float = 0.0           # 항구에서 상선에 타고 내리는 남은 시간
    hp_m: list = field(default_factory=lambda: [h for _, h in R.CARAVAN_MEMBERS])   # 구성원마다 체력 (0이면 쓰러졌다)
    alive: bool = True
    raided_by: set = field(default_factory=set)   # 구성원을 쓰러뜨린 나라 (약탈 단계는 행렬마다 한 번)
    escort: list = field(default_factory=list)     # 따라가는 호위병 (병사 번호)
    last: int = -1               # 마지막으로 친 나라 (무너지면 짐을 가져간다)
    alert: float = 0.0           # 공격받았다: 이 시간 동안 호위병이 맞서 싸운다 (그 전엔 먼저 치지 않는다)
    moving: bool = False         # 걷는 중 (화면: 짐말 다리)

    @property
    def at_sea(self) -> bool:
        return bool(self.sea[int(np.clip(round(self.pos), 0, len(self.sea) - 1))])

    @property
    def length(self) -> float:
        return float(len(self.path) - 1)

    @property
    def hp(self) -> float:
        return float(sum(max(h, 0.0) for h in self.hp_m))

    @property
    def maxhp(self) -> float:
        return float(sum(h for _, h in R.CARAVAN_MEMBERS))

    def members(self) -> list[int]:
        """살아 있는 구성원 번호."""
        return [k for k, h in enumerate(self.hp_m) if h > 0]

    def member_at(self, k: int) -> tuple[float, float, float]:
        """구성원 k의 (x, y, 방향): 맨 앞(자리 pos)에서 가는 쪽 반대로 길을 따라 k × CARAVAN_GAP 뒤."""
        off = k * R.CARAVAN_GAP
        p = self.pos - off if not self.back else self.pos + off
        return self._point(float(np.clip(p, 0.0, self.length)))

    def at(self) -> tuple[float, float, float]:
        """(x, y, 가는 방향 라디안): 맨 앞."""
        return self._point(self.pos)

    def _point(self, pos: float) -> tuple[float, float, float]:
        p = self.path
        i = int(np.clip(pos, 0, len(p) - 1))
        j = min(i + 1, len(p) - 1)
        f = float(pos) - i
        y = p[i][0] + (p[j][0] - p[i][0]) * f + 0.5
        x = p[i][1] + (p[j][1] - p[i][1]) * f + 0.5
        dy, dx = (p[j][0] - p[i][0], p[j][1] - p[i][1]) if j != i else (p[i][0] - p[max(i - 1, 0)][0], p[i][1] - p[max(i - 1, 0)][1])
        ang = float(np.arctan2(dy, dx))
        if self.back:
            ang += np.pi
        return float(x), float(y), ang


class Trade:
    """한 판의 무역: 행렬들, 무역소마다 쉬는 시간, 나라 사이 켜고 끄기, 길 캐시."""

    def __init__(self, world):
        self.w = world
        n = len(world.nations)
        self.mode = np.zeros((n, n), np.int8)        # a가 b와: 0 자동 (적대면 멈춤), 1 켬 (적대여도), -1 끔
        self.caravans: list[Caravan] = []
        self.rest: dict[int, float] = {}               # 무역소 → 다음 출발까지 남은 초
        self._paths: dict[tuple, tuple | None] = {}       # (무역소, 무역소, 탈 수 있는 항구들) → (길, 바다 칸, 걸리는 시간)
        self._ones = None                                # 바닷길 거리 비용 (모두 1)
        self._next = 1
        self.log = {'trips': 0, 'moved': 0.0, 'raided': 0}   # 테스트·통계용
        self.escorts: dict[int, list[int]] = {}        # 무역소 → 기다리는 호위병
        self.raiders: dict[int, int] = {}              # 병사 → 치러 가는 행렬 번호
        self._ucd: dict[int, float] = {}               # 행렬을 치는 병사의 다음 공격까지
        self._follow: dict[int, float] = {}            # 다시 길을 정해 줄 때까지 (너무 자주 명령하지 않게)
        self._goal: dict[int, tuple] = {}              # 뒤처진 호위병에게 길찾기로 정해 준 곳
        self._hp: dict[int, float] = {}                # 호위병의 지난 체력 (맞았는지 알려고)
        self.raid_lv = np.zeros(n, np.float32)         # 나라마다 약탈 단계
        self._forget = np.zeros(n, np.float32)

    # ---- 켜고 끄기
    def wants(self, a: int, b: int) -> bool:
        """a 쪽에서 b와 무역하려 하나 (자동이면 적대가 아닐 때)."""
        m = int(self.mode[a, b])
        if m != 0:
            return m > 0
        if self.raid_lv[b] >= T['raid_stop']:                         # 약탈국과는 저절로 멈춘다
            return False
        return self.w.diplo.level(a, b) > 0                          # 0 = 적대

    def allowed(self, a: int, b: int) -> bool:
        """두 나라 사이에 행렬이 다니나: 둘 다 살아 있고, 둘 다 원할 때."""
        na, nb = self.w.nations[a], self.w.nations[b]
        return a != b and na.alive and nb.alive and self.wants(a, b) and self.wants(b, a)

    def set_mode(self, a: int, b: int, on: bool) -> None:
        """a가 b와의 무역을 켠다 (적대여도) / 끈다. 화면의 거점 말풍선 [무역 재개 / 중단]."""
        if 0 <= b < len(self.w.nations) and a != b:
            self.mode[a, b] = 1 if on else -1

    def status(self, a: int, b: int) -> str:
        """a의 눈으로 b와의 무역: on 다님 / off 내가 끔 / theirs 상대가 끔 / hostile 적대로 멈춤 / raider 약탈국이라 멈춤 /
        nopost 무역소 없음."""
        if self.mode[a, b] < 0:
            return 'off'
        if self.mode[a, b] == 0 and self.raid_lv[b] >= T['raid_stop']:
            return 'raider'
        if not self.wants(a, b):
            return 'hostile'
        if not self.wants(b, a):
            return 'theirs' if self.mode[b, a] < 0 else 'hostile'
        if not len(self.posts(a)) or not len(self.posts(b)):
            return 'nopost'
        return 'on'

    # ---- 무역소와 길
    def posts(self, nid: int) -> np.ndarray:
        return self.w.building_ids(nid, R.TRADE_POST, done=True)

    def _path(self, src: int, dst: int, own: int | None = None) -> np.ndarray | None:
        """무역소 src → dst의 길 칸 목록 (가장 빠른 길: 땅 또는 상선). 못 가면 None."""
        r = self.route(src, dst, own)
        return None if r is None else r[0]

    def route(self, src: int, dst: int, own: int | None = None):
        """무역소 src → dst: (길 [(y, x)...], 바다 칸 [bool...], 걸리는 시간 초) 또는 None. 한 번 재면 둔다."""
        w, b = self.w, self.w.builds
        key = (src, int(b.gen[src]), dst, int(b.gen[dst]))
        if key not in self._paths:
            s = w.fields.snap(float(b.y[src]), float(b.x[src]))
            t = w.fields.snap(float(b.y[dst]), float(b.x[dst]))
            self._paths[key] = None if s is None or t is None else self._measure(s, t)
        return self._paths[key]

    def _measure(self, s: tuple, t: tuple):
        """칸 s → 칸 t: 걸어서만, 또는 (걸어서 해안 → 상선 → t 가까운 해안 → 걸어서) 중 빠른 쪽 (항구 없이)."""
        m = self.w.map
        cs, ct = int(m.comp[s]), int(m.comp[t])
        coast_s = (m.comp == cs) & m.land & m.walk & _near(m.nav)    # s 땅의 바닷가 (탈 수 있는 땅)
        coast_t = (m.comp == ct) & m.land & m.walk & _near(m.nav)
        sy, sx = np.nonzero(coast_s)
        ds = self._field(m.walk, m.cost, s, [t] + list(zip(sy.tolist(), sx.tolist())))   # 출발에서 걸어서
        best = (ds[t] / T['speed'], None) if ds[t] < INF else None
        ty_, tx_ = np.nonzero(coast_t)
        if len(sy) and len(ty_):
            # 탈 곳: 바닷가 땅 곁의 물 칸 중 (걸어가는 시간 + t까지 곧은 거리를 배로) 가장 짧은 곳
            nb_s = _min_neighbor(np.where(coast_s, ds, INF).astype(np.float32))
            wy, wx = np.nonzero(m.nav & (nb_s < INF))
            if len(wy):
                guess = nb_s[wy, wx] / T['speed'] + np.hypot(wy - t[0], wx - t[1]) / SHIP_SPEED
                k = int(np.argmin(guess))
                w1 = (int(wy[k]), int(wx[k]))
                dd = self._field(m.walk, m.cost, t, list(zip(ty_.tolist(), tx_.tolist())))   # 바닷가에서 t까지 걸어서
                nb_t = _min_neighbor(np.where(coast_t, dd, INF).astype(np.float32))
                vy, vx = np.nonzero(m.nav & (nb_t < INF))
                if len(vy):
                    dsea = self._field(m.nav, self._sea_cost(), w1, list(zip(vy.tolist(), vx.tolist())))
                    tot = dsea[vy, vx] / SHIP_SPEED + nb_t[vy, vx] / T['speed']
                    j = int(np.argmin(tot))
                    if np.isfinite(tot[j]) and dsea[vy[j], vx[j]] < INF:
                        time = float(nb_s[w1]) / T['speed'] + float(tot[j]) + 2 * T['board']
                        if best is None or time < best[0]:
                            best = (time, (w1, (int(vy[j]), int(vx[j])), dsea, dd))
        if best is None:
            return None
        if best[1] is None:                                          # 걸어서만
            path = _descend(ds, t, s)[::-1]                          # ds는 s에서 퍼진 거리: t에서 내려가면 s에 닿는다
            return path, np.zeros(len(path), bool), best[0]
        w1, w2, dsea, dd = best[1]
        land1 = _land_of(ds, w1, m)                                  # 탈 바닷가 땅 (그 물 칸 곁에서 s에 가장 가까운)
        land2 = _land_of(dd, w2, m)                                  # 내릴 바닷가 땅 (t에 가장 가까운)
        leg1 = _descend(ds, land1, s)[::-1]                          # 출발 → 탈 곳 (땅)
        leg2 = _descend(dsea, w2, w1)[::-1]                          # 앞바다 → 내릴 곳 앞바다
        leg3 = _descend(dd, land2, t)                                # 내린 곳 → 상대 무역소 (땅)
        path = np.concatenate([leg1, leg2, leg3])
        sea = np.concatenate([np.zeros(len(leg1), bool), np.ones(len(leg2), bool), np.zeros(len(leg3), bool)])
        return path, sea, best[0]

    def _sea_cost(self) -> np.ndarray:
        if self._ones is None:
            self._ones = np.ones(self.w.map.nav.shape, np.float32)
        return self._ones

    @staticmethod
    def _field(walk, cost, origin, stops) -> np.ndarray:
        """origin에서 퍼지는 거리 지도 (stops에 모두 닿으면 멈춘다: 못 닿은 곳은 INF)."""
        n = walk.size
        out = np.empty(walk.shape, np.float32)
        stops = list(stops) or [origin]
        sy = np.array([p[0] for p in stops], np.int64)
        sx = np.array([p[1] for p in stops], np.int64)
        _flow(walk, cost, int(origin[0]), int(origin[1]), sy, sx, out, np.zeros(n, np.uint8),
              np.empty(n * 3, np.float32), np.empty(n * 3, np.int64))
        return out

    # ---- 걸음마다
    def update(self, dt: float) -> None:
        w, b = self.w, self.w.builds
        for p in [p for p in self.rest if not (b.alive[p] and b.kind[p] == R.TRADE_POST)]:
            del self.rest[p]
        out = {c.home for c in self.caravans}
        for nat in w.nations:
            if not nat.alive:
                continue
            for p in self.posts(nat.id):
                p = int(p)
                if p in out:
                    continue
                self.rest[p] = self.rest.get(p, T['every'] / self.speed(nat.id)) - dt
                if self.rest[p] <= 0:                                   # 쉬는 시간이 끝났다: 떠난다 (바꿀 것이 없으면 다시 쉰다)
                    self.rest[p] = T['every'] / self.speed(nat.id)
                    self._depart(nat.id, p)
        for c in self.caravans:
            self._move(c, dt)
        self._escorts(dt)
        self._combat(dt)
        self.caravans = [c for c in self.caravans if c.alive]
        for k in range(len(self.raid_lv)):                             # 약탈 단계는 시간이 지나면 내려간다
            if self.raid_lv[k] > 0:
                self._forget[k] += dt
                if self._forget[k] >= T['raid_forget']:
                    self._forget[k] = 0.0
                    self.raid_lv[k] = max(0.0, self.raid_lv[k] - 1)

    def speed(self, nid: int) -> float:
        """무역 빠르기 배율 (출발 간격을 이만큼 줄인다). 부족 (5단계: 온대 1.2)이 들어오면 여기서."""
        return 1.0

    def rest_after(self, own: int, partner: int) -> float:
        """행렬이 돌아온 뒤 다음 출발까지: 약탈국과 오가는 길이면 (어느 쪽이든) raid_mul배씩 더 쉰다."""
        lv = max(self.raid_lv[own], self.raid_lv[partner] if partner >= 0 else 0.0)
        return T['every'] / self.speed(own) * T['raid_mul'] ** float(lv)

    def _depart(self, nid: int, post: int) -> bool:
        """가장 바꿀 것이 많은 상대 무역소로 떠난다. 반환: 떠났나."""
        w, b = self.w, self.w.builds
        me = w.nations[nid]
        best = None
        for other in w.nations:
            if not self.allowed(nid, other.id):
                continue
            ex = pick_exchange(me, other)
            if ex is None:
                continue
            for q in self.posts(other.id):
                r = self.route(post, int(q), nid)
                if r is None:
                    continue
                key = (-ex[2], r[2])                                   # 많이 바꾸는 쪽, 같으면 빨리 가는 쪽
                if best is None or key < best[0]:
                    best = (key, other.id, int(q), r, ex)
        if best is None:
            return False
        _, partner, dest, (path, sea, _), (give, want, amt) = best
        c = Caravan(self._next, nid, post, dest, partner, path, sea, give, want)
        self._next += 1
        _take(me, give, amt)
        c.cargo[give] = amt
        self.caravans.append(c)
        wait = [e for e in self.escorts.get(post, []) if self._ok_escort(e, nid)]   # 기다리던 호위병 중 가까운 escort명이 따라간다
        u = w.units
        wait.sort(key=lambda e: (u.x[e] - b.x[post]) ** 2 + (u.y[e] - b.y[post]) ** 2)
        c.escort = wait[:T['escort']]
        self.escorts[post] = wait[T['escort']:]
        return True

    def _move(self, c: Caravan, dt: float) -> None:
        w, b, m = self.w, self.w.builds, self.w.map
        before = c.pos
        self._advance(c, dt)
        c.moving = c.alive and abs(c.pos - before) > 1e-4

    def _advance(self, c: Caravan, dt: float) -> None:
        w, b, m = self.w, self.w.builds, self.w.map
        if c.wait > 0:                                                # 상대 무역소에서 짐을 바꾸는 중
            c.wait -= dt
            if c.wait <= 0:
                self._swap(c)
                c.back = True
            return
        if c.board > 0:                                               # 항구에서 상선에 타고 내리는 중
            c.board -= dt
            return
        i = int(np.clip(c.pos, 0, len(c.path) - 1))
        y, x = c.path[i]
        j = min(i + 1, len(c.path) - 1) if not c.back else max(i - 1, 0)
        seg = float(np.hypot(*(c.path[j] - c.path[i]))) or 1.0          # 대각선 칸은 √2: 칸 수가 아니라 실제 거리로 걷는다
        step = (SHIP_SPEED if c.sea[i] else T['speed'] * float(m.speed_mul[y, x])) * dt / seg
        if not c.back and not c.at_sea and not (b.alive[c.dest] and self.allowed(c.own, c.partner)):
            c.back = True                                              # 상대 무역소가 없어졌거나 무역이 멈췄다: 돌아간다 (바다 위면 건넌 뒤에)
            return
        old = c.pos
        c.pos = min(c.pos + step, c.length) if not c.back else max(c.pos - step, 0.0)
        lo, hi = sorted((int(np.floor(old)), int(np.floor(c.pos))))
        ks = range(lo, hi) if not c.back else range(hi - 1, lo - 1, -1)
        for k in ks:                                                  # 땅 ↔ 바다가 바뀌는 곳: 거기서 멈춰 타고 내린다
            if c.sea[k] != c.sea[k + 1]:
                c.pos = float(k + 1) if not c.back else float(k)
                c.board = T['board']
                break
        if not c.back and c.pos >= c.length:
            c.wait = T['wait']
        elif c.back and c.pos <= 0:
            self._arrive_home(c)

    def _swap(self, c: Caravan) -> None:
        """상대 무역소에서: 싣고 온 짐을 주고, 상대가 줄 수 있는 만큼 받는다 (1:1). 못 바꾼 짐은 도로 가져간다."""
        other = self.w.nations[c.partner]
        give = c.cargo[c.give]
        can = min(give, have(other, c.want) - other.caps[c.want] * T['keep'], other.caps[c.give] - have(other, c.give))
        can = max(0.0, can)
        if can > 0:
            _give(other, c.give, can)
            _take(other, c.want, can)
            c.cargo[c.give] -= can
            c.cargo[c.want] += can
            self.log['moved'] += can

    def _arrive_home(self, c: Caravan) -> None:
        w = self.w
        me = w.nations[c.own]
        for k in range(NRES):
            if c.cargo[k] > 0:
                _give(me, k, c.cargo[k])
        c.alive = False
        self.log['trips'] += 1
        self.rest[c.home] = self.rest_after(c.own, c.partner)
        d = w.diplo                                                    # 무사히 다녀왔다: 두 나라가 서로 조금 더 좋아한다
        d.rel[c.own, c.partner] = min(100.0, d.rel[c.own, c.partner] + T['rel'])
        d.rel[c.partner, c.own] = min(100.0, d.rel[c.partner, c.own] + T['rel'])
        self._back_to_post(c)

    # ---- 호위
    def _ok_escort(self, e: int, nid: int) -> bool:
        u = self.w.units
        return 0 <= e < u.n and bool(u.alive[e]) and int(u.own[e]) == nid

    def escort_ids(self, nid: int | None = None) -> list[int]:
        """호위를 맡은 병사들 (기다리는 중 + 따라가는 중). AI가 다른 일에 쓰지 않게."""
        out = [e for lst in self.escorts.values() for e in lst] + [e for c in self.caravans for e in c.escort]
        return [e for e in out if nid is None or (self._ok_escort(e, nid))]

    def escorting(self) -> list[int]:
        """지금 행렬을 따라가는 호위병 (무역소에 돌아올 때까지 명령을 받지 않는다, 화면에서도 고를 수 없다)."""
        return [e for c in self.caravans for e in c.escort if self._ok_escort(e, c.own)]   # 죽은 칸을 다른 병사가 다시 쓴 경우는 빼고

    def release(self, ids) -> None:
        """다른 명령을 받은 병사: 호위·약탈에서 뺀다 (배에 타 있었으면 내려놓는다)."""
        ids = {int(i) for i in ids}
        if not ids:
            return
        for p in self.escorts:
            self.escorts[p] = [e for e in self.escorts[p] if e not in ids]
        u = self.w.units
        for c in self.caravans:
            for e in c.escort:
                if e in ids and u.aboard[e]:
                    self._land(e, c)
            c.escort = [e for e in c.escort if e not in ids]
        for i in ids:
            self.raiders.pop(i, None)
            self.w.units.passive[i] = False

    def assign(self, ids, post: int) -> bool:
        """고른 병사들을 무역소 post의 호위병으로 (그 곁에서 기다리다 떠나는 행렬을 따라간다)."""
        w, b = self.w, self.w.builds
        if not (b.alive[post] and b.kind[post] == R.TRADE_POST and b.prog[post] >= 1):
            return False
        ids = [int(i) for i in ids if self._ok_escort(int(i), int(b.own[post]))]
        if not ids:
            return False
        self.release(ids)
        self.escorts.setdefault(post, []).extend(ids)
        w.order_move(np.array(ids), float(b.y[post]) + 4.0, float(b.x[post]))
        w.say(f'호위병 {len(ids)}명이 무역소에서 행렬을 기다립니다 (행렬마다 {T["escort"]}명까지 따라간다)', to=int(b.own[post]))
        return True

    def _land(self, e: int, c: Caravan) -> None:
        """상선에서 내린다: 행렬 곁의 땅으로."""
        u, w = self.w.units, self.w
        x, y, _ = c.at()
        spot = w.fields.snap(y, x, 10)
        u.aboard[e] = False
        if spot is not None:
            u.y[e], u.x[e] = spot[0] + 0.5, spot[1] + 0.5

    def _back_to_post(self, c: Caravan) -> None:
        """행렬이 끝났다 (돌아왔거나 무너졌다): 호위병은 무역소로 돌아가 다음 행렬을 기다린다."""
        w, b = self.w, self.w.builds
        alive = [e for e in c.escort if self._ok_escort(e, c.own)]
        if not c.alive and c.at_sea:                                   # 상선이 가라앉았다: 함께 탄 호위병도 잃는다
            for e in alive:
                w.units.alive[e] = False
                w.units.aboard[e] = False
            c.escort = []
            return
        for e in alive:
            w.units.passive[e] = False                                 # 무역소에서 기다리는 동안은 보통 병사처럼
            if w.units.aboard[e]:
                self._land(e, c)
        c.escort = []
        if not alive:
            return
        if b.alive[c.home] and b.kind[c.home] == R.TRADE_POST:
            self.escorts.setdefault(c.home, []).extend(alive)
            w.order_move(np.array(alive), float(b.y[c.home]) + 4.0, float(b.x[c.home]))

    def _escorts(self, dt: float) -> None:
        """따라가는 호위병: 정해진 대형으로 행렬을 감싼다.
        상인(짐말 둘, 수레)은 일렬, 호위병은 그 줄의 양옆에 같은 간격으로 앞에서 끝까지 (slots). 바다에서는 상선에 함께 탄다.
        싸우는 호위병(적을 잡았다)은 두고, 싸움이 끝나면 제자리로 돌아온다. 상대 무역소 HOLD칸 앞에서는 대형 그대로 기다린다
        (남의 땅에 들어가 싸움을 걸지 않게), 돌아오는 행렬이 지나가면 다시 감싼다."""
        w, u = self.w, self.w.units
        for p in list(self.escorts):
            if not (w.builds.alive[p] and w.builds.kind[p] == R.TRADE_POST):
                del self.escorts[p]                                    # 무역소가 없어졌다: 호위에서 풀린다
                continue
            self.escorts[p] = [e for e in self.escorts[p] if self._ok_escort(e, int(w.builds.own[p]))]
        for c in self.caravans:
            c.escort = [e for e in c.escort if self._ok_escort(e, c.own)]
            if not c.escort:
                continue
            hurt = any(u.hp[e] < self._hp.get(e, u.hp[e]) - 1e-3 for e in c.escort)   # 호위병이 맞았다
            for e in c.escort:
                self._hp[e] = float(u.hp[e])
            if hurt:
                c.alert = ALERT
            c.alert = max(0.0, c.alert - dt)
            for e in c.escort:
                u.passive[e] = c.alert <= 0                          # 가는 길엔 중립: 공격받기 전까지 먼저 치지 않는다
                if u.passive[e] and (u.tgt[e] >= 0 or u.tgb[e] >= 0) and u.state[e] == IDLE:
                    u.tgt[e] = -1                                      # 경계가 풀렸다: 잡고 있던 적을 놓고 대형으로
                    u.tgb[e] = -1
            x, y, ang = c.at()
            if c.at_sea:                                               # 상선에 함께 탄다
                for e in c.escort:
                    u.aboard[e] = True
                    u.x[e], u.y[e] = x, y
                continue
            for e in c.escort:
                if u.aboard[e]:
                    self._land(e, c)
            stop = max(0, len(c.path) - 1 - HOLD)                      # 상대 무역소 앞, 호위병이 기다리는 칸
            if c.pos > stop:                                           # 행렬은 상대 무역소에 들어갔다: 대형은 그 앞에 둔다
                ay, ax = c.path[stop]
                ny, nx = c.path[min(stop + 1, len(c.path) - 1)]
                x, y, ang = ax + 0.5, ay + 0.5, float(np.arctan2(ny - ay, nx - ax))
                if c.back:
                    ang += np.pi
            j = int(np.clip(c.pos + (-AHEAD if c.back else AHEAD), 0, stop if not c.back else len(c.path) - 1))
            ahead = (float(c.path[j][0]) + 0.5, float(c.path[j][1]) + 0.5)   # 뒤처진 호위병이 길찾기로 갈 곳: 행렬 길 위 조금 앞
            for k, e in enumerate(c.escort):
                if u.tgt[e] >= 0 or u.tgb[e] >= 0:                      # 싸우는 중: 커널이 움직인다
                    continue
                ty, tx = self._walkable_slot(x, y, ang, k, len(c.escort))
                self._step_to(e, ty, tx, dt, ahead)

    def _walkable_slot(self, x, y, ang, k, n):
        """대형 자리: 물·절벽이면 상인 줄 쪽으로 당겨 (길가를 따라 걷게) 걸을 수 있는 곳으로."""
        m = self.w.map
        for f in (1.0, 0.6, 0.3, 0.0):
            ty, tx = _slot(x, y, ang, k, n, f)
            if 0 <= int(ty) < m.H and 0 <= int(tx) < m.W and m.walk[int(ty), int(tx)]:
                return ty, tx
        return _slot(x, y, ang, k, n)

    def _step_to(self, e: int, ty: float, tx: float, dt: float, ahead=None) -> None:
        """호위병을 대형의 제자리 쪽으로 (걷는 빠르기보다 조금 빠르게: 뒤처지지 않게). 멀리 떨어졌으면 길찾기로 부른다."""
        w, u, m = self.w, self.w.units, self.w.map
        dx, dy = tx - u.x[e], ty - u.y[e]
        dist = float(np.hypot(dx, dy))
        if dist > FAR:                                                 # 멀리 떨어졌다 (싸우다, 막혀서): 길찾기로 따라온다
            g = self._goal.get(e)                                      # 목적지는 행렬 길 위로 조금 앞 (다다르기 전엔 다시 정하지 않는다)
            if u.state[e] == IDLE or g is None or np.hypot(g[0] - ty, g[1] - tx) > FAR + 6:
                gy, gx = ahead if ahead is not None else (ty, tx)
                self._goal[e] = (gy, gx)
                w.order_move(np.array([e]), float(gy), float(gx))
            return
        self._goal.pop(e, None)
        if u.state[e] != IDLE:                                         # 길을 따라 오던 중: 대형 곁에 왔으니 그만두고 제자리로
            w.order_stop(np.array([e]))
        k = int(u.kind[e])
        sp = w.k_speed[k] * 1.25 * float(m.speed_mul[int(u.y[e]), int(u.x[e])]) ** w.k_terrain[k] * dt
        if dist < 0.05:
            u.moving[e] = False
            return
        f = min(1.0, sp / dist)
        ok = lambda yy, xx: 0 <= int(yy) < m.H and 0 <= int(xx) < m.W and bool(m.walk[int(yy), int(xx)])
        for my, mx in ((dy * f, dx * f), (0.0, dx * f), (dy * f, 0.0)):  # 곧장, 막히면 옆으로 미끄러지듯
            ny, nx = float(u.y[e] + my), float(u.x[e] + mx)
            if (my or mx) and ok(ny, nx):
                u.y[e], u.x[e] = ny, nx
                u.moving[e] = np.hypot(my, mx) > 0.005                 # 실제로 걸었으면 다리를 움직인다
                self._follow[e] = 0.0
                return
        u.moving[e] = False                                            # 꽉 막혔다: 잠시 뒤 길찾기로 돌아온다
        self._follow[e] = self._follow.get(e, 0.0) + dt
        if self._follow[e] > 0.8:
            self._follow[e] = 0.0
            gy, gx = ahead if ahead is not None else (ty, tx)
            self._goal[e] = (gy, gx)
            w.order_move(np.array([e]), float(gy), float(gx))

    # ---- 약탈
    def caravan_at(self, y: float, x: float, r: float = 3.0) -> Caravan | None:
        """(y, x) 둘레의 행렬 (짐말·수레 줄 전체를 본다)."""
        best, bd = None, r
        for c in self.caravans:
            for k in (c.members() if not c.at_sea else [0]):
                cx, cy, _ = c.member_at(k)
                d = np.hypot(cx - x, cy - y)
                if d < bd:
                    best, bd = c, d
        return best

    def _nearest_member(self, c: Caravan, x: float, y: float) -> tuple[int, float, float, float]:
        """(x, y)에서 가장 가까운 살아 있는 구성원: (번호, 그 x, 그 y, 거리)."""
        best = (-1, 0.0, 0.0, 1e9)
        for k in c.members():
            mx, my, _ = c.member_at(k)
            d = float(np.hypot(mx - x, my - y))
            if d < best[3]:
                best = (k, mx, my, d)
        return best

    def hostile(self, a: int, b: int) -> bool:
        """a가 b의 행렬을 저절로 치나: 동맹이 아니고, 적대거나 무역이 끊겼을 때 (무역하는 사이면 지나가게 둔다)."""
        if a == b or a >= len(self.w.nations) or b >= len(self.w.nations) or self.w.diplo.allied(a, b):
            return False
        return self.w.diplo.level(a, b) == 0 or not self.allowed(a, b)

    def raid(self, ids, c: Caravan) -> bool:
        """고른 병사들에게 행렬 c를 치게 한다 (동맹의 행렬은 못 친다)."""
        ids = [int(i) for i in ids if self.w.units.alive[i] and not self.w.diplo.allied(int(self.w.units.own[i]), c.own)
               and int(self.w.units.own[i]) != c.own]
        if not ids:
            return False
        self.release(ids)
        for i in ids:
            self.raiders[i] = c.id
            self._follow[i] = 0.0
        return True

    def _combat(self, dt: float) -> None:
        w, u, b = self.w, self.w.units, self.w.builds
        by_id = {c.id: c for c in self.caravans}
        # 행렬은 저절로 공격받지 않는다: 명령받은 병사만 친다 (오른쪽 클릭, AI가 정한 약탈)
        # 치러 간 병사: 닿으면 치고, 멀면 따라간다
        for i, cid in list(self.raiders.items()):
            c = by_id.get(cid)
            if c is None or not u.alive[i] or c.at_sea:
                self.raiders.pop(i, None)
                continue
            mk, x, y, dist = self._nearest_member(c, float(u.x[i]), float(u.y[i]))
            if mk < 0:
                self.raiders.pop(i, None)
                continue
            k = int(u.kind[i])
            reach = R.UNIT_STATS[k]['range'] + 1.2
            if dist > reach:
                self._follow[i] = self._follow.get(i, 0.0) - dt
                if self._follow[i] <= 0:
                    self._follow[i] = 0.6
                    w.order_move(np.array([i]), y, x)
                continue
            if u.state[i] != IDLE:
                w.order_stop(np.array([i]))
            self._ucd[i] = self._ucd.get(i, 0.0) - dt
            if self._ucd[i] <= 0:
                self._ucd[i] = R.UNIT_STATS[k]['cd']
                self._hit(c, mk, R.UNIT_STATS[k]['dmg'], int(u.own[i]))
                w.recent.append((w.time, float(u.x[i]), float(u.y[i]), x, y, 1 if R.UNIT_STATS[k]['ranged'] else 0))
        for c in self.caravans:
            if c.alive and not c.members():
                self._lost(c)

    def _hit(self, c: Caravan, k: int, dmg: float, by: int) -> None:
        """구성원 k가 맞는다. 쓰러지면 그가 진 짐 (살아 있던 구성원 수로 나눈 몫)을 친 나라가 가져간다."""
        if not c.alive or k < 0 or c.hp_m[k] <= 0:
            return
        alive_before = len(c.members())
        c.hp_m[k] -= dmg
        c.last = by
        c.alert = ALERT                                                # 호위병이 맞서 싸운다
        if by < len(self.w.nations):
            self.w.diplo.hits[by, c.own] += dmg                       # 관계에 반영 (빼앗긴 쪽이 친 쪽을 미워한다)
        if c.hp_m[k] <= 0:
            self._fallen(c, k, by, alive_before)

    def _fallen(self, c: Caravan, k: int, by: int, alive_before: int) -> None:
        """구성원 k가 쓰러졌다: 그 몫의 짐을 친 나라가 가져가고 (한도까지), 처음 쓰러뜨렸으면 약탈 단계가 오른다."""
        w = self.w
        share = [v / max(alive_before, 1) for v in c.cargo]
        for kk in range(NRES):
            c.cargo[kk] -= share[kk]
        names = [*R.RES_NAMES, '유황']
        who = '상인' if R.CARAVAN_MEMBERS[k][0] == 'trader' else '낙타'
        owner = w.nations[c.own]
        if not (0 <= by < len(w.nations)) or by == c.own:
            w.say(f'무역 행렬의 {who}{"이" if who == "상인" else "가"} 쓰러졌습니다', to=c.own)
            return
        got = w.nations[by]
        gain = [_give(got, kk, share[kk]) if share[kk] > 0 else 0.0 for kk in range(NRES)]
        parts = [f'{names[kk]} {int(v)}' for kk, v in enumerate(gain) if v >= 1]
        w.say(f'{owner.name}의 무역 행렬을 약탈했습니다' + (f' ({", ".join(parts)})' if parts else ''), to=by)
        w.say(f'{got.name}에게 무역 행렬의 {who}{"을" if who == "상인" else "를"} 잃고 짐을 빼앗겼습니다', to=c.own)
        if by in c.raided_by:
            return
        c.raided_by.add(by)                                            # 약탈 단계: 행렬마다 한 번
        self.raid_lv[by] = min(self.raid_lv[by] + 1, T['raid_stop'])
        self._forget[by] = 0.0
        lv = int(self.raid_lv[by])
        if lv >= T['raid_stop']:                                       # 알림은 무역이 완전히 막힐 때만 (그 전엔 조용히 덜 보낸다)
            w.say('약탈을 계속해 다른 나라들과 무역을 할 수 없게 됐습니다 (시간이 지나면 풀린다)', to=by)

    def _lost(self, c: Caravan) -> None:
        """행렬의 구성원이 모두 쓰러졌다 (짐은 쓰러질 때마다 이미 넘어갔다)."""
        c.alive = False
        self.log['raided'] += 1
        self.w.say('무역 행렬을 모두 잃었습니다', to=c.own)
        self._back_to_post(c)
        self.rest[c.home] = self.rest_after(c.own, c.partner)

    # ---- 화면
    def state_for(self, me: int) -> dict:
        """화면에 보낼 것: 나라마다 무역 상태, 내 무역소마다 행렬."""
        w = self.w
        posts = {}
        for p in self.posts(me):
            p = int(p)
            c = next((c for c in self.caravans if c.home == p), None)
            info = ({'rest': max(0, round(self.rest.get(p, T['every'])))} if c is None else
                    {'to': c.partner, 'back': c.back, 'sea': c.at_sea, 'cargo': [round(v) for v in c.cargo], 'give': c.give, 'want': c.want,
                     'hp': round(c.hp / c.maxhp, 2), 'escort': len(c.escort)})
            info['wait'] = len([e for e in self.escorts.get(p, []) if self._ok_escort(e, me)])   # 기다리는 호위병
            posts[str(p)] = info                                       # 건물 번호 = 화면의 slot
        return {
            'trade': [self.status(me, b) if b != me else '' for b in range(len(w.nations))],
            'trade_mode': [int(v) for v in self.mode[me]],
            'raid': [int(v) for v in self.raid_lv],                    # 나라마다 약탈 단계
            'posts': posts,
        }


def _near(mask: np.ndarray) -> np.ndarray:
    """mask 칸의 8방향 이웃인 칸."""
    out = np.zeros_like(mask)
    H, W = mask.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)] |= mask[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)]
    return out


def _min_neighbor(v: np.ndarray) -> np.ndarray:
    """칸마다 8방향 이웃 값의 가장 작은 것."""
    out = np.full_like(v, INF)
    H, W = v.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            dst = out[max(dy, 0):H + min(dy, 0), max(dx, 0):W + min(dx, 0)]
            np.minimum(dst, v[max(-dy, 0):H + min(-dy, 0), max(-dx, 0):W + min(-dx, 0)], out=dst)
    return out


def _land_of(dd: np.ndarray, wcell: tuple, m) -> tuple:
    """물 칸 곁의 땅 중 t까지 가장 가까운 칸 (내리는 곳)."""
    y, x = wcell
    best, bd = None, INF
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            yy, xx = y + dy, x + dx
            if 0 <= yy < m.H and 0 <= xx < m.W and m.land[yy, xx] and m.walk[yy, xx] and dd[yy, xx] < bd:
                best, bd = (yy, xx), dd[yy, xx]
    return best


def _descend(dist: np.ndarray, s: tuple, t: tuple) -> np.ndarray:
    """거리 지도를 따라 s에서 t까지 내려가는 길 (8방향)."""
    H, W = dist.shape
    y, x = s
    out = [(y, x)]
    seen = {(y, x)}
    for _ in range(H * W):
        if (y, x) == tuple(t):
            break
        best, bd = None, dist[y, x]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and dist[yy, xx] < bd and (yy, xx) not in seen:
                    best, bd = (yy, xx), dist[yy, xx]
        if best is None:
            break
        y, x = best
        seen.add(best)
        out.append(best)
    return np.array(out, np.int32)
