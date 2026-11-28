"""개척 (부족 바꾸기, sim/tribes.py Pioneer).
- 다른 기후 지역에 거점을 다 지으면 그 기후의 부족으로 바꿀 카드가 뜬다. 바꾸면 옛 부족, 유지하면 새 기후를 버린다 (다시 뜨지 않는다).
- 지금 부족 기후의 거점을 모두 잃으면 남은 거점이 가장 많은 기후의 부족이 된다. 이렇게 잃은 기후는 다시 지으면 다시 뜬다.
- 기다리는 카드는 그 거점이 무너지면 사라진다. AI는 새 기후의 거점이 더 많아지면 바꾼다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim import tribes
from sim.terrain import GameMap
from sim.world import World


def _spots(w, want, n):
    """기후 want인 거점 자리 n개 (서로, 다른 건물과 떨어진)."""
    out = []
    b = w.builds
    for y in range(20, w.map.H - 20, 7):
        for x in range(20, w.map.W - 20, 7):
            if len(out) >= n:
                return out
            if not w.can_place(y, x, R.BUILD_STATS[R.HALL]['r']) or tribes.classify(w.map, y, x) != want:
                continue
            live = np.flatnonzero(b.alive[:b.n])
            if any(np.hypot(b.x[i] - x, b.y[i] - y) < 14 for i in live) or any(np.hypot(px - x, py - y) < 14 for py, px in out):
                continue
            out.append((y, x))
    return out


def _build(w, nid, spot):
    """거점을 거의 다 지어 두고 병사 하나로 마무리한다 (실제 완성 경로로)."""
    st = R.BUILD_STATS[R.HALL]
    y, x = spot
    h = w.builds.add(nid, R.HALL, x + 0.5, y + 0.5, st['hp'], st['r'], prog=0.97)
    k = w.units.add(nid, R.INFANTRY, x + 0.5, y + 0.5, 40.0)
    w.order_build([k], h)
    for _ in range(400):
        w.update(0.05)
        if w.builds.prog[h] >= 1:
            break
    w.units.alive[k] = False
    return h


def _raze(w, h):
    w.builds.hp[h] = 0.0
    w.update(0.05)


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = World(gm, 2, seed=5, map_seed=42)
    for i in w.unit_ids():
        w.units.alive[i] = False
    w.wild.animals.clear()
    b = w.builds
    for i in np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] == 0)):
        b.alive[i] = False
    T, S, D = tribes.TEMPERATE, tribes.SNOW, tribes.DESERT
    ts, ss, ds = _spots(w, T, 2), _spots(w, S, 1), _spots(w, D, 2)
    assert len(ts) == 2 and len(ss) == 1 and len(ds) == 2, (ts, ss, ds)
    st = R.BUILD_STATS[R.HALL]
    b.add(0, R.HALL, ts[0][1] + 0.5, ts[0][0] + 0.5, st['hp'], st['r'], prog=1.0)   # 시작 거점 (온대)
    nat = w.nations[0]
    nat.tribe = nat.start_tribe = T
    v0 = w.pioneer.version

    # 1. 사막에 거점 → 카드, 바꾸면 온대를 버린다
    d1 = _build(w, 0, ds[0])
    offered = [o[0] for o in nat.offers]
    w.pioneer.pick(0, True)
    report('다른 기후 (사막)에 거점을 다 지으면 카드, 바꾸면 그 부족이 되고 옛 부족은 버린다',
           offered == [D] and nat.tribe == D and nat.dropped == [T] and not nat.offers and w.pioneer.version > v0,
           f'카드 {offered}, 부족 {nat.tribe}, 버림 {nat.dropped}')

    # 2. 버린 기후 (온대)에 다시 지어도 카드가 없다
    t1 = _build(w, 0, ts[1])
    report('스스로 버린 기후에 거점을 지어도 카드가 뜨지 않는다', not nat.offers and w.builds.prog[t1] >= 1, f'카드 {nat.offers}')

    # 3. 설원에 거점 → 카드, 유지하면 설원을 버린다
    s1 = _build(w, 0, ss[0])
    offered = [o[0] for o in nat.offers]
    w.pioneer.pick(0, False)
    report('유지를 고르면 새 기후 (설원)를 버린다', offered == [S] and nat.tribe == D and nat.dropped == [T, S],
           f'카드 {offered}, 부족 {nat.tribe}, 버림 {nat.dropped}')

    # 4. 사막 거점을 모두 잃으면 남은 거점이 많은 기후 (온대 2, 설원 1)로. 사막은 버린 것이 아니다
    _raze(w, d1)
    report('지금 부족 기후의 거점을 모두 잃으면 남은 거점이 가장 많은 기후의 부족이 된다 (버림 목록은 그대로)',
           nat.tribe == T and nat.dropped == [T, S], f'부족 {nat.tribe}, 버림 {nat.dropped}, 거점 {w.pioneer.halls(0)}')

    # 5. 잃은 기후 (사막)에 다시 지으면 다시 카드. 고르기 전에 그 거점이 무너지면 카드는 사라진다
    d2 = _build(w, 0, ds[1])
    again = [o[0] for o in nat.offers]
    _raze(w, d2)
    report('잃어서 바뀐 기후는 다시 지으면 카드가 뜨고, 고르기 전에 거점이 무너지면 카드가 사라진다',
           again == [D] and not nat.offers and nat.tribe == T, f'다시 {again}, 무너진 뒤 {nat.offers}')
    _ = s1

    # 6. AI: 새 기후의 거점이 지금 부족 기후보다 많아지면 바꾼다
    from sim.ai import Bot
    w2 = World(gm, 2, seed=5, map_seed=42)
    n2 = w2.nations[1]
    bot = Bot(1, np.random.default_rng(0))
    h0 = int(w2.building_ids(1, R.HALL)[0])
    other = next(c for c in (T, S, D) if c != n2.tribe)
    n2.offers = [(other, h0, int(w2.builds.gen[h0]))]
    w2.pioneer.zone[(h0, int(w2.builds.gen[h0]))] = n2.tribe
    bot._tribe_card(w2, n2)
    kept = n2.tribe != other and len(n2.offers) == 1
    w2.pioneer.zone[(h0, int(w2.builds.gen[h0]))] = other       # 이제 새 기후의 거점이 더 많다
    bot._tribe_card(w2, n2)
    report('AI는 새 기후의 거점이 더 많아지면 부족을 바꾼다 (그 전에는 카드를 들고 기다린다)', kept and n2.tribe == other,
           f'기다림 {kept}, 부족 {n2.tribe}')
