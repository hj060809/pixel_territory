"""계절 순환.

- SeasonCycle: 1년 시계 (0 = 3월 1일 봄의 시작, 0.25 = 6월, 0.5 = 9월, 0.75 = 12월). 낮밤 시계처럼
  자동으로 흐르게 하거나 멈추고, 앞뒤로 돌릴 수 있다.
- SeasonPainter: 셰이더가 렌더링할 때 남긴 픽셀별 정보(재질, 명암 단계, 눈/바다 얼음까지의 여유)로
  다시 렌더링하지 않고 계절에 맞게 다시 칠한다 (수 ms).
  - state(계절): 그림 없이 재질과 바다 얼음만 (서버의 게임 규칙용)
  - paint(계절): 같은 재질에 색을 입힌 낮 이미지 (화면용, 웹에서는 셰이더가 같은 계산을 한다)

계절에 따라 바뀌는 것
- 식생 팔레트: 봄은 연두빛, 여름은 기본, 가을은 숲이 주황·적갈색이고 풀은 황금빛, 겨울은 누렇게 마르고 숲은 앙상한 회갈색.
  침엽수림·상록림·관목은 거의 그대로. 중간색을 섞지 않고 디더링으로 픽셀 하나씩 다음 계절 팔레트로 바뀐다.
  계절 팔레트는 기본 팔레트를 색조 변환해 만들고, 어두운 단계의 푸른 그림자 톤은 덜 바꾼다.
- 설선: 겨울에 내려오고 여름에 조금 올라간다.
- 바다 얼음: 겨울에 넓어지고 여름에 줄어든다 (추운 곳만).
계절 폭은 기후를 따른다: 더운 곳(열대)은 거의 변하지 않고, 추운 곳일수록 크다.
"""
from __future__ import annotations

import colorsys

import numpy as np

from engine.render import shader as S

SEASON_CENTERS = (0.10, 0.35, 0.60, 0.85)          # 봄 / 여름 / 가을 / 겨울이 가장 뚜렷한 때 (1년 비율)
SEASON_NAMES = ('봄', '여름', '가을', '겨울')

DECIDUOUS = (S.FOREST,)                             # 잎이 지는 숲
GRASSY = (S.GRASS, S.DRYGRASS, S.GRASS_DEAD, S.GRASS_YELLOW, S.SAVANNA, S.STEPPE, S.COLD_STEPPE,
          S.MARSH, S.ALPINE, S.TUNDRA, S.MOSS)
EVERGREEN = (S.TAIGA, S.RAINFOREST, S.SHRUB)


class SeasonCycle:
    """1년 시계. update(dt)로 흐르고, advance()로 앞뒤로 돌린다."""

    def __init__(self, year: float = 0.35, year_length: float = 240.0, auto: bool = True):
        self.year = year % 1.0
        self.year_length = year_length              # 1년이 몇 초에 지나가는지
        self.auto = auto

    def update(self, dt: float) -> None:
        if self.auto:
            self.advance(dt / self.year_length)

    def advance(self, years: float) -> None:
        self.year = (self.year + years) % 1.0

    def weights(self) -> np.ndarray:
        """(봄, 여름, 가을, 겨울) 비중. 이웃한 두 계절 사이를 선형으로."""
        c = SEASON_CENTERS
        w = np.zeros(4)
        y = self.year
        for k in range(4):
            a, b = c[k], c[(k + 1) % 4] + (1.0 if k == 3 else 0.0)
            yy = y + 1.0 if (k == 3 and y < c[0]) else y
            if a <= yy < b:
                t = (yy - a) / (b - a)
                w[k], w[(k + 1) % 4] = 1 - t, t
                break
        return w

    def label(self) -> str:
        month = int(self.year * 12 + 2) % 12 + 1
        name = SEASON_NAMES[(month - 3) % 12 // 3]
        return f'{name} ({month}월)'


def _shift(rgb, target_h, mix, sat, val):
    """한 색의 색조를 target_h 쪽으로 mix만큼, 채도와 명도를 배율로."""
    h, s, v = colorsys.rgb_to_hsv(*(np.asarray(rgb) / 255.0))
    d = ((target_h - h + 0.5) % 1.0) - 0.5                 # 가까운 쪽으로 돈다
    h = (h + d * mix) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, min(s * sat, 1.0), min(v * val, 1.0))
    return np.array([r, g, b]) * 255.0


def season_palettes(base: np.ndarray) -> np.ndarray:
    """(4, 재질, 단계, 3): 봄, 여름(기본), 가을, 겨울 팔레트. 어두운 단계일수록 덜 바꾼다 (푸른 그림자 유지)."""
    rules = {   # 재질 묶음: (봄, 가을, 겨울) 각각 (목표 색조, 섞는 정도, 채도 배율, 명도 배율)
        DECIDUOUS: ((0.25, 0.35, 1.10, 1.07), (0.06, 0.70, 1.25, 1.02), (0.08, 0.50, 0.35, 0.82)),
        GRASSY:    ((0.25, 0.30, 1.10, 1.05), (0.12, 0.55, 1.05, 1.02), (0.11, 0.50, 0.40, 0.86)),
        EVERGREEN: ((0.30, 0.10, 1.03, 1.03), (0.20, 0.10, 1.00, 1.00), (0.40, 0.10, 0.75, 0.88)),
    }
    out = np.repeat(base[None].astype(np.float64), 4, axis=0)
    n_shade = base.shape[1]
    for mats, per_season in rules.items():
        for slot, (th, mix, sat, val) in zip((0, 2, 3), per_season):
            for m in mats:
                for k in range(n_shade):
                    w = 0.35 + 0.65 * k / max(n_shade - 1, 1)        # 어두운 단계는 덜
                    out[slot, m, k] = _shift(base[m, k], th, mix * w, 1 + (sat - 1) * w, 1 + (val - 1) * w)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


class SeasonPainter:
    """셰이더 렌더링 때 남긴 픽셀별 정보(layers)로 계절에 맞게 다시 칠한다."""

    def __init__(self, layers: dict, shader):
        self.sh = shader
        self.L = layers
        self.pal = season_palettes(shader.palette)
        T = layers['temperature']
        self.amp = np.clip((0.85 - T) / 0.35, 0, 1).astype(np.float32)       # 계절 폭: 열대 0, 온대 0.7, 추운 곳 1
        self.amp_ice = np.clip((0.35 - T) / 0.25, 0, 1).astype(np.float32)   # 바다 얼음 계절 폭: 추운 곳만
        self.dither = np.roll(layers['thresh'], (1, 3), axis=(0, 1))          # 명암과 다른 디더 무늬
        self.snow_ok = ~layers['water'] & (layers['pre'] != S.ICE)
        self.veg_mask = np.isin(np.arange(len(shader.palette)), S.VEGETATION)
        self.ice_mask = np.zeros(layers['water'].shape, bool)                  # 마지막으로 칠한 바다 얼음
        # 매번 쓰는 값은 미리 (칠하기 한 번이 수 ms가 되게)
        self.n_mat, self.n_shade = shader.palette.shape[:2]
        self.flat_pal = self.pal.reshape(-1, 3)
        self.mat0 = layers['pre'].astype(np.int32)
        self.idx0 = layers['idx'].astype(np.int32)
        self.idx_land = layers['idx_land'].astype(np.int32)
        self.foam = layers['water'] & layers['near_land']
        self.tint = ((layers['alt'] - 0.3)[..., None] * S._COOL * shader.altitude_tint
                     if shader.altitude_tint > 0 else None)

    @staticmethod
    def _weights(weights):
        if weights is None:
            return np.array([0.0, 1.0, 0.0, 0.0]), True
        return np.asarray(weights, float), False

    def _snow_and_ice(self, w, neutral):
        """눈(설선)과 바다 얼음. 반환: (눈 덮인 칸, 그 칸의 눈 재질, 바다 얼음 칸)."""
        L, sh = self.L, self.sh
        # 설선: 겨울에 내려오고 여름에 조금 올라간다 (높이 단위로 옮긴 만큼 여유를 고친다)
        shift = 0.0 if neutral else self.amp * (w[3] * 1.0 + w[2] * 0.25 + w[0] * 0.3 - w[1] * 0.3) * 0.10
        cover = L['snow_cover'] + shift / sh.snow_blend
        old = L['snow_old'] - shift / (4 * sh.snow_blend)
        snow = self.snow_ok & (cover > 0)
        snow_mat = np.where(L['ice_zone'], S.ICE, np.where(old > 0, S.SNOW_OLD, S.SNOW))
        # 바다 얼음: 겨울에 넓어지고 여름에 줄어든다
        ice_shift = 0.0 if neutral else self.amp_ice * (w[3] - 0.6 * w[1] + 0.2 * w[2] + 0.2 * w[0]) * 0.4
        ice = L['water'] & (L['ice'] + ice_shift > 0)
        return snow, snow_mat, ice

    def state(self, weights=None):
        """그림 없이 재질만: (재질 지도, 바다 얼음 마스크). 게임 규칙(눈 덮인 길, 얼어붙은 바다)이 쓴다.
        paint(weights)가 칠하는 재질과 같다."""
        w, neutral = self._weights(weights)
        snow, snow_mat, ice = self._snow_and_ice(w, neutral)
        mat = np.where(snow, snow_mat, self.mat0)
        mat = np.where(ice, S.SEA_ICE, mat)
        return mat, ice

    def paint(self, weights=None) -> np.ndarray:
        """(봄, 여름, 가을, 겨울) 비중으로 칠한 낮 이미지 (H, W, 3) uint8. weights=None이면 계절 효과 없이 (원래 렌더와 같음)."""
        L, sh = self.L, self.sh
        w, neutral = self._weights(weights)
        mat, idx = self.mat0, self.idx0

        # 식생 팔레트: 계절 비중 × 계절 폭만큼 디더링으로 다음 계절 팔레트를 고른다
        if neutral:
            variant = np.ones(mat.shape, np.int32)                                # 1 = 여름(기본)
        else:
            a, u = self.amp, self.dither
            p_wi, p_au, p_sp = w[3] * a, w[2] * a, w[0] * a
            variant = np.select([u < p_wi, u < p_wi + p_au, u < p_wi + p_au + p_sp], [3, 2, 0], 1).astype(np.int32)

        snow, snow_mat, ice = self._snow_and_ice(w, neutral)
        mat = np.where(snow, snow_mat, mat)
        variant = np.where(snow, 1, variant)
        mat = np.where(ice, S.SEA_ICE, mat)
        idx = np.where(ice, self.idx_land, idx)
        variant = np.where(ice, 1, variant)
        self.ice_mask = ice                                                     # 마지막으로 칠한 바다 얼음 (물결을 그리지 않을 곳)

        img = self.flat_pal[(variant * self.n_mat + mat) * self.n_shade + idx].astype(np.float64)
        if sh.foam:
            img[self.foam & ~ice] = S.DEFAULT_FOAM
        if sh.color_noise > 0 or sh.altitude_tint > 0:
            img += L['noise_delta']
            if self.tint is not None:
                img += self.tint * self.veg_mask[mat][..., None]
        np.clip(img, 0, 255, out=img)
        return img.astype(np.uint8)
