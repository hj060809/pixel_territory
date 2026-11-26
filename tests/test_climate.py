"""기후 효과 (sim/climate.py): 부족과 병사가 선 땅으로 이동·피해 배율, 더위·동상 확률 피해 (최대 체력 30% 아래로는 안 깎인다),
길들이는 시간. 병사만 받는다."""
from types import SimpleNamespace

import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import climate, tribes
from sim import rules as R
from sim.terrain import GameMap
from sim.world import World

C = R.CLIMATE


def run(report, cache_dir='.cache'):
    w = gm = None
    for seed in (7, 8767564, 11, 23):
        gm = GameMap(TerrainScene.load(default_config(512, seed), cache_dir, progress=lambda s: None))
        snow, sand = tribes.zones(gm)
        if (snow & gm.walk).any() and (sand & gm.walk).any():
            w = World(gm, 4, seed=3, map_seed=seed)
            break
    if w is None:
        report('설원과 사막이 함께 있는 지도', False)
        return
    u = w.units
    rng = np.random.default_rng(1)
    plain = gm.walk & ~snow & ~sand & gm.land

    def cell(mask):
        ys, xs = np.nonzero(mask)
        k = int(rng.integers(len(ys)))
        return float(xs[k]) + 0.5, float(ys[k]) + 0.5

    spots = {'snow': cell(snow & gm.walk), 'sand': cell(sand & gm.walk), 'plain': cell(plain)}
    nid = 0
    nat = w.nations[nid]
    hp = R.UNIT_STATS[R.INFANTRY]['hp']
    men = {k: u.add(nid, R.INFANTRY, x, y, hp) for k, (x, y) in spots.items()}
    rider = u.add(nid, R.DRAGON_RIDER, *spots['sand'], R.UNIT_STATS[R.DRAGON_RIDER]['hp'])

    def fx(tribe):
        nat.tribe = tribe
        climate.update(w, 0.0)                                  # dt 0: 배율만 (확률 피해 없음)
        return {k: (round(float(u.fx_speed[i]), 3), round(float(u.fx_take[i]), 3), round(float(u.fx_deal[i]), 3)) for k, i in men.items()}

    sl = C['slow']
    t = fx(tribes.TEMPERATE)
    report('온대: 설원·사막에서 느려지고, 평지에선 그대로',
           t['snow'][0] == sl and t['sand'][0] == sl and t['plain'] == (1.0, 1.0, 1.0), f'{t}')
    s = fx(tribes.SNOW)
    sm = float(gm.speed_mul[int(spots['snow'][1]), int(spots['snow'][0])])
    terr = R.UNIT_STATS[R.INFANTRY]['terrain']
    dry = float(climate.dry_cost(gm)[int(spots['snow'][1]), int(spots['snow'][0])])
    plain_like = abs(s['snow'][0] * sm ** terr - max(sm, 1 / dry) ** terr) < 1e-2   # 지형 × 기후 = 눈이 없을 때의 지형 (더 빠르면 그대로)
    report('설원 부족: 설원에선 눈 몫만 빠지고 덜 다치고, 사막에선 느리고, 평지는 그대로',
           plain_like and s['sand'][0] == sl and s['plain'][1] == 1.0 and s['snow'][1] == C['snow_take']
           and s['sand'][1] == 1.0 and s['plain'][2] == 1.0, f'{s} (설원 지형 {sm:.2f}, 눈 없으면 {1 / dry:.2f})')
    d = fx(tribes.DESERT)
    report('사막 부족: 설원에선 느리고, 설원 밖에선 더 세게, 사막에선 그대로',
           d['snow'][0] == sl and d['sand'][0] == 1.0 and d['plain'][2] == C['desert_deal'] and d['sand'][2] == C['desert_deal']
           and d['snow'][2] == 1.0 and d['plain'][1] == 1.0, f'{d}')
    report('용기사는 기후를 받지 않는다', (u.fx_speed[rider], u.fx_take[rider], u.fx_deal[rider]) == (1.0, 1.0, 1.0))

    # 확률 피해: 불리한 곳만, 최대 체력의 30% 아래로는 안 깎인다, 공격 기록 8 동상 / 9 더위
    nat.tribe = tribes.TEMPERATE
    w.recent.clear()
    fake = SimpleNamespace(hp=float(hp))
    w.wild.tamers[men['snow']] = fake                            # 길들이는 중이라 치고: 기준 체력도 같이 내려가야 한다
    hits = 0
    for _ in range(400):
        before = float(u.hp[men['snow']])
        climate.update(w, C['every'])                            # 한 번에 every초: chance 확률
        hits += float(u.hp[men['snow']]) < before
    del w.wild.tamers[men['snow']]
    floor = hp * C['floor']
    kinds = {r[5] for r in w.recent}
    report('더위·동상: 30% 아래로는 안 깎이고, 평지는 그대로, 동상·더위 효과가 남는다',
           abs(float(u.hp[men['snow']]) - floor) < 1e-3 and abs(float(u.hp[men['sand']]) - floor) < 1e-3
           and float(u.hp[men['plain']]) == hp and kinds == {climate.FROST, climate.HEAT},
           f'설원 {u.hp[men["snow"]]:.1f} 사막 {u.hp[men["sand"]]:.1f} 평지 {u.hp[men["plain"]]:.1f} / {floor:.1f}, 효과 {sorted(kinds)}')
    need = int(np.ceil((1 - C['floor']) / C['dmg']))
    report('더위·동상: 한 번에 최대 체력의 2%씩, 반쯤의 확률', need - 1 <= hits <= need + 1, f'{hits}번 깎임 (필요 {need})')
    report('더위·동상은 길들이기를 멈추게 하지 않는다 (기준 체력도 같이)', abs(fake.hp - float(u.hp[men['snow']])) < 1e-3, f'{fake.hp:.1f}')

    # 걸음 전체 (전투 계산까지): 멈추지 않는다
    for i in men.values():
        u.hp[i] = hp
    nat.tribe = tribes.DESERT
    for _ in range(20):
        w.update(0.1)
    report('기후를 켠 채로 판이 돌아간다', True)

    # 길들이는 시간
    mul = {}
    for tr in (tribes.TEMPERATE, tribes.SNOW, tribes.DESERT):
        nat.tribe = tr
        mul[tr] = tuple(climate.tame_mul(w, nid, a) for a in (R.TORTOISE_W, R.DRAGON, R.HORSE))
    report('길들이기: 설원은 거북 ×1.5, 사막은 드래곤 ×1.25, 나머지 그대로',
           mul[tribes.TEMPERATE] == (1.0, 1.0, 1.0) and mul[tribes.SNOW] == (C['tame_snow_tortoise'], 1.0, 1.0)
           and mul[tribes.DESERT] == (1.0, C['tame_desert_dragon'], 1.0), f'{mul}')

    for i in men.values():
        u.alive[i] = True
        u.own[i] = nid
    w.season_w = np.array([0.0, 0.0, 0.0, 1.0])                 # 겨울
    # 사막의 갈증: 사막 지역에 있는 병사는 부족과 상관없이 먹는 양 ×thirst_upkeep (겨울 배율은 그대로)
    on_sand = sum(float(w.k_upkeep[u.kind[i]]) for i in range(u.n) if u.alive[i] and u.own[i] == nid and not u.aboard[i]
                  and u.kind[i] in climate.SOLDIERS and sand[min(int(u.y[i]), gm.H - 1), min(int(u.x[i]), gm.W - 1)])
    dry, rate = {}, {}
    for tr in (tribes.TEMPERATE, tribes.DESERT):
        nat.tribe = tr
        dry[tr] = float(climate.thirst(w)[nid])
        w._economy(0.0)
        rate[tr] = nat.rate[R.FOOD]
    cnt = sum(float(w.k_upkeep[u.kind[i]]) for i in range(u.n) if u.alive[i] and u.own[i] == nid)
    want_eat = (cnt + on_sand * (C['thirst_upkeep'] - 1)) * 1.5 * R.UPKEEP     # 겨울 1.5배, 사막 칸 병사는 1.2배 더
    report('갈증: 사막 지역의 병사는 부족과 상관없이 먹는 식량 ×1.2 (설원 부족의 덜 먹기는 없다)',
           on_sand > 0 and abs(dry[tribes.TEMPERATE] - on_sand) < 1e-4 and abs(dry[tribes.DESERT] - on_sand) < 1e-4
           and abs(rate[tribes.DESERT] - rate[tribes.TEMPERATE]) < 1e-6 and not hasattr(climate, 'cold_home'),
           f'{dry}, 겨울에 먹는 양 {want_eat:.3f}/초')

    # 길찾기: 부족마다 실제 걷는 빠르기로 (설원 부족은 눈길을 피하지 않는다, 다른 부족은 설원·사막을 조금 비싸게)
    import numpy as _np
    from sim.kernels.flow import INF, _flow
    from scipy import ndimage as _nd
    pc = {tr: climate.path_cost(w, tr) for tr in (tribes.TEMPERATE, tribes.SNOW, tribes.DESERT)}
    sw = snow & gm.walk
    ok_cost = (bool((pc[tribes.SNOW][sw] <= gm.cost[sw] + 1e-5).all()) and bool((pc[tribes.SNOW][sw] < gm.cost[sw] - 1e-3).any())
               and bool((pc[tribes.TEMPERATE][sw] > gm.cost[sw]).all()) and bool((pc[tribes.DESERT][sand & gm.walk] == gm.cost[sand & gm.walk]).all()))
    report('길찾기 비용: 설원 부족은 설원에서 싸고, 온대는 설원·사막에서 비싸고, 사막 부족은 사막에서 그대로', ok_cost)
    # 설원을 가로지르는 두 점: 설원 부족이 지나는 칸 중 설원 비율이 온대보다 높다
    core = _nd.binary_erosion(sw, iterations=6)
    ys, xs = _np.nonzero(core)
    k = len(ys) // 2
    cy, cx = int(ys[k]), int(xs[k])
    def path(cost, s, t):
        n = gm.walk.size
        out = _np.empty((gm.H, gm.W), _np.float32)
        _flow(gm.walk, cost, t[0], t[1], _np.array([s[0]]), _np.array([s[1]]), out, _np.zeros(n, _np.uint8),
              _np.empty(n * 3, _np.float32), _np.empty(n * 3, _np.int64))
        y, x, cells = s[0], s[1], []
        for _ in range(4000):
            cells.append((y, x))
            if (y, x) == t:
                break
            nb = [(out[yy, xx], yy, xx) for yy in range(max(y - 1, 0), min(y + 2, gm.H)) for xx in range(max(x - 1, 0), min(x + 2, gm.W))]
            _, y, x = min(nb)
        return cells
    ring = [(cy + int(dy), cx + int(dx)) for dy, dx in ((0, 40), (0, -40), (40, 0), (-40, 0))]
    pair = next(((a, b) for a in ring for b in ring if a < b and all(0 <= v[0] < gm.H and 0 <= v[1] < gm.W and gm.walk[v] for v in (a, b))
                 and not snow[a] and not snow[b]), None)
    if pair is None:
        pair = ((cy, cx - 30), (cy, cx + 30))
    share = {tr: _np.mean([snow[c] for c in path(pc[tr], pair[0], pair[1])]) for tr in (tribes.SNOW, tribes.TEMPERATE)}
    report('길찾기: 설원 부족은 눈길로 가로질러 가고, 온대는 눈길을 덜 지난다', share[tribes.SNOW] >= share[tribes.TEMPERATE],
           f'지나는 칸 중 설원 비율: 설원 부족 {share[tribes.SNOW]:.2f}, 온대 {share[tribes.TEMPERATE]:.2f}')
    s1 = w._route(_np.array([men['plain']]), float(pair[1][0]), float(pair[1][1]))
    nat.tribe = tribes.SNOW
    s2 = w._route(_np.array([men['plain']]), float(pair[1][0]), float(pair[1][1]))
    report('길찾기 캐시는 부족마다 따로', w.fields.keys[s1] != w.fields.keys[s2], f'{w.fields.keys[s1]} / {w.fields.keys[s2]}')
