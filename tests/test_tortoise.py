"""거대 바위거북 (함께 싸우는 사막 동물, sim/wildlife.py + sim/companions.py).
- 넓은 사막에 1~2마리씩 산다. 사람이 와도 달아나지 않는다.
- 병사가 가서 먹이(식량 rules.WILDLIFE 바위거북 food)를 주면 4초 만에 길들여 그 나라의 바위거북 병사가 된다 (병사는 그대로).
- 발 구르기: 붙은 땅의 적 모두에게 피해 (날고 있는 적은 맞지 않는다). 낮은 포효: 둘레 적이 바위거북만 노린다.
  껍질 숨기: 체력이 낮으면 피해를 크게 줄인다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = World(gm, 3, seed=4, map_seed=42)
    wild, u = w.wild, w.units
    pang = [a for a in wild.animals.values() if a.kind == R.TORTOISE_W]
    report('사막에 바위거북이 산다', 1 <= len(pang) <= R.WILDLIFE[R.TORTOISE_W]['cap'], f'{len(pang)}마리')

    a = pang[0]
    inf = u.add(0, R.INFANTRY, a.x + 3, a.y, R.UNIT_STATS[R.INFANTRY]['hp'])
    if not gm.walk[int(u.y[inf]), int(u.x[inf])]:
        u.x[inf], u.y[inf] = a.x, a.y
    w.nations[0].res[R.FOOD] = 800.0
    got = wild.order_tame(0, [inf], a.id, quiet=True)
    for _ in range(int(8 / 0.05)):
        w.update(0.05)
        if a.id not in wild.animals:
            break
    mine = [i for i in w.unit_ids(0) if u.kind[i] == R.TORTOISE]
    report('먹이를 주고 금방 길들인다 (병사는 그대로, 바위거북이 함께 싸운다)',
           got >= 1 and len(mine) >= 1 and u.kind[inf] == R.INFANTRY and w.nations[0].res[R.FOOD] <= 800 - R.WILDLIFE[R.TORTOISE_W]['food'] + 5,   # 먹이만큼 줄었다
           f'보냄 {got}, 바위거북 {len(mine)}, 식량 {w.nations[0].res[R.FOOD]:.0f}')
    p = mine[0]

    # 발 구르기: 붙은 적 셋이 함께 맞는다
    foes = [u.add(1, R.INFANTRY, float(u.x[p]) + dx, float(u.y[p]) + dy, 40.0) for dx, dy in ((1.5, 0), (-1.5, 0), (0, 1.5))]
    for i in foes:
        if not gm.walk[int(u.y[i]), int(u.x[i])]:
            u.x[i], u.y[i] = u.x[p], u.y[p]
    hp0 = [float(u.hp[i]) for i in foes]
    w.companions.st.get(p) and setattr(w.companions.st[p], 'spin', 0.0)
    w.companions.update(0.05)
    hit = sum(u.hp[i] < h - R.STOMP['dmg'] + 0.01 for i, h in zip(foes, hp0))
    report('발 구르기: 붙은 적 모두를 친다', hit == 3, f'{hit}명')
    # 발 구르기는 땅의 적만
    rider = u.add(1, R.DRAGON_RIDER, float(u.x[p]) + 4, float(u.y[p]), R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    u.air[rider] = True
    rh = float(u.hp[rider])
    w.companions.st[p].spin = 0.0
    w.companions.update(0.05)
    report('발 구르기는 날고 있는 적을 맞히지 않는다', u.hp[rider] == rh, f'{rh:.0f} → {u.hp[rider]:.0f}')
    u.alive[rider] = False

    # 낮은 포효: 다른 걸 치던 적도 바위거북을 노린다
    far = u.add(1, R.ARCHER, float(u.x[p]) + 5, float(u.y[p]), 26.0)
    w.order_attack(np.array([far]), unit=inf)
    w.companions.st[p].taunt = 0.0
    w.companions.update(0.05)
    report('낮은 포효: 둘레 적이 바위거북만 노린다', u.tgt[far] == p and all(u.tgt[i] == p for i in foes if u.alive[i]))

    # 껍질 숨기: 체력이 낮으면 받는 피해가 크게 준다
    for i in foes + [far]:
        u.alive[i] = False
    u.hp[p] = R.UNIT_STATS[R.TORTOISE]['hp'] * 0.2
    w.companions.update(0.05)
    curled = u.state[p] == 5
    before = float(u.hp[p])
    u.hp[p] -= 50.0
    w.companions.update(0.05)
    taken = before - float(u.hp[p])
    report('껍질 숨기: 피해를 줄인다', curled and abs(taken - 50 * (1 - R.HIDE['cut'])) < 0.5, f'말림 {curled}, 받은 피해 {taken:.1f}')
