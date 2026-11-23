"""시뮬레이션 회귀.
- 게임 지도(걷기 비용, 엄폐, 바다, 겨울의 눈·얼음)가 최상위 원본(game/)과 같은지.
- 판: 같은 시드면 두 번 돌려도 같은 판인지 (numba 안의 난수도 판 시드로 정한다).
  판 규칙은 web_game에서 바뀌어서 (항구에 모여 차례로 타는 나룻배, 여러 섬에서 시작) 원본과 같은 판은 더 이상 비교하지 않는다.
  2026-11-20 전까지는 원본과 AI끼리 같은 판(기본 420초, 열도 900초)이 나오는 것을 확인했다."""
import numpy as np

from tests import toplevel  # noqa: F401

from game.terrain import GameMap as TopMap
from map_shader.shader import PixelArtShader as TopShader
from viewer.scene_cache import SceneCache

from engine.mapgen import generate_world, load_preset
from engine.mapgen.defaults import default_config
from engine.render.seasons import SeasonCycle
from engine.scene import TerrainScene
from sim.terrain import GameMap
from sim.match import Match
from sim.world import World

U_KEYS = ('x', 'y', 'hp', 'own', 'kind', 'state', 'slot', 'tgt', 'tgb', 'bld', 'alive', 'aboard')
B_KEYS = ('x', 'y', 'kind', 'own', 'hp', 'prog', 'site', 'alive')
MAP_KEYS = ('walk', 'cost', 'value', 'cover', 'cliff', 'ocean', 'nav', 'ford')


def _play(world, seconds, year_length=360.0):
    m = Match(world)                                          # AI끼리
    cyc = SeasonCycle(year=0.05, year_length=year_length)
    for _ in range(int(seconds)):
        cyc.advance(1 / year_length)
        m.update(1.0, cyc.weights())
    return world


def _snapshot(w):
    u, b = w.units, w.builds
    snap = {f'병사.{k}': getattr(u, k)[:u.n].copy() for k in U_KEYS}
    snap.update({f'건물.{k}': getattr(b, k)[:b.n].copy() for k in B_KEYS})
    snap['자원'] = np.array([n.res for n in w.nations])
    snap['나라'] = np.array([n.alive for n in w.nations])
    snap['배'] = np.array([(bt.own, bt.y, bt.x, bt.hp) for bt in w.fleet.boats]).reshape(-1, 4)
    snap['배 기록'] = np.array(list(w.fleet.log.values()))
    return snap


def run(report):
    _case(report, '기본 지형', None, 420)
    _case(report, '열도 (배가 뜨는 판)', 'island_arc', 900, map_seed=42, seed=5)


def _case(report, name, preset, seconds, seed=3, map_seed=8767564, size=384):
    cfg = default_config(size, map_seed)
    world = generate_world(load_preset(preset, cfg) if preset else cfg)
    scene = TerrainScene(world.height, world.coast, world.climate)
    top_scene = SceneCache(world.height, TopShader(), coast=world.coast, climate=world.climate)
    # 게임 지도: 처음 상태, 그리고 겨울 (원본은 '칠한 뒤 refresh', 새 코드는 set_season)
    tm, gm = TopMap(top_scene, world.coast), GameMap(scene)
    report(f'게임 지도 처음: {name}', all(np.array_equal(getattr(tm, k), getattr(gm, k)) for k in MAP_KEYS))
    w_winter = (0, 0, 0.2, 0.8)
    top_scene.seasons.paint(w_winter)
    tm.refresh_season()
    gm.set_season(w_winter)
    report(f'게임 지도 겨울 (눈, 얼어붙은 바다): {name}',
           all(np.array_equal(getattr(tm, k), getattr(gm, k)) for k in ('walk', 'cost', 'ice', 'nav')))
    # 판: 같은 시드로 두 번
    a = _snapshot(_play(World(GameMap(scene), 5, seed=seed, map_seed=map_seed), seconds))
    b = _snapshot(_play(World(GameMap(scene), 5, seed=seed, map_seed=map_seed), seconds))
    bad = [k for k in a if a[k].shape != b[k].shape or not np.array_equal(a[k], b[k])]
    report(f'같은 시드 → 같은 판, AI끼리 {seconds}초: {name} (병사 {int(a["병사.alive"].sum())}명, '
           f'건물 {int(a["건물.alive"].sum())}채, 나룻배 {int(a["배 기록"][0])}척 띄움)', not bad, ', '.join(bad))
