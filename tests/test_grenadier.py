"""유황 척탄병 (rules.GRENADIER, sim/grenade.py).
- 거점에서 훈련: 식량·목재와 함께 유황이 든다 (없으면 거절).
- 사거리 안의 적에게 단지를 던진다: fly초 뒤 직격 dmg, 맞은 자리에 burn초 동안 불 (burn_r칸, 초마다 burn_dps).
- 건물엔 직격 ×vs_build, 바위거북엔 ×1.5 (불은 껍질로 못 막는다), 설원 지역에 떨어지면 ×snow. 창기병은 척탄병에 ×1.5.
- 자기 나라 병사는 불에 맞지 않는다.
- 척탄병이 야생말을 길들이면 척탄기마병: 단지는 같고 빠르다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim import tribes
from sim.terrain import GameMap
from sim.world import World
from tests.test_formation import _open_area

G = R.GRENADE
ST = R.UNIT_STATS[R.GRENADIER]


def _fresh(gm):
    w = World(gm, 3, seed=5, map_seed=42)
    for i in w.unit_ids():
        w.units.alive[i] = False
    w.wild.animals.clear()
    return w


def _throw_once(w, g, target_hp_of, steps=None):
    """척탄병 g가 한 번 던져 (날아가 맞고 불이 꺼질 때까지) 일어난 일. 반환: (던짐 수, 불 수)."""
    thrown = fires = 0
    for _ in range(steps or int((ST['cd'] * 0.9) / 0.05)):
        t0 = w.time
        w.update(0.05)
        new = [r for r in w.recent if r[0] > t0 - 1e-9]
        thrown += sum(1 for r in new if r[5] == 15)
        fires += sum(1 for r in new if r[5] == 16)
    return thrown, fires


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = _fresh(gm)
    u, b = w.units, w.builds
    cx, cy = _open_area(gm, w)

    # 훈련: 유황이 든다
    hall = w.building_ids(0, R.HALL)[0]
    nat = w.nations[0]
    nat.res = [500.0, 500.0, 500.0]
    nat.sulfur = 0.0
    no = w.train(0, hall, R.GRENADIER, quiet=True)
    nat.sulfur = 40.0
    yes = w.train(0, hall, R.GRENADIER, quiet=True)
    report('척탄병 훈련: 유황이 없으면 거절, 있으면 식량·목재·유황을 쓴다',
           not no and yes and abs(nat.sulfur - (40 - ST['sulfur'])) < 1e-6 and abs(nat.res[R.WOOD] - (500 - ST['cost'][R.WOOD])) < 1e-6,
           f'유황 {nat.sulfur:.0f}, 목재 {nat.res[R.WOOD]:.0f}')
    b.queue[hall].clear()

    # 던지기: 직격 + 불
    gr = u.add(0, R.GRENADIER, cx - 6, cy, ST['hp'])
    foe = u.add(1, R.INFANTRY, cx + 1, cy, 400.0)
    u.freeze[foe] = 999.0
    hp0 = float(u.hp[foe])
    thrown, fires = _throw_once(w, gr, None, int((G['fly'] + G['burn'] + 0.2) / 0.05))
    lost = hp0 - float(u.hp[foe])
    want = ST['dmg'] + G['burn_dps'] * G['burn']          # 직격 + 불 (설원 아님)
    report('사거리 안의 적에게 단지를 던져 직격과 불 피해', thrown >= 1 and fires >= 1 and abs(lost - want) < 2.5,
           f'던짐 {thrown}, 불 {fires}, 잃은 체력 {lost:.1f} (예상 약 {want:.0f})')

    # 자기 편은 불에 맞지 않는다 (적 바로 옆의 아군)
    w2 = _fresh(gm)
    u2 = w2.units
    g2 = u2.add(0, R.GRENADIER, cx - 6, cy, ST['hp'])
    f2 = u2.add(1, R.INFANTRY, cx + 1, cy, 400.0)
    mate = u2.add(0, R.INFANTRY, cx + 1.8, cy + 0.6, 40.0)
    u2.freeze[f2] = u2.freeze[mate] = 999.0
    _throw_once(w2, g2, None, int((G['fly'] + G['burn'] + 0.2) / 0.05))
    report('자기 나라 병사는 불에 맞지 않는다', abs(float(u2.hp[mate]) - 40.0) < 1e-6, f'아군 체력 {float(u2.hp[mate]):.1f}')

    # 건물: 직격 ×vs_build
    w3 = _fresh(gm)
    u3, b3 = w3.units, w3.builds
    g3 = u3.add(0, R.GRENADIER, cx - 8, cy, ST['hp'])
    farm = b3.add(1, R.FARM, cx, cy, R.BUILD_STATS[R.FARM]['hp'], R.BUILD_STATS[R.FARM]['r'], prog=1.0)
    hp0 = float(b3.hp[farm])
    w3.order_attack(np.array([g3]), building=farm)
    _throw_once(w3, g3, None, int((ST['cd'] * 1.5) / 0.05))
    hits = round((hp0 - float(b3.hp[farm])) / (ST['dmg'] * G['vs_build']), 2)
    report('건물에는 직격 피해 ×2', hits >= 1 and abs(hits - round(hits)) < 0.02, f'건물 체력 {hp0:.0f} → {float(b3.hp[farm]):.0f} (×2 직격 {hits}번)')

    # 상성: 바위거북 ×1.5, 창기병 → 척탄병 ×1.5
    report('불은 바위거북에 ×1.5, 창기병은 척탄병에 ×1.5',
           abs(w.k_vs[R.GRENADIER, R.TORTOISE] - 1.5) < 1e-6 and abs(w.k_vs[R.LANCER, R.GRENADIER] - 1.5) < 1e-6)

    # 설원 지역에 떨어지면 ×snow
    snow, _ = tribes.zones(gm)
    cells = np.argwhere(snow & gm.walk)
    sy, sx = next(((y, x) for y, x in cells[::37] if gm.walk[y, x - 7:x + 2].all() and snow[y, x - 7:x + 2].all()), cells[0])
    w4 = _fresh(gm)
    u4 = w4.units
    g4 = u4.add(0, R.GRENADIER, sx - 6 + 0.5, sy + 0.5, ST['hp'])
    f4 = u4.add(1, R.INFANTRY, sx + 0.5, sy + 0.5, 400.0)
    u4.freeze[f4] = 999.0
    hp0 = float(u4.hp[f4])
    _throw_once(w4, g4, None, int((G['fly'] + G['burn'] + 0.2) / 0.05))
    lost = hp0 - float(u4.hp[f4])
    want = (ST['dmg'] + G['burn_dps'] * G['burn']) * G['snow'] * float(u4.fx_take[f4])
    report('설원 지역에 떨어지면 불이 약하다 (×0.7)', abs(lost - want) < 2.0, f'잃은 체력 {lost:.1f} (예상 약 {want:.1f})')

    # 척탄기마병: 척탄병이 야생말을 길들이면 된다, 단지를 똑같이 던진다
    w5 = World(gm, 3, seed=5, map_seed=42)
    for i in w5.unit_ids():
        w5.units.alive[i] = False
    u5, wild = w5.units, w5.wild
    horse = next(a for a in wild.animals.values() if a.kind == R.HORSE and a.unit < 0)
    g5 = u5.add(0, R.GRENADIER, horse.x + 2.0, horse.y, ST['hp'])
    if not gm.walk[int(u5.y[g5]), int(u5.x[g5])]:
        u5.x[g5], u5.y[g5] = horse.x, horse.y
    got = wild.order_tame(0, [g5], horse.id, quiet=True)
    for _ in range(int(25 / 0.05)):
        w5.update(0.05)
        if u5.kind[g5] == R.HORSE_GRENADIER:
            break
    tamed = int(u5.kind[g5]) == R.HORSE_GRENADIER
    report('척탄병이 야생말을 길들이면 척탄기마병 (빠르다)', got >= 1 and tamed and R.UNIT_STATS[R.HORSE_GRENADIER]['speed'] > ST['speed'],
           f'보냄 {got}, 병종 {R.UNIT_NAMES[int(u5.kind[g5])]}')
    wild.animals.clear()
    hx, hy = float(u5.x[g5]), float(u5.y[g5])
    f5 = u5.add(1, R.INFANTRY, hx + 6, hy, 400.0)
    if not gm.walk[int(hy), int(hx + 6)]:
        u5.x[f5] = hx - 6
    u5.freeze[f5] = 999.0
    hp0 = float(u5.hp[f5])
    thrown, fires = _throw_once(w5, g5, None, int((G['fly'] + G['burn'] + 0.2) / 0.05))
    report('척탄기마병도 단지를 던진다 (직격과 불)', thrown >= 1 and fires >= 1 and hp0 - float(u5.hp[f5]) > ST['dmg'] * 0.6,
           f'던짐 {thrown}, 잃은 체력 {hp0 - float(u5.hp[f5]):.1f}')
