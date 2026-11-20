"""2단계 높이: 해안에서 내륙으로 갈수록 높아지는 바탕 + 산맥 + 작은 언덕 + 호수 분지.

- 산맥은 릿지드 멀티프랙탈(가지처럼 갈라지는 능선)을 판 경계 근처와 '산이 생기는 지역'에서만 세우고,
  능선이 촘촘히 모인 곳은 두꺼운 산괴가 되게 한다. 해안에서 바로 솟지 않고 내륙으로 들어가며 솟는다.
- 작은 섬은 큰 땅덩어리만큼 높이 솟지 않는다.
- 내륙 저지대에 크기가 제각각인 그릇을 파서 호수 자리를 만든다.
- 마지막에 0~1 높이로 바꾼다: 육지는 해수면 위, 바다는 얕은 대륙붕을 지나 깊어진다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.core.noise import fbm, normalize, sample


def elevation(cfg, rng, gen, S, land, ocean, wx, wy):
    """반환: (0~1 높이, 산맥 세기 0~1)"""
    d_in = ndimage.distance_transform_edt(land) / S               # 해안에서 내륙까지 거리 (비율)
    d_out = ndimage.distance_transform_edt(~land) / S             # 해안에서 바다 쪽 거리

    base = 0.25 * (1.0 - np.exp(-d_in / 0.10))                   # 내륙일수록 완만하게 높아진다
    size_f = _island_size_factor(land, d_in)
    mount = mountains(cfg, rng, gen, S, land, d_in, wx, wy)
    # 언덕은 해안까지 깔아서 해안 사면이 고른 경사가 되지 않게 (고른 경사는 침식이 평행한 골을 판다)
    hills = (fbm(gen, S, S * 0.05, 5, 60.0) * 0.5 + 0.5) * np.clip(0.35 + d_in / 0.03, 0, 1)
    elev = (base + mount * 0.75 * cfg.mountain_height + hills * cfg.hill_height) * size_f

    _dig_lake_basins(cfg, rng, gen, S, elev, land, d_in, mount, size_f)
    return _to_height(cfg, gen, S, elev, land, ocean, d_out), mount


def _island_size_factor(land, d_in):
    """작은 섬은 큰 땅덩어리만큼 높이 솟지 않게 (덩어리마다 가장 깊은 내륙 거리로 크기를 잰다)."""
    lab, n = ndimage.label(land)
    if n:
        reach = ndimage.maximum(d_in, lab, np.arange(1, n + 1))
        return np.concatenate([[0.0], np.clip(reach / 0.08, 0.5, 1.0)])[lab]
    return np.zeros_like(d_in)


def mountains(cfg, rng, gen, S, land, d_in, wx, wy):
    """가지처럼 갈라지고, 모인 곳은 두꺼워지는 산맥 (0~1)."""
    region = _mountain_region(cfg, rng, gen, S, land, wx, wy)
    rmf = _ridged_multifractal(cfg, gen, S, wx, wy)

    # 능선이 촘촘히 모인 곳은 두꺼운 산괴로 (흐린 능선 밀도를 몸통으로 더한다)
    thick = ndimage.gaussian_filter(rmf, S * 0.012)
    thick = np.clip(thick / (np.quantile(thick, 0.99) + 1e-9), 0, 1)
    clump = np.clip(normalize(fbm(gen, S, S * 0.15, 3, 120.0)) * 0.4 + 0.6, 0.2, 1.0)
    body = (1 - cfg.massif) * rmf + cfg.massif * thick * clump
    # 해안에서 바로 솟으면 해안을 따라 바위벽이 서므로, 내륙으로 들어가며 서서히 솟게 한다
    inland = np.clip(d_in / 0.06, 0, 1)
    return region * body * inland * inland * (3 - 2 * inland)


def _mountain_region(cfg, rng, gen, S, land, wx, wy):
    """산이 생기는 지역: 판 경계 근처 + 큰 노이즈. 육지 중 mountain_coverage 만큼만 (0~1, 부드럽게)."""
    k = rng.integers(cfg.plates[0], cfg.plates[1] + 1)
    pts = rng.uniform(0, S, (k, 2))
    d = np.sort(np.stack([np.hypot(wx - x, wy - y) for x, y in pts]), axis=0)
    belt = np.exp(-((d[1] - d[0]) / S / 0.08) ** 2)
    score = 0.6 * belt + 0.4 * (normalize(fbm(gen, S, S * 0.35, 3, 100.0)) * 0.25 + 0.5)
    if not land.any():
        return np.zeros((S, S))
    hi = np.quantile(score[land], 1 - cfg.mountain_coverage * 0.5)
    lo = np.quantile(score[land], 1 - cfg.mountain_coverage * 1.6)
    region = np.clip((score - lo) / max(hi - lo, 1e-6), 0, 1)
    return region * region * (3 - 2 * region)


def _ridged_multifractal(cfg, gen, S, wx, wy):
    """릿지드 멀티프랙탈: 앞 옥타브의 능선이 강한 곳에서만 다음 옥타브 능선이 자라서 가지처럼 갈라진다.
    좌표를 살짝 비틀어 능선이 곧게 뻗지 않게 한다 (0~1)."""
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
    my, mx = yy + (wy - yy) * 0.35, xx + (wx - xx) * 0.35
    pad = int(np.ceil(max(np.abs(my - yy).max(), np.abs(mx - xx).max()))) + 4
    scale = S * cfg.ridge_scale
    weight = np.ones((S, S))
    rmf = np.zeros((S, S))
    amp, total = 1.0, 0.0
    for o in range(6):
        n = sample(fbm(gen, S, scale / (2 ** o), 1, 110.0 + o * 13.0, pad=pad), my, mx, pad)
        s = (1.0 - np.abs(n)) ** 2 * weight
        weight = np.clip(s * 2.0, 0, 1)
        rmf += s * amp
        total += amp
        amp *= 0.55
    rmf /= total
    return np.clip(rmf / (np.quantile(rmf, 0.995) + 1e-9), 0, 1)


def _dig_lake_basins(cfg, rng, gen, S, elev, land, d_in, mount, size_f):
    """내륙 저지대(산이 아닌 곳)에 크기가 제각각인 그릇을 판다. 주변도 같이 낮아져 호숫가가 완만하다 (elev를 고친다)."""
    cand = np.argwhere(land & (d_in > 0.025) & (mount < 0.2) & (size_f > 0.9))
    if not len(cand):
        return
    k = rng.integers(cfg.lakes[0], cfg.lakes[1] + 1)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
    wob = fbm(gen, S, S * 0.03, 3, 80.0)
    lo, hi = np.log(cfg.lake_radius[0]), np.log(cfg.lake_radius[1])
    for cy, cx in cand[rng.choice(len(cand), size=min(k, len(cand)), replace=False)]:
        r = np.exp(rng.uniform(lo, hi)) * S                      # 작은 호수가 더 많게 (로그 분포)
        dist = np.hypot(yy - cy, xx - cx) / r + wob * 0.35       # 울퉁불퉁한 호숫가
        elev -= 0.12 * np.exp(-(dist / 1.5) ** 2)                # 넓고 완만한 분지
        elev -= 0.10 * np.clip(1.0 - dist, 0, 1)                 # 물이 고이는 바닥


def _to_height(cfg, gen, S, elev, land, ocean, d_out):
    """0~1 높이로: 육지는 해수면 위, 물은 해수면 아래."""
    sea = cfg.sea_level
    e_max = np.quantile(elev[land], 0.998) if land.any() else 1.0
    h = np.empty((S, S))
    e = elev[land]
    h[land] = np.where(e >= 0,
                       sea + 0.004 + (1 - sea - 0.004) * np.clip(e / e_max, 0, 1) ** cfg.lowland,
                       sea + e * 0.5)                             # 호수 분지 바닥은 해수면 아래로
    shelf = 1.0 - np.exp(-d_out / 0.045)                          # 해안 근처는 얕은 대륙붕
    h[ocean] = sea - 0.01 - 0.33 * shelf[ocean] - 0.02 * (fbm(gen, S, S * 0.1, 3, 70.0)[ocean] * 0.5 + 0.5)
    inland = ~land & ~ocean                                       # 육지에 갇힌 물 → 호수 바닥
    h[inland] = sea - 0.01 - 0.06 * (1.0 - np.exp(-d_out[inland] / 0.02))
    return np.clip(h, 0.0, 1.0)
