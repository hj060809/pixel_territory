"""진형 (sim/world.py order_formation, 커널 sim/kernels/combat.py).
- 병사마다 제 자리로 가 선다 (함께 길을 따라가다 가까이서 곧장). 긴 선은 토막마다 따로 길을 찾는다.
- 선 뒤 진형을 지킨다: 근접은 제 자리에서 leash칸 안의 적만 쫓고, 궁수는 사거리 밖으로 쫓지 않는다. 밀리면 돌아온다.
- 걸을 수 없는 자리는 가까운 걸을 수 있는 칸으로. 다른 명령을 받으면 풀린다. 남의 병사는 진형에 넣지 못한다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim import rules as R
from sim.commands import PlayerCommands
from sim.entities import IDLE
from sim.terrain import GameMap
from sim.world import World


def _open_area(gm, w, hw=22, hh=14):
    """나라 0의 거점 가까이, (2hw × 2hh) 칸이 모두 걸을 수 있는 평평한 곳의 가운데 (x, y)."""
    b = w.builds
    hall = w.building_ids(0, R.HALL)[0]
    hx, hy = int(b.x[hall]), int(b.y[hall])
    walk = gm.walk
    best = None
    for r in range(12, 120, 3):
        for t in np.linspace(0, 2 * np.pi, 32, endpoint=False):
            x, y = int(hx + r * np.cos(t)), int(hy + r * np.sin(t))
            if hw <= x < gm.W - hw and hh <= y < gm.H - hh and walk[y - hh:y + hh, x - hw:x + hw].all():
                best = (x + 0.5, y + 0.5)
                break
        if best:
            break
    return best


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = World(gm, 3, seed=5, map_seed=42)
    u = w.units
    for i in w.unit_ids():                                    # 처음 병사는 치운다 (시험에 끼지 않게)
        u.alive[i] = False
    cx, cy = _open_area(gm, w)
    lr = R.FORMATION['leash']

    # 보병 10이 앞줄, 궁수 6이 뒷줄 (1.6칸 뒤). 12칸 뒤에서 출발
    inf = [u.add(0, R.INFANTRY, cx - 4 + (k % 5) * 1.6, cy + 12 + (k // 5) * 1.2, 40.0) for k in range(10)]
    arc = [u.add(0, R.ARCHER, cx - 3 + k * 1.2, cy + 13.5, 26.0) for k in range(6)]
    gx = [cx - 6.75 + k * 1.5 for k in range(10)] + [cx - 3.75 + k * 1.5 for k in range(6)]
    gy = [cy] * 10 + [cy + 1.6] * 6
    ids = inf + arc
    ok = w.order_formation(np.array(ids), gx, gy)
    for _ in range(int(20 / 0.05)):
        w.update(0.05)
    off = [float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(ids, gx, gy)]
    report('진형: 병사마다 제 자리에 가 선다 (보병 앞줄, 궁수 뒷줄)',
           ok and max(off) < 0.6 and all(u.state[i] == IDLE and u.form[i] for i in ids), f'제 자리에서 가장 먼 병사 {max(off):.2f}칸')

    # 진형을 지킨다: leash 밖의 적은 근접이 쫓지 않고, 궁수는 사거리 안이면 제자리에서 쏜다
    foe = u.add(1, R.INFANTRY, cx, cy - (lr + 4), 9999.0)
    u.freeze[foe] = 999.0                                     # 시험용: 제자리
    hp0 = float(u.hp[foe])
    for _ in range(int(5 / 0.05)):
        w.update(0.05)
    moved_i = max(float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(inf, gx, gy))
    moved_a = max(float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(arc, gx[10:], gy[10:]))
    report('진형을 지킨다: 근접은 제 자리에서 leash칸 밖의 적을 쫓지 않고, 궁수는 제자리에서 쏜다',
           moved_i < 0.6 and moved_a < 0.6 and u.hp[foe] < hp0, f'보병 {moved_i:.2f}칸, 궁수 {moved_a:.2f}칸 움직임, 적 체력 {hp0:.0f} → {float(u.hp[foe]):.0f}')

    # leash 안으로 들어온 적: 근접이 나가 친다 → 적이 쓰러지면 제 자리로 돌아온다
    u.x[foe], u.y[foe] = cx + 0.3, cy - 3.0
    u.hp[foe] = 300.0
    went = False
    for _ in range(int(4 / 0.05)):
        w.update(0.05)
        went |= any(np.hypot(u.x[i] - u.x[foe], u.y[i] - u.y[foe]) < 2.6 for i in inf)
    u.alive[foe] = False
    for _ in range(int(6 / 0.05)):
        w.update(0.05)
    back = max(float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(inf, gx, gy))
    report('leash칸 안의 적은 근접이 나가 치고, 끝나면 제 자리로 돌아온다', went and back < 0.6, f'나감 {went}, 돌아옴 (가장 먼 병사 {back:.2f}칸)')

    # 궁수는 사거리 밖의 적을 쫓지 않는다
    far = u.add(1, R.INFANTRY, cx, cy + 1.6 - (R.UNIT_STATS[R.ARCHER]['range'] + 2.5), 9999.0)
    u.freeze[far] = 999.0
    for _ in range(int(4 / 0.05)):
        w.update(0.05)
    moved_a = max(float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(arc, gx[10:], gy[10:]))
    report('궁수는 사거리 밖의 적을 쫓지 않는다', moved_a < 0.6, f'궁수 {moved_a:.2f}칸 움직임')
    u.alive[far] = False

    # 밀려나면 돌아온다
    u.x[inf[0]] += 2.0
    for _ in range(int(2 / 0.05)):
        w.update(0.05)
    report('밀려나면 제 자리로 돌아온다', np.hypot(u.x[inf[0]] - gx[0], u.y[inf[0]] - gy[0]) < 0.6,
           f'{float(np.hypot(u.x[inf[0]] - gx[0], u.y[inf[0]] - gy[0])):.2f}칸')

    # 걸을 수 없는 자리 (물): 가까운 걸을 수 있는 칸으로
    wy, wx = np.argwhere(~gm.walk[int(cy) - 60:int(cy) + 60, int(cx) - 60:int(cx) + 60])[0] + [int(cy) - 60, int(cx) - 60]
    w.order_formation(np.array([inf[1]]), [wx + 0.5], [wy + 0.5])
    report('걸을 수 없는 자리는 가까운 걸을 수 있는 칸으로', bool(gm.walk[int(u.gy[inf[1]]), int(u.gx[inf[1]])]) or not u.form[inf[1]],
           f'자리 ({float(u.gx[inf[1]]):.1f}, {float(u.gy[inf[1]]):.1f})')

    # 긴 선 (40칸): 토막마다 따로 길을 찾는다, 모두 제 자리에
    long_x = [cx - 20 + k * 2.6 for k in range(16)]
    long_y = [cy - 6] * 16
    w.order_formation(np.array(ids), long_x, long_y)
    segs = len(set(int(s) for s in u.fslot[ids]))
    for _ in range(int(20 / 0.05)):
        w.update(0.05)
    off = [float(np.hypot(u.x[i] - x, u.y[i] - y)) for i, x, y in zip(ids, long_x, long_y)]
    report('긴 선은 토막마다 따로 길을 찾아 모두 제 자리에', segs >= 3 and max(off) < 0.6, f'토막 {segs}, 가장 먼 병사 {max(off):.2f}칸')

    # 다른 명령을 받으면 풀린다
    w.order_move(np.array(ids[:3]), cy + 8, cx)
    report('다른 명령을 받으면 진형이 풀린다', not any(u.form[i] for i in ids[:3]) and all(u.form[i] for i in ids[3:]))

    # 명령: 남의 병사, 세대가 다른 병사는 넣지 못한다
    other = u.add(1, R.INFANTRY, cx + 2, cy + 8, 40.0)
    c = PlayerCommands(w, 0)
    c.formation([[other, int(u.gen[other]), cx, cy], [ids[5], int(u.gen[ids[5]]) + 1, cx, cy], [ids[6], int(u.gen[ids[6]]), cx + 1, cy + 9]])
    report('진형 명령: 남의 병사·세대가 다른 병사는 빼고 내 병사만', not u.form[other] and abs(float(u.gx[ids[6]]) - (cx + 1)) < 0.6 and u.form[ids[6]])
