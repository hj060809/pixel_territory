"""목장 (docs/PASTURE_PLAN.md). 2단계: 울타리 모양 (sim/pasture.fence_shape).
- 방향마다 반지름 (DIRS개), 완전한 원이 아니다 (자리로 정해지는 물결), 같은 자리면 같은 모양.
- 울타리 선이 다른 건물(반지름 + 여유)·빈 자원지·물·절벽에 걸치지 않는다.
- 둘레가 거의 다 막힌 곳(물 위, 건물 사이)에는 지을 수 없다 (None)."""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import pasture
from sim import rules as R
from sim.terrain import GameMap
from sim.world import World


def points(cx, cy, radii):
    n = len(radii)
    return [(cx + np.cos(2 * np.pi * i / n) * r, cy + np.sin(2 * np.pi * i / n) * r) for i, r in enumerate(radii)]


def clear_of_obstacles(w, cx, cy, radii):
    """울타리 선 (방향마다 점과 그 사이)이 장애물에 걸치지 않나."""
    m, b = w.map, w.builds
    pts = points(cx, cy, radii)
    line = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        for t in np.linspace(0, 1, 6):
            line.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    alive = np.flatnonzero(b.alive[:b.n])
    for x, y in line:
        if m.water[int(y), int(x)] or not m.walk_static[int(y), int(x)] or m.cliff[int(y), int(x)]:
            return False, ('물·절벽', x, y)
        for i in alive:
            if np.hypot(b.x[i] - x, b.y[i] - y) < b.r[i] + pasture.MARGIN - 0.75:     # 점 사이를 이은 선이라 반 칸쯤 봐준다
                return False, ('건물', x, y)
        for s in w.sites:
            if s.building < 0 and np.hypot(s.x - x, s.y - y) < pasture.SITE_R - 0.75:
                return False, ('자원지', x, y)
    return True, None


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 5, seed=3, map_seed=7)
    b = w.builds
    rng = np.random.default_rng(4)

    # 여러 자리: 거점 둘레(건물 곁)와 아무 땅
    spots = []
    for nat in w.nations:
        h = int(w.building_ids(nat.id, R.HALL)[0])
        for d in (16, 20, 26):
            a = rng.uniform(0, 2 * np.pi)
            spots.append((float(b.x[h]) + np.cos(a) * d, float(b.y[h]) + np.sin(a) * d))
    ys, xs = np.nonzero(gm.walk_static & ~gm.water)
    for k in rng.integers(0, len(ys), 30):
        spots.append((float(xs[k]) + 0.5, float(ys[k]) + 0.5))
    shapes, bad, irregular, none = 0, None, [], 0
    for cx, cy in spots:
        if not (20 < cx < gm.W - 20 and 20 < cy < gm.H - 20):
            continue
        s = pasture.fence_shape(w, cy, cx, 15.0)
        if s is None:
            none += 1
            continue
        shapes += 1
        ok, why = clear_of_obstacles(w, cx, cy, s)
        if not ok and bad is None:
            bad = (round(cx), round(cy), why)
        if min(s) >= 14.0 * 0.6:                                   # 막힌 데 없는 자리: 바탕 모양이 원이 아닌가
            irregular.append(float(np.std(s) / np.mean(s)))
    report('울타리 모양: 방향마다 반지름, 다른 건물·자원지·물·절벽에 걸치지 않는다', shapes > 10 and bad is None,
           f'모양 {shapes}개, 지을 수 없는 자리 {none}' + (f', 걸침 {bad}' if bad else ''))
    report('바탕 모양이 원이 아니다 (자연스럽게 흐트러진다)', len(irregular) > 3 and min(irregular) > 0.03,
           f'반지름 흩어짐 (표준편차/평균) {np.round(sorted(irregular)[:3], 3).tolist()} …')

    cx, cy = spots[0]
    report('같은 자리면 같은 모양', pasture.fence_shape(w, cy, cx, 15.0) == pasture.fence_shape(w, cy, cx, 15.0))
    ys, xs = np.nonzero(gm.water & ~gm.ford)
    k = int(np.argmax([gm.water[max(y - 12, 0):y + 13, max(x - 12, 0):x + 13].mean() for y, x in zip(ys[::997], xs[::997])]))
    wy, wx = ys[::997][k], xs[::997][k]
    report('물 한가운데에는 지을 수 없다', pasture.fence_shape(w, wy + 0.5, wx + 0.5, 15.0) is None)

    # ---------------------------------------------------------------- 3단계: 목장 건물
    run_pens(report, cache_dir)


def run_pens(report, cache_dir):
    from server.protocol import StateEncoder, decode
    from sim.wildlife import FLEE
    gm = GameMap(TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None))
    w = World(gm, 4, seed=3, map_seed=7)
    wild, P = w.wild, R.PASTURE_RULES
    nat = w.nations[0]
    nat.res = [400.0, 400.0, 400.0]

    def herd_of(kind):
        for a in wild.animals.values():
            if a.kind == kind and len(w.pastures.herd_at(a.y, a.x)) >= P['min_herd']:
                return a
        return None

    pens = {}
    for kind in (R.REINDEER, R.HORSE):
        a0 = herd_of(kind)
        ids = np.array([w.units.add(0, R.INFANTRY, a0.x + 9 + i, a0.y, 40.0) for i in range(3)])
        b = w.pastures.place(0, ids, a0.y, a0.x, quiet=True)
        pens[kind] = b
    ok = all(b >= 0 for b in pens.values())
    report('목장: 말·순록 떼를 눌러 짓는다', ok, f'{pens}')
    if not ok:
        return
    side = True
    for kind, b in pens.items():
        p = w.pastures.pens[b]
        bx, by = float(w.builds.x[b]), float(w.builds.y[b])
        out = not w.pastures.inside(p, bx, by, -float(w.builds.r[b]))       # 헛간은 울타리 밖
        east_west = abs(by - p.cy) < abs(bx - p.cx)                          # 오른쪽·왼쪽
        side &= out and east_west and w.builds.kind[b] == R.PASTURE
    report('울타리 자리를 먼저 정하고 헛간은 울타리 바로 바깥 오른쪽·왼쪽에', side)
    p = w.pastures.pens[pens[R.REINDEER]]
    claimed = [wild.animals[i] for i in p.claim]
    report('떼가 목장 몫이 된다 (다른 나라 목장 몫이 아닌 것만)', len(claimed) >= P['min_herd'] and all(a.pen == p.b for a in claimed))

    # 짓는 나라 병사에게는 놀라지 않고, 다른 나라 병사에게는 놀란다
    a = claimed[0]
    mine = w.units.add(0, R.INFANTRY, a.x + 1.5, a.y, 40.0)
    wild._fear_t = 0.0
    wild.update(0.05)
    calm = a.mode != FLEE
    other = w.units.add(1, R.INFANTRY, a.x - 1.5, a.y, 40.0)
    wild._fear_t = 0.0
    wild.update(0.05)
    report('몫인 동물은 짓는 나라 병사에겐 놀라지 않고 다른 나라 병사에겐 달아난다', calm and a.mode == FLEE)
    w.units.alive[mine] = w.units.alive[other] = False

    # 울타리 안에는 다른 건물을 짓지 못한다
    report('울타리 안에는 다른 건물을 짓지 못한다', not w.can_place(int(p.cy), int(p.cx), 3))

    # 다 지으면 울타리 안의 몫만 든다, 야생에서 빠진다
    for _ in range(3000):
        w.update(0.1)
        if all(w.pastures.pens[b].done for b in pens.values()):
            break
    done = all(w.pastures.pens[b].done for b in pens.values())
    w.update(0.1)                                                  # 한도는 다음 걸음에 다시 센다
    p = w.pastures.pens[pens[R.REINDEER]]
    inside = all(w.pastures.inside(p, p.cx + dx, p.cy + dy) for dx, dy in p.spots)
    report('다 지으면 울타리 안의 몫인 동물이 목장에 든다 (야생에서 빠지고 자리가 남는다)',
           done and p.n > 0 and len(p.spots) == p.n and inside and not any(an.pen == p.b for an in wild.animals.values()),
           f'순록 {p.n}마리, 말 {w.pastures.pens[pens[R.HORSE]].n}마리')

    # 생산: 마리마다, 겨울엔 덜
    want = sum(P['food'][q.kind] * q.n for q in w.pastures.pens.values())
    summer = w.pastures.food(0, np.array([0, 1.0, 0, 0]))
    winter = w.pastures.food(0, np.array([0, 0, 0, 1.0]))
    want_w = sum(P['food'][q.kind] * q.n * P['winter'][q.kind] for q in w.pastures.pens.values())
    report('생산: 마리마다 식량 (겨울엔 순록 ×0.7, 말 ×0.4)', abs(summer - want) < 1e-6 and abs(winter - want_w) < 1e-6,
           f'여름 {summer:.2f}/초, 겨울 {winter:.2f}/초')
    report('식량 한도 +25', w.nations[0].caps[R.FOOD] >= R.STORE_BASE + R.STORE_HALL + 2 * R.STORE_SITE)

    # 새끼: 봄·여름에, 최대까지
    n0 = p.n
    w.season_w = np.array([0.0, 1.0, 0.0, 0.0])
    w.pastures.update(P['breed'] + 1)
    report('봄·여름에 새끼가 는다', p.n == min(n0 + 1, P['cap']) and len(p.spots) == p.n, f'{n0} → {p.n}')

    # 말 꺼내기: 보병·궁수가 문으로 가서 타고 나온다 (있는 만큼), 순록 목장은 안 된다
    from sim.commands import PlayerCommands
    hp_ = w.pastures.pens[pens[R.HORSE]]
    gy, gx = w.pastures.gate(hp_)
    n0 = hp_.n
    riders = [w.units.add(0, kind, gx + 12 + k, gy + 2, R.UNIT_STATS[kind]['hp'] * 0.5) for k, kind in enumerate((R.INFANTRY, R.ARCHER))]
    c = PlayerCommands(w, 0)
    shown = c.command([(i, int(w.units.gen[i])) for i in riders], [], hp_.cx, hp_.cy)
    for _ in range(600):
        w.update(0.1)
        if not w.pastures.riders:
            break
    kinds = [int(w.units.kind[i]) for i in riders]
    hpr = [round(float(w.units.hp[i]) / R.UNIT_STATS[int(w.units.kind[i])]['hp'], 2) for i in riders]
    report('말 목장: 보병·궁수가 말을 꺼내 탄다 (창기병·기마궁수, 체력 비율 그대로, 말이 준다)',
           shown == 'tame' and kinds == [R.LANCER, R.HORSE_ARCHER] and all(0.44 <= v <= 0.5 for v in hpr) and hp_.n == n0 - 2 and len(hp_.spots) == hp_.n,
           f'{shown}, 병종 {kinds}, 체력 {hpr}, 말 {n0} → {hp_.n}')
    rp = w.pastures.pens[pens[R.REINDEER]]
    extra = w.units.add(0, R.INFANTRY, rp.cx + 2, rp.cy, 40.0)
    report('순록 목장에서는 꺼내 탈 수 없다', w.pastures.order_ride(0, [extra], rp.b, quiet=True) == 0)
    many = [w.units.add(0, R.INFANTRY, gx + 10, gy + k * 0.5, 40.0) for k in range(hp_.n + 3)]
    report('2마리는 남기고 그 위만큼만 간다', w.pastures.order_ride(0, many, hp_.b, quiet=True) == hp_.n - R.PASTURE_RULES['keep'])
    for i in many:
        w.units.alive[i] = False
    w.pastures.riders.clear()
    w.units.alive[extra] = False

    # 화면으로: 목장이 바뀌면 실린다
    enc = StateEncoder(w)
    d = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, True, 0))
    got = {q['b']: q for q in d.get('pens', [])}
    ok = set(got) == set(pens.values()) and all(len(q['radii']) == pasture.DIRS and len(q['spots']) == w.pastures.pens[q['b']].n
                                                 for q in got.values())
    d2 = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    report('목장이 상태 메시지에 실린다 (바뀔 때만)', ok and 'pens' not in d2)

    # 무너지면 든 동물이 야생 무리로 풀려난다
    before = wild.count(R.REINDEER)
    n = p.n
    w.builds.hp[p.b] = 0
    w.update(0.1)
    report('헛간이 무너지면 든 동물이 야생으로 풀려난다', pens[R.REINDEER] not in w.pastures.pens and wild.count(R.REINDEER) == before + n,
           f'야생 순록 {before} → {wild.count(R.REINDEER)}')

    # 작은 무리·떼가 없는 곳
    ys, xs = np.nonzero(gm.walk_static)
    far = next((float(x), float(y)) for y, x in zip(ys[::501], xs[::501])
               if all(np.hypot(an.x - x, an.y - y) > 30 for an in wild.animals.values()))
    report('떼가 없는 곳에는 목장을 짓지 못한다', w.pastures.place(0, np.array([], np.int64), far[1], far[0], quiet=True) < 0)
