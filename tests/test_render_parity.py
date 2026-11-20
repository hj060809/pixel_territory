"""렌더 회귀: web_game의 기준 구현(surface, daylight, water, frame)이 최상위 뷰어 화면과 비트 단위로 같은지.

뷰어 쪽: SceneCache + 계절 칠하기(제자리) + WaterAnimator.apply + 얼음 위 물결 지우기 + DayNightCycle.shade
(뷰어의 그림자 캐시가 끼지 않게 시각마다 새 DayNightCycle을 쓴다.)
"""
import numpy as np

from tests import toplevel  # noqa: F401

from map_shader.shader import PixelArtShader as TopShader
from viewer.day_night import DayNightCycle as TopCycle
from viewer.scene_cache import SceneCache
from viewer.water import WaterAnimator as TopWater

from engine.mapgen import generate_world, load_preset
from engine.mapgen.defaults import default_config
from engine.render.frame import FrameRenderer
from engine.scene import TerrainScene

# (시각, 계절 비중, 물결 시각)
FRAMES = [(12.0, None, 0.0), (7.5, (1, 0, 0, 0), 3.2), (17.6, (0, 0, 1, 0), 11.7), (19.2, (0, 0, 0.3, 0.7), 25.0),
          (23.5, (0, 0, 0, 1), 40.4), (5.6, (0.6, 0.4, 0, 0), 7.0), (14.0, (0, 1, 0, 0), None)]


def _top_frame(top, top_water, day0, hour, season, wave_t):
    if season is not None:
        top.day[...] = top.seasons.paint(season)
    else:
        top.day[...] = day0
    base = top.day
    if wave_t is not None:
        top_water._t = wave_t
        base = top_water.apply()
        ice = top.seasons.ice_mask if season is not None else None
        if ice is not None and ice.any():
            base[ice] = top.day[ice]
    return TopCycle(hour=hour).shade(base, top)


def run(report):
    for name, preset, seed in (('기본', None, 8767564), ('대륙', 'continent', 42)):
        cfg = default_config(384, seed)
        world = generate_world(load_preset(preset, cfg) if preset else cfg)
        scene = TerrainScene(world.height, world.coast, world.climate)
        top = SceneCache(world.height, TopShader(), coast=world.coast, climate=world.climate)
        day0 = top.day.copy()
        top_water = TopWater(top)
        fr = FrameRenderer(scene)
        ok = True
        for hour, season, wave_t in FRAMES:
            a = _top_frame(top, top_water, day0, hour, season, wave_t)
            b = fr.render(hour, season, wave_t)
            same = np.array_equal(a, b)
            ok &= same
            if not same:
                print(f'     다름: {name} {hour}시 계절 {season} 물결 {wave_t} — 다른 칸 {(a != b).any(-1).sum()}')
        report(f'화면 합성 = 뷰어 ({name}, {len(FRAMES)}장면: 낮·노을·밤·계절·물결)', ok)
