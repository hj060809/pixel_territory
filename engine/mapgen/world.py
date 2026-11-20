"""큰 구조부터 작은 구조 순서로 만드는 지형 생성 (WorldGenerator).

1. 땅 모양 (stages.landmass): 땅덩어리들이 육지 비율을 나눠 가지며 자라나고, 사이는 해협으로 떨어진다.
   지도 가장자리와 이어진 물만 바다, 육지에 갇힌 물은 호수가 된다.
2. 높이 (stages.elevation): 해안에서 내륙으로 갈수록 높아지는 바탕 + 산맥 + 작은 언덕 + 호수 분지.
   바다는 얕은 대륙붕을 지나 깊어진다.
3. 침식 (stages.erosion): 수력 침식으로 골짜기를 판다 (해안 근처는 서서히 약하게).
4. 물 (stages.water): 움푹한 곳을 넘칠 때까지 채워 호수를 찾고, 물이 모이는 경로를 따라 강을 낸다.
5. 해안 종류 (stages.coast): 절벽, 모래사장, 석회암 해안, 석호.
6. 기후 (stages.climate): 위치에 따른 기후 영역의 기온과 습도. 셰이더가 이것으로 바이옴을 고른다 (앞 단계에 영향 없음).

크기는 어떤 값이든 되도록 모든 길이를 지도 크기에 대한 비율로 정한다 (기본 512).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import opensimplex
from numpy.typing import NDArray

from engine.mapgen.config import WorldConfig
from engine.mapgen.core.fields import ocean_of
from engine.mapgen.core.height_map import HeightMap
from engine.mapgen.stages.climate import climate
from engine.mapgen.stages.coast import shape_coasts
from engine.mapgen.stages.elevation import elevation
from engine.mapgen.stages.erosion import droplet_count, erode
from engine.mapgen.stages.landmass import land_shape
from engine.mapgen.stages.water import water_bodies


@dataclass
class World:
    height: HeightMap                       # 셰이더에 넘기는 높이맵 (0~1)
    ocean: NDArray[np.bool_]                # 바다
    lakes: NDArray[np.int32]                # 호수 번호 (0 = 호수 아님)
    rivers: NDArray[np.float32]             # 강 폭 (0 = 강 아님)
    flow: NDArray[np.float64]               # 각 칸에 모이는 물의 양
    config: WorldConfig
    coast: NDArray[np.uint8] | None = None  # 해안 종류 (engine.mapgen.coast_types), 셰이더에 넘긴다
    stages: dict = field(default_factory=dict)   # 단계별 중간 결과 (확인용)
    temperature: NDArray[np.float32] | None = None   # 기온 0~1 (셰이더의 바이옴용)
    moisture: NDArray[np.float32] | None = None      # 습도 0~1

    @property
    def climate(self):
        """셰이더에 넘기는 (기온, 습도). 없으면 None."""
        return None if self.temperature is None else (self.temperature, self.moisture)


class WorldGenerator:
    """설정 하나로 세계를 만든다. 같은 설정(시드 포함)이면 항상 같은 결과.

    모든 단계가 난수 생성기 하나(rng)와 노이즈 생성기 하나(gen)를 차례로 나눠 쓰므로,
    단계 순서가 결과의 일부다.
    """

    def __init__(self, cfg: WorldConfig, progress=None):
        self.cfg = cfg
        self.S = cfg.size
        self.rng = np.random.default_rng(cfg.seed)
        self.gen = opensimplex.OpenSimplex(cfg.seed)
        self.report = progress or (lambda text: None)       # progress(text): 단계가 바뀔 때마다 (로딩 화면용)
        self.stages = {}

    def run(self) -> World:
        cfg, S, rng, gen = self.cfg, self.S, self.rng, self.gen

        self.report('땅 모양 만드는 중... (1/6)')
        land, wx, wy = land_shape(cfg, rng, gen, S)
        ocean = ocean_of(~land)
        self.stages['land'] = land.copy()

        self.report('산과 높이 만드는 중... (2/6)')
        h, mountains = elevation(cfg, rng, gen, S, land, ocean, wx, wy)
        self.stages['elevation'] = h.copy()
        self.stages['mountains'] = mountains

        droplets = droplet_count(cfg)
        if droplets > 0:
            self.report(f'침식 중... (3/6, 물방울 {droplets:,}개)')
        h = erode(cfg, h, droplets)
        self.stages['eroded'] = h.copy()

        self.report('호수와 강 만드는 중... (4/6)')
        h, ocean, lakes, rivers, flow = water_bodies(cfg, h, S, gen, rng)
        self.stages['before_coast'] = h.copy()

        self.report('해안 다듬는 중... (5/6)')
        h, coast = shape_coasts(cfg, rng, gen, S, h, ocean, lakes)
        ocean = ocean_of(h < cfg.sea_level)

        self.report('기후 계산 중... (6/6)')
        temperature, moisture = climate(cfg, gen, S, h, ocean, lakes, rivers)
        return World(HeightMap(np.clip(h, 0.0, 1.0)), ocean, lakes, rivers, flow, cfg, coast, self.stages,
                     temperature, moisture)


def generate_world(cfg: WorldConfig | None = None, progress=None, **overrides) -> World:
    """progress(text): 단계가 바뀔 때마다 불린다 (뷰어 로딩 화면용)."""
    return WorldGenerator(replace(cfg or WorldConfig(), **overrides), progress).run()
