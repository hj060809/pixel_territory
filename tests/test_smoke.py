"""화면 없이 AI끼리 한 판 (서버처럼 계절에 맞춰 눈/얼음 갱신): 오류 없이 돌고, 한 걸음이 충분히 빠른지."""
import time

from engine.mapgen.defaults import default_config
from engine.render.seasons import SeasonCycle
from engine.scene import TerrainScene
from sim.terrain import GameMap
from sim.match import Match
from sim.world import TICK, World


def run(report, seconds=900, size=512, cache_dir='.cache'):
    scene = TerrainScene.load(default_config(size, 8767564), cache_dir, progress=lambda s: None)
    gm = GameMap(scene)
    w = World(gm, 5, seed=11, map_seed=8767564)
    m = Match(w)                                              # AI끼리 (사람 없음)
    cyc = SeasonCycle(year=0.05, year_length=360)
    t0 = time.perf_counter()
    painted = None
    for _ in range(seconds):
        cyc.advance(1 / 360)
        step = int(cyc.year * 240)
        if step != painted:                     # 계절이 1/240년 움직일 때마다 눈/얼음 갱신
            painted = step
            gm.set_season(cyc.weights())
        m.update(1.0, cyc.weights())
    ms = (time.perf_counter() - t0) / (seconds / TICK) * 1000
    alive = sum(n.alive for n in w.nations)
    report(f'AI끼리 {seconds}초 한 판: 걸음당 {ms:.2f} ms, 남은 나라 {alive}, 배 {w.fleet.log}', ms < 10)
