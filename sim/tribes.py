"""부족과 기후 지역 (docs/ECONOMY_PLAN.md 4장).

부족: 판을 시작할 때 나라마다 시작 거점 자리로 한 번 정한다 (그 뒤로 바뀌지 않는다).
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
