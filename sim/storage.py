"""자원 한도와 무너질 때 빼앗기기 (docs/ECONOMY_PLAN.md 2장). 창고는 없다: 거점과 자원 건물이 창고를 겸한다.

- 한도: 자원마다 따로 (식량·목재·석재·유황). 기본 STORE_BASE + 다 지은 거점마다 모든 자원 +STORE_HALL
  + 다 지은 자원 건물마다 그 건물이 내는 자원 +STORE_SITE (농장 식량, 벌목장 목재, 채석장 석재, 유황 채취장 유황).
  한도를 넘는 생산·선물·약탈은 버려진다.
- 나눠 보관: 자원 k는 한도에 이바지한 비율대로 그 건물들에 나뉘어 있다 (기본 몫은 어디에도 없어 빼앗기지 않는다).
- 빼앗기기: 거점·자원 건물이 무너지면 그 몫 (가진 양 × 그 건물의 이바지 / 한도)을 잃고, 마지막으로 친 나라가 가져간다
  (가져가는 나라의 한도를 넘는 만큼은 사라진다). 비율대로 나뉘어 있으므로 남은 자원은 언제나 남은 한도 안에 든다.

World가 부른다: 걸음마다 update_caps → clamp, 건물이 무너질 때 loot.
"""
from __future__ import annotations

from sim import rules as R

NRES = 4                                     # 식량, 목재, 석재, 유황
RES_OF = {R.FARM: R.FOOD, R.LUMBER: R.WOOD, R.QUARRY: R.STONE, R.SULFUR_PIT: 3, R.PASTURE: R.FOOD}   # 자원 건물 → 그 건물이 늘리는 한도 (목장은 식량)


def contrib(kind: int) -> list[float]:
    """이 건물 종류가 늘리는 한도 (자원마다)."""
    kind = int(kind)
    if kind == R.HALL:
        return [R.STORE_HALL] * NRES
    out = [0.0] * NRES
    if kind in RES_OF:
        out[RES_OF[kind]] = R.STORE_SITE
    return out


def have(nat, k: int) -> float:
    return nat.res[k] if k < 3 else nat.sulfur


def _put(nat, k: int, v: float) -> None:
    if k < 3:
        nat.res[k] = v
    else:
        nat.sulfur = v


def update_caps(world) -> None:
    """나라마다 자원별 한도(nat.caps)를 다시 센다 (다 지은 거점·자원 건물)."""
    b, n = world.builds, len(world.nations)
    caps = [[R.STORE_BASE] * NRES for _ in range(n)]
    for i in range(b.n):
        if not b.alive[i] or b.prog[i] < 1 or b.own[i] >= n:
            continue
        c = contrib(b.kind[i])
        row = caps[b.own[i]]
        for k in range(NRES):
            row[k] += c[k]
    for nat in world.nations:
        nat.caps = caps[nat.id]


def clamp(nat) -> None:
    """한도를 넘는 자원은 버린다."""
    for k in range(NRES):
        if have(nat, k) > nat.caps[k]:
            _put(nat, k, nat.caps[k])


def loot(world, i: int, by: int) -> None:
    """건물 i가 무너졌다 (아직 alive를 끄기 전, 한도를 다시 세기 전): 그 몫을 by 나라에게 (by < 0이면 그냥 잃는다)."""
    b = world.builds
    own = int(b.own[i])
    if b.prog[i] < 1 or own >= len(world.nations):
        return
    c = contrib(b.kind[i])
    if not any(c):
        return
    nat = world.nations[own]
    take = [have(nat, k) * min(c[k] / nat.caps[k], 1.0) if c[k] and nat.caps[k] > 0 else 0.0 for k in range(NRES)]
    for k in range(NRES):
        _put(nat, k, have(nat, k) - take[k])
    if by < 0 or by >= len(world.nations) or by == own or not world.nations[by].alive:
        return
    got = world.nations[by]
    gain = [min(take[k], max(0.0, got.caps[k] - have(got, k))) for k in range(NRES)]
    for k in range(NRES):
        _put(got, k, have(got, k) + gain[k])
    names = [*R.RES_NAMES, '유황']
    parts = [f'{names[k]} {int(gain[k])}' for k in range(NRES) if gain[k] >= 1]
    if parts:
        name = R.BUILD_NAMES[int(b.kind[i])]
        world.say(f'{nat.name}의 {name}에서 자원을 빼앗았습니다 ({", ".join(parts)})', to=by)
        world.say(f'{name}에 있던 자원을 {R.josa(got.name, "이", "가")} 빼앗아 갔습니다', to=own)
