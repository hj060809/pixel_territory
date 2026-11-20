"""낮밤 빛과 물결에 쓰는 지도별 준비 (최상위 viewer.scene_cache.SceneCache의 계산 부분, 화면 없음).

- 지형 법선과 '지평선 높이': 해/달 고도가 바뀔 때 빛과 그림자를 빠르게 계산하기 위한 것
- 물 칸마다 물 ramp의 몇 번째 단계인지 (렌더 결과에서 가장 가까운 ramp 색으로 역산), 그 색과의 차이
- 해안에서의 거리, 수심, 디더링용 Bayer 임계값
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from engine.render.shader import WATER, bayer


class Surface:
    MAX_RESIDUAL = 40       # 물 ramp 색과 이보다 멀면(거품 등) 물결 대상에서 뺀다
    HORIZON_STEPS = 300     # 지평선 높이를 계산할 때 광원 쪽으로 최대 몇 칸까지 볼지

    def __init__(self, scene):
        """scene: engine.scene.TerrainScene (낮 이미지는 계절 효과 없는 원래 렌더)."""
        self.shader = sh = scene.shader
        full = np.asarray(scene.height, dtype=np.float64)
        self.day = scene.day
        self.H, self.W = scene.H, scene.W

        # --- 셰이더와 같은 방식으로 지형 표면을 다시 만든다 (물은 수면에서 평평)
        h = sh._downsample(full)[:self.H, :self.W]
        self.water = h < sh.sea_level
        hn = sh._noisy_land(h) if sh.height_noise > 0 else h
        zscale = sh.relief * full.shape[1] / sh.pixel_size
        z = np.maximum(hn, sh.sea_level) * zscale

        gy, gx = np.gradient(z)
        n = np.stack([-gx, -gy, np.ones_like(z)])
        n /= np.linalg.norm(n, axis=0)
        self.normal = n.astype(np.float32)                         # (3, H, W)

        dx, dy = sh.light_dir
        length = np.hypot(dx, dy) or 1.0
        self.light_xy = (dx / length, dy / length)                 # 해/달이 오는 화면 방향 (고정)
        self.horizon = self._horizon(z).astype(np.float32)         # 이 tan 값보다 해가 낮으면 그늘

        # --- 물 칸: ramp 단계 역산, 해안 거리, 수심
        self.ramp = sh.palette[WATER].astype(np.int16)              # (n, 3)
        self.n_shades = len(self.ramp)
        self.water_y, self.water_x = np.nonzero(self.water)          # 거품 포함 모든 물 (하늘 반사용)

        idx, delta, ok = self._match(self.day[self.water])
        self.wy, self.wx = self.water_y[ok], self.water_x[ok]        # 물결을 칠할 물 (거품 제외)
        self.widx = idx[ok]
        self.wdelta = delta[ok]                                      # 색 노이즈 등은 그대로 다시 더한다
        shore = sh._shore_distance(~self.water, 10)
        self.wshore = shore[self.wy, self.wx].astype(np.int16)
        self.wdepth = (sh.sea_level - h)[self.wy, self.wx]

        # --- 디더링: 물결은 셰이더와 같은 패턴, 빛/그늘 전환은 어긋난 패턴
        self.thresh = bayer(self.H, self.W)
        self.w_thresh = self.thresh[self.wy, self.wx]
        self.light_thresh = np.roll(self.thresh, (1, 2), axis=(0, 1))

    def _horizon(self, z: NDArray[np.float64]) -> NDArray[np.float64]:
        """광원 쪽으로 걸어가며 '앞을 가리는 지형의 최대 앙각(tan)'을 구한다.
        해의 고도 tan이 이 값보다 작으면 그 칸은 산 그림자 안에 있다."""
        dx, dy = self.shader.light_dir
        step = max(abs(dx), abs(dy)) or 1.0
        sx, sy = dx / step, dy / step
        dist = np.hypot(sx, sy)
        z_range = z.max() - z.min()
        steps = int(min(self.HORIZON_STEPS, np.ceil(z_range / (dist * np.tan(np.radians(1.0))))))

        pad = steps + 1
        p = np.pad(z, pad, mode='edge')
        H, W = z.shape
        hz = np.full(z.shape, -np.inf)
        for s in range(1, steps + 1):
            ox, oy = int(round(sx * s)), int(round(sy * s))
            blocker = p[pad + oy:pad + oy + H, pad + ox:pad + ox + W]
            np.maximum(hz, (blocker - z) / (dist * s), out=hz)
        return hz

    def _match(self, px: NDArray[np.uint8]):
        """각 칸에 가장 가까운 ramp 단계, 그 색과의 차이, 물 색으로 볼 수 있는지."""
        p = px.astype(np.int16)
        dist = ((p[:, None, :] - self.ramp[None]) ** 2).sum(-1)    # (N, n)
        idx = np.argmin(dist, axis=1)
        delta = p - self.ramp[idx]
        ok = np.abs(delta).max(axis=1) <= self.MAX_RESIDUAL
        return idx, delta, ok
