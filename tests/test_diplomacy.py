"""외교 (sim/diplomacy.py): 요청 → 수락하면 동맹, 동맹끼리는 서로 치지 않는다, 자원(비율)·고른 병사 보내기, 깨면 배신자 (피해 증가·관계 하락)."""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.diplomacy import TRAITOR_HURT
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 4, seed=3, map_seed=7)                     # AI 없이 (World만)
    d, u = w.diplo, w.units
    d.request(0, 1)
    pending = (0, 1) in d.requests
    d.reply(1, 0, True)
    report('요청을 수락하면 동맹', pending and d.allied(0, 1) and not d.foe(0, 1) and d.foe(0, 2))

    # 동맹 병사 둘을 붙여 두면 서로 치지 않는다 (동맹이 아닌 나라와는 싸운다)
    hall = int(w.building_ids(0, R.HALL)[0])
    y, x = float(w.builds.y[hall]) + 8, float(w.builds.x[hall])
    a = u.add(0, R.INFANTRY, x, y, R.UNIT_STATS[R.INFANTRY]['hp'])
    b = u.add(1, R.INFANTRY, x + 1, y, R.UNIT_STATS[R.INFANTRY]['hp'])
    for _ in range(40):
        w._tick(0.05)
    calm = u.alive[a] and u.alive[b] and u.hp[a] == R.UNIT_STATS[R.INFANTRY]['hp'] and u.hp[b] == R.UNIT_STATS[R.INFANTRY]['hp']
    report('동맹 병사끼리는 서로 치지 않는다', bool(calm), f'체력 {u.hp[a]:.0f}, {u.hp[b]:.0f}')

    w.nations[0].res[R.FOOD] = 300
    before = w.nations[1].res[R.FOOD]
    d.give_res(0, 1, [0.25, 0, 0])
    report('동맹에게 자원 보내기 (가진 것의 25%)', abs(w.nations[1].res[R.FOOD] - before - 75) < 1e-6 and d.rel[1, 0] > 60)
    w.nations[0].sulfur, s1 = 40.0, w.nations[1].sulfur
    d.donate_cd[0] = 0
    d.give_res(0, 1, [0, 0, 0, 0.5])
    report('유황도 보낼 수 있다', abs(w.nations[1].sulfur - s1 - 20) < 1e-6 and abs(w.nations[0].sulfur - 20) < 1e-6)
    pick = w.unit_ids(0)[:2]
    d.troop_cd[0] = 0
    refused = d.give_units(0, 1, pick) == 0                      # 동맹은 다른 섬, 내 항구가 없다: 못 보낸다
    st = R.BUILD_STATS[R.HALL]                                   # 내 섬에 동맹의 거점을 하나 세워 두고 다시
    spot = w._open_spot(w.builds.y[hall], w.builds.x[hall], 28, 5)
    w.builds.add(1, R.HALL, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0)
    sent = d.give_units(0, 1, pick)
    goes = refused and sent == 2 and (u.own[pick] == 0).all() and d.marches
    for _ in range(int(200 / 0.2)):                              # update: 길찾기 계산도 돌아간다
        w.phase = 'play'
        w.update(0.2)
        if (u.own[pick] == 1).all():
            break
    report('병력 보내기: 바다 건너 항구가 없으면 못 보내고, 동맹 거점까지 가서 닿으면 소속이 바뀐다', bool(goes) and bool((u.own[pick] == 1).all()),
           f'보냄 {sent}, 소속 {u.own[pick].tolist()}, {w.time:.0f}초')

    d.end(0, 1, betray=True)
    report('동맹을 깨면 배신자 (받는 피해 증가, 배신당한 나라는 적대, 다른 나라도 관계 하락)',
           not d.allied(0, 1) and d.traitor(0) and d.hurt[0] == TRAITOR_HURT and d.level(1, 0) == 0 and d.rel[2, 0] < 0,
           f'관계 {d.rel[1, 0]:.0f}, {d.rel[2, 0]:.0f}')
