"""부족과 기후 지역 (docs/ECONOMY_PLAN.md 4장).

부족: 판을 시작할 때 나라마다 시작 거점 자리로 정한다. 다른 기후에 거점을 세우면 바꿀 수 있다 (Pioneer, 아래).
  시작 거점 둘레 RADIUS칸의 육지 중 설원 지역이 SHARE 이상 → 설원, 사막 지역이 SHARE 이상 → 사막,
  둘 다면 비율이 큰 쪽, 둘 다 아니면 온대. 설정 화면·대기실 미리보기도 같은 함수 (classify)를 쓴다.
기후 지역 (6단계 기후 효과도 이것을 쓴다):
  설원 지역 = 봄·가을에도 눈 (고정 설원)·얼음·툰드라. 겨울에만 눈이 덮이는 땅은 아니다.
  사막 지역 = 사막·모래언덕.
"""
from __future__ import annotations

import numpy as np

from engine.render import materials as S

TEMPERATE, SNOW, DESERT = range(3)
NAMES = ('온대', '설원', '사막')
RADIUS = 20
SHARE = 0.4


def zones(gmap) -> tuple[np.ndarray, np.ndarray]:
    """(설원 지역, 사막 지역): 땅 칸만. 지도마다 한 번 재어 둔다."""
    got = gmap.__dict__.get('_climate_zones')
    if got is not None:
        return got
    from sim.terrain import _SNOWY_LUT
    pre = gmap.layers['pre']
    base, _ = gmap.seasons.state(None)                       # 계절을 타지 않는 바탕 (봄·가을에도 남는 눈)
    snow = (_SNOWY_LUT[base] | np.isin(pre, (S.SNOW, S.SNOW_OLD, S.ICE, S.TUNDRA))) & gmap.land
    sand = np.isin(pre, (S.DESERT, S.DUNE)) & gmap.land & ~snow
    gmap.__dict__['_climate_zones'] = (snow, sand)
    return snow, sand


def classify(gmap, y: int, x: int) -> int:
    """(y, x)에 시작 거점이 있는 나라의 부족 (TEMPERATE / SNOW / DESERT)."""
    snow, sand = zones(gmap)
    H, W = snow.shape
    y0, y1, x0, x1 = max(y - RADIUS, 0), min(y + RADIUS + 1, H), max(x - RADIUS, 0), min(x + RADIUS + 1, W)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    disk = (yy - y) ** 2 + (xx - x) ** 2 <= RADIUS * RADIUS
    land = gmap.land[y0:y1, x0:x1] & disk
    n = int(land.sum())
    if n == 0:
        return TEMPERATE
    fs = int((snow[y0:y1, x0:x1] & disk).sum()) / n
    fd = int((sand[y0:y1, x0:x1] & disk).sum()) / n
    if max(fs, fd) < SHARE:
        return TEMPERATE
    return SNOW if fs >= fd else DESERT


def assign(world) -> None:
    """나라마다 부족 (첫 거점 자리로). 판을 만든 뒤 한 번."""
    from sim import rules as R
    b = world.builds
    for nat in world.nations:
        halls = world.building_ids(nat.id, R.HALL)
        nat.tribe = classify(world.map, int(b.y[halls[0]]), int(b.x[halls[0]])) if len(halls) else TEMPERATE
        nat.start_tribe = nat.tribe


class Pioneer:
    """개척 (부족 바꾸기): 다른 기후 지역에 거점을 다 지으면 그 기후의 부족으로 바꿀 기회 (카드: 지금 부족 유지 / 새 부족).
    - 거점의 기후는 classify (시작 부족과 같은 기준: 둘레 20칸 땅의 40%)로 다 지을 때 한 번 잰다.
    - 스스로 버린 기후 (바꾸며 떠난 옛 부족, 또는 유지를 골라 거절한 새 기후)는 nat.dropped에 올라 다시 뜨지 않는다.
    - 지금 부족 기후의 거점을 모두 잃으면 남은 거점이 가장 많은 기후의 부족이 된다 (같으면 버리지 않은 기후, 시작 기후 순).
      이렇게 잃은 기후는 버린 것이 아니라 다시 지으면 다시 고를 수 있다.
    - 기다리는 카드 (nat.offers: [(기후, 거점 번호, 거점 gen)])는 그 거점이 무너지면 사라진다 (버린 것은 아니다).
    version: 부족·카드가 바뀔 때마다 +1 (서버가 보낸다)."""

    def __init__(self, world):
        self.w = world
        self.zone: dict = {}                                     # (거점 번호, gen) → 기후
        self.version = 0

    def climate_of(self, i: int) -> int:
        b = self.w.builds
        key = (int(i), int(b.gen[i]))
        c = self.zone.get(key)
        if c is None:
            c = self.zone[key] = classify(self.w.map, int(b.y[i]), int(b.x[i]))
        return c

    def halls(self, nid: int) -> dict:
        """다 지은 거점의 기후마다 수."""
        from sim import rules as R
        out = {TEMPERATE: 0, SNOW: 0, DESERT: 0}
        for i in self.w.building_ids(nid, R.HALL, done=True):
            out[self.climate_of(int(i))] += 1
        return out

    def hall_done(self, i: int) -> None:
        """거점 i를 다 지었다: 다른 기후이고 버리지 않은 기후면 카드."""
        w, b = self.w, self.w.builds
        nid = int(b.own[i])
        if nid >= len(w.nations):
            return
        nat, c = w.nations[nid], self.climate_of(i)
        if c == nat.tribe or c in nat.dropped or any(o[0] == c for o in nat.offers):
            return
        nat.offers.append((c, int(i), int(b.gen[i])))
        self.version += 1
        w.say(f'{NAMES[c]} 지역에 거점을 세웠습니다: {NAMES[c]} 부족으로 바꿀 수 있습니다 (부족 버튼)', to=nid)

    def pick(self, nid: int, accept: bool) -> bool:
        """맨 앞 카드를 고른다: accept면 새 기후 부족이 되고 옛 부족은 버린다, 아니면 새 기후를 버린다."""
        nat = self.w.nations[nid]
        self._prune(nat)
        if not nat.offers:
            return False
        c = nat.offers.pop(0)[0]
        if accept:
            nat.dropped.append(nat.tribe)
            self.w.say(f'{NAMES[c]} 부족이 되었습니다 ({NAMES[nat.tribe]} 특성은 다시 고를 수 없습니다)', to=nid)
            nat.tribe = c
        else:
            nat.dropped.append(c)
            self.w.say(f'{NAMES[nat.tribe]} 부족을 지킵니다 ({NAMES[c]} 특성은 다시 고를 수 없습니다)', to=nid)
        self._prune(nat)
        self.version += 1
        return True

    def _prune(self, nat) -> bool:
        """더는 맞지 않는 카드를 뺀다 (거점이 무너졌거나, 이미 그 부족이거나, 버린 기후)."""
        b = self.w.builds
        keep = [o for o in nat.offers if b.alive[o[1]] and int(b.gen[o[1]]) == o[2] and o[0] != nat.tribe and o[0] not in nat.dropped]
        changed = len(keep) != len(nat.offers)
        nat.offers = keep
        return changed

    def halls_lost(self, owners) -> None:
        """거점이 무너진 나라들: 기다리던 카드를 정리하고, 지금 부족 기후의 거점이 하나도 없으면 바꾼다."""
        w = self.w
        for nid in set(int(o) for o in owners):
            if nid >= len(w.nations) or not w.nations[nid].alive:
                continue
            nat = w.nations[nid]
            if self._prune(nat):
                self.version += 1
            n = self.halls(nid)
            if n[nat.tribe] > 0 or sum(n.values()) == 0:
                continue
            c = max(n, key=lambda k: (n[k], k not in nat.dropped, k == nat.start_tribe))
            old, nat.tribe = nat.tribe, c
            self._prune(nat)
            self.version += 1
            w.say(f'{NAMES[old]} 지역의 거점을 모두 잃어 {NAMES[c]} 부족이 되었습니다', to=nid)
