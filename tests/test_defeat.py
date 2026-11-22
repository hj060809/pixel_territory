"""패배: 거점과 병사를 모두 잃으면 (자원지·망루가 남아도) 멸망하고, 남은 건물은 허물어진다. 거점이 하나라도 있으면 산다."""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 3, seed=3, map_seed=7)
    u, b = w.units, w.builds
    hall = int(w.building_ids(0, R.HALL)[0])
    st = R.BUILD_STATS[R.FARM]
    farm = b.add(0, R.FARM, b.x[hall] + 9, b.y[hall], st['hp'], st['r'], prog=1.0)
    u.alive[w.unit_ids(0)] = False                       # 병사를 모두 잃었다 (거점은 남았다)
    w._census()
    keep = w.nations[0].alive
    b.alive[hall] = False                                # 거점까지 잃었다 (농장은 남았다)
    w._census()
    report('거점과 병사를 모두 잃으면 패배 (자원지가 남아도)',
           keep and not w.nations[0].alive and w.phase == 'over' and not b.alive[farm],
           f'거점만 남았을 때 {keep}, 거점도 잃은 뒤 {w.nations[0].alive}, 농장 남음 {bool(b.alive[farm])}')
