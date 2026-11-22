"""야생 동물과 길들이기 (sim/wildlife.py).
- 넓은 초원에 야생말이 흩어져 생긴다 (지도 최대 수까지).
- 보병을 보내 길들이면 창기병, 궁수는 기마궁수가 된다 (훈련 버튼은 없다).
- 길들이는 중에 다른 명령을 받으면 끊기고 말은 다시 자유롭게 거닌다.
- 상태 메시지에 동물이 실리고, 사라진 동물은 사라진 목록으로 간다.
"""
import numpy as np

from engine.mapgen import load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.protocol import StateEncoder, decode
from sim import rules as R
from sim.entities import TAME
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    scene = TerrainScene.load(load_preset('continent', default_config(512, 42)), cache_dir, progress=lambda s: None)
    gm = GameMap(scene)
    w = World(gm, 2, seed=3, map_seed=42)
    wild = w.wild
    n = wild.count(R.HORSE)
    horses = [a for a in wild.animals.values() if a.kind == R.HORSE]
    report('야생말이 생긴다', n > 0 and n == wild.cap[R.HORSE], f'{n}마리 (최대 {wild.cap[R.HORSE]})')
    pts = np.array([(a.x, a.y) for a in horses])
    spread = float(np.ptp(pts[:, 0]) + np.ptp(pts[:, 1])) if len(pts) else 0.0
    report('넓게 흩어진다', spread > 80, f'가로+세로 폭 {spread:.0f}칸')
    report('기병은 훈련할 수 없다', not w.train(0, int(w.building_ids(0, R.HALL)[0]), R.LANCER, quiet=True))

    enc = StateEncoder(w)
    first = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    report('상태 메시지에 동물', sum(int(r['kind']) == R.HORSE for r in first['animals']) == n, f'{len(first["animals"])}')

    # 말 둘 곁에 보병, 궁수를 하나씩 두고 길들인다
    a1, a2 = horses[:2]
    inf = w.units.add(0, R.INFANTRY, a1.x + 4, a1.y, R.UNIT_STATS[R.INFANTRY]['hp'])
    arc = w.units.add(0, R.ARCHER, a2.x + 4, a2.y, R.UNIT_STATS[R.ARCHER]['hp'])
    for i, a in ((inf, a1), (arc, a2)):
        w.units.x[i] = a.x + 3
        w.units.y[i] = a.y
        if not gm.walk[int(w.units.y[i]), int(w.units.x[i])]:
            w.units.x[i], w.units.y[i] = a.x, a.y
    got = wild.order_tame(0, [inf], a1.id, quiet=True) + wild.order_tame(0, [arc], a2.id, quiet=True)
    report('길들이러 간다', got == 2 and w.units.state[inf] == TAME, f'{got}명')
    for _ in range(int((R.WILDLIFE[R.HORSE]['tame'] + 4) / 0.05)):
        if inf in wild.tamers:
            w.units.hp[inf] = R.UNIT_STATS[R.INFANTRY]['hp']    # 다른 나라 병사에 맞지 않게 (시험용)
        w._tick(0.05)
    report('보병 → 창기병', w.units.kind[inf] == R.LANCER and a1.id not in wild.animals,
           f'종류 {w.units.kind[inf]}, 말 남음 {a1.id in wild.animals}')
    report('궁수 → 기마궁수', w.units.kind[arc] == R.HORSE_ARCHER, f'종류 {w.units.kind[arc]}')
    later = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    gone = set(int(x) for x in later['animals_gone'])
    report('사라진 동물 목록', {a1.id, a2.id} <= gone, f'{sorted(gone)[:6]}')

    # 끊기: 길들이다 이동 명령
    a3 = next(a for a in wild.animals.values() if a.kind == R.HORSE and not wild.taming(a.id))
    i3 = w.units.add(0, R.INFANTRY, a3.x, a3.y, R.UNIT_STATS[R.INFANTRY]['hp'])
    wild.order_tame(0, [i3], a3.id, quiet=True)
    for _ in range(40):
        w._tick(0.05)
    w.order_move(np.array([i3]), a3.y + 20, a3.x)
    report('다른 명령이면 끊긴다', i3 not in wild.tamers and a3.prog == 0 and w.units.kind[i3] == R.INFANTRY)
