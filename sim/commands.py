"""플레이어 명령 해석: 화면에서 한 일(오른쪽 클릭, 건물 자리 클릭, 훈련 키)을 세계 명령으로 바꾼다.
데스크톱 판(최상위 game/app.py)의 _command / _place / _train과 같은 규칙이다. 서버가 이것으로 처리하고,
브라우저는 '어디를 클릭했는지'만 보낸다.

오른쪽 클릭 (병사):  적 병사 → 공격 / 야생 동물 → 그 무리를 길들이러 (동물마다 가까운 병사 하나씩) /
                     적 건물 → 공격 / 짓다 만 내 건물 → 거들기 /
                     빈 자원지 → 가까운 3명이 짓고 나머지는 곁을 지킨다 / 그 밖 → 이동 (A를 눌렀으면 공격하며 이동)
오른쪽 클릭 (전함):  적 배 → 쫓아가 공격 / 물 → 이동
오른쪽 클릭 (병사를 태운 나룻배):  물 → 그 자리로 가서 기다림 / 땅 → 가까운 해안에 내려 주고 병사는 그곳으로
"""
from __future__ import annotations

import numpy as np

from sim import rules as R

PLACE_KINDS = {'tower': R.TOWER, 'hall': R.HALL, 'harbor': R.HARBOR,
               'farm': R.FARM, 'lumber': R.LUMBER, 'quarry': R.QUARRY, 'sulfur': R.SULFUR_PIT,   # 농장~유황은 빈 자원지에
               'fire': R.FIRE_TOWER, 'fishery': R.FISHERY}
SITE_OF = {v: k for k, v in R.SITE_BUILDING.items()}                       # 건물 → 자원지 종류
TRAIN_KINDS = {'infantry': R.INFANTRY, 'archer': R.ARCHER, 'warship': R.WARSHIP}     # 기병은 훈련하지 않는다 (길들인다)


class PlayerCommands:
    def __init__(self, world, nid: int = 0):
        self.w = world
        self.nid = nid

    # ------------------------------------------------------------- 고른 것 확인
    def units(self, refs) -> np.ndarray:
        """[(칸, 세대)] → 지금도 살아 있고 내 것이며 배에 타지 않은 병사 칸들."""
        u = self.w.units
        out = [int(i) for i, g in refs
               if 0 <= int(i) < u.n and u.alive[i] and u.own[i] == self.nid and not u.aboard[i] and int(u.gen[i]) == int(g)]
        return np.array(out, np.int64)

    def building(self, ref, mine=True):
        if ref is None:
            return -1
        b = self.w.builds
        i, g = int(ref[0]), int(ref[1])
        if 0 <= i < b.n and b.alive[i] and int(b.gen[i]) == g and (not mine or b.own[i] == self.nid):
            return i
        return -1

    def ships(self, ids):
        return [s for s in (self.w.fleet.boat_by_id(int(i)) for i in ids) if s is not None and s.own == self.nid]

    # ------------------------------------------------------------- 오른쪽 클릭
    def command(self, unit_refs, ship_ids, x, y, attack=False, r=2.0) -> str | None:
        """반환: 화면에 표시할 명령 종류 ('attack' / 'tame' / 'build' / 'move' / 'amove' / 'ship' / None)."""
        w = self.w
        sel = self.units(unit_refs)
        boats = self.ships(ship_ids)
        ships = [s for s in boats if s.kind == 'warship']
        ferries = [s for s in boats if s.kind == 'ferry']
        shown = None
        if ferries and w.fleet.order_ferries(ferries, y, x):   # 병사를 태운 나룻배: 물이면 그 자리로, 땅이면 해안에 내려 준다
            shown = 'ship' if not (w.map.land[int(y), int(x)] if 0 <= int(y) < w.map.H and 0 <= int(x) < w.map.W else False) else 'move'
        if ships:
            foe = w.fleet.boat_at(y, x, max(3.0, r * 1.25))
            if foe is not None and w.diplo.foe(self.nid, foe.own):
                w.fleet.hunt(ships, foe)
                shown = 'attack'
            elif w.fleet.order_ships(ships, y, x):
                shown = 'ship'
            elif len(sel) == 0:
                w.say('전함은 물 위로만 갈 수 있습니다')
        if len(sel) == 0:
            return shown
        foe = w.unit_at(y, x, max(2.0, r))
        if foe >= 0 and w.diplo.foe(self.nid, int(w.units.own[foe])):
            w.order_attack(sel, unit=foe)
            return 'attack'
        a = self._animal_at(y, x, max(1.8, r))
        an = w.wild.animals.get(a) if a is not None else None
        if an is not None and an.unit >= 0 and an.mode in (5, 6):     # 잠들었거나 싸우는 사나운 동물: 친다
            w.order_attack(sel, unit=an.unit)
            return 'attack'
        if an is not None and not attack:
            return 'tame' if w.wild.order_tame(self.nid, sel, a) else None
        b = w.building_at(y, x)
        if b >= 0 and w.diplo.foe(self.nid, int(w.builds.own[b])):
            w.order_attack(sel, building=b)
            return 'attack'
        if b >= 0 and w.builds.prog[b] < 1:
            w.order_build(sel, b)
            return 'build'
        s = w.site_at(y, x, max(4.0, r * 1.25))
        if s >= 0 and w.sites[s].building < 0 and not attack:
            site = w.sites[s]
            builders = self._builders(sel, site.y, site.x)
            if w.place_building(self.nid, R.SITE_BUILDING[site.kind], 0, 0, builders, site=s) >= 0:
                rest = np.setdiff1d(sel, builders)
                if len(rest):                         # 나머지는 곁에서 지킨다
                    w.order_move(rest, site.y, site.x, attack=True)
                return 'build'
            return None
        if w.order_move(sel, y, x, attack=attack):
            return 'amove' if attack else 'move'
        return None

    def _animal_at(self, y, x, r):
        best, bd = None, r
        for a in self.w.wild.animals.values():
            big = 2.5 if a.unit >= 0 else 0.0                     # 큰 동물 (드래곤)은 넓게
            d = float(np.hypot(a.x - x, a.y - 0.4 - big * 0.5 - y)) - big
            if d < bd:
                best, bd = a.id, d
        return best

    def _builders(self, sel, y, x, k=3):
        """고른 병사 중 가장 가까운 몇 명이 짓는다."""
        u = self.w.units
        d = np.hypot(u.x[sel] - x, u.y[sel] - y)
        return sel[np.argsort(d)[:k]]

    # ------------------------------------------------------------- 건물 놓기 (하단 버튼 / 숫자 키)
    def place(self, kind_name, unit_refs, x, y) -> bool:
        """건물 자리를 클릭했다. 농장·벌목장·채석장은 그 가까이의 빈 자원지에.
        고른 병사가 있으면 그중 가까운 3명이, 없으면 가까운 쉬는 병사 3명이 짓는다."""
        w = self.w
        kind = PLACE_KINDS[kind_name]
        site = -1
        if kind in SITE_OF:
            site = self._free_site(SITE_OF[kind], y, x, 8.0)
            if site < 0:
                w.say(f'{R.josa(R.BUILD_NAMES[kind], "은", "는")} 빈 {R.SITE_NAMES[SITE_OF[kind]]} 자리에 지어야 합니다')
                return False
            y, x = w.sites[site].y, w.sites[site].x
        sel = self.units(unit_refs)
        if len(sel) == 0:
            sel = self._idle_near(y, x)
        if len(sel) == 0:
            w.say('지을 병사가 없습니다')
            return False
        builders = self._builders(sel, y, x, 3)
        if site >= 0:
            return w.place_building(self.nid, kind, 0, 0, builders, site=site) >= 0
        return w.place_building(self.nid, kind, int(y), int(x), builders) >= 0

    def _free_site(self, res, y, x, r) -> int:
        """(y, x)에서 r 안의 가장 가까운 빈 자원지 (res 종류)."""
        best, bd = -1, r
        for s in self.w.sites:
            if s.kind == res and s.building < 0:
                d = float(np.hypot(s.y - y, s.x - x))
                if d <= bd:
                    best, bd = s.id, d
        return best

    def _idle_near(self, y, x, k=3):
        """짓게 할 병사를 따로 고르지 않았을 때: 가까운 쉬는 병사 (없으면 가까운 아무 병사)."""
        from sim.entities import IDLE
        u = self.w.units
        mine = self.w.unit_ids(self.nid)
        if len(mine) == 0:
            return mine
        idle = mine[u.state[mine] == IDLE]
        pool = idle if len(idle) else mine
        return pool[np.argsort(np.hypot(u.x[pool] - x, u.y[pool] - y))[:k]]

    # ------------------------------------------------------------- 훈련 (Q 보병, W 궁수, E 전함)
    def train(self, kind_name, building_refs=()) -> bool:
        w, b = self.w, self.w.builds
        kind = TRAIN_KINDS[kind_name]
        chosen = [i for i in (self.building(r) for r in building_refs) if i >= 0 and b.prog[i] >= 1]
        if kind == R.WARSHIP:
            harbors = [i for i in chosen if b.kind[i] == R.HARBOR]
            return bool(harbors) and w.train(self.nid, harbors[0], R.WARSHIP)
        halls = [i for i in chosen if b.kind[i] == R.HALL] or list(w.building_ids(self.nid, R.HALL, done=True))
        if not halls:
            w.say('훈련할 거점이 없습니다')
            return False
        return w.train(self.nid, min(halls, key=lambda i: len(b.queue[i])), kind)

    def stop(self, unit_refs) -> None:
        self.w.order_stop(self.units(unit_refs))
