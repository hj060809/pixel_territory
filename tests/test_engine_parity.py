"""엔진 회귀: web_game/engine이 최상위 원본(map_gen, map_shader, viewer.seasons)과 비트 단위로 같은지."""
import dataclasses

import numpy as np

from tests import toplevel  # noqa: F401  (경로 설정)

import main as top_main
from map_gen import generate_world as top_generate, load_preset as top_preset
from map_shader.shader import PixelArtShader as TopShader
from viewer.seasons import SeasonPainter as TopPainter

from engine.mapgen import generate_world, load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene

CASES = [('기본', None, 1), ('대륙', 'continent', 42), ('열도', 'island_arc', 42),
         ('열대 섬', 'tropical_islands', 7), ('다양한 기후', 'varied_climates', 3)]
WORLD_KEYS = ('ocean', 'lakes', 'rivers', 'flow', 'coast', 'temperature', 'moisture')
SEASONS = [None, (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1), (0, 0, 0.4, 0.6), (0.3, 0, 0, 0.7)]


def _configs(preset, seed, size=384):
    top = top_main.make_config(size, seed)
    web = default_config(size, seed)
    assert dataclasses.asdict(top) == dataclasses.asdict(web), '기본 설정이 다르다'
    if preset:
        top, web = top_preset(preset, top), load_preset(preset, web)
    return top, web


def run(report):
    for name, preset, seed in CASES:
        top_cfg, web_cfg = _configs(preset, seed)
        a, b = top_generate(top_cfg), generate_world(web_cfg)
        same = np.array_equal(a.height.map, b.height.map) and all(
            np.array_equal(getattr(a, k), getattr(b, k)) for k in WORLD_KEYS)
        report(f'지형 생성: {name}', same)
        # 렌더 (계절용 정보 포함)
        top_layers, scene = {}, TerrainScene(b.height, b.coast, b.climate)
        top_day = TopShader().render(np.asarray(a.height, dtype=np.float64), a.coast, a.climate, layers=top_layers)
        same = np.array_equal(top_day, scene.day) and set(top_layers) == set(scene.layers) and all(
            np.array_equal(top_layers[k], scene.layers[k]) for k in top_layers)
        report(f'렌더: {name}', same)
        # 계절 칠하기, 그리고 새 state()가 원본의 '칠한 재질·얼음'과 같은지
        tp = TopPainter(top_layers, TopShader())
        ok_paint = ok_state = True
        for w in SEASONS:
            ok_paint &= np.array_equal(tp.paint(w), scene.seasons.paint(w))
            mat, ice = scene.seasons.state(w)
            ok_state &= np.array_equal(tp.mat, mat) and np.array_equal(tp.ice_mask, ice)
        report(f'계절 칠하기: {name}', ok_paint)
        report(f'계절 상태(state) = 칠한 재질: {name}', ok_state)
