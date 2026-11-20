"""4단계 물: 호수와 강.

1. 움푹한 곳을 넘칠 때까지 채워 호수를 찾는다 (작거나 너무 높은 웅덩이는 메운다)
2. 높은 곳부터 물을 흘려 많이 모이는 경로를 강으로
3. 강을 굽이치게 하고 범람원, 우각호, 삼각주를 만든다 (engine.mapgen.stages.rivers)
4. 강바닥과 우각호를 해수면 아래로 판다

셰이더는 '높이 < 해수면'이면 물로 칠하므로, 호수 바닥과 강바닥은 해수면 아래로 파서 표현한다.
깊이에 따라 물색이 달라서 바다(깊음) / 호수(중간) / 강(얕음)이 저절로 구분된다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.core.fields import ocean_of
from engine.mapgen.core.hydrology import flow_accumulate, priority_flood
from engine.mapgen.core.noise import fbm
from engine.mapgen.stages.rivers import RiverRefiner


def water_bodies(cfg, h, S, gen, rng):
    """반환: (고친 높이, 바다, 호수 번호, 강 폭, 물 모임)"""
    sea = cfg.sea_level
    ocean = ocean_of(h < sea)
    # 더 큰 세상을 잘라낸 지도이므로 물은 바다뿐 아니라 지도 테두리 밖으로도 빠져나갈 수 있다
    drain = ocean.copy()
    drain[0, :] = drain[-1, :] = drain[:, 0] = drain[:, -1] = True

    out, lakes = find_lakes(cfg, h, S, ocean, drain)
    flow, down, thr, river = trace_flow(cfg, gen, S, out, ocean, lakes, drain)

    # 굽이치는 강, 범람원, 우각호, 삼각주
    out, chan, chan_w, oxbow = RiverRefiner(cfg, rng, S, out, river, flow, down, thr, ocean, lakes).run()
    ocean = ocean_of(out < sea)                                   # 삼각주로 바다가 땅이 된 곳을 반영

    width_full = carve_channels(cfg, out, chan, chan_w, oxbow, ocean, lakes)
    return out, ocean, lakes, width_full.astype(np.float32), flow


def find_lakes(cfg, h, S, ocean, drain):
    """넘칠 때까지 채운 높이에서 채워진 깊이가 있는 곳이 호수 후보. 반환: (고친 높이, 호수 번호)"""
    sea = cfg.sea_level
    scale_area = (S / 512) ** 2
    filled = priority_flood(h, drain)
    depth = filled - h
    cand = ~ocean & (depth > 5e-4)
    lab, n = ndimage.label(cand)
    lakes = np.zeros((S, S), np.int32)
    out = h.copy()
    if n:
        idx = np.arange(1, n + 1)
        area = ndimage.sum_labels(np.ones_like(h), lab, idx)
        level = ndimage.maximum(filled, lab, idx)                 # 호수 수면 높이 (넘치는 높이)
        max_depth = ndimage.maximum(depth, lab, idx)
        keep = (area >= cfg.lake_min_area * scale_area) & (level <= sea + cfg.lake_max_level)
        new_id = np.zeros(n + 1, np.int32)
        new_id[idx[keep]] = np.arange(1, keep.sum() + 1)
        lakes = new_id[lab]

        is_lake = lakes > 0
        # 호수: 가장자리는 얕고 가운데는 깊게. 큰 호수일수록 깊다
        rel = depth / np.maximum(max_depth[lab - 1], 1e-6)
        big = np.clip(area[lab - 1] / (S * S * 0.01), 0, 1)
        out[is_lake] = sea - 0.012 - (0.03 + 0.07 * big[is_lake]) * rel[is_lake]
        # 작은 웅덩이나 너무 높은 웅덩이는 메워서 땅으로
        dry = cand & ~is_lake
        out[dry] = np.maximum(filled[dry], sea + 0.002)
    return out, lakes


def trace_flow(cfg, gen, S, out, ocean, lakes, drain):
    """높은 곳부터 물을 흘려 각 칸에 모이는 양을 센다. 반환: (물 모임, 내려가는 칸, 강 기준량, 강 칸)"""
    active = ~ocean
    # 평지에서 물이 출구로 일직선으로 가지 않게, 흐름 계산에만 아주 작은 기복을 더한다
    meander = fbm(gen, S, S * 0.02, 3, 90.0) * 4e-4
    flow_src = priority_flood(out + meander, drain)               # 메운 뒤 다시 채워서 끊김 없이 흐르게
    order = np.argsort(-flow_src.ravel(), kind='stable')
    flow, down = flow_accumulate(flow_src, order, active)
    thr = cfg.river_threshold * S * S
    river = (flow >= thr) & ~ocean & (lakes == 0)
    return flow, down, thr, river


def carve_channels(cfg, out, chan, chan_w, oxbow, ocean, lakes):
    """강바닥과 우각호를 해수면 아래로 판다 (out을 고친다). 반환: 칸마다 강 폭."""
    sea = cfg.sea_level
    # 셰이더는 땅에 닿은 물을 거품으로 칠하므로 최소 3픽셀 폭으로 파서 가운데에 물색이 보이게 하고,
    # 넓은 강은 더 넓힌다
    keep_out = ocean | (lakes > 0)
    channel = ndimage.binary_dilation(chan) & ~keep_out
    for r in range(2, cfg.river_max_width + 1):
        wide = chan & (chan_w >= r)
        if wide.any():
            channel |= ndimage.binary_dilation(wide, iterations=r) & ~keep_out
    width_full = ndimage.grey_dilation(chan_w, size=3) * channel
    out[channel] = np.minimum(out[channel], sea - 0.006 - 0.004 * width_full[channel])

    # 우각호: 같은 이유로 3픽셀 폭으로, 강과는 한 칸 이상 떨어지게
    ox = ndimage.binary_dilation(oxbow) & ~ndimage.binary_dilation(channel, iterations=2) & ~keep_out
    out[ox] = np.minimum(out[ox], sea - 0.012)
    return width_full
