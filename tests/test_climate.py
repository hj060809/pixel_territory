"""기후 효과 (sim/climate.py): 부족과 병사가 선 땅으로 이동·피해 배율, 더위·동상 확률 피해 (최대 체력 30% 아래로는 안 깎인다),
길들이는 시간, 온대의 무역 빠르기. 병사만 받는다."""
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
    report('설원 부족: 설원에선 눈 몫만 빠지고, 사막에선 느리고, 사막 밖에선 덜 다친다',
           plain_like and s['sand'][0] == sl and s['plain'][1] == C['snow_take'] and s['snow'][1] == C['snow_take']
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

    # 길들이는 시간, 무역 빠르기
    mul = {}
    for tr in (tribes.TEMPERATE, tribes.SNOW, tribes.DESERT):
        nat.tribe = tr
        mul[tr] = tuple(climate.tame_mul(w, nid, a) for a in (R.TORTOISE_W, R.DRAGON, R.HORSE))
    report('길들이기: 설원은 거북 ×1.5, 사막은 드래곤 ×1.25, 나머지 그대로',
           mul[tribes.TEMPERATE] == (1.0, 1.0, 1.0) and mul[tribes.SNOW] == (C['tame_snow_tortoise'], 1.0, 1.0)
           and mul[tribes.DESERT] == (1.0, C['tame_desert_dragon'], 1.0), f'{mul}')
    sp = {}
    for tr in (tribes.TEMPERATE, tribes.SNOW, tribes.DESERT):
        nat.tribe = tr
        sp[tr] = w.trade.speed(nid)
    report('무역: 온대만 1.2배 더 자주', sp == {tribes.TEMPERATE: C['temperate_trade'], tribes.SNOW: 1.0, tribes.DESERT: 1.0}, f'{sp}')
