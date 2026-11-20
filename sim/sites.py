"""자원지: 지형에서 저절로 생긴다. 지도에 따로 그리지 않아도 숲은 숲으로, 들판은 들판으로 보인다.

- 식량: 비옥하고 평평한 풀밭 (강가일수록 풍부)
- 목재: 숲 (활엽수림, 열대우림, 침엽수림)
- 석재: 걸어 들어갈 수 있는 바위·자갈 비탈·석회암 지대
같은 종류가 넓게 모인 곳의 가운데를 고르고, 서로 일정 거리 이상 떨어지게 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from sim.rules import FOOD, STONE, WOOD
from engine.render import materials as S

GRASSY = (S.GRASS, S.GRASS_YELLOW, S.GRASS_DEAD, S.DRYGRASS, S.SAVANNA, S.STEPPE)
WOODS = (S.FOREST, S.RAINFOREST, S.TAIGA)
ROCKY = (S.ROCK, S.ROCK_WARM, S.ROCK_RED, S.SCREE, S.LIMESTONE)


@dataclass
class Site:
    id: int
    kind: int          # FOOD / WOOD / STONE
    x: int
    y: int
    rich: float        # 풍부함 (0.6 ~ 1.4 정도)
    cold: float        # 계절 폭 (추운 곳일수록 겨울에 덜 난다)
    building: int = -1  # 이 자리에 지은 건물 번호


def sites_for(gmap, map_seed: int) -> list[Site]:
    """이 지도의 자원지 (지도와 지도 시드만으로 정해진다). 같은 지도로 새 판을 열 때는 처음 찾은 것을 복사해 쓴다."""
    import copy
    cache = gmap.__dict__.setdefault('_sites_cache', {})
    if map_seed not in cache:
        cache[map_seed] = find_sites(gmap, np.random.default_rng(map_seed))
    return copy.deepcopy(cache[map_seed])


# 지도마다 종류별 최소 개수: 육지 넓이에 비례하는 목표의 절반, 아래 한도는 이만큼 (작은 섬 지도에서도 자원이 모자라지 않게)
MIN_FLOOR = {FOOD: 5, WOOD: 5, STONE: 3}

# 기준에 맞는 곳이 모자랄 때 '가장 비슷한 곳'을 고르는 재질 점수 (1 = 기준에 맞음)
_LIKE = {
    FOOD: {**{m: 1.0 for m in GRASSY}, S.MOSS: 0.6, S.COLD_STEPPE: 0.6, S.SHRUB: 0.6, S.DIRT: 0.5, S.MARSH: 0.4,
           S.TUNDRA: 0.35, S.FOREST: 0.3, S.RAINFOREST: 0.3, S.TAIGA: 0.3, S.SAND: 0.25},
    WOOD: {**{m: 1.0 for m in WOODS}, S.SHRUB: 0.8, S.MARSH: 0.6, S.SAVANNA: 0.5, S.GRASS: 0.45, S.GRASS_YELLOW: 0.4,
           S.MOSS: 0.4, S.STEPPE: 0.3, S.COLD_STEPPE: 0.3, S.DRYGRASS: 0.3, S.TUNDRA: 0.3, S.ALPINE: 0.25},
    STONE: {**{m: 1.0 for m in ROCKY}, S.ALPINE: 0.7, S.TUNDRA: 0.5, S.DIRT: 0.5, S.DESERT: 0.45, S.COLD_STEPPE: 0.4,
            S.SAND: 0.35, S.DUNE: 0.3, S.SNOW: 0.3, S.SNOW_OLD: 0.3},
}


def _like_score(gmap, kind, mat, walk):
    """기준과 얼마나 비슷한가 (0~1): 재질 점수를 주변 9칸으로 고르게 하고, 종류마다 지형을 조금 반영한다."""
    lut = np.full(256, 0.1, np.float32)
    for m, v in _LIKE[kind].items():
        lut[m] = v
    like = lut[mat] * walk
    if kind == FOOD:                                   # 평평하고 비옥할수록
        like = like * np.where(gmap.base_cost <= 1.3, 1.0, 0.5) * np.clip(0.5 + gmap.value, 0.5, 1.5) / 1.5
    elif kind == STONE:                                # 험할수록
        like = like * (0.7 + 0.3 * np.clip((gmap.base_cost - 1.0) / 1.5, 0, 1))
    return ndimage.uniform_filter(like.astype(np.float32), 9) * walk


def _spread(order, ys, xs, pool, npool, spacing, limit):
    """order 순서대로, 이미 고른 자리(pool[:npool])와 spacing 이상 떨어진 곳을 limit개까지. 반환: (고른 자리, npool)."""
    chosen = []
    for k in order:
        if len(chosen) >= limit:
            break
        p = np.array([ys[k], xs[k]], float)
        if npool and np.min(np.hypot(pool[:npool, 0] - p[0], pool[:npool, 1] - p[1])) < spacing:
            continue
        chosen.append(p)
        pool[npool] = p
        npool += 1
    return chosen, npool


def find_sites(gmap, rng, spacing: float = 30.0) -> list[Site]:
    mat = gmap.layers['pre']
    walk = gmap.walk_static & gmap.land
    # 크게 이어진 땅(다른 나라들이 시작하는 땅)과 같은 덩어리 위주로: 다른 섬에도 생기지만 덜
    rules = [
        (FOOD, np.isin(mat, GRASSY) & (gmap.base_cost <= 1.15), gmap.value, 1.0 / 5500),
        (WOOD, np.isin(mat, WOODS), None, 1.0 / 6500),
        (STONE, np.isin(mat, ROCKY), None, 1.0 / 11000),
    ]
    sites: list[Site] = []
    taken = np.zeros((0, 2))
    for kind, mask, weight, per_land in rules:
        want = max(3, int(gmap.land_count * per_land))
        need = min(want, max(MIN_FLOOR[kind], want // 2))          # 이 지도의 최소 개수
        pool = np.zeros((len(taken) + want, 2))          # 이미 고른 자리 (미리 잡은 배열에 채워 간다)
        pool[:len(taken)] = taken
        npool = len(taken)
        chosen, rich = [], []
        # 1. 기준에 맞는 곳: 같은 종류가 넓게 모인 곳의 가운데
        mask = mask & walk
        if mask.sum() >= 30:
            dens = ndimage.uniform_filter(mask.astype(np.float32), 13)        # 주변 13칸 안에 얼마나 모였나
            score = dens * (weight if weight is not None else 1.0)
            ys, xs = np.nonzero(mask & (dens > 0.45))
            if len(ys):
                order = np.argsort(-(score[ys, xs] * rng.uniform(0.8, 1.2, len(ys))))[:5000]
                chosen, npool = _spread(order, ys, xs, pool, npool, spacing, want)
                rich = [float(np.clip(score[int(y), int(x)] * (1.3 if kind == FOOD else 1.4), 0.6, 1.4)) for y, x in chosen]
        # 2. 모자라면 기준에 안 맞아도 가장 비슷한 곳 (그래도 모자라면 간격을 줄여서). 비슷한 곳은 덜 풍부하다
        if len(chosen) < need:
            like = _like_score(gmap, kind, mat, walk)
            ys, xs = np.nonzero(like > 0.05)
            if len(ys):
                fb = np.random.default_rng([kind, gmap.land_count])   # 따로 쓰는 난수 (다른 종류의 자리는 그대로)
                order = np.argsort(-(like[ys, xs] * fb.uniform(0.9, 1.1, len(ys))))[:20000]
                for gap in (spacing, spacing * 0.6):
                    more, npool = _spread(order, ys, xs, pool, npool, gap, need - len(chosen))
                    chosen += more
                    rich += [float(np.clip(0.4 + 0.5 * like[int(y), int(x)], 0.6, 1.0)) for y, x in more]
                    if len(chosen) >= need:
                        break
        for (y, x), r in zip(chosen, rich):
            y, x = int(y), int(x)
            sites.append(Site(len(sites), kind, x, y, r, float(gmap.cold[y, x])))
        if chosen:
            taken = np.vstack([taken, np.array(chosen)])
    return sites
