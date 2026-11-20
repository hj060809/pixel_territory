"""게임 규칙에 쓰는 지형 정보. 렌더 픽셀 하나 = 땅 한 칸.

- 걸어서 갈 수 있는 칸: 땅, 여울(좁은 물: 강, 좁은 해협, 작은 못), 얼어붙은 바다(겨울)
- 넓은 물(바다, 큰 호수)은 배로만 건넌다. 배는 강도 거슬러 올라간다.
- 칸마다
  - 비용: 걷는 데 드는 시간 (평지 1, 숲 1.5, 습지 1.8, 바위산 2.6, 눈 덮이면 더, 여울 2.5)
  - 가치: 비옥함 (강가·호숫가 평야가 가장 높고, 사막·툰드라·바위·얼음은 낮다). 식량 자원지의 풍부함
  - 엄폐: 숲 속은 화살을 덜 맞는다
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.coast_types import CLIFF
from engine.render import materials as S

# 재질 → (비용, 가치)
_RULES = {
    S.GRASS: (1.0, 1.0), S.GRASS_YELLOW: (1.0, 0.85), S.GRASS_DEAD: (1.0, 0.75), S.DRYGRASS: (1.0, 0.7),
    S.SAVANNA: (1.0, 0.8), S.STEPPE: (1.0, 0.6), S.COLD_STEPPE: (1.1, 0.4), S.MOSS: (1.1, 0.4),
    S.DIRT: (1.0, 0.5), S.SAND: (1.0, 0.4), S.DUNE: (1.2, 0.2), S.DESERT: (1.1, 0.15),
    S.FOREST: (1.5, 0.8), S.RAINFOREST: (1.7, 0.9), S.TAIGA: (1.5, 0.5), S.SHRUB: (1.3, 0.5),
    S.MARSH: (1.8, 0.6), S.TUNDRA: (1.3, 0.25), S.ALPINE: (1.6, 0.35),
    S.SCREE: (2.2, 0.15), S.LIMESTONE: (2.0, 0.15), S.ROCK: (2.6, 0.08), S.ROCK_WARM: (2.6, 0.08),
    S.ROCK_RED: (2.6, 0.08), S.SNOW: (3.0, 0.03), S.SNOW_OLD: (3.0, 0.03), S.ICE: (3.0, 0.02),
}
SNOWY = (S.SNOW, S.SNOW_OLD, S.ICE)
_SNOWY_LUT = np.zeros(256, bool)                  # 재질 번호 → 눈 덮였나 (np.isin보다 훨씬 빠르다)
_SNOWY_LUT[list(SNOWY)] = True
FORD_COST = 2.5
SEA_ICE_COST = 2.2


class GameMap:
    """scene: engine.scene.TerrainScene. 계절은 set_season(계절 비중)으로 정한다 (처음에는 눈·얼음 없는 상태)."""

    def __init__(self, scene):
        self.scene = scene
        self.H, self.W = scene.H, scene.W
        L = self.layers = scene.layers
        self.seasons = scene.seasons
        coast = scene.coast
        water = L['water'].astype(bool)
        self.water = water
        land = ~water

        # 넓은 물(배) / 좁은 물(여울: 걸어서 건넌다)
        disk = ndimage.generate_binary_structure(2, 1)
        wide = ndimage.binary_opening(water, disk, iterations=3)
        wide = ndimage.binary_dilation(wide, disk) & water
        self.ford = water & ~wide
        self.land = land
        self.walk_static = land | self.ford                       # 계절과 상관없이 걸어서 갈 수 있는 칸
        self.nav_static = water                                    # 배가 다닐 수 있는 칸 (얼면 빠진다)

        # 비용과 가치
        pre = L['pre'].astype(np.int32)
        cost = np.ones(pre.shape, np.float32)
        value = np.full(pre.shape, 0.5, np.float32)
        for m, (c, v) in _RULES.items():
            sel = pre == m
            cost[sel], value[sel] = c, v
        alt = L['alt']
        cost *= 1.0 + np.clip(alt - 0.35, 0, 1) * 0.8             # 높을수록 조금 더 비싸다
        # 민물(강·호수) 가까이는 비옥하다
        labels, n = ndimage.label(water)
        edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        ocean = np.isin(labels, edge[edge > 0])
        self.ocean = ocean & ~self.ford                          # 바다 (지도 가장자리와 이어진 넓은 물). 항구는 여기에만
        fresh = (water & ~ocean) | self.ford
        near_fresh = ndimage.distance_transform_edt(~fresh) if fresh.any() else np.full(pre.shape, 99.0)
        value *= 1.0 + 0.7 * np.clip(1 - near_fresh / 8.0, 0, 1)
        value[water] = 0.0
        cost[self.ford] = FORD_COST
        self.base_cost = cost
        self.value = value.astype(np.float32)
        self.land_count = int(land.sum())

        # 절벽 해안: 이 칸으로는 상륙할 수 없다
        if coast is not None:
            c = np.asarray(coast)[:self.H, :self.W]
            self.cliff = land & (c == CLIFF)
        else:
            self.cliff = np.zeros(pre.shape, bool)

        # 계절 폭 (겨울에 인구가 덜 느는 정도)
        self.cold = scene.seasons.amp.astype(np.float32)
        # 숲 속은 화살을 덜 맞는다
        self.cover = np.where(np.isin(pre, (S.FOREST, S.RAINFOREST, S.TAIGA)), 0.6,
                              np.where(np.isin(pre, (S.SHRUB, S.MARSH)), 0.85, 1.0)).astype(np.float32)
        self.ice = np.zeros(pre.shape, bool)
        self._apply(L['pre'].copy(), np.zeros(pre.shape, bool))

    def set_season(self, weights) -> None:
        """(봄, 여름, 가을, 겨울) 비중으로 눈과 바다 얼음을 정한다. 화면의 계절 칠하기와 같은 계산."""
        self.install_season(self.compute_season(weights))

    def compute_season(self, weights) -> dict:
        """계절에 맞는 새 지도 값들을 계산만 한다 (지금 지도는 건드리지 않는다).
        numpy 배열 연산뿐이라 서버는 이것을 보조 스레드에서 돌리고, 걸음 사이에 install_season으로 바꿔 끼운다."""
        mat, ice = self.seasons.state(weights)
        return self._compute(mat, ice, getattr(self, 'walk', None))

    def install_season(self, d: dict) -> None:
        """compute_season의 결과를 한 번에 바꿔 끼운다 (걸음 사이에서)."""
        if d['walk_changed']:
            self.walk_version = getattr(self, 'walk_version', 0) + 1
            self.comp = d['comp']
        for k in ('mat', 'cost', 'ice', 'walk', 'nav', 'speed_mul'):
            setattr(self, k, d[k])

    def _apply(self, mat, sea_ice) -> None:
        self.install_season(self._compute(mat, sea_ice, getattr(self, 'walk', None)))

    def _compute(self, mat, sea_ice, old_walk) -> dict:
        """눈 덮인 칸은 비싸지고(느려지고), 얼어붙은 바다는 걸어서 건널 수 있다.
        걸어갈 수 있는 칸이 바뀌면 walk_version이 올라간다 (길찾기 캐시가 새로 계산하게)."""
        snow_now = _SNOWY_LUT[mat] & self.land
        cost = np.where(snow_now, np.maximum(self.base_cost * 1.6, 3.0), self.base_cost).astype(np.float32)
        ice = sea_ice & self.water & ~self.ford
        cost[ice] = SEA_ICE_COST
        walk = self.walk_static | ice
        changed = old_walk is None or not np.array_equal(old_walk, walk)
        return {'mat': mat,                                      # 지금 재질 (눈 포함)
                'cost': cost, 'ice': ice, 'walk': walk, 'walk_changed': changed,
                'comp': ndimage.label(walk)[0] if changed else None,   # 걸어서 이어진 땅 덩어리
                'nav': self.nav_static & ~ice,
                'speed_mul': (1.0 / cost).astype(np.float32)}   # 걷는 속도 배율 (평지 1)
