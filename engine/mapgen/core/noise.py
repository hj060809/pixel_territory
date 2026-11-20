"""노이즈 도우미.

- fbm          S x S 격자 fBm. 옥타브마다 주파수를 두 배로 (ridged=True면 이어진 능선 모양). pad로 지도 밖까지 넓게
- fbm_offset   옥타브마다 좌표를 조금씩 밀어서 겹치는 fBm (해안 종류 단계에서 쓰는 형식)
- normalize    평균 0, 표준편차 1로
- zscore       마스크 안의 값 기준으로 평균 0, 표준편차 1로
- sample       격자를 (비튼) 좌표에서 읽기
- smooth_1d    길이 n의 부드러운 1차원 노이즈 (난수 매듭을 선형 보간)
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def fbm(gen, S, scale, octaves, off, ridged=False, pad=0):
    """S x S 격자의 fBm (-1~1 근처). ridged=True면 이어진 능선 모양 (0~1).
    pad > 0이면 지도 바깥으로 pad칸씩 더 넓게 만든다 ((S+2pad) 격자, 좌표는 -pad부터)."""
    n_px = S + 2 * pad
    ax = (np.arange(n_px, dtype=np.float64) - pad) / scale + off
    out = np.zeros((n_px, n_px))
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        n = gen.noise2array(ax, ax)
        out += amp * ((1.0 - np.abs(n)) ** 2 if ridged else n)
        total += amp
        ax = ax * 2.0
        amp *= 0.5
    return out / total


def fbm_offset(gen, S, scale, octaves, off):
    """옥타브마다 좌표를 조금씩 밀어서 겹치는 fBm (-1~1 근처)."""
    out = np.zeros((S, S))
    amp, total = 1.0, 0.0
    ax = np.arange(S, dtype=np.float64)
    for o in range(octaves):
        f = (2 ** o) / scale
        out += amp * gen.noise2array(ax * f + off + o * 17.3, ax * f + off * 0.7 + o * 5.1)
        total += amp
        amp *= 0.5
    return out / total


def normalize(a):
    """평균 0, 표준편차 1로."""
    return (a - a.mean()) / (a.std() + 1e-9)


def zscore(a, mask):
    """mask 안의 값 기준으로 평균 0, 표준편차 1로."""
    m, s = a[mask].mean(), a[mask].std() + 1e-9
    return (a - m) / s


def sample(field, yy, xx, pad=0):
    """격자 field를 (비튼) 좌표에서 읽는다. field가 pad칸 넓게 만들어졌으면 그만큼 밀어서 읽는다.
    pad가 비틀림 폭보다 넉넉하면 지도 밖 좌표도 실제로 이어지는 노이즈를 읽는다 (반사하지 않음)."""
    return ndimage.map_coordinates(field, [yy + pad, xx + pad], order=1, mode='nearest')


def smooth_1d(rng, n, scale):
    """길이 n의 부드러운 1차원 노이즈 (-1~1 근처)."""
    k = max(int(n / scale) + 3, 3)
    knots = rng.uniform(-1, 1, k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), knots)
