"""바다 애니메이션 (최상위 viewer.water의 계산, 화면 없음). 웹에서는 셰이더가 같은 계산을 한다.

원칙: 셰이더가 그린 물(색, 디더링)은 그대로 두고, 움직임은 일부 칸에만 듬성듬성 입힌다.
새 색은 만들지 않고 물 ramp 색과 기존 거품색만 쓴다.

- 물결: 가늘고 길게 이어진 마루 텍스처(노이즈의 0 부근)를 '흐름 맵' 방식으로 흘린다.
  장소마다 흐름 방향과 속도가 다르고(큰 노이즈), 마루는 그 흐름에 수직으로 놓인다(방향별 텍스처를 섞음).
  텍스처를 흐름 방향으로 조금 밀었다가 되감기를 반복하는데, 반 박자 어긋난 두 겹을 칸 단위 디졸브로 바꿔서
  되감는 순간이 보이지 않고, 되감을 때마다 텍스처의 다른 곳을 읽어서 같은 무늬가 반복되지 않는다.
  마루 중심에 가까울수록 높은 확률로, Bayer 디더링을 거쳐 물 ramp에서 한 단계만 밝게 한다.
- 해안: 거품이 닿는 범위를 수심으로 정하고, 장소마다 다른 박자로 밀려왔다 빠지게 한다.
  거품 바로 바깥은 한 단계 밝은 물.

노이즈는 지도 내용과 상관없다 (지도 크기와 고정 시드로만 정해진다): water_noise_fields, ridge_noise.
웹은 이 둘을 같은 알고리즘(OpenSimplex)으로 직접 만들고, 지도마다 다른 값(WaterAnimator.scalars())만 받는다.
"""
from __future__ import annotations

import numpy as np
import opensimplex
from numpy.typing import NDArray

from engine.render.shader import DEFAULT_FOAM

try:
    from numba import njit
except ImportError:          # numba가 없으면 numpy로 계산한다 (느림)
    njit = None

PARAMS = dict(ripple_size=10.0, ripple_length=3.0, coverage=0.06, flow_speed=3.0, flow_period=6.0,
              flow_scale=140.0, surf_period=4.0, surf_reach=1.3, seed=0)
N_ORIENT = 6        # 마루 방향 텍스처 수 (180도를 30도씩)
JUMP = 256          # 되감을 때 건너뛰는 범위 (2의 거듭제곱: 비트 연산용)


# ------------------------------------------------------------------ 지도와 상관없는 노이즈 (웹이 똑같이 만든다)
def grid_noise(gen, h, w, scale, off, octaves=1, stretch=1.0):
    """격자 노이즈 (h, w) float64: 칸 (y, x)는 OpenSimplex noise2(x / (scale*stretch) + off, y / scale + off)의 옥타브 합."""
    ax = np.arange(w, dtype=np.float64) / (scale * stretch) + off
    ay = np.arange(h, dtype=np.float64) / scale + off
    out, amp, total = np.zeros((h, w)), 1.0, 0.0
    for _ in range(octaves):
        out += amp * gen.noise2array(ax, ay)
        total += amp
        ax, ay, amp = ax * 2, ay * 2, amp * 0.5
    return out / total


def water_noise_fields(H, W, params=PARAMS):
    """흐름 맵과 해안 박자에 쓰는 지도 전체 노이즈 (지도 크기로만 정해진다). 이름 → (H, W) float64."""
    gen = opensimplex.OpenSimplex(params['seed'] + 31)
    fs = params['flow_scale']
    return {
        'angle_a': grid_noise(gen, H, W, fs, 100.0, 2),
        'angle_b': grid_noise(gen, H, W, fs * 3, 150.0),
        'speed': grid_noise(gen, H, W, fs * 0.7, 200.0),
        'phase': grid_noise(gen, H, W, 60.0, 300.0),
        'phase2': grid_noise(gen, H, W, 45.0, 350.0),
        'density': grid_noise(gen, H, W, 90.0, 450.0, 2),
        'surf': grid_noise(gen, H, W, 22.0, 800.0, 2),
    }


def ridge_noise(side, size, length, off, params=PARAMS):
    """마루 텍스처의 바탕 노이즈 (side, side) float64. 칸 값은 side와 상관없다 (더 큰 격자의 앞부분과 같다)."""
    gen = opensimplex.OpenSimplex(params['seed'] + 31)
    return grid_noise(gen, side, side, size, off, octaves=2, stretch=length)


def _sample_loop(tex, base, off0, off1, ow, vx, vy, phase, dissolve, u_add, speed_mul, tw, mask, out):
    """흐름 맵 한 겹을 칸마다 계산한다 (numba로 컴파일해서 쓴다). numpy 버전(_sample)과 같은 계산."""
    for i in range(base.shape[0]):
        best = 0.0
        w_first = 0.0
        for s in range(2):
            v = phase[i] + u_add + 0.5 * s
            cf = np.floor(v)
            c = np.int32(cf)
            f = v - cf
            w = 1.0 - abs(2.0 * f - 1.0)
            jx = (c * 97 + 53 * s) & mask
            jy = (c * 61 + 29 * s) & mask
            d = (f - 0.5) * speed_mul
            ox = np.int32(np.rint(vx[i] * d))
            oy = np.int32(np.rint(vy[i] * d))
            idx = base[i] + (jy - oy) * tw + (jx - ox)
            val = tex[idx + off0[i]] * (1.0 - ow[i]) + tex[idx + off1[i]] * ow[i]
            if s == 0:
                w_first = w
                best = val
            elif not (w_first > dissolve[i]):
                best = val
        out[i] = best


_sample_jit = njit(cache=True, nogil=True)(_sample_loop) if njit is not None else None


class WaterAnimator:
    """surface: engine.render.surface.Surface. apply(base, t)로 t초 순간의 물결과 해안 거품을 입힌다."""

    N_ORIENT = N_ORIENT

    def __init__(self, surface, fps: float = 1.0, **params):
        self.surface = surface
        self.params = p = dict(PARAMS, **params)
        self.fps = fps
        self.update_hz = 12.0            # 화면에서는 초당 이만큼만 다시 칠한다 (픽셀아트답게 조금 끊기게)
        self.flow_period = p['flow_period']
        self.surf_period = p['surf_period']
        self.surf_reach = p['surf_reach']
        self._t = 0.0
        self._since = 1.0
        self._empty = len(surface.wy) == 0
        if not self._empty:
            self._prepare(p)

    # ------------------------------------------------------------- 준비
    def _prepare(self, p) -> None:
        sc = self.surface
        ys, xs = sc.wy, sc.wx
        F = water_noise_fields(sc.H, sc.W, p)
        at = lambda name: F[name][ys, xs].astype(np.float32)

        # --- 흐름 맵: 장소마다 방향과 속도가 다르다
        angle = at('angle_a') * np.pi * 1.6 + at('angle_b') * np.pi
        speed = p['flow_speed'] * (0.9 + 0.4 * at('speed'))
        travel = speed * self.flow_period                       # 한 주기 동안 미는 거리 (칸)
        self._vx = (np.cos(angle) * travel).astype(np.float32)
        self._vy = (np.sin(angle) * travel).astype(np.float32)
        self._phase = (at('phase') * 0.5 + 0.5).astype(np.float32)    # 장소마다 되감는 박자
        self._phase2 = (at('phase2') * 0.5 + 0.5).astype(np.float32)  # 큰 마루 겹은 다른 박자

        # 마루는 흐름에 수직으로 놓인다: 가까운 방향 텍스처 두 장과 섞는 비율
        crest = (angle + np.pi / 2) % np.pi
        pos = crest / (np.pi / N_ORIENT)
        k0 = np.floor(pos).astype(np.int32) % N_ORIENT
        self._o_w = (pos - np.floor(pos)).astype(np.float32)
        self._o_k0, self._o_k1 = k0, (k0 + 1) % N_ORIENT

        # 물결이 많은 곳과 잔잔한 곳
        self._density = np.clip(0.6 + at('density') * 1.2, 0.15, 1.0).astype(np.float32)

        # --- 마루 텍스처: 맵보다 크게 만들어 되감을 때마다 다른 곳을 읽는다
        self.margin = int(np.ceil(np.abs(np.concatenate([self._vx, self._vy])).max() / 2)) + 2
        self._jump = JUMP
        th, tw = sc.H + 2 * self.margin + JUMP, sc.W + 2 * self.margin + JUMP
        self._th, self._tw, self._tsize = th, tw, th * tw
        self._tex1, self.std1 = self._crest_textures(th, tw, p['ripple_size'], p['ripple_length'], 400.0)
        self._tex2, self.std2 = self._crest_textures(th, tw, p['ripple_size'] * 1.8, p['ripple_length'] * 0.8, 600.0)
        # 텍스처는 1차원으로 펴서 읽는다 (2차원 인덱싱보다 빠르다)
        self._base = ((ys + self.margin) * tw + (xs + self.margin)).astype(np.int32)
        self._o_off0 = (self._o_k0 * self._tsize).astype(np.int32)
        self._o_off1 = (self._o_k1 * self._tsize).astype(np.int32)

        # 되감는 두 겹은 값을 섞지 않고 칸 단위 디졸브로 바꾼다 (섞으면 마루가 흐려져 깜빡인다)
        self._dissolve = np.roll(sc.thresh, (2, 1), axis=(0, 1))[ys, xs].astype(np.float32)

        # 밝아지는 범위: 실제 분포에서 맞춘다 (마루 중심일수록 디더링 확률이 높다)
        sample = self._ripple(0.0)
        self.cut = float(np.quantile(sample, 1 - p['coverage'] * 2.5))
        self.band = float(np.quantile(sample, 1 - p['coverage'] * 0.4)) - self.cut + 1e-6

        # --- 해안 거품: 해안 바로 앞 줄들의 수심을 기준으로 범위를 정한다.
        #     얕은 작은 호수가 통째로 하얘지지 않게 해안에서의 거리로도 한계를 둔다
        ref = sc.wdepth[sc.wshore == 2]
        self.d_ref = float(np.median(ref)) if len(ref) else 0.005
        self._foam_zone = sc.wshore <= 3
        self._rim_zone = sc.wshore <= 5
        self._depth_n = (sc.wdepth / (0.35 * self.d_ref)).astype(np.float32)  # 수심을 거품 단위로
        self._surf_phase = (at('surf') * 0.6 + 0.5).astype(np.float32)

        # 매 프레임 쓰는 값들
        self._flat = (ys * sc.W + xs).astype(np.intp)
        self._widx = sc.widx
        self._thresh = sc.w_thresh.astype(np.float32)

    def _crest_textures(self, th, tw, size, length, off):
        """가늘고 길게 이어진 마루 텍스처를 N_ORIENT 방향으로 돌려 만든다 (N, th*tw)를 1차원으로.
        노이즈의 0 부근(1 - |n|)을 쓰면 봉우리 대신 이어진 가는 능선이 생긴다.
        반환: (텍스처, 바탕 노이즈의 표준편차 — 지도마다 다르다)."""
        side = int(np.ceil(np.hypot(th, tw))) + 4
        n = ridge_noise(side, size, length, off, self.params)
        std = float(n.std())
        ridge = np.clip(1.0 - np.abs(n) / (std * 1.2), 0, 1) ** 2   # 0 부근이 1인 가는 마루

        yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
        yy -= th / 2
        xx -= tw / 2
        out = np.empty((N_ORIENT, th * tw), np.float32)
        for k in range(N_ORIENT):
            b = np.pi * k / N_ORIENT
            u = xx * np.cos(b) + yy * np.sin(b)                # 마루 방향
            v = -xx * np.sin(b) + yy * np.cos(b)
            sx = np.clip(np.rint(u + side / 2), 0, side - 1).astype(np.int32)
            sy = np.clip(np.rint(v + side / 2), 0, side - 1).astype(np.int32)
            out[k] = ridge[sy, sx].ravel()
        return out.ravel(), std

    def scalars(self) -> dict:
        """지도마다 다른 값 (웹은 노이즈를 직접 만들고 이것만 받는다)."""
        if self._empty:
            return {'empty': True}
        return dict(empty=False, margin=self.margin, std1=self.std1, std2=self.std2, cut=self.cut,
                    band=self.band, d_ref=self.d_ref)

    # ------------------------------------------------------------- 물결
    def _sample(self, tex, phase, t, speed_mul):
        """흐름 맵 한 겹: 반 박자 어긋난 두 번 읽기 중 하나를 칸마다 디졸브로 고른다."""
        if _sample_jit is not None:
            out = np.empty_like(phase)
            _sample_jit(tex, self._base, self._o_off0, self._o_off1, self._o_w, self._vx, self._vy,
                        phase, self._dissolve, np.float32(t / self.flow_period * speed_mul),
                        np.float32(speed_mul), np.int32(self._tw), np.int32(self._jump - 1), out)
            return out
        u = phase + np.float32(t / self.flow_period * speed_mul)
        tw = self._tw
        mask = self._jump - 1
        ow = self._o_w
        vals, weights = [], []
        for shift in (0.0, 0.5):
            v = u + np.float32(shift)
            cf = np.floor(v)
            c = cf.astype(np.int32)
            f = v - cf
            weights.append(np.float32(1.0) - np.abs(np.float32(2.0) * f - np.float32(1.0)))
            jx = (c * 97 + int(shift * 106)) & mask
            jy = (c * 61 + int(shift * 58)) & mask
            d = (f - np.float32(0.5)) * np.float32(speed_mul)
            ox = np.rint(self._vx * d).astype(np.int32)
            oy = np.rint(self._vy * d).astype(np.int32)
            idx = self._base + (jy - oy) * tw + (jx - ox)
            vals.append(tex[idx + self._o_off0] * (np.float32(1.0) - ow) + tex[idx + self._o_off1] * ow)
        return np.where(weights[0] > self._dissolve, vals[0], vals[1])

    def _ripple(self, t: float) -> NDArray[np.float32]:
        small = self._sample(self._tex1, self._phase, t, 1.0)
        large = self._sample(self._tex2, self._phase2, t, 0.6)
        return np.maximum(small, large * np.float32(0.85))

    # ------------------------------------------------------------- 재생
    def update(self, dt: float) -> bool:
        """시간을 진행하고, 물을 다시 칠할 때가 됐으면 True (초당 update_hz번)."""
        self._t += dt * self.fps
        self._since += dt
        if self._since >= 1.0 / self.update_hz:
            self._since = 0.0
            return True
        return False

    def apply(self, base: NDArray[np.uint8], t: float | None = None) -> NDArray[np.uint8]:
        """base(낮 이미지)에 t초(없으면 지금) 순간의 물결과 해안 거품을 입힌 새 이미지."""
        sc = self.surface
        out = base.copy()
        if self._empty:
            return out
        t = self._t if t is None else t
        thresh = self._thresh

        # 물결: 마루 중심에 가까울수록 높은 확률로 한 단계만 밝게 (셰이더와 같은 Bayer 디더링)
        r = self._ripple(t)
        p = np.clip((r - np.float32(self.cut)) / np.float32(self.band), 0, 1) * self._density
        lift = (p > thresh).astype(np.intp)

        # 해안: 거품이 닿는 수심이 박자에 맞춰 늘었다 줄었다 한다 (밀려올 땐 빠르게, 빠질 땐 천천히)
        s = self._surf_phase + np.float32(t / self.surf_period)
        s -= np.floor(s)
        breath = np.where(s < 0.3, s * np.float32(1 / 0.3), (np.float32(1.0) - s) * np.float32(1 / 0.7))
        breath *= np.sqrt(breath)                                # ^1.5
        wet = (np.float32(0.3) + np.float32(self.surf_reach) * breath) * np.float32(1 / 0.35) - self._depth_n
        foam = self._foam_zone & (wet > thresh)
        rim = self._rim_zone & ~foam & (wet > thresh - 1.3)      # 거품 바로 바깥은 밝은 물
        lift = np.maximum(lift, rim.astype(np.intp))

        k = np.clip(self._widx + lift, 0, sc.n_shades - 1)
        changed = k != self._widx
        flat = out.reshape(-1, 3)
        flat[self._flat[changed]] = np.clip(sc.ramp[k[changed]] + sc.wdelta[changed], 0, 255).astype(np.uint8)
        flat[self._flat[foam]] = DEFAULT_FOAM
        return out
