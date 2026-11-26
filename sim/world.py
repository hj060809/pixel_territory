"""게임 세계: 나라, 자원, 병사, 건물, 명령, 승패.

- 자원지에 건물(농장/벌목장/채석장)을 지으면 자원이 난다. 양은 자원지의 풍부함 × 계절.
  추운 곳일수록 계절 차이가 크다: 가을에 수확이 많고 겨울에는 농장이 거의 쉰다.
- 병사는 식량을 먹는다 (겨울엔 더). 식량이 바닥나면 굶어서 약해진다. 거점 가까이서는 회복한다.
- 얼음 위에 있던 병사는 얼음이 녹으면 빠진다.
- 거점과 병사를 모두 잃은 나라는 멸망 (남은 자원지·망루는 허물어진다). 나만 남으면 승리.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from sim import rules as R
from sim import climate, storage, tribes
from sim.trade import Trade
from sim.boats import Fleet
from sim.entities import AMOVE, ATTACK, BUILD, IDLE, MOVE, Buildings, Units
from sim.kernels import rng as kernel_rng
from sim.kernels.combat import step
from sim.pathing import FieldCache, WalkCost

FERRY_CHECK = 20.0         # 같은 땅에서 직선으로 이보다 멀리 보낼 때만 배가 더 빠른지 견준다 (칸).
                           # 좁은 물 건너편은 직선으로는 가까워도 걸어서는 멀 수 있어서 작게 둔다
from sim.sites import sites_for
from sim.spawn import choose_starts, pick_colors

TICK = 0.05


def m_snow(gmap):
    """지금 눈 덮인 땅 (계절마다 바뀐다)."""
    from sim.terrain import _SNOWY_LUT
    return _SNOWY_LUT[gmap.mat] & gmap.land


@dataclass
class Nation:
    id: int
    name: str
    color: tuple
    light: tuple
    res: list = field(default_factory=lambda: list(R.START_RES))
    rate: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    sulfur: float = 0.0              # 유황 (화염탑 연료와 건설)
    sulfur_rate: float = 0.0
    bonus: float = 1.0               # 자원 수입 배율 (AI 난이도)
    alive: bool = True
    starving: bool = False
    n_units: int = 0
    n_buildings: int = 0
    caps: list = field(default_factory=lambda: [R.STORE_BASE + R.STORE_HALL] * 4)   # 자원마다 한도 (식량·목재·석재·유황, sim/storage.py)
    idle: bool = False               # 조종자 없음 (사람이 떠났다): 판 끝을 셀 때 남은 나라로 치지 않는다
    tribe: int = 0                   # 부족 (sim/tribes.py: 0 온대, 1 설원, 2 사막). 시작 거점 자리로 한 번 정한다


class World:
    def __init__(self, gmap, n: int = 5, seed: int = 0, map_seed: int = 0, starts=None, colors=None,
                 names=None, spots=None):
        """나라 n개 (최대 rules.COLORS 수). 게임은 나라만 안다: 누가 조종하는지 (사람/AI)는 바깥(sim/match.py)이 정한다.
        seed: 이 판의 난수 (시작 자리, 색). map_seed: 지도의 난수 (자원지는 같은 지도면 그대로).
        starts, colors, names: 나라 번호 순서대로 거점 자리·색 번호·이름 (없으면 여기서 정한다).
        spots: {나라 번호: (y, x)} 미리 고른 거점 자리 (나머지 나라는 무작위)."""
        self.map = gmap
        self.rng = np.random.default_rng(seed)
        np.random.seed(seed % (2 ** 31))
        kernel_rng.seed(seed % (2 ** 31))              # numba 안의 난수도 같은 시드로 (같은 시드 → 같은 판)
        self.sites = sites_for(gmap, map_seed)
        self.units = Units()
        self.builds = Buildings()
        self.fields = FieldCache(gmap, slots=32)
        self.routes = WalkCost(gmap)              # 걷는 비용 재기 (배를 탈지 정할 때)
        self.fleet = Fleet(self)
        self.shots = np.zeros((512, 5), np.float32)
        self.n_shots = 0
        self.recent: deque = deque(maxlen=600)
        self.messages: deque = deque(maxlen=256)      # 알림 (글, 시각, 받는 나라 | None = 모두, 빼는 나라들)
        self.time = 0.0
        self.phase = 'play'                       # 'over': 판 끝 (나라가 하나만 남았다), 멈춘다
        self.winner: int | None = None             # 판 끝에 남은 나라 (없으면 None)
        self.on_tick = None                       # 걸음마다 부를 것 (조종자들의 차례: sim/match.py)
        self.season_w = np.array([1.0, 0, 0, 0])
        self._acc = 0.0
        self._builders = np.zeros(self.builds.cap, np.int32)
        self._slow = 0.0
        ks = [R.UNIT_STATS[k] for k in range(len(R.UNIT_STATS))]           # 병종 번호 순서
        self.k_speed = np.array([s['speed'] for s in ks], np.float32)
        self.k_range = np.array([s['range'] for s in ks], np.float32)
        self.k_dmg = np.array([s['dmg'] for s in ks], np.float32)
        self.k_cd = np.array([s['cd'] for s in ks], np.float32)
        self.k_sight = np.array([s['sight'] for s in ks], np.float32)
        self.k_ranged = np.array([s['ranged'] for s in ks])
        self.k_terrain = np.array([s['terrain'] for s in ks], np.float32)
        self.k_charge = np.array([s['charge'] for s in ks], np.float32)
        self.k_vs = np.ones((len(ks), len(ks)), np.float32)              # 상성 (치는 쪽, 맞는 쪽)
        for (a, b), v in R.UNIT_VS.items():
            self.k_vs[a, b] = v
        self.k_fly = np.array([s['fly'] for s in ks])
        self.k_splash = np.array([s['splash'] for s in ks], np.float32)
        self.k_upkeep = np.array([s['upkeep'] for s in ks], np.float32)
        self.k_hp = np.array([s['hp'] for s in ks], np.float32)
        n = max(1, min(int(n), len(R.COLORS)))
        if colors is None or len(colors) != n:
            colors = pick_colors(self.rng, n)
        if starts is None or len(starts) != n:
            spots = dict(spots or {})
            order = [k for k in sorted(spots) if 0 <= k < n]       # 미리 고른 나라들이 맨 앞 자리들을 받는다
            got = choose_starts(gmap, n, self.rng, [spots[k] for k in order], self.sites)
            rest = iter(got[len(order):])
            by = dict(zip(order, got))
            starts = [by[i] if i in by else next(rest) for i in range(n)]
        animals = list(self.rng.permutation(R.ANIMALS))
        self.nations = []
        for i, c in enumerate(colors):
            word, col, light = R.COLORS[c]
            name = names[i] if names and i < len(names) and names[i] else f'{word} {animals[i % len(animals)]}'
            self.nations.append(Nation(i, name, col, light))
        self._spawn_all(starts)
        tribes.assign(self)                                # 나라마다 부족 (시작 거점 둘레의 지형)
        from sim.companions import Companions
        self.companions = Companions(self)
        from sim.firetower import FireTowers
        self.fire = FireTowers(self)
        from sim.wildlife import Wildlife
        self.wild = Wildlife(self, np.random.default_rng([abs(int(seed)) & 0xFFFFFFFF, 7]))   # 야생 동물 (거점이 선 다음에: 거점 곁엔 안 생기게)
        from sim.diplomacy import Diplomacy
        self.diplo = Diplomacy(self)                       # 외교: 동맹과 관계
        self.trade = Trade(self)                           # 무역: 무역소와 행렬 (sim/trade.py)

    # ------------------------------------------------------------- 알림
    def say(self, text: str, to: int | None = None, skip=()) -> None:
        """알림을 쌓는다. to: 받는 나라 (None이면 모든 나라), skip: 빼는 나라들. 누가 읽을지는 조종자가 정한다."""
        last = self.messages[-1] if self.messages else None
        if last and last[0] == text and last[2] == to and self.time - last[1] < 5:
            return
        self.messages.append((text, self.time, to, tuple(skip)))

    # ------------------------------------------------------------- 시작
    def _spawn_all(self, starts) -> None:
        """나라마다 거점 하나와 병사들 (starts: 나라 순서대로 거점 자리)."""
        st = R.BUILD_STATS[R.HALL]
        for nat, (hy, hx) in zip(self.nations, starts):
            self.builds.add(nat.id, R.HALL, hx + 0.5, hy + 0.5, st['hp'], st['r'], prog=1.0)
            for kind, cnt in R.START_UNITS:
                for _ in range(cnt):
                    self._spawn_unit(nat.id, kind, hy, hx, 7)

    def _open_spot(self, y, x, dist, r):
        """(y, x)에서 dist쯤 떨어진, 반지름 r 안이 모두 땅이고 다른 건물이 없는 자리."""
        m = self.map
        for _ in range(60):
            a = self.rng.uniform(0, 2 * np.pi)
            yy, xx = int(y + np.sin(a) * dist), int(x + np.cos(a) * dist)
            if self.can_place(yy, xx, r):
                return yy, xx
        return None

    def can_place(self, y, x, r) -> bool:
        m = self.map
        if not (r <= y < m.H - r and r <= x < m.W - r):
            return False
        if not (m.land[y - r:y + r + 1, x - r:x + r + 1].all()):
            return False
        b = self.builds
        alive = b.alive[:b.n]
        if alive.any():
            d = np.hypot(b.x[:b.n][alive] - x, b.y[:b.n][alive] - y) - b.r[:b.n][alive]
            if d.min() < r + 2:
                return False
        return True

    def _spawn_unit(self, nid, kind, y, x, ring):
        m = self.map
        for _ in range(40):
            a = self.rng.uniform(0, 2 * np.pi)
            rr = ring + self.rng.uniform(0, 3)
            yy, xx = y + np.sin(a) * rr, x + np.cos(a) * rr
            if 0 <= yy < m.H and 0 <= xx < m.W and m.walk[int(yy), int(xx)]:
                return self.units.add(nid, kind, xx, yy, R.UNIT_STATS[kind]['hp'])
        return self.units.add(nid, kind, x + 0.5, y + 0.5, R.UNIT_STATS[kind]['hp'])

    # ------------------------------------------------------------- 명령
    def _busy_slots(self):
        u = self.units
        busy = np.zeros(len(self.fields.keys), bool)
        s = u.slot[:u.n][u.alive[:u.n] & (u.slot[:u.n] >= 0)]
        busy[s] = True
        return busy

    def _route(self, ids, y, x):
        spot = self.fields.snap(y, x)
        if spot is None:
            return -1
        u = self.units
        sy, sx = u.y[ids].astype(np.int64), u.x[ids].astype(np.int64)
        return self.fields.get(spot[0], spot[1], sy, sx, self._busy_slots())

    def _split(self, ids, y, x):
        """걸어서 갈 수 있는 병사와 바다를 건너야 하는 병사. 반환: (걸어갈 병사, [(병사, 출발 땅)], 도착 땅)."""
        m, u = self.map, self.units
        spot = self.fields.snap(y, x, 12)
        if spot is None:
            return ids, [], 0
        dst = int(m.comp[spot])
        comps = m.comp[u.y[ids].astype(int), u.x[ids].astype(int)]
        near = ids[comps == dst]
        far = [(ids[comps == c], int(c)) for c in np.unique(comps[comps != dst]) if c > 0]
        # 같은 땅이어도 멀면 걷기와 배(그 땅의 항구에서)를 견주어 배가 10% 넘게 빠르면 배로 (어림 오차만큼 여유)
        if len(near) and np.hypot(u.y[near].mean() - y, u.x[near].mean() - x) > FERRY_CHECK:
            est = self.fleet.ferry_time(near, y, x, dst, self.routes)
            if est is not None and est[0] < est[1] * 0.9:
                self.say(f'배로 가는 길이 더 빠릅니다 (걸어서 {est[1]:.0f}초 → 배로 {est[0]:.0f}초)', to=int(u.own[near[0]]))
                far.append((near, dst))
                near = near[:0]
        return near, far, dst

    def order_move(self, ids, y, x, attack: bool = False, ferry: bool = True) -> bool:
        """ferry: 바다 건너면 나룻배를 타게 한다 (나룻배가 병사를 항구로 부를 때는 False: 서로 부르며 끝없이 돌지 않게)."""
        ids = self._mine(ids)
        if len(ids) == 0:
            return False
        self.wild.release(ids)
        u = self.units
        can = self.k_fly[u.kind[ids]]
        if can.any():                                # 날 수 있는 병사 (용기사): 물을 건너야 하면 날고, 같은 땅이면 걷는다
            fl = ids[can]
            air = self._must_fly(fl, y, x)
            up, walk = fl[air], fl[~air]
            u.air[up] = True
            u.state[up] = AMOVE if attack else MOVE
            u.tx[up], u.ty[up] = x, y
            u.slot[up] = u.tgt[up] = u.tgb[up] = u.bld[up] = -1
            if len(walk):
                s = self._route(walk, y, x)
                if s >= 0:
                    u.state[walk] = AMOVE if attack else MOVE
                    u.slot[walk] = s
                    u.tgt[walk] = u.tgb[walk] = u.bld[walk] = -1
            ids = ids[~can]
            if len(ids) == 0:
                return True
        ids, far, dst = self._split(ids, y, x) if ferry else (ids, [], None)
        ok = False
        for group, src in far:                       # 바다 건너: 나룻배를 타고 간다
            ok |= self.fleet.ferry(group, y, x, ('move', attack, y, x), src, dst)
        if len(ids) == 0:
            return ok
        s = self._route(ids, y, x)
        if s < 0:
            return False
        u = self.units
        u.state[ids] = AMOVE if attack else MOVE
        u.slot[ids] = s
        u.tgt[ids] = u.tgb[ids] = u.bld[ids] = -1
        return True

    def calm_between(self, a, b) -> None:
        """동맹을 맺었다: 서로를 노리던 병사들은 그만둔다."""
        u, bb = self.units, self.builds
        n = u.n
        for x, y in ((a, b), (b, a)):
            mine = np.flatnonzero(u.alive[:n] & (u.own[:n] == x))
            if not len(mine):
                continue
            t, tb = u.tgt[mine], u.tgb[mine]
            bad = ((t >= 0) & (u.own[np.maximum(t, 0)] == y)) | ((tb >= 0) & (bb.own[np.maximum(tb, 0)] == y))
            ids = mine[bad]
            if len(ids):
                u.tgt[ids] = u.tgb[ids] = -1
                u.state[ids[u.state[ids] == ATTACK]] = IDLE

    def order_attack(self, ids, unit=-1, building=-1) -> None:
        ids = self._mine(ids)
        if len(ids) == 0:
            return
        own = int(self.units.own[ids[0]])
        tgt_own = int(self.units.own[unit]) if unit >= 0 else int(self.builds.own[building])
        if self.diplo.allied(own, tgt_own):                 # 동맹은 칠 수 없다 (먼저 동맹을 깨야)
            self.say('동맹은 공격할 수 없습니다 (먼저 동맹을 깨세요)', to=own)
            return
        self.wild.release(ids)
        u, b = self.units, self.builds
        ty, tx = (u.y[unit], u.x[unit]) if unit >= 0 else (b.y[building], b.x[building])
        can = self.k_fly[u.kind[ids]]
        if unit >= 0 and u.air[unit]:                # 날고 있는 적: 근접 병사는 칠 수 없다
            ids = ids[self.k_ranged[u.kind[ids]] | can]
            can = self.k_fly[u.kind[ids]]
        if can.any():                                # 용기사: 물 건너면 날아서 쫓고, 같은 땅이면 걸어서
            fl = ids[can]
            air = self._must_fly(fl, ty, tx)
            up, walk = fl[air], fl[~air]
            u.air[up] = True
            u.slot[up] = -1
            if len(walk):
                u.slot[walk] = self._route(walk, ty, tx)
            u.state[fl] = ATTACK
            u.tgt[fl], u.tgb[fl], u.bld[fl] = unit, building, -1
            ids = ids[~can]
        if len(ids) == 0:
            return
        ids, far, dst = self._split(ids, ty, tx)
        for group, src in far:
            self.fleet.ferry(group, ty, tx, ('attack', unit, building), src, dst)
        if len(ids) == 0:
            return
        s = self._route(ids, ty, tx)
        u.state[ids] = ATTACK
        u.slot[ids] = s
        u.tgt[ids] = unit
        u.tgb[ids] = building
        u.bld[ids] = -1

    def _must_fly(self, ids, y, x):
        """날아야 하나: 용기사는 움직이거나 싸울 때 늘 난다."""
        return np.ones(len(ids), bool)

    def _lift(self) -> None:
        """용기사는 움직이거나 싸우는 동안 날고, 할 일 없이 멈춰 있으면 땅에 내려앉는다 (물 위면 떠 있다).
        땅에 있는 동안은 근접 병사에게도 맞는다. 맞으면 맞서 싸우느라 다시 날아오른다."""
        u, m = self.units, self.map
        n = u.n
        fly = u.alive[:n] & self.k_fly[u.kind[:n]]
        busy = (u.state[:n] != IDLE) | (u.tgt[:n] >= 0) | (u.tgb[:n] >= 0) | u.moving[:n]
        wet = ~m.walk[u.y[:n].astype(int).clip(0, m.H - 1), u.x[:n].astype(int).clip(0, m.W - 1)]
        u.air[:n] = fly & (busy | wet)

    def order_stop(self, ids) -> None:
        ids = self._mine(ids)
        self.wild.release(ids)
        u = self.units
        u.state[ids] = IDLE
        u.slot[ids] = u.tgt[ids] = u.tgb[ids] = u.bld[ids] = -1

    def _mine(self, ids):
        ids = np.asarray(ids, np.int64)
        return ids[self.units.alive[ids]] if len(ids) else ids

    def can_afford(self, nid, cost, sulfur=0) -> bool:
        return all(self.nations[nid].res[k] >= cost[k] for k in range(3)) and self.nations[nid].sulfur >= sulfur

    def _pay(self, nid, cost, sulfur=0) -> None:
        for k in range(3):
            self.nations[nid].res[k] -= cost[k]
        self.nations[nid].sulfur -= sulfur

    def place_building(self, nid, kind, y, x, ids, site=-1, quiet=False) -> int:
        """건물 자리를 잡고(비용을 내고) ids 병사들을 보내 짓게 한다. 반환: 건물 번호 (못 지으면 -1)."""
        st = R.BUILD_STATS[kind]
        if not self.can_afford(nid, st['cost'], st.get('sulfur', 0)):
            if not quiet:
                need = ', '.join([f'{R.RES_NAMES[k]} {st["cost"][k]}' for k in range(3) if st['cost'][k]]
                                 + ([f'유황 {st["sulfur"]}'] if st.get('sulfur') else []))
                self.say(f'{R.BUILD_NAMES[kind]}: 자원이 모자랍니다 ({need})', to=nid)
            return -1
        if site >= 0:
            s = self.sites[site]
            if s.building >= 0:
                if not quiet:
                    self.say('이미 건물이 있는 자원지입니다', to=nid)
                return -1
            y, x = s.y, s.x
        elif kind == R.HARBOR and not self.fleet.can_place_harbor(int(y), int(x)):
            if not quiet:
                self.say('항구는 바다에 맞닿은 해안에 지어야 합니다 (절벽은 안 됩니다)', to=nid)
            return -1
        elif kind != R.HARBOR and not self.can_place(int(y), int(x), st['r']):
            if not quiet:
                self.say('여기에는 지을 수 없습니다 (평평한 땅, 다른 건물과 떨어진 곳)', to=nid)
            return -1
        self._pay(nid, st['cost'], st.get('sulfur', 0))
        b = self.builds.add(nid, kind, x + 0.5, y + 0.5, st['hp'], st['r'], prog=0.0, site=site)
        if site >= 0:
            self.sites[site].building = b
        self.order_build(ids, b)
        return b

    def order_build(self, ids, b) -> None:
        ids = self._mine(ids)
        if len(ids) == 0:
            return
        self.wild.release(ids)
        ids = ids[~self.k_fly[self.units.kind[ids]]]          # 용기사는 짓지 않는다
        if len(ids) == 0:
            return
        ids, far, dst = self._split(ids, self.builds.y[b], self.builds.x[b])
        for group, src in far:
            self.fleet.ferry(group, self.builds.y[b], self.builds.x[b], ('build', b), src, dst)
        if len(ids) == 0:
            return
        s = self._route(ids, self.builds.y[b], self.builds.x[b])
        u = self.units
        u.state[ids] = BUILD
        u.slot[ids] = s
        u.bld[ids] = b
        u.tgt[ids] = u.tgb[ids] = -1

    def train(self, nid, hall, kind, quiet=False) -> bool:
        """거점에서 보병/궁수, 항구에서 전함(kind = R.WARSHIP)."""
        b = self.builds
        if kind == R.WARSHIP:
            st = dict(cost=R.WARSHIP_COST, time=R.WARSHIP_TIME)
            where, name = R.HARBOR, '전함'
        elif kind in R.TRAINABLE:
            st = R.UNIT_STATS[kind]
            where, name = R.HALL, R.UNIT_NAMES[kind]
        else:
            return False                                           # 기병은 훈련하지 않는다 (야생말을 길들인다)
        if not (b.alive[hall] and b.kind[hall] == where and b.own[hall] == nid and b.prog[hall] >= 1):
            return False
        if len(b.queue[hall]) >= 5:
            if not quiet:
                self.say('훈련 대기열이 가득 찼습니다', to=nid)
            return False
        if not self.can_afford(nid, st['cost']):
            if not quiet:
                need = ', '.join(f'{R.RES_NAMES[k]} {st["cost"][k]}' for k in range(3) if st['cost'][k])
                self.say(f'{name}: 자원이 모자랍니다 ({need})', to=nid)
            return False
        self._pay(nid, st['cost'])
        b.queue[hall].append([kind, st['time']])
        return True

    # ------------------------------------------------------------- 찾기
    def unit_ids(self, nid=None):
        """살아 있는 병사 (배에 탄 병사는 뺀다)."""
        u = self.units
        a = u.alive[:u.n] & ~u.aboard[:u.n]
        if nid is not None:
            a = a & (u.own[:u.n] == nid)
        return np.flatnonzero(a)

    def building_ids(self, nid=None, kind=None, done=None):
        b = self.builds
        a = b.alive[:b.n].copy()
        if nid is not None:
            a &= b.own[:b.n] == nid
        if kind is not None:
            a &= b.kind[:b.n] == kind
        if done is not None:
            a &= (b.prog[:b.n] >= 1) == done
        return np.flatnonzero(a)

    def unit_at(self, y, x, r=2.5, nid=None):
        ids = self.unit_ids(nid)
        if len(ids) == 0:
            return -1
        d = np.hypot(self.units.x[ids] - x, self.units.y[ids] - y)
        k = int(np.argmin(d))
        return int(ids[k]) if d[k] <= r else -1

    def building_at(self, y, x, nid=None):
        ids = self.building_ids(nid)
        if len(ids) == 0:
            return -1
        b = self.builds
        d = np.hypot(b.x[ids] - x, b.y[ids] - y) - b.r[ids]
        k = int(np.argmin(d))
        return int(ids[k]) if d[k] <= 1.0 else -1

    def site_at(self, y, x, r=6):
        best, bd = -1, r
        for s in self.sites:
            d = np.hypot(s.x - x, s.y - y)
            if d < bd:
                best, bd = s.id, d
        return best

    # ------------------------------------------------------------- 진행
    def update(self, dt, season_w=None) -> None:
        if season_w is not None:
            self.season_w = np.asarray(season_w, float)
        self.fields.wait()                          # 지난번에 맡긴 길찾기 계산을 받는다 (보통 이미 끝나 있다)
        if self.phase != 'play':
            return
        self._acc += dt
        while self._acc >= TICK:
            self._acc -= TICK
            self._tick(TICK)

    def _tick(self, dt) -> None:
        self.time += dt
        u, b, m = self.units, self.builds, self.map
        self._economy(dt)
        self._training(dt)
        climate.update(self, dt)                            # 기후 효과: 병사마다 이동·피해 배율, 더위·동상 (sim/climate.py)
        self.n_shots = step(dt, u.n, u.x, u.y, u.hp, u.own, u.kind, u.state, u.slot, u.tgt, u.tgb, u.bld, u.cd,
                            u.search, u.anim, u.moving, u.alive, u.aboard, u.tx, u.ty, u.slow, u.air,
                            b.n, b.x, b.y, b.kind, b.own, b.hp, b.r, b.prog, b.cd, b.alive,
                            self.k_speed, self.k_range, self.k_dmg, self.k_cd, self.k_sight, self.k_ranged,
                            self.k_terrain, self.k_charge, self.k_vs, self.k_splash,
                            m.walk, m.speed_mul, m.cover, self.fields.fields, self.fields.ready, R.TOWER, R.TOWER_RANGE, R.TOWER_DMG,
                            R.TOWER_CD, R.NEUTRAL, self.shots, self._builders,
                            self.diplo.friend, self.diplo.hurt, self.diplo.hits, b.last, u.passive, u.fx_speed, u.fx_take, u.fx_deal)
        if self.n_shots:                                    # 화면에 잠깐 그릴 공격 (화살, 칼부림)
            for row in self.shots[:self.n_shots].tolist():
                self.recent.append((self.time, *row))
        while self.recent and self.time - self.recent[0][0] > 0.3:
            self.recent.popleft()
        self._lift()                                        # 용기사: 움직이거나 싸울 때만 난다
        self.companions.update(dt)                          # 바위거북: 발 구르기, 낮은 포효, 껍질 숨기
        self.fire.update(dt)                                # 화염탑: 불을 뿜는다
        self.wild.update(dt)                                # 야생 동물, 길들이기 (병사가 움직인 다음에)
        # 짓기
        for i in np.flatnonzero(self._builders[:b.n]):
            if b.alive[i] and b.prog[i] < 1:
                st = R.BUILD_STATS[int(b.kind[i])]
                add = dt * self._builders[i] / st['work']
                b.prog[i] = min(b.prog[i] + add, 1.0)
                b.hp[i] = min(b.hp[i] + add * b.maxhp[i], b.maxhp[i])
                if b.prog[i] >= 1:
                    self.say(f'{R.BUILD_NAMES[int(b.kind[i])]} 완성', to=int(b.own[i]))
        self.fleet.update(dt)
        self.trade.update(dt)                               # 무역 행렬
        self.diplo.update(dt)                               # 외교: 관계, 동맹 기간, 배신자
        # 무너진 건물
        dead = np.flatnonzero(b.alive[:b.n] & (b.hp[:b.n] <= 0))
        for i in dead:
            storage.loot(self, i, int(b.last[i]))              # 거점·자원 건물: 그 몫을 마지막으로 친 나라에게
            b.alive[i] = False
            if b.kind[i] == R.HARBOR:
                self.fleet.harbor_lost(i)
            if b.site[i] >= 0:
                self.sites[b.site[i]].building = -1
            if b.own[i] < len(self.nations):
                self.say(f'{R.josa(R.BUILD_NAMES[int(b.kind[i])], "이", "가")} 무너졌습니다!', to=int(b.own[i]))
        self._slow += dt
        if self._slow >= 0.5:
            self._slow = 0.0
            self._drown()
            self.wild.drown()
            self._census()
        if self.on_tick is not None:                       # 조종자들의 차례 (AI가 생각한다: sim/match.py)
            self.on_tick(dt)

    def _economy(self, dt) -> None:
        u, b, w = self.units, self.builds, self.season_w
        storage.update_caps(self)                       # 자원 한도 (다 지은 거점·자원 건물)
        for nat in self.nations:
            nat.rate = [0.0, 0.0, 0.0]
            nat.sulfur_rate = 0.0
        for i in np.flatnonzero(b.alive[:b.n] & (b.prog[:b.n] >= 1)):
            nat = self.nations[b.own[i]]
            k = int(b.kind[i])
            if k == R.HALL:
                for r in range(3):
                    nat.rate[r] += R.HALL_YIELD[r]
            elif k == R.SULFUR_PIT and b.site[i] >= 0:      # 유황: 계절과 상관없이
                nat.sulfur_rate += R.SULFUR_YIELD * self.sites[b.site[i]].rich
            elif k in R.YIELD:
                s = self.sites[b.site[i]]
                res, base = R.YIELD[k]
                sf = float(np.dot(R.SEASON_YIELD[res], w))
                nat.rate[res] += base * s.rich * (1 + s.cold * (sf - 1))
        for nat in self.nations:                       # 난이도: AI의 자원 수입 배율
            if nat.bonus != 1.0:
                nat.rate = [r * nat.bonus for r in nat.rate]
        live = u.alive[:u.n]                           # 먹는 양: 병종마다 (기병은 말까지 먹어서 더)
        counts = np.bincount(u.own[:u.n][live], weights=self.k_upkeep[u.kind[:u.n][live]], minlength=len(self.nations))
        winter = 1 + 0.5 * w[3]
        for nat in self.nations:
            nat.rate[R.FOOD] -= counts[nat.id] * R.UPKEEP * winter
            for r in range(3):
                nat.res[r] += nat.rate[r] * dt
            nat.sulfur += nat.sulfur_rate * (nat.bonus if nat.bonus != 1.0 else 1.0) * dt
            nat.starving = nat.res[R.FOOD] < 0
            if nat.starving:
                nat.res[R.FOOD] = 0.0
            storage.clamp(nat)                          # 한도를 넘는 만큼은 버린다
        # 굶주림과 회복
        alive = np.flatnonzero(u.alive[:u.n])
        if len(alive):
            starve = np.zeros(256, bool)                       # 나라 번호 → 굶주림 (야생 동물은 굶지 않는다)
            starve[:len(self.nations)] = [n.starving for n in self.nations]
            starving = starve[u.own[alive]]
            u.hp[alive[starving]] -= R.STARVE * dt
            halls = self.building_ids(kind=R.HALL, done=True)
            if len(halls):
                hx, hy, ho = b.x[halls], b.y[halls], b.own[halls]
                d = np.hypot(u.x[alive][:, None] - hx[None], u.y[alive][:, None] - hy[None])
                near = ((d < 12) & (u.own[alive][:, None] == ho[None])).any(1)
                hmax = self.k_hp[u.kind[alive]]
                u.hp[alive[near]] = np.minimum(u.hp[alive[near]] + R.HEAL_NEAR_HALL * dt, hmax[near])
            fl = alive[self.k_fly[u.kind[alive]]]                 # 용기사: 눈 위에서 회복 (설원의 진지)
            if len(fl):
                on = m_snow(self.map)[u.y[fl].astype(int), u.x[fl].astype(int)]
                rate = np.where(on, R.HEAL_ON_SNOW, R.HEAL_RIDER)       # 어디서든 회복, 눈 위에서는 더 빨리
                u.hp[fl] = np.minimum(u.hp[fl] + rate * dt, self.k_hp[u.kind[fl]])
            u.alive[alive[u.hp[alive] <= 0]] = False

    def _training(self, dt) -> None:
        b = self.builds
        for i in self.building_ids(done=True):
            q = b.queue[i]
            if not q:
                continue
            q[0][1] -= dt
            if q[0][1] <= 0:
                kind = q.pop(0)[0]
                if kind == R.WARSHIP:
                    self.fleet.launch_warship(int(b.own[i]), i)
                    self.say('전함 완성', to=int(b.own[i]))
                else:
                    self._spawn_unit(int(b.own[i]), kind, float(b.y[i]), float(b.x[i]), b.r[i] + 2)

    def _drown(self) -> None:
        u, m = self.units, self.map
        a = np.flatnonzero(u.alive[:u.n] & ~u.aboard[:u.n])
        a = a[~u.air[a]]                                       # 날고 있으면 빠지지 않는다
        wet = a[~m.walk[u.y[a].astype(int), u.x[a].astype(int)]]
        up = wet[self.k_fly[u.kind[wet]]]                      # 용기사는 발밑 얼음이 녹으면 날아오른다
        u.air[up] = True
        wet = wet[~self.k_fly[u.kind[wet]]]
        if len(wet):
            u.alive[wet] = False
            for o, c in zip(*np.unique(u.own[wet], return_counts=True)):
                if o < len(self.nations):
                    self.say(f'얼음이 녹아 병사 {int(c)}명이 물에 빠졌습니다', to=int(o))

    def ruin(self, nid: int) -> None:
        """그 나라의 병사·건물·배를 모두 허문다 (항복). 다음 걸음의 정리(_census)에서 망한 나라가 된다."""
        u, b = self.units, self.builds
        u.hp[:u.n][u.alive[:u.n] & (u.own[:u.n] == nid)] = -1e9      # 회복보다 크게: 거점 곁 회복이 먼저 돌아도 살아나지 않게
        b.hp[:b.n][b.alive[:b.n] & (b.own[:b.n] == nid)] = -1e9
        for boat in self.fleet.boats:
            if boat.alive and boat.own == nid:
                self.fleet._sink(boat)

    def _census(self) -> None:
        u, b = self.units, self.builds
        nu = np.bincount(u.own[:u.n][u.alive[:u.n]], minlength=R.NEUTRAL + 1)
        done = b.alive[:b.n] & (b.prog[:b.n] >= 1)                     # 짓다 만 건물은 나라를 지켜 주지 못한다
        nb = np.bincount(b.own[:b.n][done], minlength=len(self.nations))
        nh = np.bincount(b.own[:b.n][done & (b.kind[:b.n] == R.HALL)], minlength=len(self.nations))
        for nat in self.nations:
            nat.n_units, nat.n_buildings = int(nu[nat.id]), int(nb[nat.id])
            if nat.alive and nat.n_units == 0 and nh[nat.id] == 0:      # 거점과 병사를 모두 잃으면 (자원지만 남아도 할 수 있는 게 없다)
                nat.alive = False
                for i in np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] == nat.id)):   # 남은 건물(자원지, 망루, 공사장)은 허물어진다
                    b.alive[i] = False
                    if b.site[i] >= 0:
                        self.sites[b.site[i]].building = -1
                self.say('나라를 잃었습니다', to=nat.id)
                self.say(f'{R.josa(nat.name, "이", "가")} 멸망했습니다', skip=(nat.id,))
        # 판 끝: 나라가 하나만 남으면 (누가 조종하든, 동맹이든 아니든). 조종자가 없는 나라는 세지 않는다
        active = [nat.id for nat in self.nations if nat.alive and not nat.idle]
        if self.phase == 'play' and len(self.nations) > 1 and len(active) <= 1:
            self.phase = 'over'
            self.winner = active[0] if active else None
            if self.winner is not None:
                self.say(f'{R.josa(self.nations[self.winner].name, "이", "가")} 이겼습니다!', skip=(self.winner,))
                self.say('승리! 마지막까지 남았습니다', to=self.winner)
