"""자원 한도 (sim/storage.py): 자원마다 기본 + 거점 + 자원 건물, 넘치는 자원은 버려진다,
거점·자원 건물이 무너지면 그 몫을 마지막으로 친 나라가 가져간다. 놓기 명령 이름, 비용이 처음 한도 안인지."""
import re
from pathlib import Path

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.commands import PLACE_KINDS
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 3, seed=3, map_seed=7)
    b = w.builds
    me, foe = w.nations[0], w.nations[1]
    hall = int(w.building_ids(0, R.HALL)[0])
    w.update(0.1)
    start = R.STORE_BASE + R.STORE_HALL
    report('처음 한도 = 기본 + 거점 하나 (자원마다)', all(abs(c - start) < 1e-6 for c in me.caps), f'한도 {me.caps}')

    me.res = [9999.0, 9999.0, 9999.0]                          # 개발 명령·선물로 받은 것: 한도를 넘어도 깎지 않는다
    me.sulfur = 9999.0
    w.update(0.1)
    kept = all(me.res[k] > 9999.0 - 5 for k in range(3)) and me.sulfur > 9999.0 - 5
    me.res = [float(me.caps[k]) for k in range(3)]                # 한도에 찬 상태: 생산은 더 쌓이지 않는다
    me.sulfur = float(me.caps[3])
    me.rate = [1.0, 1.0, 1.0]
    w.update(0.5)
    full = all(me.res[k] <= me.caps[k] + 1e-3 for k in range(1, 3))
    report('한도는 자원 건물 생산에만: 명령·선물로 넘게 가진 것은 그대로, 한도에 차면 생산은 더 안 쌓인다', kept and full,
           f'넘게 가짐 그대로 {kept}, 한도에서 멈춤 {full} ({[round(v) for v in me.res]} / {[round(c) for c in me.caps[:3]]})')

    fs = R.BUILD_STATS[R.FARM]
    farm = b.add(0, R.FARM, b.x[hall] + 10, b.y[hall], fs['hp'], fs['r'], prog=0.5)
    w.update(0.1)
    half = list(me.caps)
    b.prog[farm] = 1.0
    w.update(0.1)
    report('다 지은 자원 건물은 그 자원 한도만 늘린다 (농장: 식량 +STORE_SITE)',
           abs(half[0] - start) < 1e-6 and abs(me.caps[0] - start - R.STORE_SITE) < 1e-6 and all(abs(me.caps[k] - start) < 1e-6 for k in (1, 2, 3)),
           f'짓는 중 {half}, 다 지은 뒤 {me.caps}')

    me.res = [200.0, 150.0, 100.0]
    foe.res = [0.0, 0.0, 0.0]
    b.last[farm] = foe.id                                # 적이 마지막으로 쳤다
    b.hp[farm] = 0.0
    total = start + R.STORE_SITE
    w.update(0.1)
    want = 200 * R.STORE_SITE / total                    # 농장 몫 = 식량 × 농장이 늘린 한도 / 식량 한도
    report('무너진 자원 건물의 몫을 친 나라가 가져간다 (그 자원만)',
           abs(foe.res[0] - want) < 2 and foe.res[1] < 1 and foe.res[2] < 1 and abs(me.res[0] - (200 - want)) < 2,
           f'적 {[round(v) for v in foe.res]}, 나 {[round(v) for v in me.res]}, 기대 {want:.0f}')
    report('건물을 잃은 뒤 남은 자원은 남은 한도 안', all(me.res[k] <= me.caps[k] + 1e-3 for k in range(3)) and abs(me.caps[0] - start) < 1e-6,
           f'한도 {me.caps}, 자원 {[round(v) for v in me.res]}')

    # 실제 싸움: 적 병사가 건물을 치면 마지막으로 친 나라가 기록된다
    f2 = b.add(0, R.FARM, b.x[hall] - 10, b.y[hall], fs['hp'], fs['r'], prog=1.0)
    ids = [w._spawn_unit(foe.id, R.INFANTRY, int(b.y[f2]), int(b.x[f2]) - 5, 2) for _ in range(3)]
    w.order_attack(ids, building=f2)
    for _ in range(100):
        w.update(0.1)
        if b.last[f2] == foe.id:
            break
    report('적 병사가 건물을 치면 마지막으로 친 나라가 기록된다', int(b.last[f2]) == foe.id, f'기록 {int(b.last[f2])}, 병사 {ids}')

    # 놓기 명령: 모든 건물 종류에 서버 이름이 있고, 화면(controller.ts BUILD_NAMES_EN)과 같은 순서
    ts = Path(__file__).resolve().parents[1] / 'web' / 'src' / 'game' / 'controller.ts'
    m = re.search(r"BUILD_NAMES_EN = \[([^\]]*)\]", ts.read_text(encoding='utf-8'))
    names = re.findall(r"'([a-z_]+)'", m.group(1)) if m else []
    same = [PLACE_KINDS.get(n) for n in names] == list(range(len(R.BUILD_STATS)))
    report('모든 건물에 놓기 명령 이름 (화면과 서버가 같다)', same and set(PLACE_KINDS.values()) == set(R.BUILD_STATS),
           f'화면 {names}, 서버 {sorted(PLACE_KINDS, key=PLACE_KINDS.get)}')

    # 어떤 비용도 처음 한도보다 크면 안 된다 (모을 수가 없다)
    costs = [max(v['cost']) for v in R.BUILD_STATS.values()] + [max(v['cost']) for v in R.UNIT_STATS.values()]
    costs += [max(R.WARSHIP_COST)] + [a.get('food', 0) for a in R.WILDLIFE.values()] + [v.get('sulfur', 0) for v in R.BUILD_STATS.values()]
    report('모든 비용이 처음 한도 안', max(costs) <= start, f'가장 큰 비용 {max(costs)}, 한도 {start}')
