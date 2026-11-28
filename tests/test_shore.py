"""전함의 지상 포격, 땅에서 배로 (sim/boats.py, rules.SHORE).
- 전함은 사거리 안에 적 배가 없으면 해안의 적 병사·건물을 쏜다 (건물 ×vs_build, 둘레 병사는 ×splash_mul).
- 포격하라고 찍은 땅의 목표가 멀면 사거리 안의 바다까지 가서 쏜다.
- 땅의 원거리 병사 (궁수, 척탄병: 나무배에 ×vs_pot)와 망루는 칠 것이 없으면 사거리 안의 적 배를 쏜다.
- 날고 있는 용기사는 포격하지 않는다.
- 원거리 병사는 사거리 안의 적 (병사·배)을 먼저, 그 안에서 가장 세게 맞는 쪽을 노린다 (배 공격 명령도).
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.boats import WARSHIP, Boat
from sim.terrain import GameMap
from sim.world import World


def _coast(gm, need_far=False):
    """바다 칸 (y, x)과 그 둘레 4~7칸의 걸을 수 있는 땅 칸, (need_far면 바다 쪽으로 30칸 넘게 떨어진 바다 칸도)."""
    m = gm
    sea = np.argwhere(m.nav)
    rng = np.random.default_rng(3)
    for k in rng.permutation(len(sea))[:4000]:
        sy, sx = sea[k]
        if not (12 < sy < m.H - 12 and 12 < sx < m.W - 12):
            continue
        win = m.walk[sy - 7:sy + 8, sx - 7:sx + 8] & m.land[sy - 7:sy + 8, sx - 7:sx + 8]
        pts = np.argwhere(win)
        if len(pts) < 20:
            continue
        d = np.hypot(pts[:, 0] - 7, pts[:, 1] - 7)
        ok = pts[(d >= 4) & (d <= 7)]
        if len(ok) < 6:
            continue
        land = [(int(sy - 7 + y), int(sx - 7 + x)) for y, x in ok[:6]]
        return (int(sy), int(sx)), land
    raise AssertionError('해안을 찾지 못함')


def _world(gm):
    w = World(gm, 3, seed=5, map_seed=42)
    for i in w.unit_ids():
        w.units.alive[i] = False
    w.wild.animals.clear()
    return w


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    (sy, sx), land = _coast(gm)

    # 1. 해안의 적 병사를 저절로 포격
    w = _world(gm)
    u = w.units
    ship = w.fleet._add(Boat(WARSHIP, 0, sy + 0.5, sx + 0.5, R.WARSHIP_HP))
    ly, lx = land[0]
    foe = u.add(1, R.INFANTRY, lx + 0.5, ly + 0.5, 400.0)
    u.freeze[foe] = 999.0
    hp0 = float(u.hp[foe])
    shells = 0
    for _ in range(int(4 / 0.05)):
        t0 = w.time
        w.update(0.05)
        shells += sum(1 for r in w.recent if r[0] > t0 - 1e-9 and r[5] == 2 and gm.land[int(r[4]), int(r[3])])
    report('전함이 해안의 적 병사를 저절로 포격한다', u.hp[foe] < hp0 and shells >= 1, f'체력 {hp0:.0f} → {float(u.hp[foe]):.0f}, 포탄 {shells}')
    u.alive[foe] = False

    # 2. 건물엔 ×vs_build
    farm = w.builds.add(1, R.FARM, lx + 0.5, ly + 0.5, R.BUILD_STATS[R.FARM]['hp'], R.BUILD_STATS[R.FARM]['r'], prog=1.0)
    hp0 = float(w.builds.hp[farm])
    ship.cd = 0.0
    w.update(0.05)
    mid = hp0 - float(w.builds.hp[farm])
    for _ in range(int(R.WARSHIP_FLY / 0.05) + 1):
        w.update(0.05)
    lost = hp0 - float(w.builds.hp[farm])
    report('건물 포격은 ×1.5, 포탄이 떨어질 때 맞는다', mid == 0 and abs(lost - R.WARSHIP_DMG * R.SHORE['vs_build']) < 0.5,
           f'쏜 순간 {mid:.1f}, {R.WARSHIP_FLY}초 뒤 한 방 {lost:.1f}')
    w.builds.alive[farm] = False

    # 3. 멀리서 포격 명령: 사거리 안의 바다까지 가서 쏜다
    w3 = _world(gm)
    sea = np.argwhere(gm.nav)
    d = np.hypot(sea[:, 0] - sy, sea[:, 1] - sx)
    far = sea[(d > R.WARSHIP_RANGE + 12) & (d < R.WARSHIP_RANGE + 30)]
    far = next(((int(y), int(x)) for y, x in far if w3.fleet._path(y + 0.5, x + 0.5, w3.fleet._point_goal(sy, sx, 2)) is not None), None)
    ship3 = w3.fleet._add(Boat(WARSHIP, 0, far[0] + 0.5, far[1] + 0.5, R.WARSHIP_HP))
    b3 = w3.builds.add(1, R.FARM, lx + 0.5, ly + 0.5, R.BUILD_STATS[R.FARM]['hp'], R.BUILD_STATS[R.FARM]['r'], prog=1.0)
    w3.fleet.bombard([ship3], building=b3)
    for _ in range(int(40 / 0.05)):
        w3.update(0.05)
        if not w3.builds.alive[b3]:
            break
    keep = R.WARSHIP_RANGE * R.SHORE['keep_min']
    d3 = float(np.hypot(ship3.x - (lx + 0.5), ship3.y - (ly + 0.5))) - R.BUILD_STATS[R.FARM]['r']
    report('포격 명령: 멀면 다가가 무너뜨리되, 해안에서 떨어져 쏜다', not w3.builds.alive[b3] and d3 >= keep - 1.0,
           f'처음 거리 {float(np.hypot(far[0] - ly, far[1] - lx)):.0f}칸, 쏜 거리 {d3:.1f}칸 (최소 {keep:.1f}), 남은 체력 {float(w3.builds.hp[b3]):.0f}')

    # 거리 두기: 해안 건물 바로 앞에서 포격하던 전함은 물러나며 계속 쏜다
    w6 = _world(gm)
    ship6 = w6.fleet._add(Boat(WARSHIP, 0, sy + 0.5, sx + 0.5, R.WARSHIP_HP))
    b6 = w6.builds.add(1, R.HALL, lx + 0.5, ly + 0.5, 99999.0, R.BUILD_STATS[R.HALL]['r'], prog=1.0)
    d0 = float(np.hypot(ship6.x - (lx + 0.5), ship6.y - (ly + 0.5))) - R.BUILD_STATS[R.HALL]['r']
    hp0 = float(w6.builds.hp[b6])
    for _ in range(int(10 / 0.05)):
        w6.update(0.05)
    d1 = float(np.hypot(ship6.x - (lx + 0.5), ship6.y - (ly + 0.5))) - R.BUILD_STATS[R.HALL]['r']
    report('해안 목표가 너무 가까우면 물러나며 계속 쏜다', d1 >= keep - 1.0 and w6.builds.hp[b6] < hp0,
           f'거리 {d0:.1f} → {d1:.1f}칸 (최소 {keep:.1f}), 거점 체력 {hp0:.0f} → {float(w6.builds.hp[b6]):.0f}')

    # 거리 두기: 적 전함끼리 바짝 붙으면 벌린다
    w7 = _world(gm)
    pts = np.argwhere(gm.nav)
    pair = None
    for y, x in pts[::97]:
        if 20 < y < gm.H - 20 and 20 < x < gm.W - 20 and gm.nav[y - 15:y + 16, x - 15:x + 16].mean() > 0.97:
            pair = (int(y), int(x))
            break
    a7 = w7.fleet._add(Boat(WARSHIP, 0, pair[0] + 0.5, pair[1] + 0.5, 9999.0))
    b7 = w7.fleet._add(Boat(WARSHIP, 1, pair[0] + 0.5, pair[1] + 3.5, 9999.0))
    for _ in range(int(10 / 0.05)):
        w7.update(0.05)
    gap = float(np.hypot(a7.x - b7.x, a7.y - b7.y))
    report('적 전함과 바짝 붙으면 거리를 벌리며 싸운다', gap >= keep - 1.0 and a7.hp < 9999 and b7.hp < 9999,
           f'거리 3.0 → {gap:.1f}칸 (최소 {keep:.1f})')


    # 4. 땅에서 배로: 궁수, 척탄병 (×2), 망루
    w4 = _world(gm)
    u4 = w4.units
    ship4 = w4.fleet._add(Boat(WARSHIP, 1, sy + 0.5, sx + 0.5, 9999.0))
    ship4.cd = 1e9                                   # 맞기만 한다 (쏘면 거리를 두려 물러난다)
    arc = u4.add(0, R.ARCHER, land[1][1] + 0.5, land[1][0] + 0.5, 26.0)
    hp0 = ship4.hp
    for _ in range(int(2 / 0.05)):
        w4.update(0.05)
    arrows = hp0 - ship4.hp
    u4.alive[arc] = False
    gr = u4.add(0, R.GRENADIER, land[1][1] + 0.5, land[1][0] + 0.5, 30.0)
    hp1 = ship4.hp
    for _ in range(int(3.2 / 0.05)):
        w4.update(0.05)
    pots = hp1 - ship4.hp
    u4.alive[gr] = False
    want_pot = R.UNIT_STATS[R.GRENADIER]['dmg'] * R.SHORE['vs_pot']
    report('땅의 궁수·척탄병이 적 전함을 쏜다 (척탄병 ×2)', arrows >= R.UNIT_STATS[R.ARCHER]['dmg'] - 1e-3 and pots >= want_pot - 0.5,
           f'화살 {arrows:.1f}, 단지 {pots:.1f} (한 번 {want_pot:.0f})')
    tw = w4.builds.add(0, R.TOWER, land[2][1] + 0.5, land[2][0] + 0.5, R.BUILD_STATS[R.TOWER]['hp'], R.BUILD_STATS[R.TOWER]['r'], prog=1.0)
    hp2 = ship4.hp
    for _ in range(int(2 / 0.05)):
        w4.update(0.05)
    report('망루도 사거리 안의 적 전함을 쏜다', hp2 - ship4.hp >= R.TOWER_DMG - 1e-3, f'{hp2 - ship4.hp:.1f}')
    w4.builds.alive[tw] = False

    # 5. 날고 있는 용기사는 포격하지 않는다 (멈춰 내려앉은 용기사는 누구에게나 맞는다)
    w5 = _world(gm)
    u5 = w5.units
    ship5 = w5.fleet._add(Boat(WARSHIP, 0, sy + 0.5, sx + 0.5, R.WARSHIP_HP))
    rider = u5.add(1, R.DRAGON_RIDER, land[0][1] + 0.5, land[0][0] + 0.5, R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    u5.air[rider] = True
    flying = w5.fleet._land_foe(ship5, R.WARSHIP_RANGE)
    u5.air[rider] = False
    landed = w5.fleet._land_foe(ship5, R.WARSHIP_RANGE)
    report('날고 있는 용기사는 포격하지 않는다 (내려앉으면 맞는다)', flying is None and landed == ('u', rider), f'날 때 {flying}, 내려앉으면 {landed}')


    # 6. 세게 맞는 쪽을 노린다: 척탄병은 사거리 안의 보병 (×1)보다 적 전함 (×2)
    w8 = _world(gm)
    u8 = w8.units
    ship8 = w8.fleet._add(Boat(WARSHIP, 1, sy + 0.5, sx + 0.5, 9999.0))
    ship8.cd = 1e9
    g8 = u8.add(0, R.GRENADIER, land[1][1] + 0.5, land[1][0] + 0.5, 30.0)
    f8 = u8.add(1, R.INFANTRY, land[2][1] + 0.5, land[2][0] + 0.5, 400.0)
    u8.freeze[f8] = 999.0
    for _ in range(int(3.2 / 0.05)):
        w8.update(0.05)
    report('척탄병은 사거리 안의 보병보다 적 전함 (×2)을 노린다', ship8.hp < 9999 and u8.hp[f8] >= 400 - 1e-3,
           f'전함 {9999 - ship8.hp:.0f} 피해, 보병 {400 - float(u8.hp[f8]):.0f} 피해')

    # 7. 궁수는 가까운 바위거북 (×0.6)보다 조금 먼 보병 (×1)을
    w9 = _world(gm)
    u9 = w9.units
    pts = np.argwhere(gm.walk & gm.land & (gm.cover >= 0.99))
    a = next((int(y), int(x)) for y, x in pts[::37] if 20 < y < gm.H - 20 and 20 < x < gm.W - 20
             and (gm.walk[y - 8:y + 9, x - 8:x + 9] & (gm.cover[y - 8:y + 9, x - 8:x + 9] >= 0.99)).all())
    arc9 = u9.add(0, R.ARCHER, a[1] + 0.5, a[0] + 0.5, 26.0)
    tt = u9.add(1, R.TORTOISE, a[1] + 4.5, a[0] + 0.5, 600.0)
    inf = u9.add(1, R.INFANTRY, a[1] + 0.5, a[0] + 8.5, 400.0)
    u9.freeze[[tt, inf]] = 999.0
    for _ in range(int(3 / 0.05)):
        w9.update(0.05)
    report('궁수는 가까운 바위거북 (×0.6)보다 사거리 안의 보병 (×1)을 노린다', u9.hp[inf] < 400 and u9.hp[tt] >= 600 - 1e-3,
           f'보병 {400 - float(u9.hp[inf]):.0f}, 바위거북 {600 - float(u9.hp[tt]):.0f} 피해')

    # 8. 배 공격 명령: 땅 안쪽의 궁수가 해안까지 걸어가 적 배를 쏜다. 근접 병사만이면 거절
    w10 = _world(gm)
    u10 = w10.units
    ship10 = w10.fleet._add(Boat(WARSHIP, 1, sy + 0.5, sx + 0.5, 9999.0))
    ship10.cd = 1e9
    comp = gm.comp[land[0]]
    wl = np.argwhere(gm.walk & (gm.comp == comp))
    dd = np.hypot(wl[:, 0] - sy, wl[:, 1] - sx)
    cand = wl[(dd > R.UNIT_STATS[R.ARCHER]['range'] + 6) & (dd < R.UNIT_STATS[R.ARCHER]['range'] + 14)]
    arc10 = None
    for y, x in cand[::7]:
        arc10 = u10.add(0, R.ARCHER, x + 0.5, y + 0.5, 26.0)
        if w10.order_ship_attack([arc10], ship10):
            break
        u10.alive[arc10] = False
    d0 = float(np.hypot(u10.x[arc10] - ship10.x, u10.y[arc10] - ship10.y))
    for _ in range(int(20 / 0.05)):
        w10.update(0.05)
        if ship10.hp < 9999:
            break
    inf10 = u10.add(0, R.INFANTRY, land[3][1] + 0.5, land[3][0] + 0.5, 40.0)
    melee = w10.order_ship_attack([inf10], ship10)
    report('배 공격 명령: 궁수가 해안의 사거리 안까지 가서 쏜다 (근접 병사는 거절)', ship10.hp < 9999 and not melee,
           f'처음 거리 {d0:.0f}칸 → {float(np.hypot(u10.x[arc10] - ship10.x, u10.y[arc10] - ship10.y)):.1f}칸, 전함 {9999 - ship10.hp:.0f} 피해, 근접 {melee}')
