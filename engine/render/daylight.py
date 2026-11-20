"""낮/밤 (최상위 viewer.day_night의 계산, 화면 없음). 웹에서는 셰이더가 같은 계산을 매 프레임 한다.

화면 전체에 같은 색을 곱하지 않고, 실제 빛처럼:
- 해의 고도가 시간에 따라 바뀐다 (방향은 고정). 해가 낮아지면 산 그림자가 길어져
  골짜기부터 어두워지고 봉우리에 마지막 빛이 남는다. 밤에는 달이 같은 방식으로 비춘다.
- 빛 받는 칸과 그늘진 칸을 다른 색으로 물들인다 (노을: 빛은 주황, 그늘은 보라).
  빛/그늘 경계는 Bayer 디더링으로 픽셀아트답게 나눈다.
- 물은 하늘색을 반사한다.

뷰어는 해가 조금 움직일 때만 빛/그늘을 다시 계산했지만(성능), 여기서는 부를 때마다 정확히 계산한다.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# 해 고도(도)별: 빛 받는 곳 색 배율, 그늘 색 배율, 하늘색, 물에 비치는 하늘 비율
LIGHT_KEYS = (
    (-30.0, (0.55, 0.64, 0.92), (0.30, 0.35, 0.58), (30, 50, 110), 0.08),    # 한밤 (달빛)
    (-10.0, (0.55, 0.58, 0.88), (0.34, 0.36, 0.62), (50, 55, 120), 0.08),    # 해 진 뒤 푸른 시간
    (-4.0,  (0.80, 0.60, 0.78), (0.44, 0.40, 0.66), (140, 80, 150), 0.10),   # 땅거미
    (0.0,   (1.10, 0.68, 0.52), (0.52, 0.44, 0.68), (255, 130, 100), 0.12),  # 해가 지평선에
    (6.0,   (1.14, 0.86, 0.64), (0.66, 0.60, 0.80), (255, 180, 120), 0.08),  # 황금빛 시간
    (16.0,  (1.06, 0.98, 0.88), (0.84, 0.82, 0.94), (205, 215, 235), 0.03),
    (32.0,  (1.00, 1.00, 1.00), (0.95, 0.95, 1.00), (180, 210, 240), 0.00),  # 한낮
    (90.0,  (1.00, 1.00, 1.00), (0.95, 0.95, 1.00), (180, 210, 240), 0.00),
)
MAX_SUN_ALT = 65.0      # 정오의 해 고도
MAX_MOON_ALT = 50.0     # 자정의 달 고도


class DayNightCycle:
    LIGHT_KEYS = LIGHT_KEYS

    def __init__(self, hour: float = 12.0, day_length: float = 120.0, auto: bool = True,
                 max_sun_alt: float = MAX_SUN_ALT, max_moon_alt: float = MAX_MOON_ALT):
        self.hour = hour % 24
        self.day_length = day_length              # 하루(24시간)가 몇 초에 지나가는지
        self.auto = auto
        self.max_sun_alt = max_sun_alt
        self.max_moon_alt = max_moon_alt

    # ------------------------------------------------------------- 시간
    def update(self, dt: float) -> None:
        if self.auto:
            self.advance(dt * 24.0 / self.day_length)

    def advance(self, hours: float) -> None:
        self.hour = (self.hour + hours) % 24

    def label(self) -> str:
        h = int(self.hour)
        return f'{h:02d}:{int((self.hour - h) * 60):02d}'

    def sun_alt(self) -> float:
        """6시에 뜨고 18시에 지는 해의 고도 (도). 밤에는 음수."""
        return self.max_sun_alt * np.sin(np.pi * (self.hour - 6.0) / 12.0)

    def moon_alt(self) -> float:
        return self.max_moon_alt * np.sin(np.pi * (self.hour - 18.0) / 12.0)

    # ------------------------------------------------------------- 빛
    def keyframe(self):
        """지금 해 고도의 (빛 색 배율, 그늘 색 배율, 하늘색, 물에 비치는 하늘 비율)."""
        alt = self.sun_alt()
        keys = self.LIGHT_KEYS
        alts = [k[0] for k in keys]
        i = int(np.clip(np.searchsorted(alts, alt, side='right') - 1, 0, len(keys) - 2))
        a0, a1 = keys[i], keys[i + 1]
        t = float(np.clip((alt - a0[0]) / (a1[0] - a0[0]), 0, 1))
        mix = lambda u, v: np.asarray(u, float) * (1 - t) + np.asarray(v, float) * t
        return mix(a0[1], a1[1]), mix(a0[2], a1[2]), mix(a0[3], a1[3]), a0[4] * (1 - t) + a1[4] * t

    def sources(self):
        """빛을 주는 해와 달: [(고도, 비중)]."""
        sun, moon = self.sun_alt(), self.moon_alt()
        return (
            (sun, np.clip(sun / 3.0, 0, 1)),                                        # 해: 뜨자마자 서서히
            (moon, np.clip((-sun - 6.0) / 6.0, 0, 1) * np.clip(moon / 3.0, 0, 1)),  # 달: 땅거미 뒤에
        )

    def lit(self, surface) -> NDArray[np.float32]:
        """칸마다 빛을 받는 정도 (0~1)."""
        lx, ly = surface.light_xy
        nx, ny, nz = surface.normal
        lit = np.zeros((surface.H, surface.W), dtype=np.float32)
        for alt, weight in self.sources():
            if weight <= 0 or alt <= 0:
                continue
            a = np.radians(alt)
            ndl = nx * (lx * np.cos(a)) + ny * (ly * np.cos(a)) + nz * np.sin(a)
            amount = np.clip(ndl / max(np.sin(a), 0.2), 0, 1)                    # 낮은 해에도 평지는 빛을 받게
            amount *= surface.horizon < np.tan(a)                                # 산에 가려지면 그늘
            lit += weight * amount
        return lit

    def lit_mask(self, surface) -> NDArray[np.bool_]:
        """빛 받는 칸 (경계는 디더링)."""
        return self.lit(surface) > surface.light_thresh

    def shade(self, img: NDArray[np.uint8], surface) -> NDArray[np.uint8]:
        """지금 시각의 빛을 입힌 이미지."""
        light, shadow, sky, sky_amount = self.keyframe()
        lit = self.lit_mask(surface)
        # 그늘 표(0~255)와 빛 표(256~511)를 이어 붙여서, 채널마다 표 조회 한 번으로 끝낸다
        v = np.arange(256, dtype=np.float64)[:, None]
        table = np.clip(np.concatenate([v * shadow, v * light]), 0, 255).astype(np.uint8)  # (512, 3)
        offset = lit.astype(np.uint16) * 256
        out = np.empty_like(img)
        for c in range(3):
            out[..., c] = table[:, c][img[..., c] + offset]
        if sky_amount > 0 and len(surface.water_y):
            wy, wx = surface.water_y, surface.water_x
            w = out[wy, wx].astype(np.float32)
            out[wy, wx] = (w * (1 - sky_amount) + np.asarray(sky, np.float32) * sky_amount).astype(np.uint8)
        return out
