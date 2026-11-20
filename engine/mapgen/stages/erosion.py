"""3단계 침식: 물방울 수력 침식으로 내륙 골짜기를 판다.

해안 근처에서는 서서히 침식 전 지형으로 돌아간다. 그대로 두면 골마다 끝에 흙이 쌓여 해안이 톱니처럼 되고,
해안을 깎아 평평한 모래띠가 생긴다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.core.height_map import HeightMap


def droplet_count(cfg) -> int:
    """침식 물방울 수 (None이면 크기에 맞춰 자동: 512에서 30만)."""
    S = cfg.size
    return cfg.erosion_droplets if cfg.erosion_droplets is not None else int(300_000 * (S / 512) ** 2)


def erode(cfg, h, droplets):
    """침식한 높이 (droplets가 0 이하이면 그대로)."""
    if droplets <= 0:
        return h
    S = cfg.size
    before = h
    eroded = HeightMap(h).erode(droplets=droplets, seed=cfg.seed).map
    sea = cfg.sea_level
    was_land = before >= sea
    fade = np.clip(ndimage.distance_transform_edt(was_land) / (S * 0.03) - 0.3, 0, 1)
    h = before + (eroded - before) * fade
    return np.where(was_land, np.maximum(h, sea + 0.002), np.minimum(h, before))
