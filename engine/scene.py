"""지도 한 장: 지형 생성(캐시) → 픽셀아트 렌더(계절 칠하기에 쓸 픽셀별 정보 포함) → 계절 칠하기 준비.

서버(게임 규칙)는 layers, seasons.state(), coast, climate를 쓰고,
화면(웹)은 이것을 구운 묶음(1단계 bake)을 받아 같은 계산을 셰이더로 한다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from engine.mapgen import generate_cached
from engine.render.seasons import SeasonPainter
from engine.render.shader import PixelArtShader


class TerrainScene:
    def __init__(self, height, coast=None, climate=None, shader: PixelArtShader | None = None):
        self.shader = sh = shader or PixelArtShader()
        self.height = height
        self.coast = coast                     # 해안 종류 지도 (engine.mapgen.coast_types)
        self.climate = climate                 # (기온, 습도)
        self.layers: dict = {}                 # 계절 칠하기에 쓸 픽셀별 정보 (shader.render 참고)
        self.day = sh.render(np.asarray(height, dtype=np.float64), coast, climate, layers=self.layers)
        self.seasons = SeasonPainter(self.layers, sh)
        self.H, self.W = self.day.shape[:2]

    @classmethod
    def load(cls, cfg, cache_dir: str | Path | None = '.cache', progress=print) -> 'TerrainScene':
        """설정으로 지도를 만들고(같은 설정이 캐시에 있으면 불러오고) 렌더한다."""
        hm, coast, climate = generate_cached(cfg, cache_dir, progress=progress)
        progress('렌더링 중...')
        return cls(hm, coast, climate)
