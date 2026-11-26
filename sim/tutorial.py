"""튜토리얼 판 (로비 '튜토리얼'): 기능을 짧게 해 보는 작은 판.

- 나라 둘: 사람 하나 + 가만히 있는 적 하나 (AI가 생각하지 않는다: 먼저 쳐들어오지 않는다).
- 적 거점은 내 거점에서 걸어서 갈 수 있는 같은 땅, 너무 멀지 않은 곳 (ENEMY_DIST). 적 병사는 조금만, 거점은 반쯤 부서진 채.
- 내 거점 곁에 야생말 무리 (길들이기 연습), 자원은 넉넉히 (건물·훈련을 바로 해 보게).
- 자리는 늘 같다 (같은 지도 + 고정 난수): 언제 해도 같은 판.
단계 안내와 확인은 브라우저가 한다 (web/src/game/tutorial.ts).
"""
from __future__ import annotations

import numpy as np

from sim import rules as R

SEED = 7
ENEMY_DIST = (45.0, 75.0)        # 적 거점까지 (칸)
HORSE_DIST = (16.0, 26.0)        # 말 무리까지 (칸)
HORSES = 6
RES = (250.0, 250.0, 250.0)      # 처음 자원 (식량, 목재, 석재): 처음 한도(STORE_BASE + STORE_HALL) 안에서
ENEMY_UNITS = 2                  # 적 병사 수 (보병)
ENEMY_HALL_HP = 0.5              # 적 거점 체력 비율


def starts(gmap, sites) -> list[tuple[int, int]]:
    """[내 거점, 적 거점] 자리 (y, x). 내 자리는 보통 판처럼 고르고, 적은 같은 땅의 알맞은 거리에."""
    from sim.spawn import choose_starts
    rng = np.random.default_rng(SEED)
    me = choose_starts(gmap, 1, rng, None, sites)[0]
    my, mx = me
    c0 = gmap.comp[my, mx]
    best, bd = None, 1e9
    for _ in range(4000):
        a = rng.uniform(0, 2 * np.pi)
        d = rng.uniform(*ENEMY_DIST)
        y, x = int(my + np.sin(a) * d), int(mx + np.cos(a) * d)
        if not (8 <= y < gmap.H - 8 and 8 <= x < gmap.W - 8) or gmap.comp[y, x] != c0:
            continue
        if not gmap.land[y - 5:y + 6, x - 5:x + 6].all() or gmap.cliff[y, x]:
            continue
        score = abs(d - sum(ENEMY_DIST) / 2) + gmap.base_cost[y, x] * 5      # 가운데 거리, 걷기 쉬운 땅
        if score < bd:
            best, bd = (y, x), score
    return [tuple(me), best or (my, min(mx + 50, gmap.W - 10))]


def setup(world, me: int, enemy: int) -> None:
    """판이 만들어진 뒤: 자원, 적 병사·거점 줄이기, 내 거점 곁 말 무리."""
    w = world
    w.nations[me].res = list(RES)
    w.nations[me].tribe = 0                                  # 튜토리얼은 온대 (sim/tribes.py)
    u, b = w.units, w.builds
    foes = [int(i) for i in np.flatnonzero(u.alive[:u.n] & (u.own[:u.n] == enemy))]
    for i in foes[ENEMY_UNITS:]:
        u.alive[i] = False
    for i in np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] == enemy)):
        b.hp[i] *= ENEMY_HALL_HP
    hall = next(int(i) for i in np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] == me) & (b.kind[:b.n] == R.HALL)))
    _horses(w, float(b.y[hall]), float(b.x[hall]))


def _horses(w, hy: float, hx: float) -> None:
    """내 거점 곁 (같은 땅, 걷기 쉬운 곳)에 말 무리."""
    from sim.wildlife import Animal
    wild, m = w.wild, w.map
    rng = np.random.default_rng(SEED + 1)
    c0 = m.comp[int(hy), int(hx)]
    center = None
    for _ in range(400):
        a, d = rng.uniform(0, 2 * np.pi), rng.uniform(*HORSE_DIST)
        y, x = hy + np.sin(a) * d, hx + np.cos(a) * d
        if 4 <= y < m.H - 4 and 4 <= x < m.W - 4 and m.walk[int(y), int(x)] and m.comp[int(y), int(x)] == c0 \
                and m.base_cost[int(y), int(x)] <= 1.3:
            center = (y, x)
            break
    if center is None:
        return
    for k in range(HORSES):
        for _ in range(30):
            a, r = rng.uniform(0, 2 * np.pi), 5.0 * np.sqrt(rng.uniform(0, 1))
            y, x = center[0] + np.sin(a) * r, center[1] + np.cos(a) * r
            if m.walk[int(y), int(x)] and m.comp[int(y), int(x)] == c0:
                break
        else:
            y, x = center
        an = Animal(wild._next, R.HORSE, float(x), float(y), wild.rng)
        an.hy, an.hx = center
        wild.animals[an.id] = an
        wild._next += 1
