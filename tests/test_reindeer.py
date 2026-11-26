"""순록 (sim/wildlife.py, rules.WILDLIFE[REINDEER]): 넓고 낮은 설원·툰드라에 촘촘한 무리로 산다, 사람을 보면 달아난다,
길들일 수 없다 (오른쪽 클릭하면 병사는 그냥 그 자리로 간다), AI도 길들이려 하지 않는다. 목장은 docs/PASTURE_PLAN.md 3단계."""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.protocol import StateEncoder, decode
from sim import rules as R
from sim import tribes
from sim.commands import PlayerCommands
from sim.terrain import GameMap
from sim.wildlife import FLEE
from sim.world import World


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 4, seed=3, map_seed=7)
    wild = w.wild
    rd = [a for a in wild.animals.values() if a.kind == R.REINDEER]
    snow, _ = tribes.zones(gm)
    on_snow = all(snow[int(a.y), int(a.x)] for a in rd)
    report('순록이 설원에 생긴다 (지도 최대 수까지)', len(rd) > 0 and len(rd) == wild.cap[R.REINDEER] and on_snow,
           f'{len(rd)}마리 (최대 {wild.cap[R.REINDEER]}), 모두 설원 {on_snow}')
    # 촘촘한 무리: 가장 가까운 다른 순록까지가 가깝다
    pts = np.array([(a.x, a.y) for a in rd])
    nn = [float(np.sort(np.hypot(pts[:, 0] - x, pts[:, 1] - y))[1]) for x, y in pts]
    report('촘촘한 무리로 산다', float(np.median(nn)) < 6.0, f'가장 가까운 순록까지 중간값 {np.median(nn):.1f}칸')

    enc = StateEncoder(w)
    first = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    report('상태 메시지에 순록', sum(int(r['kind']) == R.REINDEER for r in first['animals']) == len(rd))

    # 길들일 수 없다: 오른쪽 클릭하면 병사는 그 자리로 걸어간다
    a = rd[0]
    inf = w.units.add(0, R.INFANTRY, a.x + 6, a.y, R.UNIT_STATS[R.INFANTRY]['hp'])
    report('순록은 길들일 수 없다', wild.order_tame(0, [inf], a.id, quiet=True) == 0 and inf not in wild.tamers)
    c = PlayerCommands(w, 0)
    shown = c.command([(inf, int(w.units.gen[inf]))], [], a.x, a.y)
    report('오른쪽 클릭: 길들이지 않고 그 자리로 간다', shown != 'tame' and inf not in wild.tamers and w.units.state[inf] != 5, f'{shown}')

    # 사람이 다가가면 달아난다
    b = rd[-1]
    w.units.add(0, R.INFANTRY, b.x + 2.0, b.y, R.UNIT_STATS[R.INFANTRY]['hp'])
    wild._fear_t = 0.0
    wild.update(0.05)
    report('사람이 다가가면 달아난다', b.mode == FLEE, f'상태 {b.mode}')

    # AI는 순록을 길들이러 가지 않는다 (판이 돌아가며 순록 수가 줄지 않는다, 길들이는 병사도 순록에 붙지 않는다)
    from sim.match import Match
    m = Match(w)
    for _ in range(600):
        m.update(0.5)
    tamed = [t for t in wild.tamers.values() if t.aid in wild.animals and wild.animals[t.aid].kind == R.REINDEER]
    report('AI는 순록을 길들이지 않는다 (판이 멈추지도 않는다)', not tamed and wild.count(R.REINDEER) > 0,
           f'남은 순록 {wild.count(R.REINDEER)}, 다른 동물 길들이는 병사 {len(wild.tamers)}')
