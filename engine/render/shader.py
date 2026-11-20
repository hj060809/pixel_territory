"""HeightMap을 픽셀아트 스타일로 렌더링하는 셰이더.

색을 연속적으로 섞지 않고, 바이옴마다 정해진 명암 단계(ramp)에서 한 색만 고른다.
- 조명: 경사(법선)와 광원 방향으로 ramp 안의 밝기 단계를 고른다
- 그림자: 광원 쪽으로 레이마칭해서 가려진 곳은 단계를 낮춘다
- 디더링: 명암 경계와 바이옴 경계를 4x4 Bayer 패턴으로 섞는다
- 경사: 너무 가파르면 높이와 상관없이 바위로 만든다
- 물: 깊이에 따라 단계를 나누고, 해안선에 거품을 넣는다
- 외곽선: 아래쪽으로 급하게 떨어지는 절벽 가장자리를 가장 어두운 색으로 칠한다
- 색 노이즈: 큰 덩어리 노이즈로 색을 살짝 따뜻하게/차갑게, 밝게/어둡게 흔든다
"""
from __future__ import annotations

import numpy as np
import opensimplex
from numpy.typing import NDArray

from engine.mapgen import HeightMap


def _hex(code: str) -> tuple[int, int, int]:
    code = code.lstrip('#')
    return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _ramp(*codes: str) -> list[tuple[int, int, int]]:
    return [_hex(c) for c in codes]


# 어두운 색 → 밝은 색 순서. 어두운 쪽은 푸른/보랏빛, 밝은 쪽은 노란빛으로 색조를 틀었다(hue shifting).
(WATER, SAND, GRASS, FOREST, ROCK, SNOW,
 DRYGRASS, ALPINE, DIRT, MOSS, SCREE, ROCK_WARM, ROCK_RED, SNOW_OLD, GRASS_DEAD, GRASS_YELLOW,
 LIMESTONE, DUNE, LAGOON, MARSH,
 DESERT, SAVANNA, STEPPE, SHRUB, RAINFOREST, COLD_STEPPE, TUNDRA, TAIGA, ICE, SEA_ICE) = range(30)
DEFAULT_RAMPS = {
    WATER:     _ramp('#1a2f66', '#1f4c88', '#2671a2', '#3196aa', '#5bbcb6'),  # 깊음(로열블루) → 얕음(청록)
    SAND:      _ramp('#7a5c48', '#a5805a', '#c9a46f', '#e3c88f', '#f4e4b4'),
    GRASS:     _ramp('#1f3b33', '#2b5e3b', '#45843e', '#78a948', '#b4cd6a'),
    FOREST:    _ramp('#13242a', '#1a3a32', '#255437', '#386f3b', '#5a8c42'),
    ROCK:      _ramp('#2a2535', '#463e52', '#675e6f', '#8c8590', '#b8b2b2'),  # 차가운 회색 바위
    SNOW:      _ramp('#5d6b94', '#8d9cc4', '#bccbe2', '#dee7f2', '#ffffff'),
    DRYGRASS:  _ramp('#203228', '#345230', '#527336', '#7b9143', '#a7ae63'),  # 볕 드는 사면의 마른 풀
    ALPINE:    _ramp('#33303a', '#544f48', '#7a7256', '#a09869', '#c8bf8c'),  # 수목한계선 위 고산 초지
    DIRT:      _ramp('#3b2a2c', '#5e4235', '#835f40', '#a8814f', '#c9a66a'),  # 흙 (볕 드는 비탈)
    MOSS:      _ramp('#1d2a2e', '#30443c', '#4a5f48', '#6a7c58', '#909c70'),  # 이끼 낀 바위 (그늘 비탈)
    SCREE:     _ramp('#3a3540', '#5c5458', '#827870', '#a69c8c', '#cbc2ae'),  # 자갈 비탈
    # 바위 변종은 기본 바위와 명도를 맞추고 색조만 살짝 틀었다 (튀지 않게)
    ROCK_WARM:  _ramp('#2b2533', '#483f4f', '#6a6069', '#8f8789', '#b9b3ae'),  # 약간 따뜻한 회색
    ROCK_RED:   _ramp('#2d2331', '#4f3942', '#755755', '#9a786e', '#c1a18e'),  # 은은하게 붉은 바위
    SNOW_OLD:   _ramp('#55577a', '#7f82a6', '#a7abc8', '#c8cbe0', '#e2e4ef'),  # 회보라빛 묵은 눈
    GRASS_DEAD:   _ramp('#292e26', '#464c35', '#676949', '#878760', '#a9a581'),  # 약간 죽은 풀
    # 해안 종류 (engine.mapgen.coast가 넘겨줄 때만 쓴다)
    LIMESTONE:  _ramp('#3a3540', '#6b6468', '#a39b92', '#cfc6b0', '#ece5d2'),  # 흰빛 석회암 바위 해안
    DUNE:       _ramp('#8a6a50', '#b8956a', '#dcc08a', '#efdcaa', '#faf0cf'),  # 모래사장 뒤 사구 (모래보다 밝게)
    LAGOON:     _ramp('#1f4a5e', '#2a6a72', '#3e8a80', '#5ea592', '#8cc2a6'),  # 모래톱 안 잔잔한 석호 물 (녹청색)
    MARSH:      _ramp('#2f3a34', '#4c5a48', '#6c7a5c', '#8c9870', '#aeb68c'),  # 석호 기슭 염습지 (회녹색)
    GRASS_YELLOW: _ramp('#322f24', '#565031', '#7f7542', '#a69b59', '#c5bd83'),  # 누런 풀
    # 바이옴 (기후를 줄 때만 쓴다). 어두운 단계는 다른 식생과 같은 푸른/보랏빛 그림자 톤
    DESERT:      _ramp('#5e3f38', '#94674a', '#c3935f', '#ddb57a', '#f0d6a2'),  # 사막: 붉은 기 도는 모래
    SAVANNA:     _ramp('#3a3424', '#5f5a2f', '#8c8238', '#b5a64a', '#d6c978'),  # 사바나: 누런 풀
    STEPPE:      _ramp('#33302a', '#575235', '#7d7945', '#a39f5c', '#c9c487'),  # 건조 초원: 황금빛 올리브
    SHRUB:       _ramp('#1e2a24', '#2f4230', '#4a5d38', '#6a7a45', '#8f9a5f'),  # 관목: 짙은 올리브 (지중해 관목, 사바나 나무)
    RAINFOREST:  _ramp('#0f2626', '#123a30', '#195236', '#22693a', '#3b8641'),  # 아열대 상록림: 짙고 채도 높은 초록
    COLD_STEPPE: _ramp('#262c2c', '#3f4a44', '#5e6b58', '#7f8b6f', '#a3ab8c'),  # 한랭 초원: 회녹색
    TUNDRA:      _ramp('#2a2b33', '#454741', '#676752', '#8c8a6c', '#b5b294'),  # 툰드라: 회올리브 이끼
    TAIGA:       _ramp('#10202a', '#163330', '#1f4838', '#2c5c40', '#45764c'),  # 침엽수림: 짙은 청록
    ICE:         _ramp('#46598a', '#7891bd', '#a8c0de', '#d0e1f0', '#eef6fb'),  # 빙상: 푸른빛 도는 얼음
    SEA_ICE:     _ramp('#3f5482', '#7088b4', '#a2b9d6', '#c9dbeb', '#e8f2f8'),  # 바다 얼음: 조금 더 어둡고 푸르게
}
VEGETATION = (GRASS, FOREST, DRYGRASS, ALPINE, MOSS, GRASS_DEAD, GRASS_YELLOW,
              DESERT, SAVANNA, STEPPE, SHRUB, RAINFOREST, COLD_STEPPE, TUNDRA, TAIGA)

# 바이옴 표: 기온 구간(추움 / 서늘 / 따뜻 / 더움) × 습도 구간(건조 / 보통 / 습함)
TEMP_BANDS = (0.28, 0.5, 0.75)
MOIST_BANDS = (0.33, 0.66)
BIOME_OPEN = np.array([            # 트인 땅 (숲 아래 높이)
    [TUNDRA, TUNDRA, TUNDRA],
    [COLD_STEPPE, GRASS, GRASS],
    [STEPPE, GRASS, GRASS],
    [DESERT, SAVANNA, GRASS],
])
BIOME_WOODS = np.array([           # 숲 (숲이 자라는 높이)
    [TUNDRA, TAIGA, TAIGA],
    [TAIGA, TAIGA, TAIGA],
    [SHRUB, FOREST, FOREST],
    [DESERT, SHRUB, RAINFOREST],
])
DEFAULT_FOAM = _hex('#d6eef2')

_BAYER_4 = (np.array([[0, 8, 2, 10],
                      [12, 4, 14, 6],
                      [3, 11, 1, 9],
                      [15, 7, 13, 5]], dtype=np.float64) + 0.5) / 16.0  # (0, 1) 사이 임계값

# 색 노이즈 방향: 따뜻함(빨강+, 파랑-)과 밝기
_WARM = np.array([1.0, 0.35, -0.8])
_BRIGHT = np.array([1.0, 1.0, 1.0])
# 고도 색조: 높을수록 식생이 차갑고 짙어진다
_COOL = np.array([-1.0, -0.5, 0.5])


def bayer(h: int, w: int) -> NDArray[np.float64]:
    """화면 크기만큼 깐 4x4 Bayer 임계값 (0~1)."""
    return np.tile(_BAYER_4, (h // 4 + 1, w // 4 + 1))[:h, :w]


def _shift(a: NDArray, ox: int, oy: int) -> NDArray:
    """out[y, x] = a[y + oy, x + ox]. 범위를 벗어나면 가장자리 값을 쓴다."""
    H, W = a.shape
    ys = np.clip(np.arange(H) + oy, 0, H - 1)
    xs = np.clip(np.arange(W) + ox, 0, W - 1)
    return a[ys[:, None], xs[None, :]]


def _box_blur(a: NDArray[np.float64], r: int) -> NDArray[np.float64]:
    """(2r+1)x(2r+1) 평균 필터. 누적합으로 계산해서 반경이 커도 빠르다."""
    if r <= 0:
        return a
    k = 2 * r + 1
    p = np.pad(a, r, mode='edge')
    c = np.cumsum(p, axis=0)
    c = np.vstack([np.zeros((1, c.shape[1])), c])
    rows = (c[k:] - c[:-k]) / k
    c = np.cumsum(rows, axis=1)
    c = np.hstack([np.zeros((c.shape[0], 1)), c])
    return (c[:, k:] - c[:, :-k]) / k


def _smooth(a: NDArray[np.float64], r: int) -> NDArray[np.float64]:
    """박스 블러 두 번 = 가우시안 비슷한 부드러운 블러."""
    return _box_blur(_box_blur(a, r), r)


def _fbm(gen: opensimplex.OpenSimplex, H: int, W: int, scale: float,
         octaves: int, offset: float) -> NDArray[np.float64]:
    """대략 -1~1 사이의 부드러운 노이즈. scale은 한 덩어리 크기(픽셀)."""
    xs = np.arange(W) / scale + offset
    ys = np.arange(H) / scale + offset
    out = np.zeros((H, W))
    amp, freq, total = 1.0, 1.0, 0.0
    for _ in range(octaves):
        out += amp * gen.noise2array(xs * freq, ys * freq)
        total += amp
        amp *= 0.5
        freq *= 2.0
    return out / total


def upscale(img: NDArray[np.uint8], k: int) -> NDArray[np.uint8]:
    """픽셀이 뭉개지지 않게 nearest-neighbor로 k배 확대."""
    return img.repeat(k, axis=0).repeat(k, axis=1)


class PixelArtShader:
    def __init__(
        self,
        *,
        pixel_size: int = 1,              # 높이맵을 이만큼 묶어서 1픽셀로 만든다 (클수록 도트가 굵어짐)
        relief: float = 0.15,             # 높이 1.0 = 맵 너비의 몇 배. 클수록 경사와 그림자가 강해짐
        light_dir: tuple[float, float] = (-1.0, -1.0),  # 빛이 오는 화면 방향 (기본: 왼쪽 위)
        light_altitude: float = 45.0,     # 광원 고도각(도). 낮을수록 그림자가 길어짐
        contrast: float = 1.3,            # 경사에 따른 명암 대비
        shadow_darkness: float = 0.35,    # 그림자 진 곳을 ramp에서 얼마나 내릴지 (0~1)
        shade_dither: float = 1.0,        # 명암 경계 디더링 강도 (0이면 계단식으로 끊김)
        band_dither: float = 0.02,        # 바이옴 경계 디더링 폭 (높이 단위)
        grain: float = 0.05,              # 픽셀 단위 잔노이즈 (질감)
        sea_level: float = 0.40,
        sand_level: float = 0.43,
        grass_level: float = 0.58,
        forest_level: float = 0.70,       # 이보다 높으면 고산 초지 (수목한계선)
        rock_level: float = 0.82,         # 이보다 높으면 눈
        rock_slope: float = 0.9,          # 이 경사(높이/거리, 픽셀 단위)부터 맨땅이 드러나기 시작
        # --- 재질 다양화
        curvature_strength: float = 0.35, # 능선은 더 맨땅, 골짜기는 더 초록으로 만드는 세기
        ridge_scale: float = 1.5,         # 능선/골짜기 판정 기준 (렌더 픽셀 높이 차)
        valley_green: float = 0.03,       # 골짜기를 따라 숲/풀이 위로 파고드는 정도 (높이 단위)
        aspect_strength: float = 1.0,     # 볕/그늘 사면에 따른 재질 차이 세기 (0이면 끔)
        geology_scale: float = 160.0,     # 암석 종류가 바뀌는 지역 크기 (렌더 픽셀)
        grass_mix: float = 0.3,            # 풀밭 중 죽은 풀/누런 풀 지역이 되는 비율 (반반씩). 0이면 끔
        soil_scale: float = 40.0,         # 풀색 지역 크기 (렌더 픽셀)
        altitude_tint: float = 14.0,      # 고도가 높을수록 식생을 차갑고 짙게 (RGB 기준). 0이면 끔
        snow_blend: float = 0.04,         # 설선 앞뒤로 눈이 0%→100%로 디더링되는 구간 폭 (높이 단위)
        ice_temp: float = 0.12,           # 기온이 이보다 낮으면 빙상(땅)과 바다 얼음 (기후를 줄 때만)
        water_depth: float = 0.25,        # 이만큼 깊어지면 가장 깊은 물 색
        # --- 물 표현 (각각 0/False면 끔)
        underwater_relief: float = 0.5,   # 물속 지형 명암이 비치는 세기 (얕을수록 강함)
        underwater_blur: int = 4,         # 물속 지형을 뭉개는 정도 (클수록 흐릿하게 비침)
        depth_curve: float = 0.7,         # 1보다 작으면 얕은 물(청록) 구간이 넓어진다
        outline_drop: float | None = 1.2, # 아래 픽셀과 높이 차(픽셀)가 이보다 크면 외곽선. None이면 끔
        foam: bool = True,
        color_noise: float = 18.0,        # 색 노이즈 세기 (RGB 0~255 기준, 실제 변화는 대부분 이것의 1/3 이하). 0이면 끔
        color_noise_scale: float = 40.0,  # 색 노이즈 덩어리 크기 (렌더 픽셀)
        height_noise: float = 0.015,      # 육지 렌더링 높이에 더할 노이즈 세기 (높이 단위). 0이면 끔
        height_noise_scale: float = 10.0, # 높이 노이즈 덩어리 크기 (렌더 픽셀)
        height_noise_fade: float = 0.02,  # 해수면에서 이 높이만큼 올라갈 때까지 노이즈를 서서히 키운다
        ramps: dict[int, list[tuple[int, int, int]]] | None = None,
        seed: int = 0,
    ):
        self.pixel_size = pixel_size
        self.relief = relief
        self.light_dir = light_dir
        self.light_altitude = light_altitude
        self.contrast = contrast
        self.shadow_darkness = shadow_darkness
        self.shade_dither = shade_dither
        self.band_dither = band_dither
        self.grain = grain
        self.sea_level = sea_level
        self.sand_level = sand_level
        self.grass_level = grass_level
        self.forest_level = forest_level
        self.rock_level = rock_level
        self.rock_slope = rock_slope
        self.curvature_strength = curvature_strength
        self.ridge_scale = ridge_scale
        self.valley_green = valley_green
        self.aspect_strength = aspect_strength
        self.geology_scale = geology_scale
        self.grass_mix = grass_mix
        self.soil_scale = soil_scale
        self.altitude_tint = altitude_tint
        self.snow_blend = snow_blend
        self.ice_temp = ice_temp
        self.water_depth = water_depth
        self.underwater_relief = underwater_relief
        self.underwater_blur = underwater_blur
        self.depth_curve = depth_curve
        self.outline_drop = outline_drop
        self.foam = foam
        self.color_noise = color_noise
        self.color_noise_scale = color_noise_scale
        self.height_noise = height_noise
        self.height_noise_scale = height_noise_scale
        self.height_noise_fade = height_noise_fade
        self.seed = seed

        ramps = ramps or DEFAULT_RAMPS
        n = {len(r) for r in ramps.values()}
        if len(n) != 1:
            raise ValueError('all ramps must have the same number of shades')
        self.n_shades = n.pop()
        self.palette = np.array([ramps[i] for i in range(len(ramps))], dtype=np.uint8)  # (biome, shade, 3)

    # ------------------------------------------------------------------ helpers
    def _downsample(self, h: NDArray[np.float64]) -> NDArray[np.float64]:
        p = self.pixel_size
        if p <= 1:
            return h
        H, W = h.shape[0] // p, h.shape[1] // p
        return h[:H * p, :W * p].reshape(H, p, W, p).mean(axis=(1, 3))

    def _light_vector(self) -> NDArray[np.float64]:
        alt = np.radians(self.light_altitude)
        dx, dy = self.light_dir
        norm = np.hypot(dx, dy) or 1.0
        return np.array([dx / norm * np.cos(alt), dy / norm * np.cos(alt), np.sin(alt)])

    def _cast_shadows(self, z: NDArray[np.float64]) -> NDArray[np.bool_]:
        """광원 쪽으로 한 칸씩 가면서, 지금 높이 + 광선 상승량보다 높은 지형이 있으면 그림자."""
        dx, dy = self.light_dir
        step = max(abs(dx), abs(dy)) or 1.0
        sx, sy = dx / step, dy / step                       # 한 걸음 = 큰 축으로 1픽셀
        rise = np.tan(np.radians(self.light_altitude)) * np.hypot(sx, sy)
        max_steps = int(min(512, np.ceil((z.max() - z.min()) / max(rise, 1e-6))))

        shadow = np.zeros(z.shape, dtype=bool)
        for s in range(1, max_steps + 1):
            blocker = _shift(z, int(round(sx * s)), int(round(sy * s)))
            shadow |= blocker > z + rise * s
        return shadow

    def _quantize(self, t: NDArray[np.float64], thresh: NDArray[np.float64]) -> NDArray[np.intp]:
        """0~1 값을 ramp 인덱스로. 경계는 Bayer 임계값으로 디더링."""
        d = self.shade_dither
        idx = np.floor(t * (self.n_shades - 1) + thresh * d + 0.5 * (1 - d))
        return np.clip(idx, 0, self.n_shades - 1).astype(np.intp)

    def _color_noise_delta(self, H: int, W: int) -> NDArray[np.float64]:
        """부드러운 노이즈 두 장으로 색을 따뜻함/밝기 방향으로 살짝 흔드는 RGB 변화량."""
        gen = opensimplex.OpenSimplex(self.seed)
        warm = _fbm(gen, H, W, self.color_noise_scale, 3, 0.0)
        bright = _fbm(gen, H, W, self.color_noise_scale * 0.7, 3, 1000.0)
        return (warm[..., None] * _WARM + bright[..., None] * _BRIGHT * 0.6) * self.color_noise

    def _classify(self, h, slope, ridge, sun, warp, geo, snow_noise, jitter, soil=None,
                  climate=None) -> NDArray[np.intp]:
        """높이로 식생을 정하고, 맨땅 점수(bareness)가 높을수록 흙/이끼 → 자갈 → 바위로 바꾼다.

        ridge: +1 능선 ~ -1 골짜기,  sun: +1 볕 드는 사면 ~ -1 그늘 사면
        """
        t = h + jitter * self.band_dither + warp * 0.01
        valley = np.clip(-ridge, 0, 1)
        sunny = np.clip(sun, 0, 1) * self.aspect_strength
        shady = np.clip(-sun, 0, 1) * self.aspect_strength

        # 식생: 골짜기와 그늘 사면은 '더 낮은 곳'처럼 취급해서 숲이 위로 파고든다
        hv = t - self.valley_green * valley - self.valley_green * 0.5 * shady
        if climate is None:
            grass_lv, forest_lv, rock_lv = self.grass_level, self.forest_level, self.rock_level
            open_m, woods_m, temp = GRASS, FOREST, None
        else:
            # 바이옴: 기온/습도에 디더 노이즈를 더해 고르므로 경계가 점점이 섞인다.
            # 습할수록 숲이 낮게 내려오고, 추울수록 수목한계선과 설선이 내려온다
            temp, moist = climate
            # 경계 근처는 노이즈 얼룩 + Bayer로 두 바이옴이 넓은 띠에 걸쳐 섞인다 (뚜렷한 선이 생기지 않게)
            mix_n = soil * 0.5 + warp * 0.5 if soil is not None else warp
            te = temp + jitter * 0.07 + mix_n * 0.07
            me = moist + jitter * 0.07 + mix_n * 0.08
            tb = np.digitize(te, TEMP_BANDS)
            mb = np.digitize(me, MOIST_BANDS)
            open_m, woods_m = BIOME_OPEN[tb, mb], BIOME_WOODS[tb, mb]
            grass_lv = self.grass_level - (me - 0.5) * 0.16
            # 아주 추워도 평지까지 눈이 덮이지는 않게 옮기는 폭에 한계를 둔다
            forest_lv = self.forest_level + np.clip(te - 0.6, -0.45, 0.35) * 0.25
            rock_lv = self.rock_level + np.clip(te - 0.6, -0.45, 0.35) * 0.22
        veg = np.select(
            [t < self.sand_level, hv < grass_lv, hv < forest_lv],
            [SAND, open_m, woods_m],
            ALPINE,                                    # 눈은 아래 블렌딩 규칙에서만 덮는다
        )
        # 볕 드는 사면의 풀은 마른 풀
        veg = np.where((veg == GRASS) & (sunny + jitter * 0.5 > 0.45), DRYGRASS, veg)
        # 풀색 지역: 높이/경사와 상관없이 큰 노이즈로 무작위 지역을 나눠 기본 풀 / 죽은 풀 / 누런 풀. 경계는 디더링
        grass = veg == GRASS
        if soil is not None and self.grass_mix > 0 and grass.any():
            g = soil + warp * 0.25 + jitter * 0.3
            lo, hi = np.quantile(g[grass], [1 - self.grass_mix, 1 - self.grass_mix / 2])
            veg = np.where(grass & (g > lo), np.where(g > hi, GRASS_YELLOW, GRASS_DEAD), veg)

        # 맨땅 점수: 가파를수록, 능선일수록, 높을수록 크다. 노이즈와 Bayer로 경계를 흔든다
        span = np.maximum(rock_lv - forest_lv, 0.02)
        bare = (slope / self.rock_slope
                + ridge * self.curvature_strength
                + np.clip((h - forest_lv) / span, 0, 1) * 0.25
                + warp * 0.15
                + jitter * 0.15)

        # 바위 종류는 넓은 지역 단위로 바뀐다. 설선에 가까울수록 차가운 회색 바위로 몰아서 눈과 어울리게
        high = np.clip((h - forest_lv) / span, 0, 1)
        g = geo * (1 - high) - high * 0.5 + jitter * 0.1
        if temp is not None:
            g = g + np.clip(temp - 0.7, 0, 1) * 1.5               # 더운 곳일수록 붉은 바위
        rock = np.select([g < -0.15, g < 0.2], [ROCK, ROCK_WARM], ROCK_RED)
        # 맨땅이 막 드러나는 단계: 그늘이면 이끼, 아니면 흙
        transition = np.where(shady > 0.25, MOSS, DIRT)

        mat = np.select([bare < 1.0, bare < 1.2, bare < 1.45], [veg, transition, SCREE], rock)
        pre_snow = mat.copy()
        # 눈: 설선(rock_level) 앞뒤 snow_blend 구간에서 0%→100%로 디더링.
        # 가파를수록 덜 쌓여서 바위가 드문드문 비친다
        cover = ((t - rock_lv) / self.snow_blend + 0.5
                 - np.clip(bare - 1.0, 0, 1) * 0.8
                 + warp * 0.3)
        mat[cover > jitter + 0.5] = SNOW
        # 눈 두 종류: 설선 쪽과 노이즈 얼룩은 묵은 눈, 꼭대기로 갈수록 밝은 눈. 경계는 디더링
        old = 0.6 + snow_noise * 0.9 - (t - rock_lv) / (self.snow_blend * 4)
        mat[(mat == SNOW) & (old > jitter + 0.5)] = SNOW_OLD
        # 계절용: 눈이 덮이기 전 재질과, 눈/묵은 눈이 되기까지의 여유 (0보다 크면 눈)
        self._raw = {'pre': pre_snow, 'cover': cover - (jitter + 0.5), 'old': old - (jitter + 0.5)}
        return mat

    def _biome_details(self, biome, clim, water, real_h, warp, jitter, gen) -> None:
        """바이옴 잔무늬: 사바나의 드문드문한 나무, 습한 물가 저지대의 습지."""
        H, W = biome.shape
        temp, moist = clim
        # 사바나 나무: 작은 노이즈 덩어리로 흩뿌린다 (격자 점이 되지 않게)
        trees = _fbm(gen, H, W, 3.0, 2, 6000.0) + jitter * 0.25
        biome[(biome == SAVANNA) & (trees > 0.38)] = SHRUB
        # 습지: 습하고 낮은 물가 (강, 호수, 바다 근처). 가장자리는 디더링
        dl = self._shore_distance(water, 6)
        low = real_h < self.sea_level + 0.03
        wet = moist + jitter * 0.1 + warp * 0.05 > 0.72
        soft = np.isin(biome, (GRASS, FOREST, TAIGA, RAINFOREST, GRASS_DEAD, GRASS_YELLOW, DRYGRASS))
        biome[soft & ~water & low & wet & (dl + jitter * 2 < 5) & (temp > 0.2)] = MARSH

    def _ice(self, biome, clim, water, real_h, warp, jitter, gen):
        """아주 추운 곳: 땅은 빙상(가파른 바위는 얼음 사이로 드러남), 바다는 떠 있는 얼음 조각.
        추울수록 바다 얼음이 빽빽하고, 덜 추우면 조각 사이로 물길이 보인다. 반환: 바다 얼음 마스크."""
        H, W = biome.shape
        temp = clim[0] + jitter * 0.04 + warp * 0.02
        cold = np.clip((self.ice_temp - temp) / 0.08, 0, 1)          # 0 = 얼음 없음 ~ 1 = 아주 추움
        if not cold.any():
            return np.zeros((H, W), bool)
        bare_rock = np.isin(biome, (ROCK, ROCK_WARM, ROCK_RED, SCREE))
        ice_zone = ~water & (cold > 0.15 + jitter * 0.3)
        self._raw_icezone = ice_zone                                   # 계절용: 이 안에 쌓인 눈은 빙상이 된다
        biome[ice_zone & ~bare_rock] = ICE
        # 바다 얼음: 깊을수록 덜 얼고, 노이즈 조각으로 깨진다
        depth = np.clip((self.sea_level - real_h) / self.water_depth, 0, 1)
        floes = (_fbm(gen, H, W, 9.0, 3, 7000.0) * 0.5 + 0.5) + jitter * 0.15
        cover = cold * 1.35 - depth * 0.3                             # 아주 추우면 깊은 바다까지 빽빽하게
        sea_ice = water & (floes < cover)
        self._raw_ice = np.where(water, cover - floes, -9.0)          # 계절용: 바다가 얼기까지의 여유
        biome[sea_ice] = SEA_ICE
        return sea_ice

    def _apply_coast(self, biome, coast, water, warp, jitter) -> None:
        """해안 종류에 맞춰 재질을 바꾼다. 경계는 노이즈와 Bayer 디더링으로 섞는다."""
        from engine.mapgen.coast_types import BEACH, DUNE as C_DUNE, LAGOON as C_LAGOON, MARSH as C_MARSH, ROCKY
        H, W = biome.shape
        p = self.pixel_size
        c = np.asarray(coast)[::p, ::p][:H, :W]
        land = ~water
        dl = self._shore_distance(water, 6)                       # 육지 칸: 물까지 거리 (0 = 물)
        soft = np.isin(biome, VEGETATION + (SAND, DIRT, MOSS))    # 바위/눈은 그대로 둔다
        # 석회암 바위 해안: 물가 2~3칸이 흰 바위. 안쪽 경계는 디더링
        rocky = land & (c == ROCKY) & soft & (dl + jitter * 2.0 + warp * 0.8 < 2.6)
        biome[rocky] = LIMESTONE
        # 모래사장: 높이가 조금 높아도 모래로. 안쪽 끝 한 줄은 반반 디더링
        beach = land & (c == BEACH) & soft
        inner_edge = beach & ~(_shift(beach, 1, 0) & _shift(beach, -1, 0) & _shift(beach, 0, 1) & _shift(beach, 0, -1)) & (dl > 1)
        biome[beach & ~(inner_edge & (jitter < 0))] = SAND
        # 사구: 모래보다 밝은 얼룩. 가장자리는 디더링으로 풀/모래와 섞인다
        dune = land & (c == C_DUNE) & soft & (warp * 0.6 + jitter > -0.35)
        biome[dune] = DUNE
        # 석호 물과 기슭 염습지
        biome[water & (c == C_LAGOON)] = LAGOON
        biome[land & (c == C_MARSH)] = MARSH

    @staticmethod
    def _shore_distance(land: NDArray[np.bool_], max_d: int) -> NDArray[np.int16]:
        """육지에서 몇 칸 떨어졌는지 (0 = 육지, 최대 max_d + 1).
        4방향/8방향 확장을 번갈아 써서 마름모나 사각형이 아닌 둥근 거리에 가깝게 만든다."""
        dist = np.full(land.shape, max_d + 1, dtype=np.int16)
        dist[land] = 0
        cur = land.copy()
        for k in range(1, max_d + 1):
            grown = cur | _shift(cur, 1, 0) | _shift(cur, -1, 0) | _shift(cur, 0, 1) | _shift(cur, 0, -1)
            if k % 2 == 0:
                grown |= _shift(cur, 1, 1) | _shift(cur, -1, 1) | _shift(cur, 1, -1) | _shift(cur, -1, -1)
            dist[grown & ~cur] = k
            cur = grown
        return dist

    def _noisy_land(self, h: NDArray[np.float64]) -> NDArray[np.float64]:
        """육지에만 렌더링용 높이 노이즈를 더한다. 해안선은 그대로 두려고 물가에서는 노이즈를 0으로 줄인다."""
        H, W = h.shape
        gen = opensimplex.OpenSimplex(self.seed)
        n = _fbm(gen, H, W, self.height_noise_scale, 3, 2000.0)
        fade = np.clip((h - self.sea_level) / self.height_noise_fade, 0, 1)
        noisy = np.maximum(h + n * self.height_noise * fade, self.sea_level)
        return np.where(h >= self.sea_level, noisy, h)

    # ------------------------------------------------------------------- render
    def render(self, hm: HeightMap | NDArray[np.float64], coast: NDArray[np.uint8] | None = None,
               climate=None, layers: dict | None = None) -> NDArray[np.uint8]:
        """(H, W, 3) uint8 RGB 이미지를 반환한다.
        coast: engine.mapgen.coast_types의 해안 종류 지도 (World.coast). 없으면 해안을 높이만으로 칠한다.
        climate: (기온, 습도) 0~1 지도 (World.climate). 없으면 식생을 높이만으로 칠한다.
        layers: dict를 주면 계절에 따라 다시 칠할 수 있게 픽셀별 정보를 채운다 (engine.render.seasons 참고)."""
        full = np.asarray(hm, dtype=np.float64)
        h = self._downsample(full)
        H, W = h.shape
        water = h < self.sea_level                       # 물 판정과 수심은 실제 높이 기준
        real_h = h
        if self.height_noise > 0:
            h = self._noisy_land(h)                      # 이후 조명/그림자/바이옴은 렌더링 높이 기준
        thresh = bayer(H, W)
        jitter = thresh - 0.5
        rng = np.random.default_rng(self.seed)

        # 물은 수면에서 평평하다고 보고 조명/그림자를 계산한다
        zscale = self.relief * full.shape[1] / self.pixel_size  # 높이 → (렌더) 픽셀 단위
        surface = np.maximum(h, self.sea_level)
        z = surface * zscale
        gy, gx = np.gradient(z)
        slope = np.hypot(gx, gy)

        # --- 조명: 평지가 ramp 가운데, 빛을 향한 경사는 밝게, 등진 경사는 어둡게
        L = self._light_vector()
        normal = np.stack([-gx, -gy, np.ones_like(z)])
        normal /= np.linalg.norm(normal, axis=0)
        diffuse = np.tensordot(L, normal, axes=1)
        shade = 0.5 + (diffuse - L[2]) * self.contrast
        shade += (rng.random((H, W)) - 0.5) * self.grain

        shadow = self._cast_shadows(z) if self.shadow_darkness > 0 else np.zeros((H, W), bool)
        shade -= shadow * self.shadow_darkness

        # --- 지형 분석 (자잘한 요철에 휘둘리지 않게 부드럽게 한 높이로)
        zs = _smooth(z, 2)
        ridge = np.clip((zs - _smooth(z, 8)) / self.ridge_scale, -1, 1)   # 주변보다 높으면 능선
        sgy, sgx = np.gradient(zs)
        snormal = np.stack([-sgx, -sgy, np.ones_like(zs)])
        snormal /= np.linalg.norm(snormal, axis=0)
        sun = np.clip((np.tensordot(L, snormal, axes=1) - L[2]) / 0.25, -1, 1)

        gen = opensimplex.OpenSimplex(self.seed)
        warp = _fbm(gen, H, W, 24.0, 3, 3000.0)
        geo = _fbm(gen, H, W, self.geology_scale, 2, 4000.0)

        snow_noise = _fbm(gen, H, W, 14.0, 2, 5000.0)
        soil = _fbm(gen, H, W, self.soil_scale, 3, 4500.0)

        clim = None
        if climate is not None:
            p = self.pixel_size
            clim = tuple(np.asarray(c, dtype=np.float64)[::p, ::p][:H, :W] for c in climate)
        self._raw_ice = None
        self._raw_icezone = None
        biome = self._classify(h, slope, ridge, sun, warp, geo, snow_noise, jitter, soil, clim)
        raw = self._raw
        sea_ice = self._finish_biome(biome, clim, water, real_h, warp, jitter, gen, coast)
        if layers is not None:
            # 눈이 없는 재질도 같은 순서로 마무리한다 (계절에 따라 눈이 걷히면 드러날 재질). 바다 얼음은 계절이 정한다
            pre = raw['pre']
            pre_ice = self._finish_biome(pre, clim, water, real_h, warp, jitter, gen, coast)
            pre[pre_ice] = WATER

        # --- 물: 땅과 같은 방식으로 칠한다
        #     수심(높이)으로 ramp 단계를 고르고, 물속 경사 명암 + 잔노이즈를 더해 Bayer 디더링으로 섞는다
        land = ~water
        depth = np.clip((self.sea_level - real_h) / self.water_depth, 0, 1) ** self.depth_curve
        water_shade = 1 - depth - shadow * self.shadow_darkness * 0.5
        water_shade += (rng.random((H, W)) - 0.5) * self.grain

        # 물속 지형 비침: 물 밑 경사의 명암을 뭉개서, 얕을수록 강하게
        if self.underwater_relief > 0:
            uz = _smooth(real_h * zscale, max(self.underwater_blur, 1))  # 물에 비친 듯 뭉개서
            ugy, ugx = np.gradient(uz)
            un = np.stack([-ugx, -ugy, np.ones_like(uz)])
            un /= np.linalg.norm(un, axis=0)
            under = (np.tensordot(L, un, axes=1) - L[2]) * self.contrast
            water_shade += under * self.underwater_relief * (1 - depth)

        land_shade = shade
        shade = np.where(water & ~sea_ice, water_shade, shade)      # 바다 얼음은 땅처럼 빛을 받는다
        idx = self._quantize(np.clip(shade, 0, 1), thresh)

        # --- 외곽선: 바로 아래(화면 남쪽) 픽셀이 확 낮으면 절벽 가장자리
        if self.outline_drop is not None:
            drop = z - _shift(z, 0, 1)
            idx[(drop > self.outline_drop) & ~water] = 0

        img = self.palette[biome, idx]

        # --- 거품: 땅에 맞닿은 물 픽셀
        near_land = (_shift(land, 1, 0) | _shift(land, -1, 0)
                     | _shift(land, 0, 1) | _shift(land, 0, -1))
        if self.foam:
            img[water & near_land & ~sea_ice] = DEFAULT_FOAM


        # --- 색 보정: 색 노이즈 + 고도에 따른 식생 색조
        delta = np.zeros((H, W, 3))
        noise_delta = self._color_noise_delta(H, W) if self.color_noise > 0 else np.zeros((H, W, 3))
        delta += noise_delta
        alt = np.clip((h - self.sea_level) / (self.rock_level - self.sea_level), 0, 1)
        if self.altitude_tint > 0:
            veg = np.isin(biome, VEGETATION)
            delta += ((alt - 0.3) * veg)[..., None] * _COOL * self.altitude_tint
        if self.color_noise > 0 or self.altitude_tint > 0:
            img = np.clip(img + delta, 0, 255).astype(np.uint8)

        if layers is not None:
            layers.update(
                pre=pre.astype(np.uint8), idx=idx.astype(np.uint8),
                idx_land=self._quantize(np.clip(land_shade, 0, 1), thresh).astype(np.uint8),
                snow_cover=raw['cover'].astype(np.float32), snow_old=raw['old'].astype(np.float32),
                ice=(self._raw_ice if self._raw_ice is not None else np.full((H, W), -9.0)).astype(np.float32),
                water=water, near_land=near_land, noise_delta=noise_delta, alt=alt, thresh=thresh,
                ice_zone=(self._raw_icezone if self._raw_icezone is not None else np.zeros((H, W), bool)),
                temperature=(clim[0] if clim is not None else np.full((H, W), 0.63)).astype(np.float32))
        return img

    def _finish_biome(self, biome, clim, water, real_h, warp, jitter, gen, coast):
        """분류 뒤 마무리: 바이옴 잔무늬, 물, 얼음, 해안 종류 (biome을 고친다). 반환: 바다 얼음 마스크."""
        if clim is not None:
            self._biome_details(biome, clim, water, real_h, warp, jitter, gen)
        biome[water] = WATER
        sea_ice = np.zeros(biome.shape, bool)
        if clim is not None:
            sea_ice = self._ice(biome, clim, water, real_h, warp, jitter, gen)
        if coast is not None:
            self._apply_coast(biome, coast, water, warp, jitter)
        return sea_ice
