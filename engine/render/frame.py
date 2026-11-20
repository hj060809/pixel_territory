"""한 장면 합성: 화면에 보이는 지형 한 장 (최상위 뷰어의 compose와 같은 순서). 웹 셰이더의 정답 그림.

1. 계절 칠하기 (seasons.paint) — 식생 팔레트, 설선, 바다 얼음
2. 물결과 해안 거품 (water.apply) — 얼어 있는 바다 위에는 그리지 않는다
3. 낮밤 빛과 그림자, 물에 비친 하늘 (daylight.shade)
"""
from __future__ import annotations

import numpy as np

from engine.render.daylight import DayNightCycle
from engine.render.surface import Surface
from engine.render.water import WaterAnimator


class FrameRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.surface = Surface(scene)
        self.water = WaterAnimator(self.surface)
        self.cycle = DayNightCycle(auto=False)

    def render(self, hour: float, season=None, wave_t: float | None = 0.0) -> np.ndarray:
        """hour: 0~24시. season: (봄, 여름, 가을, 겨울) 비중 (None이면 계절 효과 없이).
        wave_t: 물결 시각(초). None이면 물결 없이."""
        sc = self.scene
        if season is not None:
            day = sc.seasons.paint(season)
            ice = sc.seasons.ice_mask
        else:
            day, ice = sc.day, None
        base = day
        if wave_t is not None:
            base = self.water.apply(day, wave_t)
            if ice is not None and ice.any():
                base[ice] = day[ice]            # 얼어 있는 바다 위에는 물결을 그리지 않는다
        self.cycle.hour = hour % 24
        return self.cycle.shade(base, self.surface)
