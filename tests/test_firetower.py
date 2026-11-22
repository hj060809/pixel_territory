"""화염탑과 유황 (sim/firetower.py, sim/sites.py).
- 넓은 사막에 유황 웅덩이 (자원지 종류 SULFUR). 유황 채취장을 지으면 유황이 쌓인다.
- 화염탑은 유황 40을 들여 짓고, 불을 뿜을 때마다 유황 1을 쓴다. 유황이 없으면 약한 불 (피해 절반).
- 범위 공격, 날고 있는 용기사도 맞힌다. 드래곤은 1.6배, 바위거북은 0.7배.
- 용기사와 1대1이면 눈이 없는 땅에서는 화염탑이 아슬아슬하게 이기고, 눈 위에서는 용기사가 이긴다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.terrain import GameMap
from sim.world import World


def _tower(w, nid, x, y):
    st = R.BUILD_STATS[R.FIRE_TOWER]
    return w.builds.add(nid, R.FIRE_TOWER, x, y, st['hp'], st['r'], prog=1.0)


def _flat(gm, w):
    """아무것도 없는 넓은 평지 한 곳 (눈이 없는 곳: 용기사는 눈 위에서 더 빨리 회복한다)."""
    from sim.world import m_snow
    snow = m_snow(gm)
    for y in range(40, gm.H - 40, 7):
        for x in range(40, gm.W - 40, 7):
            if gm.walk[y - 12:y + 13, x - 12:x + 13].all() and not snow[y - 12:y + 13, x - 12:x + 13].any() and w.can_place(y, x, 3):
                return float(x), float(y)
    raise RuntimeError('평지 없음')


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = World(gm, 2, seed=4, map_seed=42)
    u, nat = w.units, w.nations[0]
    pits = [s for s in w.sites if s.kind == R.SULFUR]
    report('사막에 유황 웅덩이', 1 <= len(pits) <= 6, f'{len(pits)}곳')

    s = pits[0]
    st = R.BUILD_STATS[R.SULFUR_PIT]
    bi = w.builds.add(0, R.SULFUR_PIT, s.x + 0.5, s.y + 0.5, st['hp'], st['r'], prog=1.0, site=s.id)
    s.building = bi
    for _ in range(int(20 / 0.05)):
        w._economy(0.05)
    report('유황 채취장이 유황을 모은다', nat.sulfur > 3, f'유황 {nat.sulfur:.1f}')

    # 용기사와 1대1 (유황 넉넉히): 화염탑이 아슬아슬하게 이긴다
    x, y = _flat(gm, w)
    t = _tower(w, 0, x, y)
    nat.sulfur = 500.0
    rider = u.add(1, R.DRAGON_RIDER, x + 7.5, y, R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    w.order_attack(np.array([rider]), building=t)
    for _ in range(int(90 / 0.05)):
        w.update(0.05)
        if not u.alive[rider] or not w.builds.alive[t] or w.builds.hp[t] <= 0:
            break
    hp = float(w.builds.hp[t])
    report('용기사와 1대1: 화염탑이 아슬아슬하게 이긴다', not u.alive[rider] and 0 < hp < 120,
           f'용기사 살아 있음 {bool(u.alive[rider])}, 탑 체력 {hp:.0f}/520')
    w.builds.alive[t] = False

    # 눈 위에서는 용기사가 이긴다 (눈 위 회복)
    from sim.world import m_snow
    gm.set_season([0.0, 0.0, 0.0, 1.0])                                  # 겨울: 눈이 넓다
    snow = m_snow(gm)
    ys, xs = np.nonzero(snow)
    k = next(i for i in range(0, len(ys), 37) if 20 <= ys[i] < gm.H - 20 and 20 <= xs[i] < gm.W - 20
             and w.can_place(int(ys[i]), int(xs[i]), 3) and snow[ys[i] - 6:ys[i] + 7, xs[i] - 2:xs[i] + 11].all())
    sx, sy = float(xs[k]), float(ys[k])
    t2 = _tower(w, 0, sx, sy)
    rider2 = u.add(1, R.DRAGON_RIDER, sx + 7.5, sy, R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    w.order_attack(np.array([rider2]), building=t2)
    for _ in range(int(120 / 0.05)):
        w.update(0.05)
        if not u.alive[rider2] or w.builds.hp[t2] <= 0:
            break
    report('눈 위에서는 용기사가 이긴다', bool(u.alive[rider2]) and w.builds.hp[t2] <= 0, f'용기사 체력 {u.hp[rider2]:.0f}')
    u.alive[rider2] = False
    w.builds.alive[t2] = False

    # 범위 공격, 바위거북 내성, 유황이 없으면 약한 불
    t = _tower(w, 0, x, y)
    w.builds.cd[t] = 0.0
    foes = [u.add(1, R.INFANTRY, x + 6 + dx, y + dy, 40.0) for dx, dy in ((0, 0), (1.2, 0.8), (-1, 1))]
    tort = u.add(1, R.TORTOISE, x - 6, y, R.UNIT_STATS[R.TORTOISE]['hp'])
    nat.sulfur = 10.0
    w.fire.update(0.05)
    hit = sum(u.hp[i] < 40 for i in foes)
    report('범위 공격: 둘레 적도 맞는다', hit >= 2 and nat.sulfur == 9.0, f'{hit}명, 유황 {nat.sulfur}')
    for i in foes:
        u.alive[i] = False
    w.builds.cd[t] = 0.0
    th = float(u.hp[tort])
    nat.sulfur = 0.0
    w.fire.update(0.05)
    lost = th - float(u.hp[tort])
    want = R.FIRE['dmg'] * R.FIRE['weak'] * R.FIRE['vs_tortoise']
    report('유황이 없으면 약한 불, 바위거북은 덜 맞는다', abs(lost - want) < 0.01, f'{lost:.1f} (기대 {want:.1f})')
