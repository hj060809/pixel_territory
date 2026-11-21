"""야생 동물과 길들이기.

동물 하나 = rules.WILDLIFE 표 한 줄 (지금은 말. 사막 동물 등은 같은 틀에 한 줄 더하면 된다):
- 사는 곳: 표의 habitat (말 = 넓고 평평한 초원, HABITATS가 지형에서 고른다). 작은 무리(group)로 넓게 흩어져 살고,
  수가 줄면 regrow초마다 새 무리가 생긴다 (겨울엔 거의 안 생긴다). 지도의 최대 수 = 사는 땅 넓이 / per_area (cap까지).
- 동물은 풀을 뜯거나 천천히 거닐다가, 병사가 가까이 오거나 싸움이 나면 달아난다.
- 길들이기: 병사를 고르고 동물을 오른쪽 클릭하면 (order_tame) 그 둘레 무리의 동물마다 가까운 병사 하나씩 간다.
  병사가 다가가는 동안 동물은 얌전히 기다리고, 닿으면 tame초 동안 길들인다 (병사 상태 TAME).
  다른 명령을 받거나, 맞거나, 죽으면 끊긴다 (동물은 놀라 달아나고, 진행은 처음부터).
- 다 길들이면 병사와 동물이 합쳐져 표의 mounts 병종이 된다 (보병 → 창기병, 궁수 → 기마궁수). 체력 비율은 그대로.
  기병이 죽으면 말도 함께 죽는다 (돌아오지 않는다).

화면: 동물은 상태 메시지의 동물 칸에 실린다 (server/protocol.py, 바뀐 것만).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from sim import rules as R
from sim.entities import IDLE, MOVE, TAME

GRAZE, WALK, FLEE, HELD, TAMING = range(5)    # 동물 상태 (화면에 그대로 간다)

FEAR = 4.5            # 길들이러 오지 않는 병사가 이만큼 가까이 오면 달아난다 (칸)
SHOT_FEAR = 9.0       # 싸움(칼부림, 화살)이 이만큼 가까이서 나면 달아난다
ROAM = 9.0            # 무리 자리에서 이만큼 안을 거닌다
WALK_SPEED, RUN_SPEED = 0.9, 5.5
REACH = 1.7           # 병사가 이만큼 가까이 오면 길들이기 시작
TAKEOVER = 7.0        # 길을 따라오던 병사가 이만큼 가까이 오면 곧장 동물에게 다가간다
STUCK = 4.0           # 곧장 다가가다 이만큼(초) 못 닿으면 그만둔다
SPAWN_CLEAR_B, SPAWN_CLEAR_U = 16.0, 12.0     # 새 무리는 건물·병사에서 이만큼 떨어진 곳에


def _grass(gmap):
    """넓고 평평한 풀밭 (둘레 15칸의 60% 넘게 평평한 풀밭인 칸)."""
    from sim.sites import GRASSY
    flat = np.isin(gmap.layers['pre'], GRASSY) & (gmap.base_cost <= 1.15) & gmap.walk
    if flat.sum() < 300:
        return np.zeros_like(flat)
    return flat & (ndimage.uniform_filter(flat.astype(np.float32), 15) > 0.6)


HABITATS = {'grass': _grass}    # 사는 땅 이름 → 지도에서 그 땅 고르기 (사막 동물이면 'desert' 하나 더)


class Animal:
    __slots__ = ('id', 'kind', 'x', 'y', 'hx', 'hy', 'tx', 'ty', 'mode', 't', 'dir', 'prog')

    def __init__(self, aid, kind, x, y, rng):
        self.id, self.kind = aid, kind
        self.x = self.hx = self.tx = x
        self.y = self.hy = self.ty = y
        self.mode, self.t = GRAZE, float(rng.uniform(0, 4))
        self.dir = 1 if rng.random() < 0.5 else -1
        self.prog = 0.0


class Tamer:
    __slots__ = ('aid', 'gen', 'slot', 'hp', 'stuck')

    def __init__(self, aid, gen, slot, hp):
        self.aid, self.gen, self.slot, self.hp, self.stuck = aid, gen, slot, hp, 0.0


class Wildlife:
    def __init__(self, world, rng):
        self.w = world
        self.rng = rng
        self.animals: dict[int, Animal] = {}
        self.tamers: dict[int, Tamer] = {}            # 병사 번호 → 길들이는 중
        self._next = 1
        self._fear_t = 0.0
        self.home, self.cap, self.timer = {}, {}, {}
        for k, a in R.WILDLIFE.items():
            m = HABITATS[a['habitat']](world.map)
            ys, xs = np.nonzero(m)
            self.home[k] = (ys, xs)
            self.cap[k] = int(min(a['cap'], len(ys) // a['per_area']))
            self.timer[k] = a['regrow']
            while self.count(k) < self.cap[k]:           # 처음엔 가득
                if not self._spawn_group(k):
                    break

    def count(self, kind) -> int:
        return sum(1 for a in self.animals.values() if a.kind == kind)

    # ------------------------------------------------------------- 태어나기
    def _spawn_group(self, kind) -> bool:
        ys, xs = self.home[kind]
        if not len(ys):
            return False
        w, rng = self.w, self.rng
        b, u = w.builds, w.units
        bl = np.flatnonzero(b.alive[:b.n])
        ul = np.flatnonzero(u.alive[:u.n])
        here = np.array([(a.y, a.x) for a in self.animals.values()]) if self.animals else np.zeros((0, 2))
        best, bs = None, -1e9
        for k in rng.integers(0, len(ys), 40):              # 후보 몇 곳 중 다른 동물과 가장 먼 곳 (넓게 흩어지게)
            y, x = float(ys[k]) + 0.5, float(xs[k]) + 0.5
            if len(bl) and np.min(np.hypot(b.x[bl] - x, b.y[bl] - y)) < SPAWN_CLEAR_B:
                continue
            if len(ul) and np.min(np.hypot(u.x[ul] - x, u.y[ul] - y)) < SPAWN_CLEAR_U:
                continue
            s = min(np.min(np.hypot(here[:, 0] - y, here[:, 1] - x)), 80.0) if len(here) else 80.0
            s += rng.uniform(0, 8)
            if s > bs:
                best, bs = (y, x), s
        if best is None:
            return False
        lo, hi = R.WILDLIFE[kind]['group']
        room = self.cap[kind] - self.count(kind)
        walk = w.map.walk
        for _ in range(min(int(rng.integers(lo, hi + 1)), room)):
            for _ in range(10):
                y, x = best[0] + rng.uniform(-3, 3), best[1] + rng.uniform(-3, 3)
                if 0 <= y < walk.shape[0] and 0 <= x < walk.shape[1] and walk[int(y), int(x)]:
                    break
            else:
                y, x = best
            an = Animal(self._next, kind, float(x), float(y), rng)
            an.hy, an.hx = best
            self.animals[an.id] = an
            self._next += 1
        return True

    # ------------------------------------------------------------- 명령
    def order_tame(self, nid, ids, aid, quiet=False) -> int:
        """ids 병사들로 aid 동물과 그 둘레 무리를 길들인다 (동물마다 가까운 병사 하나씩). 반환: 보낸 병사 수."""
        w, u = self.w, self.w.units
        a0 = self.animals.get(aid)
        if a0 is None:
            return 0
        info = R.WILDLIFE[a0.kind]
        comp = w.map.comp
        ids = np.asarray(ids, np.int64)
        ids = ids[u.alive[ids] & ~u.aboard[ids] & (u.own[ids] == nid)] if len(ids) else ids
        dst = comp[int(a0.y), int(a0.x)]
        ok = [int(i) for i in ids if int(u.kind[i]) in info['mounts'] and comp[int(u.y[i]), int(u.x[i])] == dst]
        if not ok:
            if not quiet and len(ids):
                names = ', '.join(R.UNIT_NAMES[k] for k in info['mounts'])
                far = any(int(u.kind[i]) in info['mounts'] for i in ids)
                w.say(f'{R.josa(info["name"], "은", "는")} 같은 땅에 있는 병사만 길들일 수 있습니다' if far
                      else f'{R.josa(info["name"], "은", "는")} {names}만 길들일 수 있습니다')
            return 0
        self.release(ok)                                     # 다른 동물을 길들이러 가던 병사도 새로 맡긴다
        busy = {t.aid for t in self.tamers.values()}
        herd = [a for a in self.animals.values() if a.kind == a0.kind and a.id not in busy
                and np.hypot(a.x - a0.x, a.y - a0.y) < 10 and comp[int(a.y), int(a.x)] == dst]
        herd.sort(key=lambda a: (a.id != aid, np.hypot(a.x - a0.x, a.y - a0.y)))
        if not herd:
            if not quiet:
                w.say(f'이미 길들이는 중인 {info["name"]}입니다')
            return 0
        free = list(ok)
        pairs = []
        for a in herd:
            if not free:
                break
            d = [np.hypot(u.x[i] - a.x, u.y[i] - a.y) for i in free]
            pairs.append((free.pop(int(np.argmin(d))), a))
        group = np.array([i for i, _ in pairs], np.int64)
        s = w._route(group, a0.y, a0.x)
        for i, a in pairs:
            near = np.hypot(u.x[i] - a.x, u.y[i] - a.y) <= TAKEOVER
            u.state[i] = TAME if near or s < 0 else MOVE
            u.slot[i] = -1 if near or s < 0 else s
            u.tgt[i] = u.tgb[i] = u.bld[i] = -1
            self.tamers[i] = Tamer(a.id, int(u.gen[i]), int(u.slot[i]), float(u.hp[i]))
            a.mode, a.t = HELD, 0.0
        if nid == 0 and not quiet:
            w.say(f'{info["name"]} {len(pairs)}마리를 길들이러 갑니다 ({R.WILDLIFE[a0.kind]["tame"]:.0f}초)')
        return len(pairs)

    def release(self, ids, scare=False) -> None:
        """이 병사들의 길들이기를 그만둔다 (다른 명령, 맞음, 죽음)."""
        u = self.w.units
        for i in [int(i) for i in np.atleast_1d(ids)]:
            t = self.tamers.pop(i, None)
            if t is None:
                continue
            if u.alive[i] and u.state[i] == TAME and u.gen[i] == t.gen:
                u.state[i] = IDLE
            a = self.animals.get(t.aid)
            if a is not None:
                a.prog = 0.0
                a.mode, a.t = GRAZE, 1.0
                if scare:
                    self._flee(a, float(u.x[i]), float(u.y[i]))

    def taming(self, aid) -> bool:
        return any(t.aid == aid for t in self.tamers.values())

    # ------------------------------------------------------------- 진행
    def update(self, dt: float) -> None:
        w = self.w
        winter = float(w.season_w[3])
        for k, info in R.WILDLIFE.items():                  # 새 무리 (겨울엔 거의 안 생긴다)
            if self.count(k) >= self.cap[k]:
                self.timer[k] = info['regrow']
                continue
            self.timer[k] -= dt * (1.0 - 0.9 * winter)
            if self.timer[k] <= 0:
                self.timer[k] = info['regrow']
                self._spawn_group(k)
        self._tame(dt)
        self._fear_t -= dt
        if self._fear_t <= 0:
            self._fear_t = 0.25
            self._scare()
        for a in self.animals.values():
            self._move(a, dt)

    def _tame(self, dt) -> None:
        w, u, m = self.w, self.w.units, self.w.map
        for i, t in list(self.tamers.items()):
            a = self.animals.get(t.aid)
            if a is None or not u.alive[i] or u.gen[i] != t.gen or u.aboard[i]:
                self.release([i])
                continue
            if u.hp[i] < t.hp - 1e-3:                       # 맞았다
                if u.own[i] == 0:
                    w.say('공격을 받아 길들이기를 멈췄습니다')
                self.release([i], scare=True)
                continue
            t.hp = float(u.hp[i])
            d = float(np.hypot(u.x[i] - a.x, u.y[i] - a.y))
            st = int(u.state[i])
            if st == MOVE and u.slot[i] == t.slot:
                if d <= TAKEOVER:                            # 다 왔다: 곧장 다가간다
                    u.state[i], u.slot[i] = TAME, -1
                continue
            if st == IDLE and d <= TAKEOVER * 2:            # 길 끝에 닿았다 (동물이 조금 옆에)
                u.state[i] = TAME
                st = TAME
            if st != TAME:                                   # 길이 막혔거나 다른 일을 맡았다
                self.release([i])
                continue
            if d > REACH:
                k = int(u.kind[i])
                sp = R.UNIT_STATS[k]['speed'] * float(m.speed_mul[int(u.y[i]), int(u.x[i])]) ** R.UNIT_STATS[k]['terrain']
                step = min(sp * dt, d - REACH * 0.8)
                nx, ny = u.x[i] + (a.x - u.x[i]) / d * step, u.y[i] + (a.y - u.y[i]) / d * step
                if m.walk[int(ny), int(nx)]:
                    u.x[i], u.y[i] = nx, ny
                    u.moving[i] = True
                    u.anim[i] += dt * sp * 1.2
                    t.stuck = 0.0
                else:
                    t.stuck += dt
                    if t.stuck > STUCK:
                        self.release([i])
                continue
            a.mode = TAMING
            a.dir = 1 if u.x[i] > a.x else -1                # 병사 쪽을 본다
            a.prog += dt / R.WILDLIFE[a.kind]['tame']
            if a.prog >= 1.0:
                self._mount(i, a)

    def _mount(self, i, a) -> None:
        """병사와 동물이 합쳐진다."""
        w, u = self.w, self.w.units
        old = int(u.kind[i])
        new = R.WILDLIFE[a.kind]['mounts'][old]
        ratio = float(u.hp[i]) / R.UNIT_STATS[old]['hp']
        u.kind[i] = new
        u.hp[i] = ratio * R.UNIT_STATS[new]['hp']
        u.x[i], u.y[i] = a.x, a.y
        u.state[i], u.slot[i] = IDLE, -1
        u.cd[i] = 0.0
        del self.tamers[i]
        del self.animals[a.id]
        if u.own[i] == 0:
            w.say(f'{R.josa(R.WILDLIFE[a.kind]["name"], "을", "를")} 길들였습니다: '
                  f'{R.josa(R.UNIT_NAMES[old], "이", "가")} {R.josa(R.UNIT_NAMES[new], "이", "가")} 되었습니다')

    def _flee(self, a, fx, fy) -> None:
        d = max(float(np.hypot(a.x - fx, a.y - fy)), 0.1)
        a.mode, a.t = FLEE, 1.6
        a.tx, a.ty = a.x + (a.x - fx) / d * 9, a.y + (a.y - fy) / d * 9

    def _scare(self) -> None:
        """길들이는 중이 아닌 동물: 가까운 병사나 싸움에서 달아난다."""
        free = [a for a in self.animals.values() if a.mode not in (HELD, TAMING)]
        if not free:
            return
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        if len(ids):
            ids = ids[[int(i) not in self.tamers for i in ids]]
        ax = np.array([a.x for a in free], np.float32)
        ay = np.array([a.y for a in free], np.float32)
        if len(ids):
            d = np.hypot(u.x[ids][None] - ax[:, None], u.y[ids][None] - ay[:, None])
            near = d.argmin(1)
            for j, a in enumerate(free):
                if d[j, near[j]] < FEAR:
                    k = ids[near[j]]
                    self._flee(a, float(u.x[k]), float(u.y[k]))
        hits = [(r[1], r[2]) for r in w.recent if w.time - r[0] < 0.3]
        if hits:
            hx = np.array(hits, np.float32)
            for a in free:
                if a.mode == FLEE:
                    continue
                dd = np.hypot(hx[:, 0] - a.x, hx[:, 1] - a.y)
                if dd.min() < SHOT_FEAR:
                    k = int(dd.argmin())
                    self._flee(a, float(hx[k, 0]), float(hx[k, 1]))

    def _move(self, a, dt) -> None:
        if a.mode in (HELD, TAMING):
            return
        rng, walk = self.rng, self.w.map.walk
        a.t -= dt
        if a.t <= 0:
            if a.mode == FLEE:                              # 다 달아났다: 여기가 새 무리 자리
                a.hx, a.hy = a.x, a.y
            if a.mode == GRAZE or a.mode == FLEE or rng.random() < 0.3:
                ang, r = rng.uniform(0, 2 * np.pi), rng.uniform(0, ROAM)
                a.tx, a.ty = a.hx + np.cos(ang) * r, a.hy + np.sin(ang) * r
                a.mode, a.t = WALK, float(rng.uniform(3, 6))
            else:
                a.mode, a.t = GRAZE, float(rng.uniform(2, 6))
        if a.mode == GRAZE:
            return
        dx, dy = a.tx - a.x, a.ty - a.y
        d = float(np.hypot(dx, dy))
        if d < 0.2:
            a.mode, a.t = GRAZE, float(rng.uniform(2, 5))
            return
        step = min((RUN_SPEED if a.mode == FLEE else WALK_SPEED) * dt, d)
        nx, ny = a.x + dx / d * step, a.y + dy / d * step
        if 0 <= nx < walk.shape[1] and 0 <= ny < walk.shape[0] and walk[int(ny), int(nx)]:
            a.x, a.y = float(nx), float(ny)
        else:                                               # 물가: 무리 자리 쪽으로 돌아선다
            a.tx, a.ty = a.hx, a.hy
            if a.mode == FLEE:
                a.mode = WALK
        if abs(dx) > 0.05:
            a.dir = -1 if dx < 0 else 1

    def drown(self) -> None:
        """얼음이 녹아 물 위에 남은 동물은 사라진다."""
        walk = self.w.map.walk
        for aid in [a.id for a in self.animals.values() if not walk[int(a.y), int(a.x)]]:
            for i, t in list(self.tamers.items()):
                if t.aid == aid:
                    self.release([i])
            del self.animals[aid]
