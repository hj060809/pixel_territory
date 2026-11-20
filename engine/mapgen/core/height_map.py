"""높이맵 (0~1). 셰이더와 뷰어가 받는 형식."""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from engine.mapgen.core.erosion import erode_droplets


class HeightMap:
    def __init__(self, map: np.ndarray[tuple[int, int], np.dtype[np.float64]]):
        if np.max(map) > 1 or np.min(map) < 0:
            raise ValueError('height must be between 0 ~ 1')
        self._map = map
        self.width = map.shape[1]
        self.height = map.shape[0]

    @property
    def map(self) -> NDArray[np.float64]:
        return self._map

    def __getitem__(self, key):
        return self._map[key]

    def __array__(self, dtype=None, copy=None):
        return self._map if dtype is None else self._map.astype(dtype)

    @property
    def shape(self) -> tuple[int, int]:
        return self._map.shape

    def erode(
        self,
        droplets: int = 50_000,
        seed: int = 0,
        inertia: float = 0.05,          # 0이면 경사만 따라감, 1이면 원래 방향 유지
        capacity: float = 4.0,          # 물방울이 실을 수 있는 퇴적물 양 계수
        min_capacity: float = 0.01,     # 평지에서도 최소한 실을 수 있는 양
        deposit_rate: float = 0.3,      # 넘치는 퇴적물을 내려놓는 비율
        erode_rate: float = 0.3,        # 깎아내는 비율
        evaporate_rate: float = 0.01,   # 한 걸음마다 증발하는 물의 비율
        gravity: float = 4.0,
        max_steps: int = 30,            # 물방울 하나의 수명
        radius: int = 3,                # 깎을 때 영향을 주는 반경 (칸 단위)
    ) -> 'HeightMap':
        """물방울 기반 수력 침식. 원본은 그대로 두고 새 HeightMap을 반환한다."""
        h = self._map.astype(np.float64, copy=True)
        erode_droplets(h, droplets, seed, inertia, capacity, min_capacity, deposit_rate,
                       erode_rate, evaporate_rate, gravity, max_steps, radius)
        np.clip(h, 0.0, 1.0, out=h)
        return HeightMap(h)
