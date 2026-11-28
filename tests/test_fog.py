"""전장의 안개 (sim/vision.py, server/protocol.py의 fog).
- 나라마다 병사·건물 둘레가 보이고, 먼 곳은 안 보인다. 가 본 곳은 남는다. 동맹은 시야를 나눈다.
- 안개 판의 상태 메시지: 남의 병사는 보이는 칸에서만. 남의 건물은 본 적 있으면 마지막 모습 (안 보는 사이 무너져도 남는다, 다시 보면 사라진다).
- 진 사람 (관전)은 모두 본다. 세션: start 정보의 fog, 안개 격자 메시지 (길이로 줄인 것의 합 = 격자 칸 수).
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.protocol import StateEncoder, decode
from sim import rules as R
from sim.terrain import GameMap
from sim.vision import Vision
from sim.world import World


def _apply(units, builds, m):
    for u in m['units']:
        units[int(u['slot'])] = u
    for s in m['units_gone']:
        units.pop(int(s), None)
    for b in m['builds']:
        builds[int(b['slot'])] = b
    for s in m['builds_gone']:
        builds.pop(int(s), None)


def _walk_near(w, x, y, r0, r1):
    """(x, y)에서 r0~r1칸 떨어진 걸을 수 있는 칸 하나."""
    pts = np.argwhere(w.map.walk)
    d = np.hypot(pts[:, 1] + 0.5 - x, pts[:, 0] + 0.5 - y)
    k = np.flatnonzero((d >= r0) & (d <= r1))[0]
    return float(pts[k, 1] + 0.5), float(pts[k, 0] + 0.5)


def run(report, cache_dir='.cache'):
    gm = GameMap(TerrainScene.load(default_config(512, 42), cache_dir, progress=lambda s: None))
    w = World(gm, 3, seed=5, map_seed=42)
    w.wild.animals.clear()
    u, b = w.units, w.builds
    for i in w.unit_ids():                                   # 병사는 지우고 거점만 남긴다
        u.alive[i] = False
    h0 = int(w.building_ids(0, R.HALL)[0])
    hx, hy = float(b.x[h0]), float(b.y[h0])
    w.vision = V = Vision(w)
    near = bool(V.visible(0, [hx + 5], [hy])[0])
    h1 = int(w.building_ids(1, R.HALL)[0])
    far = bool(V.visible(0, [b.x[h1]], [b.y[h1]])[0])
    report('거점 둘레는 보이고, 먼 적 거점은 안 보인다', near and not far, f'가까이 {near}, 적 거점 {far}')

    # 병사를 보내면 그 둘레가 보이고, 떠나도 가 본 곳으로 남는다
    sx, sy = _walk_near(w, hx, hy, 40, 60)
    k = u.add(0, R.INFANTRY, sx, sy, 40.0)
    V.update(force=True)
    seen_now = bool(V.visible(0, [sx], [sy])[0])
    u.alive[k] = False
    V.update(force=True)
    gx, gy = int(sx // V.cell), int(sy // V.cell)
    lv = V.levels(0)[gy, gx]
    report('병사 둘레가 보이고, 떠나면 가 본 곳 (1)으로 남는다', seen_now and lv == 1, f'보임 {seen_now}, 떠난 뒤 {lv}')

    # 짓는 중인 건물은 보지 않는다, 다 지으면 보고, 무너지면 다시 가려진다
    st0 = R.BUILD_STATS[R.FARM]
    bx_, by_ = _walk_near(w, hx, hy, 70, 90)
    fb = b.add(0, R.FARM, bx_, by_, st0['hp'], st0['r'], prog=0.0)
    V.update(force=True)
    site_sees = bool(V.visible(0, [bx_], [by_])[0])
    site_lv = int(V.levels(0)[int(by_ // V.cell), int(bx_ // V.cell)])
    site_far = int(V.levels(0)[int((by_ + st0['r'] + R.FOG['site'] + 6) // V.cell), int(bx_ // V.cell)])
    b.prog[fb] = 1.0
    V.update(force=True)
    done_sees = bool(V.visible(0, [bx_], [by_])[0])
    b.alive[fb] = False
    V.update(force=True)
    gone_sees = bool(V.visible(0, [bx_], [by_])[0])
    report('짓는 중인 건물은 둘레만 조금 "가 본 곳" (보지는 않는다), 다 지으면 보고, 무너지면 다시 가려진다',
           not site_sees and site_lv == 1 and site_far == 0 and done_sees and not gone_sees,
           f'자리 보임 {site_sees} (격자 {site_lv}, 조금 밖 {site_far}), 완성 {done_sees}, 무너짐 {gone_sees}')

    # 동맹은 시야를 나눈다
    w.diplo.friend[0, 1] = w.diplo.friend[1, 0] = 1
    V.update(force=True)
    shared = bool(V.visible(0, [b.x[h1]], [b.y[h1]])[0])
    w.diplo.friend[0, 1] = w.diplo.friend[1, 0] = 0
    V.update(force=True)
    report('동맹은 시야를 나눈다', shared, f'동맹 거점이 보임 {shared}')

    # 상태 메시지: 남의 병사는 보이는 칸에서만
    enc = StateEncoder(w, 0)
    units, builds = {}, {}
    ex, ey = _walk_near(w, hx, hy, 6, 9)
    foe_near = u.add(2, R.INFANTRY, ex, ey, 40.0)
    fx, fy = _walk_near(w, hx, hy, 90, 120)
    foe_far = u.add(2, R.INFANTRY, fx, fy, 40.0)
    u.freeze[[foe_near, foe_far]] = 999.0
    V.update(force=True)
    _apply(units, builds, decode(enc.encode({'hour': 9, 'year': 0, 'flags': 0, 'speed': 1}, False, 0.0, fog=True)))
    report('안개: 보이는 적 병사만 보낸다', foe_near in units and foe_far not in units, f'가까운 적 {foe_near in units}, 먼 적 {foe_far in units}')

    # 남의 건물: 본 적 있으면 마지막 모습. 안 보는 사이 무너져도 남고, 다시 보면 사라진다
    st = R.BUILD_STATS[R.TOWER]
    tx, ty = _walk_near(w, fx, fy, 0, 3)
    tw = b.add(2, R.TOWER, tx, ty, st['hp'], st['r'], prog=1.0)
    k = u.add(0, R.ARCHER, fx, fy, 26.0)                    # 정찰병이 본다
    V.update(force=True)
    hdr = {'hour': 9, 'year': 0, 'flags': 0, 'speed': 1}
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    seen = tw in builds
    u.alive[k] = False                                       # 정찰병이 떠난다
    V.update(force=True)
    b.alive[tw] = False                                      # 그사이 무너진다
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    ghost = tw in builds and foe_far not in units
    k = u.add(0, R.ARCHER, fx, fy, 26.0)                    # 다시 가 본다
    V.update(force=True)
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    gone = tw not in builds
    report('남의 건물은 마지막으로 본 모습 (안 보는 사이 무너져도 남고, 다시 보면 사라진다)', seen and ghost and gone,
           f'봄 {seen}, 떠난 뒤 {ghost}, 다시 봄 {gone}')

    # 칸 번호가 다른 건물에게 넘어가도: 기억한 자리를 다시 보면 잔상이 사라진다
    k2 = u.add(0, R.ARCHER, fx, fy, 26.0)
    tw2 = b.add(2, R.TOWER, tx, ty, st['hp'], st['r'], prog=1.0)
    V.update(force=True)
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    u.alive[[k, k2]] = False
    V.update(force=True)
    b.alive[tw2] = False                                     # 안 보는 사이 무너지고
    ox, oy = _walk_near(w, hx, hy, 150, 200)
    reuse = b.add(1, R.FARM, ox, oy, st['hp'], st['r'], prog=1.0)   # 그 칸을 먼 곳의 다른 나라 건물이 쓴다
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    ghost2 = reuse == tw2 and tw2 in builds
    k = u.add(0, R.ARCHER, fx, fy, 26.0)                    # 다시 가 본다
    V.update(force=True)
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=True)))
    report('무너진 건물의 칸을 다른 건물이 써도, 기억한 자리를 다시 보면 잔상이 사라진다', ghost2 and tw2 not in builds,
           f'같은 칸 {reuse == tw2}, 잔상 {ghost2}, 다시 본 뒤 남음 {tw2 in builds}')

    # 관전 (fog=False): 모두
    _apply(units, builds, decode(enc.encode(hdr, False, 0.0, fog=False)))
    report('진 사람 (관전)은 모두 본다', foe_far in units, '')

    # 세션: start 정보와 안개 격자 메시지
    from server.config import ServerConfig as Config
    from server.session import GameSession
    got = []
    cfg = default_config(512, 42)
    scene = TerrainScene.load(cfg, cache_dir, progress=lambda s: None)
    scene.config = cfg                                       # 서버의 지도 장면처럼 (server/maps.py)
    sess = GameSession(scene, {'bots': 2, 'fog': True}, got.append, Config())
    for k in range(4):
        sess.step(0.05, k)
    start = next(m for m in got if isinstance(m, dict) and m.get('t') == 'start')
    fogm = [m for m in got if isinstance(m, dict) and m.get('t') == 'fog']
    V = sess.world.vision
    total = sum(fogm[-1]['rle'][1::2]) if fogm else -1
    report('안개 판: start 정보에 fog, 안개 격자 메시지 (길이 합 = 격자 칸 수)', start.get('fog') is True and total == V.gw * V.gh,
           f'fog {start.get("fog")}, 메시지 {len(fogm)}개, 합 {total} / {V.gw * V.gh}')
    sess2 = GameSession(scene, {'bots': 2}, [].append, Config())
    report('안개를 끈 판엔 시야 계산이 없다', sess2.world.vision is None, '')
