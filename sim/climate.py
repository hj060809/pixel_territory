"""기후 효과 (docs/ECONOMY_PLAN.md 4장): 부족(sim/tribes.py)과 병사가 선 땅(설원 지역·사막 지역)으로.

병사 (보병·궁수·창기병·기마궁수)만 받는다: 어느 거점에서 나왔든, 동맹에게 받았든 나라의 부족을 따른다.
용기사·바위거북·야생 동물·배는 받지 않는다.

걸음마다 update가 병사마다 세 배율을 정한다 (전투 계산 sim/kernels/combat.py와 화염탑·바위거북·야생 드래곤이 쓴다):
- fx_speed: 이동. 불리한 기후 지역 (온대: 설원·사막, 설원 부족: 사막, 사막 부족: 설원)이면 slow배.
            설원 부족은 설원 지역에서 눈 때문에 느려지는 몫만 없다 (dry_cost: 눈 덮인 칸은 눈 아래 땅처럼,
            만년설·얼음 재질은 고산 초원처럼. 높이·툰드라·바위 때문에 느린 몫은 그대로: 다른 지역 땅과 비슷한 빠르기).
- fx_take:  받는 피해. 설원 부족은 설원 지역에서 snow_take배.
- fx_deal:  주는 피해. 사막 부족은 설원이 아닌 곳에서 desert_deal배.
그리고 확률 피해 (더위·동상): 불리한 기후 지역의 병사는 every초에 한 번꼴로 chance 확률로 최대 체력의 dmg만큼
(기후 피해로는 최대 체력의 floor 아래로 떨어지지 않는다). 맞으면 화면에 짧은 점 효과 (공격 기록 kind 8 동상, 9 더위).
수치는 rules.CLIMATE 한 곳에.
"""
from __future__ import annotations

import numpy as np

from sim import rules as R
from sim import tribes

C = R.CLIMATE
SOLDIERS = (R.INFANTRY, R.ARCHER, R.LANCER, R.HORSE_ARCHER, R.GRENADIER, R.HORSE_GRENADIER)
FROST, HEAT = 8, 9                      # 공격 기록 kind (화면: 동상 눈송이 점, 더위 아지랑이 점)


def soldier_mask(kind: np.ndarray) -> np.ndarray:
    return np.isin(kind, SOLDIERS)


def dry_cost(m) -> np.ndarray:
    """눈이 없을 때의 걷는 비용 (설원 부족용, 계절과 무관해 한 번만): 만년설·얼음 재질(3.0)은 눈 아래 고산 초원(ALPINE)으로 친다.
    바탕 비용 = 재질 비용 × 높이 배율이라 높이 몫은 남는다. 계절 눈 덮임은 바탕 비용에 없다."""
    got = m.__dict__.get('_dry_cost')
    if got is None:
        from engine.render import materials as S
        from sim.terrain import SNOWY, _RULES
        snowy = np.isin(m.layers['pre'], SNOWY)
        got = np.where(snowy, m.base_cost / _RULES[SNOWY[0]][0] * _RULES[S.ALPINE][0], m.base_cost).astype(np.float32)
        m.__dict__['_dry_cost'] = got
    return got


def update(world, dt: float) -> None:
    w, u, m = world, world.units, world.map
    n = u.n
    u.fx_speed[:n] = 1.0
    u.fx_take[:n] = 1.0
    u.fx_deal[:n] = 1.0
    nn = len(w.nations)
    ids = np.flatnonzero(u.alive[:n] & ~u.aboard[:n] & (u.own[:n] < nn) & soldier_mask(u.kind[:n]) & ~u.air[:n])
    if not len(ids):
        return
    snow, sand = tribes.zones(m)
    cy = np.clip(u.y[ids].astype(np.int64), 0, m.H - 1)
    cx = np.clip(u.x[ids].astype(np.int64), 0, m.W - 1)
    on_snow, on_sand = snow[cy, cx], sand[cy, cx]
    tribe = np.array([nat.tribe for nat in w.nations], np.int8)[u.own[ids]]
    is_snow, is_sand = tribe == tribes.SNOW, tribe == tribes.DESERT
    bad_snow = on_snow & ~is_snow                                   # 설원 지역의 설원 부족 아닌 병사 (동상)
    bad_sand = on_sand & ~is_sand                                   # 사막 지역의 사막 부족 아닌 병사 (더위)
    bad = bad_snow | bad_sand
    speed = np.where(bad, C['slow'], 1.0)
    home = on_snow & is_snow                                        # 설원 부족은 설원에서 눈 때문에 느려지지 않는다
    if home.any():
        hy, hx = cy[home], cx[home]
        now = 1.0 / np.maximum(m.speed_mul[hy, hx], 1e-3)           # 지금 걷는 비용 (계절 눈 포함)
        terr = w.k_terrain[u.kind[ids[home]]]
        speed[home] = np.maximum(1.0, now / dry_cost(m)[hy, hx]) ** terr
    u.fx_speed[ids] = speed
    u.fx_take[ids] = np.where(is_snow & on_snow, C['snow_take'], 1.0)         # 설원 부족은 제 땅(설원 지역)에서만 덜 다친다
    u.fx_deal[ids] = np.where(is_sand & ~on_snow, C['desert_deal'], 1.0)
    # 확률 피해: 걸음마다 chance × dt / every 확률 (평균은 every초에 chance번)
    hit = ids[bad & (w.rng.random(len(ids)) < C['chance'] * dt / C['every'])]
    if not len(hit):
        return
    hmax = w.k_hp[u.kind[hit]]
    floor = hmax * C['floor']
    u.hp[hit] = np.where(u.hp[hit] > floor, np.maximum(u.hp[hit] - hmax * C['dmg'], floor), u.hp[hit])
    # 더위·동상은 '공격받았다'가 아니다: 길들이기가 멈추지 않게 기준 체력도 같이 내린다
    tamers = getattr(getattr(w, 'wild', None), 'tamers', {})
    for i in hit.tolist():
        if i in tamers:
            tamers[i].hp = float(u.hp[i])
    frost = snow[np.clip(u.y[hit].astype(np.int64), 0, m.H - 1), np.clip(u.x[hit].astype(np.int64), 0, m.W - 1)]
    for i, f in zip(hit.tolist(), frost.tolist()):
        w.recent.append((w.time, float(u.x[i]), float(u.y[i]), float(u.x[i]), float(u.y[i]), FROST if f else HEAT))


def _upkeep_where(world, pick, zone) -> np.ndarray:
    """나라마다, pick(부족)인 나라의 병사 중 zone 칸에 선 병사들의 먹는 양 가중치 합."""
    w, u, m = world, world.units, world.map
    n, nn = u.n, len(w.nations)
    out = np.zeros(nn)
    who = [nat.id for nat in w.nations if pick(nat.tribe)]
    if not who or n == 0:
        return out
    ids = np.flatnonzero(u.alive[:n] & ~u.aboard[:n] & np.isin(u.own[:n], who) & soldier_mask(u.kind[:n]))
    if not len(ids):
        return out
    on = zone[np.clip(u.y[ids].astype(np.int64), 0, m.H - 1), np.clip(u.x[ids].astype(np.int64), 0, m.W - 1)]
    ids = ids[on]
    np.add.at(out, u.own[ids], w.k_upkeep[u.kind[ids]])
    return out


def thirst(world) -> np.ndarray:
    """나라마다 '사막의 갈증'을 받는 병사들의 먹는 양 가중치 합 (사막 지역에 있는 병사: 모든 부족)."""
    return _upkeep_where(world, lambda t: True, tribes.zones(world.map)[1])


def path_cost(world, tribe: int) -> np.ndarray:
    """이 부족의 병사가 실제로 걷는 빠르기로 잰 길찾기 비용 (칸마다, 평지 1). update의 fx_speed와 같은 규칙:
    불리한 기후 지역은 1/slow배 비싸고, 설원 부족은 설원 지역에서 눈 때문에 느려지는 몫이 없다 (dry_cost).
    계절이 바뀌어 지도 비용(map.cost)이 바뀌면 다시 만든다. 길찾기(sim/pathing.py)는 부족마다 따로 캐시한다."""
    m = world.map
    cache = world.__dict__.setdefault('_path_costs', {})
    got = cache.get(tribe)
    if got is not None and got[0] is m.cost:
        return got[1]
    snow, sand = tribes.zones(m)
    cost = m.cost.astype(np.float32, copy=True)
    slow = np.float32(1.0 / C['slow'])
    if tribe == tribes.SNOW:
        cost[snow] = np.minimum(cost[snow], dry_cost(m)[snow])
        cost[sand] *= slow
    elif tribe == tribes.DESERT:
        cost[snow] *= slow
    else:
        cost[snow | sand] *= slow
    cache[tribe] = (m.cost, cost)
    return cost


def tame_mul(world, nid: int, animal: int) -> float:
    """길들이는 시간 배율: 설원 부족은 바위거북, 사막 부족은 드래곤이 더 오래 걸린다."""
    if nid >= len(world.nations):
        return 1.0
    t = world.nations[nid].tribe
    if t == tribes.SNOW and animal == R.TORTOISE_W:
        return C['tame_snow_tortoise']
    if t == tribes.DESERT and animal == R.DRAGON:
        return C['tame_desert_dragon']
    return 1.0
