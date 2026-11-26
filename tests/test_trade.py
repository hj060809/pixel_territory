"""무역 (sim/trade.py): 교환 규칙, 행렬이 오가며 1:1로 바꾸기, 적대면 멈춤, 끄고 켜기."""
from types import SimpleNamespace

import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.terrain import GameMap
from sim.trade import pick_exchange
from sim.world import World


def nat(res, sulfur=0.0, cap=500.0):
    return SimpleNamespace(res=list(res), sulfur=sulfur, caps=[cap] * 4)


def run(report, cache_dir='.cache'):
    # 1. 교환 규칙만 (판 없이)
    a, b = nat([100, 450, 100]), nat([100, 100, 450])
    ex = pick_exchange(a, b)
    report('교환 규칙: 많은 것을 주고 모자란 것을 받는다', ex is not None and ex[0] == 1 and ex[1] == 2 and abs(ex[2] - 500 * R.TRADE['load']) < 1e-6, f'{ex}')   # 한도 500 × load
    report('교환 규칙: 둘 다 나아지지 않으면 안 바꾼다', pick_exchange(nat([300, 300, 300]), nat([300, 300, 300])) is None)
    a2, b2 = nat([100, 80, 10]), nat([10, 10, 450])
    ex2 = pick_exchange(a2, b2)
    keep = 500 * R.TRADE['keep']
    report('교환 규칙: 남겨 둘 몫(keep)은 내주지 않는다', ex2 is not None and ex2[2] <= a2.res[ex2[0]] - keep + 1e-6, f'{ex2}')

    # 2. 판에서: 무역소 둘, 행렬이 오가며 바꾼다
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 5, seed=3, map_seed=7)
    b = w.builds
    st = R.BUILD_STATS[R.TRADE_POST]
    halls = {n.id: int(w.building_ids(n.id, R.HALL)[0]) for n in w.nations}
    comp = {nid: int(gm.comp[int(b.y[h]), int(b.x[h])]) for nid, h in halls.items()}
    pair = next((i, j) for i in comp for j in comp if i < j and comp[i] == comp[j])     # 같은 땅의 두 나라
    i0, i1 = pair
    posts = []
    for nid in pair:
        h = int(w.building_ids(nid, R.HALL)[0])
        spot = w._open_spot(b.y[h], b.x[h], 10, st['r'])
        posts.append(b.add(nid, R.TRADE_POST, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0))
    path = w.trade._path(posts[0], posts[1])
    report('두 무역소 사이 길을 잰다', path is not None and len(path) > 2, f'길 {None if path is None else len(path)}칸')
    A, B = w.nations[i0], w.nations[i1]
    w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60                 # 우호 (적대가 아니다)
    for _ in range(3):
        w.update(0.1)
    A.res, B.res = [100.0, 240.0, 40.0], [100.0, 40.0, 240.0]
    A.sulfur = B.sulfur = 0.0
    start = (A.res[1] + B.res[1], A.res[2] + B.res[2])
    w.trade.rest = {p: 0.05 for p in w.trade.rest}               # 바로 떠나게
    went = False
    for _ in range(3000):
        w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60
        A.rate = [0, 0, 0]
        w.update(0.2)
        went = went or len(w.trade.caravans) > 0
        if w.trade.log['trips'] >= 1:
            break
    road = [sum(c.cargo[k] for c in w.trade.caravans) for k in range(4)]          # 아직 길 위의 짐 (다른 행렬)
    total = (A.res[1] + B.res[1] + road[1], A.res[2] + B.res[2] + road[2])
    report('행렬이 떠나 상대 무역소에 갔다가 돌아온다', went and w.trade.log['trips'] >= 1, f'다녀옴 {w.trade.log}, {w.time:.0f}초')
    report('목재를 주고 석재를 받았다 (A는 석재가, B는 목재가 늘었다)', A.res[2] > 40 + 20 and B.res[1] > 40 + 20,
           f'A {[round(v) for v in A.res]}, B {[round(v) for v in B.res]}')
    # 생산이 계속 들어오므로 합은 조금 는다: 줄지만 않으면 (사라진 짐이 없다, 길 위의 짐까지 세어)
    report('바꾼 짐은 사라지지 않는다 (1:1)', total[0] >= start[0] - 1 and total[1] >= start[1] - 1, f'처음 {start}, 지금 {total}')

    # 3. 적대면 자동으로 멈추고, 켜면 다시 된다. 끄면 멈춘다
    w.diplo.rel[i0, i1] = -80
    hostile = not w.trade.allowed(i0, i1) and w.trade.status(i0, i1) == 'hostile'
    w.trade.set_mode(i0, i1, True)
    w.trade.set_mode(i1, i0, True)
    forced = w.trade.allowed(i0, i1)
    w.trade.set_mode(i1, i0, False)
    report('적대면 멈추고, 직접 켜면 다시, 상대가 끄면 멈춘다', hostile and forced and not w.trade.allowed(i0, i1) and w.trade.status(i0, i1) == 'theirs',
           f'적대 {hostile}, 켬 {forced}, 상대 끔 {w.trade.status(i0, i1)}')

    # 4. 바다 건너: 다른 땅의 두 나라, 각자 항구와 무역소 → 상선을 타고 오간다
    w = World(gm, 5, seed=3, map_seed=7)
    b = w.builds
    halls = {n.id: int(w.building_ids(n.id, R.HALL)[0]) for n in w.nations}
    comp = {nid: int(gm.comp[int(b.y[h]), int(b.x[h])]) for nid, h in halls.items()}
    pair = next(((i, j) for i in comp for j in comp if i < j and comp[i] != comp[j]), None)

    ok_setup = pair is not None
    if ok_setup:
        i0, i1 = pair
        for nid in pair:
            h = halls[nid]
            spot = w._open_spot(b.y[h], b.x[h], 10, st['r'])
            b.add(nid, R.TRADE_POST, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0)
    if ok_setup:
        A, B = w.nations[i0], w.nations[i1]
        for _ in range(3):
            w.update(0.1)
        A.res, B.res = [100.0, 240.0, 40.0], [100.0, 40.0, 240.0]
        w.trade.rest = {p: 0.05 for p in w.trade.rest}
        sea_seen = False
        for _ in range(6000):
            w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60
            w.update(0.2)
            sea_seen = sea_seen or any(c.at_sea for c in w.trade.caravans)
            if w.trade.log['trips'] >= 1:
                break
        report('바다 건너 무역: 항구 없이 해안에서 바로 상선을 타고 오간다', sea_seen and w.trade.log['trips'] >= 1 and A.res[2] > 60,
               f'바다 {sea_seen}, {w.trade.log}, {w.time:.0f}초, A {[round(v) for v in A.res]}')
    else:
        report('바다 건너 무역: 시험할 자리 (다른 땅의 두 나라와 항구 자리)', False, f'짝 {pair}')

    # 5. 호위·약탈: 무역소에 배치한 호위병이 행렬을 따라가고, 적이 행렬을 털면 짐을 가져가고 약탈 단계가 오른다
    from sim.commands import PlayerCommands
    w = World(gm, 5, seed=3, map_seed=7)
    b, u = w.builds, w.units
    halls = {n.id: int(w.building_ids(n.id, R.HALL)[0]) for n in w.nations}
    comp = {nid: int(gm.comp[int(b.y[h]), int(b.x[h])]) for nid, h in halls.items()}
    i0, i1 = next((i, j) for i in comp for j in comp if i < j and comp[i] == comp[j])
    raider = next(k for k in comp if k not in (i0, i1))
    posts = {}
    for nid in (i0, i1):
        h = halls[nid]
        spot = w._open_spot(b.y[h], b.x[h], 10, st['r'])
        posts[nid] = b.add(nid, R.TRADE_POST, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0)
    A, B = w.nations[i0], w.nations[i1]
    for _ in range(3):
        w.update(0.1)
    mine = [int(x) for x in w.unit_ids(i0)][:8]
    ok_assign = w.trade.assign(mine, posts[i0])
    A.res, B.res = [100.0, 240.0, 40.0], [100.0, 40.0, 240.0]
    w.trade.rest = {p: (0.05 if p == posts[i0] else 999.0) for p in w.trade.rest}
    car = None
    for _ in range(800):
        w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60
        w.update(0.2)
        car = next((c for c in w.trade.caravans if c.own == i0), None)
        if car is not None and car.pos > 130:                       # 집에서 걸어 온 호위병이 대형을 다 갖춘 뒤
            break
    followed = car is not None and len(car.escort) == min(R.TRADE['escort'], len(mine)) and len(w.trade.escorts.get(posts[i0], [])) == max(0, len(mine) - R.TRADE['escort'])
    x, y, ang = car.at() if car else (0, 0, 0)
    slots = [w.trade._walkable_slot(x, y, ang, k, len(car.escort)) for k in range(len(car.escort))] if car else []
    off = [float(np.hypot(u.x[e] - sl[1], u.y[e] - sl[0])) for e, sl in zip(car.escort, slots)] if car else [99]
    near = car is not None and np.mean(off) < 2.0                  # 대형: 상인 줄 양옆의 제자리
    report('호위병: 떠나는 행렬을 최대 인원까지 대형(줄 양옆)으로 감싸고, 남은 병사는 다음 행렬을 기다린다', ok_assign and followed and near,
           f'배치 {ok_assign}, 따라감 {len(car.escort) if car else None}, 기다림 {len(w.trade.escorts.get(posts[i0], []))}, 제자리에서 {[round(v, 1) for v in off]}')
    locked = car is not None and len(PlayerCommands(w, i0).units([[e, int(u.gen[e])] for e in car.escort])) == 0
    report('행렬을 따라가는 호위병은 무역소에 돌아올 때까지 명령을 받지 않는다', locked)
    calm = car is not None and all(bool(u.passive[e]) for e in car.escort)
    report('가는 길의 호위병은 먼저 치지 않는다 (공격받으면 맞서 싸운다)', calm, f'중립 {[bool(u.passive[e]) for e in car.escort] if car else None}')
    # 호위병이 없는 행렬을 적 병사가 털게 한다
    for e in car.escort:
        u.alive[e] = False
    gave = car.cargo[car.give]
    w.diplo.rel[raider, i0] = w.diplo.rel[i0, raider] = -90
    x, y, _ = car.member_at(car.members()[0])                     # 지금 행렬 자리에 (오른쪽 클릭)
    ids = [w._spawn_unit(raider, R.INFANTRY, int(y), int(x), 3) for _ in range(6)]
    PlayerCommands(w, raider).command([[i, int(u.gen[i])] for i in ids], [], x, y)
    before = w.nations[raider].res[car.give]
    for _ in range(600):
        w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60
        w.update(0.2)
        if not car.alive:
            break
    took = w.nations[raider].res[car.give] - before
    report('행렬을 털면 짐을 가져가고 약탈 단계가 오른다', not car.alive and took > gave * 0.5 and w.trade.raid_lv[raider] == 1,
           f'무너짐 {not car.alive}, 가져감 {took:.0f}/{gave:.0f}, 약탈 {w.trade.raid_lv[raider]}')
    w.trade.raid_lv[raider] = R.TRADE['raid_stop']
    report('약탈 단계가 끝까지 오르면 모든 나라가 무역을 멈춘다', not w.trade.allowed(i0, raider) and w.trade.status(i0, raider) == 'raider',
           f'{w.trade.status(i0, raider)}')

    # 6. 구성원 하나가 쓰러지면: 그 몫의 짐만 친 나라가 가져가고, 나머지는 계속 간다
    w = World(gm, 5, seed=3, map_seed=7)
    b = w.builds
    halls = {n.id: int(w.building_ids(n.id, R.HALL)[0]) for n in w.nations}
    comp = {nid: int(gm.comp[int(b.y[h]), int(b.x[h])]) for nid, h in halls.items()}
    i0, i1 = next((i, j) for i in comp for j in comp if i < j and comp[i] == comp[j])
    other = next(k for k in comp if k not in (i0, i1))
    for nid in (i0, i1):
        h = halls[nid]
        spot = w._open_spot(b.y[h], b.x[h], 10, st['r'])
        b.add(nid, R.TRADE_POST, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0)
    for _ in range(3):
        w.update(0.1)
    w.nations[i0].res, w.nations[i1].res = [100.0, 240.0, 40.0], [100.0, 40.0, 240.0]
    w.trade.rest = {p: 0.05 for p in w.trade.rest}
    car = None
    for _ in range(100):
        w.diplo.rel[i0, i1] = w.diplo.rel[i1, i0] = 60
        w.update(0.2)
        car = next((c for c in w.trade.caravans if c.own == i0), None)
        if car is not None:
            break
    if car is not None:
        load0 = sum(car.cargo)
        k = len(R.CARAVAN_MEMBERS) - 1
        before = sum(w.nations[other].res)
        w.trade._hit(car, k, 1e6, other)
        got = sum(w.nations[other].res) - before
        n = len(R.CARAVAN_MEMBERS)
        report('구성원 하나가 쓰러지면 그 몫만 빼앗기고 나머지는 계속 간다',
               car.alive and len(car.members()) == n - 1 and abs(got - load0 / n) < 1 and abs(sum(car.cargo) - load0 * (n - 1) / n) < 1,
               f'남은 구성원 {car.members()}, 빼앗긴 {got:.0f}/{load0:.0f}, 남은 짐 {sum(car.cargo):.0f}')
    else:
        report('구성원 하나가 쓰러지면 그 몫만 빼앗기고 나머지는 계속 간다', False, '행렬이 떠나지 않았다')

    # 7. 호위 중인 병사는 중립: 다른 나라 병사가 저절로 노리지 않는다
    w = World(gm, 3, seed=3, map_seed=7)
    u = w.units
    w.update(0.1)
    a_id = int(w.unit_ids(0)[0])
    u.passive[a_id] = True                                           # 행렬을 따라가는 호위병이라 치고
    foes = [w._spawn_unit(1, R.INFANTRY, int(u.y[a_id]), int(u.x[a_id]), 2) for _ in range(3)]
    hp0 = float(u.hp[a_id])
    for _ in range(40):
        u.passive[a_id] = True
        w.update(0.1)
    report('호위 중인 병사는 다른 나라 병사가 저절로 공격하지 않는다', abs(float(u.hp[a_id]) - hp0) < 1e-3 and all(int(u.tgt[f]) != a_id for f in foes),
           f'체력 {hp0:.0f} → {float(u.hp[a_id]):.0f}')
