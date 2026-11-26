"""web_game에서 바꾼 판 규칙.
- 나룻배: 병사들이 있는 땅의 항구로 모여, 항구 앞 배에 한 명씩 차례로 타고, 다 타면 모든 배가 함께 출발해 상륙한다.
  그 땅에 항구가 없으면 건너지 않고 알려 준다.
- 같은 땅의 먼 곳: 걷기와 배를 보조 스레드에서 견주고 (병사는 우선 걷는다), 다음 update에 배가 더 빠르고 그 명령대로 가고 있으면 배로.
- 시작 자리: 넓고 식량 자원지가 있는 섬이면 어디서든 (가장 큰 땅만이 아니라).
"""
import numpy as np

from engine.mapgen import load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.spawn import choose_starts, start_islands
from sim.terrain import GameMap
from sim.world import World


def run(report, cache_dir='.cache'):
    scene = TerrainScene.load(load_preset('island_arc', default_config(512, 42)), cache_dir, progress=lambda s: None)
    _convoy(report, scene)
    _no_harbor(report, scene)
    _same_land_ferry(report, scene)
    _islands(report, scene)


def _setup(scene, extra=16, harbor=True):
    """내 거점 곁에 병사를 더 두고, 내 섬 해안에 완성된 항구 하나. 반환: (세계, 병사, 내 섬, 다른 섬의 목표 칸)."""
    gm = GameMap(scene)
    w = World(gm, 5, seed=5, map_seed=42)                      # AI 없이 (World만: 내 배만 본다)
    m, b = gm, w.builds
    hall = next(i for i in range(b.n) if b.own[i] == 0 and b.kind[i] == R.HALL)
    hy, hx = int(b.y[hall]), int(b.x[hall])
    src = int(m.comp[hy, hx])
    if harbor:
        spot = next((int(hy + np.sin(a) * r), int(hx + np.cos(a) * r))
                    for r in range(6, 160, 2) for a in np.linspace(0, 2 * np.pi, 48, endpoint=False)
                    if 0 <= int(hy + np.sin(a) * r) < m.H and 0 <= int(hx + np.cos(a) * r) < m.W
                    and w.fleet.can_place_harbor(int(hy + np.sin(a) * r), int(hx + np.cos(a) * r))
                    and m.comp[int(hy + np.sin(a) * r), int(hx + np.cos(a) * r)] == src)
        st = R.BUILD_STATS[R.HARBOR]
        b.add(0, R.HARBOR, spot[1] + 0.5, spot[0] + 0.5, st['hp'], st['r'], prog=1.0)
    for _ in range(extra):
        w._spawn_unit(0, R.INFANTRY, hy, hx, 7)
    area = np.bincount(m.comp[m.land & (m.comp > 0)])
    other = next(int(c) for c in np.argsort(-area) if c != src and c > 0 and area[c] > 2000)
    ys, xs = np.nonzero(m.comp == other)
    return w, w.unit_ids(0), src, other, (float(ys[len(ys) // 2]), float(xs[len(xs) // 2]))


def _convoy(report, scene):
    w, ids, src, other, (ty, tx) = _setup(scene)
    m, u = w.map, w.units
    gen = u.gen[ids].copy()
    w.order_move(ids, ty, tx)
    c = w.fleet.convoys[0]
    gather_ok = c.gather is not None and m.comp[c.gather] == src
    one_by_one, crossed_early, max_load, departed_all = True, False, 0, None
    prev = 0
    for _ in range(int(200 / 0.05)):
        w.update(0.05)
        aboard = int(u.aboard[ids].sum())
        if aboard - prev > 1:                                  # 한 걸음에 둘 이상 타면 '차례로'가 아니다
            one_by_one = False
        prev = aboard
        ferries = [b for b in w.fleet.boats if b.kind == 'ferry']
        loading = [b for b in ferries if b.state == 'load']
        max_load = max([max_load] + [len(b.cargo) for b in ferries])
        if any(b.state == 'cross' for b in ferries):
            if departed_all is None:
                departed_all = aboard == len(ids) and all(b.state == 'cross' for b in ferries if b.cargo)
            if loading:
                crossed_early = True
        if w.time > 5 and not w.fleet.boats:
            break
    same = u.alive[ids] & (u.gen[ids] == gen)                  # 죽은 칸은 다른 병사가 다시 쓸 수 있다
    landed = (m.comp[u.y[ids].astype(int), u.x[ids].astype(int)] == other) | ~same
    report(f'나룻배: 항구에 모여 한 명씩 타고 ({len(ids)}명, 한 척 최대 {max_load}명), 다 타면 함께 출발해 상륙 '
           f'(배 {w.fleet.log["ferries"]}척, 상륙 {w.fleet.log["landed"]}명)',
           gather_ok and one_by_one and not crossed_early and departed_all and max_load <= R.BOAT_CAPACITY
           and w.fleet.log['landed'] == len(ids) and landed.all(),
           f'모이는 곳 {gather_ok}, 차례로 {one_by_one}, 함께 출발 {departed_all}, 일찍 출발 {crossed_early}, '
           f'상륙 {w.fleet.log["landed"]}/{len(ids)}')


def _no_harbor(report, scene):
    w, ids, src, other, (ty, tx) = _setup(scene, extra=0, harbor=False)
    w.order_move(ids, ty, tx)
    said = any('항구가 있어야' in t for t, *_ in w.messages)
    report('나룻배: 병사들이 있는 땅에 항구가 없으면 건너지 않고 알려 줌', said and not w.fleet.convoys and not w.fleet.boats)


def _islands(report, scene):
    gm = GameMap(scene)
    w = World(gm, 5, seed=1, map_seed=42)
    isl = set(start_islands(gm, w.sites).tolist())
    many = 0
    on_ok = True
    for seed in range(20):
        starts = choose_starts(gm, 5, np.random.default_rng(seed), None, w.sites)
        comps = {int(gm.comp[y, x]) for y, x in starts}
        on_ok &= comps <= isl
        many += len(comps) >= 2
    report(f'시작 자리: 시작할 수 있는 섬 {len(isl)}개, 20판 중 {many}판이 여러 섬에서 시작, 모두 시작할 수 있는 섬 위',
           len(isl) >= 2 and many >= 5 and on_ok)

def _same_land_ferry(report, scene):
    """같은 땅의 먼 곳: 견주기는 보조 스레드에서, 병사는 우선 걷고 다음 update에 배가 빠르면 배로 (다른 명령을 받았으면 그대로)."""
    import sim.world as SW
    from sim.entities import MOVE
    w, ids, src, other, _ = _setup(scene)
    m, u = w.map, w.units
    cy, cx = float(u.y[ids].mean()), float(u.x[ids].mean())
    ys, xs = np.nonzero((m.comp == src) & m.walk)
    k = int(np.argmax(np.hypot(ys - cy, xs - cx)))
    ty, tx = float(ys[k]), float(xs[k])                         # 같은 땅에서 가장 먼 칸
    prep = w.fleet.ferry_prep(ids, ty, tx, src)
    real = None if prep is None else SW._ferry_eval(m.walk, m.cost, m.nav, prep['ty'], prep['tx'], prep['here'], prep['land'],
                                                    prep['landing'], prep['ports'], prep['n'], R.UNIT_STATS[R.INFANTRY]['speed'])
    report('걷기·배 견주기 (보조 스레드용 계산)가 돈다', prep is not None and (real is None or (real[0] > 0 and real[1] > 0)), f'{real}')
    orig = SW._ferry_eval
    try:
        SW._ferry_eval = lambda *a: (1.0, 100.0)                 # 배가 훨씬 빠르다고 치고
        w.order_move(ids, ty, tx)
        walking = bool((u.state[ids] == MOVE).all()) and not w.fleet.convoys
        w.update(0.05)
        switched = len(w.fleet.convoys) == 1 and set(w.fleet.convoys[0].assigned) == set(map(int, ids)) and w.fleet.convoys[0].then[0] == "move"
        report('먼 같은 땅: 우선 걷고, 다음 update에 배가 빠르면 나룻배로', walking and switched,
               f'처음 걷기 {walking}, 나룻배 {len(w.fleet.convoys)}')
        w2, ids2, src2, _, _ = _setup(scene)
        w2.order_move(ids2, ty, tx)
        w2.order_move(ids2, float(w2.units.y[ids2].mean()) + 3, float(w2.units.x[ids2].mean()))   # 그새 다른 명령
        w2.update(0.05)
        report('견주는 사이 다른 명령을 받았으면 배로 바꾸지 않는다', not w2.fleet.convoys)
        SW._ferry_eval = lambda *a: (100.0, 1.0)                 # 걷기가 빠르다
        w3, ids3, _, _, _ = _setup(scene)
        w3.order_move(ids3, ty, tx)
        w3.update(0.05)
        report('걷기가 빠르면 그대로 걷는다', not w3.fleet.convoys and bool((w3.units.state[ids3] == MOVE).all()))
    finally:
        SW._ferry_eval = orig
