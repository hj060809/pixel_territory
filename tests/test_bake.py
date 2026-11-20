"""굽기: 묶음 파일 왕복, 묶음만으로 그린 그림(client_ref) = 엔진 기준 그림인지, 묶음 크기."""
import numpy as np

from engine.bake.bundle import bake
from engine.bake.client_ref import BundleRenderer
from engine.bake.container import pack, unpack
from engine.mapgen import generate_world, load_preset
from engine.mapgen.defaults import default_config
from engine.render.frame import FrameRenderer
from engine.scene import TerrainScene

FRAMES = [(12.0, (0, 1, 0, 0), 0.0), (7.5, (1, 0, 0, 0), 3.2), (17.6, (0, 0, 1, 0), 11.7),
          (19.2, (0, 0, 0.3, 0.7), 25.0), (23.5, (0, 0, 0, 1), 40.4), (12.0, None, None)]


def run(report, size=384):
    for name, preset, seed in (('기본', None, 8767564), ('열도', 'island_arc', 42)):
        cfg = default_config(size, seed)
        cfg = load_preset(preset, cfg) if preset else cfg
        world = generate_world(cfg)
        scene = TerrainScene(world.height, world.coast, world.climate)
        frame = FrameRenderer(scene)
        meta, arrays = bake(scene, frame, cfg, name)
        blob = pack(meta, arrays)
        meta2, arrays2 = unpack(blob)
        same = meta2 == meta or json_equal(meta2, meta)
        same &= all(np.array_equal(arrays[k], arrays2[k]) and arrays[k].dtype == arrays2[k].dtype for k in arrays)
        report(f'묶음 파일 왕복: {name}', same)
        client = BundleRenderer(meta2, arrays2)
        worst, exact = 1.0, 0
        for hour, season, wave_t in FRAMES:
            a = frame.render(hour, season, wave_t)
            b = client.render(hour, season, wave_t)
            match = float((a == b).all(-1).mean())
            worst = min(worst, match)
            exact += match == 1.0
        report(f'묶음만으로 그린 그림 = 엔진 그림: {name} ({len(FRAMES)}장면, 완전히 같은 장면 {exact}, '
               f'최저 일치율 {worst * 100:.4f}%)', worst >= 0.999)
        report(f'묶음 크기: {name} {size}x{size} → {len(blob) / 1e6:.2f} MB '
               f'(압축 전 {sum(a.nbytes for a in arrays.values()) / 1e6:.1f} MB)', len(blob) < 8e6 * (size / 512) ** 2)


def json_equal(a, b):
    import json
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
