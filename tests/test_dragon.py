"""드래곤 (사나운 야생 동물, sim/wildlife.py).
- 큰 설원 덩어리마다 가장 높은 곳에 둥지 (최대 3, 작은 설원엔 없다), 둥지마다 잠든 드래곤.
- 병사가 다가가 치면 깨어 싸우고 (서리 숨결: 범위 피해), 체력 30% 아래면 쓰러진다 (그동안 맞지 않는다).
- 쓰러진 동안 병사 하나가 길들이면 용기사 (어느 병사든 같은 병종). 나라마다 2기까지.
- 용기사는 움직이거나 싸울 때 날아서 (물 위로도) 곧장 가고, 그동안은 근접 병사가 칠 수 없다.
  할 일 없이 멈추면 땅에 내려앉고, 그때는 근접 병사에게도 맞는다.
- 야생 드래곤은 상태 메시지의 병사 칸에 없고 동물 칸에 있다.
"""
import numpy as np

from engine.mapgen import load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.protocol import StateEncoder, decode
from sim import rules as R
from sim.entities import AMOVE, IDLE
from sim.terrain import GameMap
from sim.wildlife import FIGHT, SLEEP, SUBDUED
from sim.world import World


def run(report, cache_dir='.cache'):
    scene = TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None)        # 큰 설원 둘 (둥지 2)
    gm = GameMap(scene)
    w = World(gm, 2, seed=3, map_seed=7)
    wild, u = w.wild, w.units
    dragons = [a for a in wild.animals.values() if a.unit >= 0]
    report('둥지마다 잠든 드래곤', 1 <= len(dragons) <= 3 and all(a.mode == SLEEP for a in dragons), f'{len(dragons)}마리')
    small = GameMap(TerrainScene.load(load_preset('continent', default_config(512, 42)), cache_dir, progress=lambda s: None))
    from sim.wildlife import lairs_for
    report('작은 설원뿐인 지도엔 드래곤이 없다', lairs_for(small) == [], f'{lairs_for(small)}')
    enc = StateEncoder(w)
    m = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    sent = {int(r['slot']) for r in m['units']}
    report('드래곤은 동물 칸으로만', all(a.unit not in sent for a in dragons)
           and sum(int(r['kind']) == R.DRAGON for r in m['animals']) == len(dragons))

    a = dragons[0]
    lx, ly = a.x, a.y
    spots = [(lx + 9 * np.cos(t), ly + 9 * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)]
    spots = [(x, y) for x, y in spots if gm.walk[int(y), int(x)]]
    army = [u.add(0, R.ARCHER if k % 3 == 0 else R.INFANTRY, *spots[k % len(spots)], 9999.0) for k in range(18)]
    for i in army:
        u.hp[i] = R.UNIT_STATS[int(u.kind[i])]['hp'] * 3                  # 시험용: 질기게
    w.order_attack(np.array(army), unit=a.unit)
    woke = subdued = False
    for _ in range(int(60 / 0.05)):
        w.update(0.05)
        woke |= a.mode == FIGHT
        if a.mode == SUBDUED:
            subdued = True
            break
    report('맞으면 깨어 싸우고, 체력이 깎이면 쓰러진다', woke and subdued, f'깸 {woke}, 쓰러짐 {subdued}, 체력 {a.hp:.2f}')
    report('쓰러진 동안은 맞지 않는다', bool(u.aboard[a.unit]))
    alive = [i for i in army if u.alive[i]]
    got = wild.order_tame(0, alive, a.id, quiet=True)
    tamer = next(i for i, t in wild.tamers.items() if t.aid == a.id)      # 가장 가까운 한 명이 간다
    for _ in range(int(19 / 0.05)):
        w.update(0.05)
        if u.kind[tamer] == R.DRAGON_RIDER:
            break
    report('길들이면 용기사', got == 1 and u.kind[tamer] == R.DRAGON_RIDER and a.id not in wild.animals,
           f'보낸 {got}, 종류 {u.kind[tamer]}')

    # 날아서 물 위로
    from scipy import ndimage
    home = (float(u.y[tamer]), float(u.x[tamer]))
    w.update(0.05)
    report('멈춰 있는 용기사는 땅에 내려앉아 있다', not u.air[tamer])
    water = np.argwhere(ndimage.binary_erosion(~gm.walk, iterations=3))      # 넓은 물 한가운데
    wy, wx = min(water, key=lambda p: (p[0] - u.y[tamer]) ** 2 + (p[1] - u.x[tamer]) ** 2)
    w.order_move(np.array([tamer]), float(wy) + 0.5, float(wx) + 0.5)
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if u.state[tamer] == IDLE:
            break
    over = not gm.walk[int(u.y[tamer]), int(u.x[tamer])]
    report('용기사는 날아서 물 위로 (물 위에선 떠 있다)', over and u.alive[tamer] and u.air[tamer], f'물 위 {over}, 날고 있음 {bool(u.air[tamer])}')

    # 나라마다 2기
    u.add(0, R.DRAGON_RIDER, float(wx), float(wy), R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    other = next((d for d in wild.animals.values() if d.unit >= 0), None)
    if other is not None:
        other.mode = SUBDUED
        n = wild.order_tame(0, [i for i in army if u.alive[i] and i != tamer], other.id, quiet=True)
        report('용기사는 나라마다 2기까지', n == 0)
    # 날고 있는 동안은 근접 병사가 못 친다
    foe = u.add(1, R.INFANTRY, float(u.x[tamer]) + 1, float(u.y[tamer]), 40.0)
    w.order_attack(np.array([foe]), unit=tamer)
    report('근접 병사는 날고 있는 용기사를 칠 수 없다', u.state[foe] in (IDLE, AMOVE) or u.tgt[foe] != tamer)
    u.alive[foe] = False
    # 땅으로 날아 돌아오는 동안은 날고, 멈추면 내려앉아 근접 병사에게도 맞는다
    w.order_move(np.array([tamer]), *home)
    w.update(0.05)
    flying = bool(u.air[tamer])
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if u.state[tamer] == IDLE and not u.air[tamer]:
            break
    landed = not u.air[tamer] and gm.walk[int(u.y[tamer]), int(u.x[tamer])]
    report('이동하는 동안은 날고, 멈추면 내려앉는다', flying and landed, f'이동 중 날기 {flying}, 내려앉음 {landed}')
    foe = u.add(1, R.INFANTRY, float(u.x[tamer]) + 1.5, float(u.y[tamer]), 40.0)
    w.order_attack(np.array([foe]), unit=tamer)
    report('내려앉은 용기사는 근접 병사에게도 맞는다', u.state[foe] == 3 and u.tgt[foe] == tamer)
