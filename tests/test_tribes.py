"""부족 (sim/tribes.py): 시작 거점 둘레 20칸의 육지 중 설원·사막 비율로 정한다 (40% 기준), 판의 나라마다 정해진다, 튜토리얼은 온대."""
from types import SimpleNamespace

import numpy as np

from engine.mapgen.defaults import default_config
from engine.render import materials as S
from engine.scene import TerrainScene
from sim import rules as R
from sim import tribes
from sim.terrain import GameMap
from sim.world import World


def fake_map(fill):
    """60×60 육지. fill(pre): 재질을 칠한다. 계절을 타지 않는 바탕은 pre와 같다고 친다."""
    pre = np.full((60, 60), S.GRASS, np.uint8)
    fill(pre)
    return SimpleNamespace(land=np.ones((60, 60), bool), layers={'pre': pre},
                           seasons=SimpleNamespace(state=lambda _w: (pre, None)))


def run(report, cache_dir='.cache'):
    # 1. 판정 기준 (가짜 지도): 가운데 (30, 30)에서 둘레 20칸
    def half_snow(pre):
        pre[:, :32] = S.SNOW                                     # 왼쪽 절반 남짓이 설원
    def a_bit_sand(pre):
        pre[:, :20] = S.DESERT                                   # 둘레의 일부만 사막 (40% 아래)
    def tundra(pre):
        pre[:, :] = S.TUNDRA
    def mixed(pre):
        pre[:, :25] = S.SNOW
        pre[:, 25:] = S.DUNE                                     # 둘 다 40% 넘으면 많은 쪽 (모래언덕)
    got = [tribes.classify(fake_map(f), 30, 30) for f in (half_snow, a_bit_sand, tundra, mixed, lambda p: None)]
    report('부족 판정: 설원 40% 이상 → 설원, 모자라면 온대, 툰드라도 설원, 둘 다면 많은 쪽, 아무것도 없으면 온대',
           got == [tribes.SNOW, tribes.TEMPERATE, tribes.SNOW, tribes.DESERT, tribes.TEMPERATE], f'{got}')

    # 2. 판: 나라마다 시작 거점 자리로 정한다
    seen = set()
    ok = True
    for seed in (7, 8767564):
        gm = GameMap(TerrainScene.load(default_config(512, seed), cache_dir, progress=lambda s: None))
        snow, sand = tribes.zones(gm)
        ok &= not (snow & sand).any() and not (snow & ~gm.land).any()
        w = World(gm, 6, seed=3, map_seed=seed)
        b = w.builds
        for n in w.nations:
            h = int(w.building_ids(n.id, R.HALL)[0])
            ok &= n.tribe == tribes.classify(gm, int(b.y[h]), int(b.x[h]))
            seen.add(n.tribe)
    report('판의 나라마다 시작 거점 자리로 부족이 정해진다 (설원·사막 지역은 겹치지 않는다)', ok, f'나온 부족 {sorted(seen)}')

    # 3. 튜토리얼은 온대
    from sim import tutorial
    w.nations[0].tribe = tribes.SNOW
    tutorial.setup(w, 0, 1)
    report('튜토리얼은 온대', w.nations[0].tribe == tribes.TEMPERATE)
