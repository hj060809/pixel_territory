"""기본 지형 설정 (최상위 main.make_config와 같다: 설정 화면의 처음 값)."""
from __future__ import annotations

from engine.mapgen.config import WorldConfig


def default_config(size: int = 512, seed: int = 8767564, droplets: int | None = None) -> WorldConfig:
    return WorldConfig(land_ratio=0.8, size=size, seed=seed, erosion_droplets=droplets)
