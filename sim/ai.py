"""AI 나라. 플레이어와 같은 명령만 쓴다. 나라마다 성향(공격성, 궁수 비율, 확장 욕심, 생각 간격)이 다르다.

생각할 때마다
1. 거점에서 병사를 훈련한다 (식량이 넉넉하면)
2. 가까운 빈 자원지에 병사 둘을 보내 건물을 짓는다 (모자란 자원 우선, 적이 가까운 곳은 피한다)
3. 다 못 지은 건물에 일손이 없으면 보낸다
4. 자원이 넉넉하면 먼 자원지 곁에 새 거점을, 석재가 모이면 망루를 세운다
5. 내 건물 근처에 적이 오면 쉬는 병사를 모두 보내 막는다
6. 쉬는 병사가 충분히 모이면 가장 가까운 적 건물을 치러 간다 (일부는 집에 남긴다)
"""
from __future__ import annotations

import numpy as np

from sim import rules as R
from sim.entities import AMOVE, BUILD, IDLE


class Bot:
    def __init__(self, nid: int, rng: np.random.Generator, difficulty: float = 1.0):
        self.id = nid
        self.rng = rng
        self.aggression = float(np.clip(rng.uniform(0.25, 0.9) + (difficulty - 1.0) * 0.6, 0.1, 1.0))
        self.archers = rng.uniform(0.2, 0.6)
        self.greed = rng.uniform(0.5, 1.0)          # 확장 욕심
        self.interval = rng.uniform(1.5, 2.5)
        self.wait = rng.uniform(0, self.interval)
        self.raid_at = 0.0

    def maybe_think(self, w, dt: float) -> None:
        self.wait -= dt
        if self.wait > 0:
            return
        self.wait = self.interval * self.rng.uniform(0.8, 1.2)
        nat = w.nations[self.id]
        if nat.alive:
            self.think(w, nat)

    def think(self, w, nat) -> None:
        u, b = w.units, w.builds
        mine = w.unit_ids(self.id)
        idle = mine[u.state[mine] == IDLE]
        halls = w.building_ids(self.id, R.HALL, done=True)
        # 1. 훈련
        want_q = 4 if nat.res[R.FOOD] > 400 else 2              # 넉넉하면 더 많이
        for h in halls:
            while len(b.queue[h]) < want_q:
                kind = R.ARCHER if self.rng.random() < self.archers else R.INFANTRY
                if nat.res[R.FOOD] < 45 or (nat.rate[R.FOOD] < 0 and nat.res[R.FOOD] < 150):
                    break
                if not (w.train(self.id, h, kind, quiet=True) or w.train(self.id, h, R.INFANTRY, quiet=True)):
                    break
        home = self._home(w)
        if home is None:
            if len(idle):
                self._attack(w, idle)
            return
        # 5. 방어
        threat = self._threat(w)
        if threat is not None and len(idle):
            w.order_move(idle, threat[0], threat[1], attack=True)
            return
        builders = mine[u.state[mine] == BUILD]
        # 3. 일손 없는 공사장
        for f in w.building_ids(self.id, done=False):
            if not (u.bld[builders] == f).any() and len(idle) >= 1:
                pick = self._nearest(w, idle, b.y[f], b.x[f], 2)
                w.order_build(pick, f)
                idle = np.setdiff1d(idle, pick)
        # 7. 길들이기: 집 가까이(같은 땅)에 야생 동물이 있으면 쉬는 병사 몇을 보낸다
        if len(idle) >= 4 and threat is None and self.rng.random() < 0.5:
            idle = self._tame(w, idle, home)
        # 2. 확장
        if len(builders) < 4 and len(idle) >= 3 and self.rng.random() < self.greed:
            site = self._pick_site(w, nat, home)
            if site is not None:
                kind = R.SITE_BUILDING[site.kind]
                pick = self._nearest(w, idle, site.y, site.x, 2)
                if w.place_building(self.id, kind, site.y, site.x, pick, site=site.id, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-1. 새 거점: 자원이 넉넉하면 거점에서 먼 내 자원지 곁에
        any_hall = len(w.building_ids(self.id, R.HALL)) > 0                     # 짓는 중인 것까지
        if (len(idle) >= (1 if not any_hall else 4) and len(halls) < 3
                and w.can_afford(self.id, R.BUILD_STATS[R.HALL]['cost']) and (not any_hall or self.rng.random() < 0.4)):
            camps = [c for c in w.building_ids(self.id, done=True) if b.kind[c] in (R.FARM, R.LUMBER, R.QUARRY)]
            if camps:
                if len(halls):
                    far = max(camps, key=lambda c: np.min(np.hypot(b.x[halls] - b.x[c], b.y[halls] - b.y[c])))
                    gap = np.min(np.hypot(b.x[halls] - b.x[far], b.y[halls] - b.y[far]))
                else:                                                            # 거점을 모두 잃었으면 다시
                    far, gap = camps[0], 99.0
                if gap > 35 or not any_hall:
                    spot = w._open_spot(b.y[far], b.x[far], self.rng.uniform(10, 14), 5)
                    if spot is not None:
                        pick = self._nearest(w, idle, spot[0], spot[1], 3)
                        if w.place_building(self.id, R.HALL, spot[0], spot[1], pick, quiet=True) >= 0:
                            idle = np.setdiff1d(idle, pick)
        # 4. 망루
        towers = len(w.building_ids(self.id, R.TOWER))
        camps = len(w.building_ids(self.id)) - len(halls) - towers
        if (len(idle) >= 3 and towers < 1 + camps // 3 and w.can_afford(self.id, R.BUILD_STATS[R.TOWER]['cost'])
                and self.rng.random() < 0.5):
            own_b = w.building_ids(self.id, done=True)
            c = int(self.rng.choice(own_b))
            spot = w._open_spot(b.y[c], b.x[c], self.rng.uniform(7, 11), 2)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.TOWER, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-1-1. 나룻배를 못 띄운 해안이 있으면 그 곁에 항구 (다른 바다로 가려면 그 바다의 항구가 필요하다)
        want = w.fleet.want_harbor.get(self.id)
        if (want is not None and len(idle) >= 2 and len(w.building_ids(self.id, R.HARBOR)) < 3
                and w.can_afford(self.id, R.BUILD_STATS[R.HARBOR]['cost'])):
            spot = self._harbor_near(w, want)
            w.fleet.want_harbor.pop(self.id, None)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.HARBOR, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-2. 항구: 바다 건너에 노릴 것(빈 자원지, 적)이 있는데 본거지 땅에 항구가 없으면 (배는 병사들이 있는 땅의 항구에서 탄다)
        if (not self._harbors_home(w, home) and len(idle) >= 2 and self.rng.random() < 0.35
                and w.can_afford(self.id, R.BUILD_STATS[R.HARBOR]['cost']) and self._overseas(w, home)):
            spot = self._harbor_spot(w, home)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.HARBOR, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-3. 전함: 항구가 있으면 몇 척, 쉬는 전함은 가까운 적 배를 쫓는다
        harbors = w.building_ids(self.id, R.HARBOR, done=True)
        ships = w.fleet.warships(self.id)
        if len(harbors) and len(ships) + sum(len(b.queue[h]) for h in harbors) < 1 + int(self.aggression * 2.5)                 and w.can_afford(self.id, R.WARSHIP_COST) and self.rng.random() < 0.3:
            w.train(self.id, int(harbors[0]), R.WARSHIP, quiet=True)
        for sh in ships:
            if sh.state == 'idle':
                foes = [o for o in w.fleet.boats if o.own != self.id and np.hypot(o.y - sh.y, o.x - sh.x) < 45]
                if foes:
                    w.fleet.hunt([sh], min(foes, key=lambda o: np.hypot(o.y - sh.y, o.x - sh.x)))
        # 6. 공격
        need = 8 + (1 - self.aggression) * 14 + w.time / 90
        if len(idle) >= need and w.time >= self.raid_at:
            keep = int(len(idle) * 0.25)
            self._attack(w, idle[keep:])
            self.raid_at = w.time + 25

    # ------------------------------------------------------------- 도움
    def _home(self, w):
        own = w.building_ids(self.id)
        if len(own) == 0:
            return None
        b = w.builds
        return float(b.y[own].mean()), float(b.x[own].mean())

    def _nearest(self, w, ids, y, x, k):
        d = np.hypot(w.units.x[ids] - x, w.units.y[ids] - y)
        return ids[np.argsort(d)[:k]]

    def _threat(self, w):
        u, b = w.units, w.builds
        own = w.building_ids(self.id)
        foes = np.flatnonzero(u.alive[:u.n] & (u.own[:u.n] != self.id))
        if len(own) == 0 or len(foes) == 0:
            return None
        d = np.hypot(u.x[foes][:, None] - b.x[own][None], u.y[foes][:, None] - b.y[own][None])
        close = d.min(1) < 22
        if not close.any():
            return None
        j = foes[close][0]
        return float(u.y[j]), float(u.x[j])

    def _tame(self, w, idle, home):
        u, comp = w.units, w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        best, bd = None, 45.0
        for a in w.wild.animals.values():
            if a.unit >= 0 or comp[int(a.y), int(a.x)] != hc or w.wild.taming(a.id):     # 사나운 동물은 노리지 않는다
                continue
            d = np.hypot(a.y - home[0], a.x - home[1])
            if d < bd:
                best, bd = a, d
        if best is None:
            return idle
        ok = idle[np.isin(u.kind[idle], list(R.WILDLIFE[best.kind]['mounts']))]
        pick = self._nearest(w, ok, best.y, best.x, 2) if len(ok) else ok
        if len(pick) and w.wild.order_tame(self.id, pick, best.id, quiet=True):
            idle = np.setdiff1d(idle, pick)
        return idle

    def _pick_site(self, w, nat, home):
        u = w.units
        foes = np.flatnonzero(u.alive[:u.n] & (u.own[:u.n] != self.id))
        need = np.array([nat.rate[R.FOOD] < 0.5, nat.res[R.WOOD] < 120, nat.res[R.STONE] < 60], float)
        best, bs = None, 1e9
        comp = w.map.comp
        hy, hx = int(home[0]), int(home[1])
        harbor = bool(w.fleet.harbors_on(self.id, comp[hy, hx]))      # 바다 건너는 이 땅에 항구가 있어야
        for s in w.sites:
            if s.building >= 0:
                continue
            far = comp[s.y, s.x] != comp[hy, hx]
            if far and not harbor:                   # 바다 건너는 항구가 있어야
                continue
            if not w.can_afford(self.id, R.BUILD_STATS[R.SITE_BUILDING[s.kind]]['cost']):
                continue
            if len(foes) and np.min(np.hypot(u.x[foes] - s.x, u.y[foes] - s.y)) < 18:
                continue
            d = np.hypot(s.y - home[0], s.x - home[1]) / (s.rich * (1 + need[s.kind])) * (1.8 if far else 1.0)
            if d < bs:
                best, bs = s, d
        return best

    def _overseas(self, w, home) -> bool:
        """바다 건너에 노릴 것이 있나 (빈 자원지, 또는 걸어서 갈 수 있는 적 건물이 없을 때 다른 땅의 적)."""
        comp = w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        if any(s.building < 0 and comp[s.y, s.x] != hc for s in w.sites):
            return True
        b = w.builds
        foes = np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] != self.id))
        if len(foes) == 0:
            return False
        same = comp[b.y[foes].astype(int), b.x[foes].astype(int)] == hc
        return not same.any()

    def _harbor_near(self, w, p):
        for r in range(2, 26, 2):
            for a in self.rng.permutation(np.linspace(0, 2 * np.pi, 24, endpoint=False)):
                y, x = int(p[0] + np.sin(a) * r), int(p[1] + np.cos(a) * r)
                if w.fleet.can_place_harbor(y, x) and w.map.comp[y, x] == w.map.comp[p[0], p[1]]:
                    return y, x
        return None

    def _harbors_home(self, w, home) -> list:
        """본거지 땅 위의 내 항구 (짓는 중 포함)."""
        b, comp = w.builds, w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        return [h for h in w.building_ids(self.id, R.HARBOR) if comp[int(b.y[h]), int(b.x[h])] == hc]

    def _harbor_spot(self, w, home):
        """본거지 땅의 내 건물 둘레 해안."""
        b, comp = w.builds, w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        own = [i for i in w.building_ids(self.id, done=True) if comp[int(b.y[i]), int(b.x[i])] == hc]
        if not own:
            return None
        for _ in range(4):
            c = int(self.rng.choice(own))
            for _ in range(80):
                a, r = self.rng.uniform(0, 2 * np.pi), self.rng.uniform(6, 30)
                y, x = int(b.y[c] + np.sin(a) * r), int(b.x[c] + np.cos(a) * r)
                if w.fleet.can_place_harbor(y, x) and comp[y, x] == hc:
                    return y, x
        return None

    def _attack(self, w, ids) -> None:
        b = w.builds
        foes = np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] != self.id))
        if len(foes) == 0:
            return
        cy, cx = w.units.y[ids].mean(), w.units.x[ids].mean()
        comp = w.map.comp
        same = comp[b.y[foes].astype(int), b.x[foes].astype(int)] == comp[int(cy), int(cx)]
        if same.any():
            foes = foes[same]
        d = np.hypot(b.x[foes] - cx, b.y[foes] - cy) * np.where(b.kind[foes] == R.HALL, 1.4, 1.0)
        t = foes[int(np.argmin(d))]
        w.order_move(ids, float(b.y[t]), float(b.x[t]), attack=True)
