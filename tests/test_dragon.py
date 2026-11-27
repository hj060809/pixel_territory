"""드래곤 (사나운 야생 동물, sim/wildlife.py).
- 큰 설원 덩어리마다 가장 높은 곳에 둥지 (최대 3, 작은 설원엔 없다), 둥지마다 잠든 드래곤.
- 병사가 다가가 치면 깨어 싸우고 (서리 숨결: 범위 피해), 체력 30% 아래면 쓰러진다 (그동안 맞지 않는다).
- 쓰러진 동안 병사 하나가 길들이면 용기사 (어느 병사든 같은 병종). 나라마다 2기까지.
- 용기사는 움직이거나 싸울 때 날아서 (물 위로도) 곧장 가고, 그동안은 근접 병사가 칠 수 없다.
  할 일 없이 멈추면 땅에 내려앉고, 그때는 근접 병사에게도 맞는다.
- 야생 드래곤은 상태 메시지의 병사 칸에 없고 동물 칸에 있다.
- 체력이 깎일수록 기술이 는다: 90% 아래 눈보라 (병사가 가장 많이 몰린 곳에 던진다: 원 안의 땅 병사마다 터져 최대 체력의 65%, 얼어붙는다),
  50% 아래 날아오르기 (쓰러질 때까지 둥지를 돌며 날고 숨결을 뿜는다, 근접 병사는 못 친다) → 30% 아래면 떨어져 쓰러진다 (길들일 수 있다).
"""
import numpy as np

from engine.mapgen import load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.protocol import StateEncoder, decode
from sim import rules as R
from sim.entities import AMOVE, IDLE
from sim.terrain import GameMap
from sim.wildlife import FIGHT, SLEEP, SUBDUED
from sim.world import World


def run(report, cache_dir='.cache'):
    scene = TerrainScene.load(default_config(512, 7), cache_dir, progress=lambda s: None)        # 큰 설원 둘 (둥지 2)
    gm = GameMap(scene)
    w = World(gm, 3, seed=3, map_seed=7)
    wild, u = w.wild, w.units
    dragons = [a for a in wild.animals.values() if a.unit >= 0]
    report('둥지마다 잠든 드래곤', 1 <= len(dragons) <= 3 and all(a.mode == SLEEP for a in dragons), f'{len(dragons)}마리')
    small = GameMap(TerrainScene.load(load_preset('continent', default_config(512, 42)), cache_dir, progress=lambda s: None))
    from sim.wildlife import lairs_for
    report('작은 설원뿐인 지도엔 드래곤이 없다', lairs_for(small) == [], f'{lairs_for(small)}')
    enc = StateEncoder(w)
    m = decode(enc.encode({'hour': 12, 'year': 0, 'flags': 0, 'speed': 1}, False, 0))
    sent = {int(r['slot']) for r in m['units']}
    report('드래곤은 동물 칸으로만', all(a.unit not in sent for a in dragons)
           and sum(int(r['kind']) == R.DRAGON for r in m['animals']) == len(dragons))

    a = dragons[0]
    lx, ly = a.x, a.y
    spots = [(lx + 9 * np.cos(t), ly + 9 * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)]
    spots = [(x, y) for x, y in spots if gm.walk[int(y), int(x)]]
    army = [u.add(0, R.ARCHER if k % 2 == 0 else R.INFANTRY, *spots[k % len(spots)], 9999.0) for k in range(24)]   # 날면 활만 닿는다: 궁수 절반
    for i in army:
        u.hp[i] = R.UNIT_STATS[int(u.kind[i])]['hp'] * 3                  # 시험용: 질기게
    w.order_attack(np.array(army), unit=a.unit)
    woke = subdued = False
    for _ in range(int(150 / 0.05)):
        w.update(0.05)
        woke |= a.mode == FIGHT
        if a.mode == SUBDUED:
            subdued = True
            break
    report('맞으면 깨어 싸우고, 체력이 깎이면 쓰러진다', woke and subdued, f'깸 {woke}, 쓰러짐 {subdued}, 체력 {a.hp:.2f}')
    report('쓰러진 동안은 맞지 않는다', bool(u.aboard[a.unit]))
    alive = [i for i in army if u.alive[i]]
    got = wild.order_tame(0, alive, a.id, quiet=True)
    tamer = next(i for i, t in wild.tamers.items() if t.aid == a.id)      # 가장 가까운 한 명이 간다
    for _ in range(int(30 / 0.05)):                                    # 날다가 떨어진 자리까지 걸어가 길들인다
        w.update(0.05)
        if u.kind[tamer] == R.DRAGON_RIDER:
            break
    report('길들이면 용기사', got == 1 and u.kind[tamer] == R.DRAGON_RIDER and a.id not in wild.animals,
           f'보낸 {got}, 종류 {u.kind[tamer]}')

    # 날아서 물 위로
    from scipy import ndimage
    home = (float(u.y[tamer]), float(u.x[tamer]))
    w.update(0.05)
    report('멈춰 있는 용기사는 땅에 내려앉아 있다', not u.air[tamer])
    water = np.argwhere(ndimage.binary_erosion(~gm.walk, iterations=3))      # 넓은 물 한가운데
    wy, wx = min(water, key=lambda p: (p[0] - u.y[tamer]) ** 2 + (p[1] - u.x[tamer]) ** 2)
    w.order_move(np.array([tamer]), float(wy) + 0.5, float(wx) + 0.5)
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if u.state[tamer] == IDLE:
            break
    over = not gm.walk[int(u.y[tamer]), int(u.x[tamer])]
    report('용기사는 날아서 물 위로 (물 위에선 떠 있다)', over and u.alive[tamer] and u.air[tamer], f'물 위 {over}, 날고 있음 {bool(u.air[tamer])}')

    # 나라마다 2기
    u.add(0, R.DRAGON_RIDER, float(wx), float(wy), R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    other = next((d for d in wild.animals.values() if d.unit >= 0), None)
    if other is not None:
        other.mode = SUBDUED
        n = wild.order_tame(0, [i for i in army if u.alive[i] and i != tamer], other.id, quiet=True)
        report('용기사는 나라마다 2기까지', n == 0)
    # 날고 있는 동안은 근접 병사가 못 친다
    foe = u.add(1, R.INFANTRY, float(u.x[tamer]) + 1, float(u.y[tamer]), 40.0)
    w.order_attack(np.array([foe]), unit=tamer)
    report('근접 병사는 날고 있는 용기사를 칠 수 없다', u.state[foe] in (IDLE, AMOVE) or u.tgt[foe] != tamer)
    u.alive[foe] = False
    # 땅으로 날아 돌아오는 동안은 날고, 멈추면 내려앉아 근접 병사에게도 맞는다
    w.order_move(np.array([tamer]), *home)
    w.update(0.05)
    flying = bool(u.air[tamer])
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if u.state[tamer] == IDLE and not u.air[tamer]:
            break
    landed = not u.air[tamer] and gm.walk[int(u.y[tamer]), int(u.x[tamer])]
    report('이동하는 동안은 날고, 멈추면 내려앉는다', flying and landed, f'이동 중 날기 {flying}, 내려앉음 {landed}')
    foe = u.add(1, R.INFANTRY, float(u.x[tamer]) + 1.5, float(u.y[tamer]), 40.0)
    w.order_attack(np.array([foe]), unit=tamer)
    report('내려앉은 용기사는 근접 병사에게도 맞는다', u.state[foe] == 3 and u.tgt[foe] == tamer)

    _skills(report, gm)
    _raid(report, gm)


def _skills(report, gm):
    """드래곤 기술: 눈보라 (몰린 곳에 던짐), 날아오르기 (쓰러질 때까지 날며 숨결), 날다가 쓰러지면 떨어진다, 아무도 없으면 내려앉는다."""
    import sim.wildlife as WL
    w = World(gm, 3, seed=3, map_seed=7)
    wild, u = w.wild, w.units
    a = [x for x in wild.animals.values() if x.unit >= 0][0]
    i = a.unit
    info = R.WILDLIFE[R.DRAGON]
    nova, fl = info['nova'], info['flight']
    maxhp = R.UNIT_STATS[R.WILD_DRAGON]['hp']

    def ring(r, n):
        pts = [(a.x + r * np.cos(t), a.y + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)]
        pts = [(x, y) for x, y in pts if gm.walk[int(y), int(x)]]
        return [pts[k % len(pts)] for k in range(n)]

    # 병사 넷이 몰린 곳 (드래곤에서 10칸)과 따로 떨어진 궁수 둘: 몰린 곳에 던진다
    cx0, cy0 = next(((x, y) for x, y in ring(10.0, 24)
                     if all(gm.walk[int(y + dy), int(x + dx)] for dx in (-1, 0, 1) for dy in (-1, 0, 1))), ring(10.0, 1)[0])
    inner = [u.add(0, R.INFANTRY, cx0 + dx, cy0 + dy, 400.0) for dx, dy in ((0, 0), (0.8, 0), (0, 0.8), (0.8, 0.8))]
    far_pts = [(x, y) for x, y in ring(10.0, 24) if np.hypot(x - cx0, y - cy0) > nova['r'] + 3]
    outer = [u.add(0, R.ARCHER, x, y, 400.0) for x, y in far_pts[:2]]   # 따로 떨어진 궁수 둘
    for j in inner + outer:
        u.hp[j] = 400.0
        u.freeze[j] = 999.0                                  # 시험용: 제자리를 지킨다 (치러 가서 흩어지지 않게)
    a.mode, u.own[i], a.nova_cd = WL.FIGHT, WL.WILD, 0.0
    u.hp[i] = maxhp * (nova['phase'] - 0.05)
    w.recent.clear()
    started, aimed, thrown, bursts, blast = False, None, False, [], False
    for _ in range(int((nova['wind'] + nova['fly'] + 1.0) / 0.05)):
        t0 = w.time
        w.update(0.05)
        new = [r for r in w.recent if r[0] > t0 - 1e-9]       # 이번 걸음의 공격 기록 (기록은 0.3초 뒤 지워진다)
        started |= a.mode == WL.NOVA
        if aimed is None and a.mode == WL.NOVA:
            aimed = (a.tx, a.ty)
        thrown |= any(r[5] == 13 for r in new)
        bursts += [r for r in new if r[5] == 10]
        blast |= any(r[5] == 14 for r in new)                 # 떨어진 곳 큰 폭발
        if thrown and not wild.bombs:
            break
    fin = [float(u.hp[j]) for j in inner]
    fout = [float(u.hp[j]) for j in outer]
    froze = bool((u.freeze[inner] > 0).all() and (u.freeze[inner] < 999).all())     # 눈보라로 얼었다 (시험용 묶음이 풀리고 freeze초)
    want = min(nova['dmg_frac'] * R.UNIT_STATS[R.INFANTRY]['hp'], nova['dmg_max'])     # 보병: 최대 체력의 65%
    on_cluster = aimed is not None and np.hypot(aimed[0] - (cx0 + 0.4), aimed[1] - (cy0 + 0.4)) < 1.0
    report('눈보라: 병사가 가장 많이 몰린 곳을 겨눠 던지고, 원 안의 병사마다 터진다 (최대 체력의 65%, 얼어붙는다)',
           started and on_cluster and thrown and blast and froze and len(bursts) >= len(inner)
           and all(abs((400 - v) - want) < 1.0 for v in fin) and all(v == 400 for v in fout),
           f'겨눈 곳 {None if aimed is None else (round(aimed[0], 1), round(aimed[1], 1))} (무리 {cx0 + 0.4:.1f}, {cy0 + 0.4:.1f}), '
           f'몰린 곳 {[round(v) for v in fin]} (잃음 {want:.0f}), 떨어진 곳 {[round(v) for v in fout]}, 얼음 {froze}')
    xy = [(float(u.x[j]), float(u.y[j])) for j in inner]
    w.order_move(np.array(inner), a.y + 30, a.x)
    w.update(0.5)
    still = all(abs(float(u.x[j]) - p[0]) < 1e-4 and abs(float(u.y[j]) - p[1]) < 1e-4 for j, p in zip(inner, xy))
    report('얼어붙은 병사는 움직이지 못한다', still)

    # 둘레에 바짝 붙은 병사들에게 밀리지 않는다 (뒷걸음질처럼 보이지 않게)
    for j in inner + outer:
        u.freeze[j] = 0.0
    a.mode, a.nova_cd = WL.FIGHT, 99.0
    u.hp[i] = maxhp * (fl['phase'] + 0.1)
    hug = [u.add(0, R.INFANTRY, float(u.x[i]) + dx, float(u.y[i]) + dy, 400.0) for dx, dy in ((0.5, 0.2), (0.4, -0.3), (0.6, 0.0))]
    for j in hug:
        u.hp[j] = 400.0
    w.order_attack(np.array(hug), unit=i)
    for _ in range(2):                                       # (하던 걸음을 마친다)
        w.update(0.05)
    gx0, gy0 = float(u.x[i]), float(u.y[i])
    for _ in range(20):
        w.update(0.05)
    report('땅에서 싸우는 드래곤은 바짝 붙은 병사에게 밀리지 않는다', np.hypot(u.x[i] - gx0, u.y[i] - gy0) < 1e-3,
           f'밀린 거리 {float(np.hypot(u.x[i] - gx0, u.y[i] - gy0)):.3f}')
    for j in hug:
        u.alive[j] = False

    # 3단계: 날아오른다 (근접 병사는 못 친다), 치고 빠진다: 병사들 반대쪽으로 궁수 사거리 밖까지 빠졌다가 돌아와 숨결
    for j in inner + outer:
        u.freeze[j] = 0.0
    a.mode, a.nova_cd = WL.FIGHT, 99.0
    u.hp[i] = maxhp * (fl['phase'] - 0.05)
    w.recent.clear()
    w.update(0.05)
    flying = a.mode == WL.FLY and bool(u.air[i])
    foe = inner[0]
    w.order_attack(np.array([foe]), unit=i)
    melee_off = u.state[foe] != 3 or u.tgt[foe] != i
    reach = R.UNIT_STATS[R.ARCHER]['range']
    breaths, escaped, back, away = 0, False, 0, []
    last_breath, slid = -9.0, 0                        # 숨결을 뿜은 뒤 hold초 안에 움직인 걸음 (뒷걸음질)
    for _ in range(int(20 / 0.05)):
        hp_keep = float(u.hp[i])
        t0 = w.time
        px0, py0 = float(u.x[i]), float(u.y[i])
        w.update(0.05)
        new = sum(1 for r in w.recent if r[0] > t0 - 1e-9 and r[5] == 3)   # 날며 뿜은 숨결 (기록은 0.3초 뒤 지워진다)
        breaths += new
        if w.time - last_breath < fl['hold'] - 0.06 and np.hypot(u.x[i] - px0, u.y[i] - py0) > 1e-4:
            slid += 1
        if new:
            last_breath = w.time
        live = [j for j in outer if u.alive[j]]
        if live and min(np.hypot(u.x[j] - u.x[i], u.y[j] - u.y[i]) for j in live) > reach:
            escaped = True                                  # 궁수 사거리 밖으로 빠졌다
        if escaped and new:
            back += 1                                       # 빠졌다가 돌아와 뿜었다
        if a.fph == WL.FLEE_P and a.ftm == 0.0 and live:   # 빠지기 시작: 빠질 곳이 병사들 가운데에서 드래곤보다 멀다 (반대쪽)
            mx, my = float(np.mean([u.x[j] for j in live])), float(np.mean([u.y[j] for j in live]))
            away.append(np.hypot(a.tx - mx, a.ty - my) >= np.hypot(a.x - mx, a.y - my) - 1e-3)
        u.hp[i] = max(u.hp[i], hp_keep)                    # 시험용: 날기를 끝까지 보게 (안 쓰러지게)
        if a.mode != WL.FLY:
            break
    still = a.mode == WL.FLY and bool(u.air[i])
    report('날아오르기 (체력 50% 아래): 병사들 반대쪽으로 궁수 사거리 밖까지 빠졌다가 돌아와 숨결, 근접 병사는 못 친다',
           flying and melee_off and breaths >= 3 and escaped and back >= 1 and away and all(away) and still and slid == 0,
           f'날기 {flying}, 근접 못 침 {melee_off}, 20초 숨결 {breaths}번, 사거리 밖 {escaped}, 돌아와 뿜음 {back}, 반대쪽으로 {sum(away)}/{len(away)}, 뿜는 동안 움직임 {slid}, 아직 남 {still}')
    # 날며 용기사에게도 눈보라 (혼자여도): 공중에 멈춰 모아 던진다, 맞으면 얼어붙는다
    rider = u.add(0, R.DRAGON_RIDER, float(u.x[i]) + 6.0, float(u.y[i]), R.UNIT_STATS[R.DRAGON_RIDER]['hp'])
    u.air[rider] = True
    for j in inner + outer:
        u.alive[j] = False
    a.nova_cd = 0.0
    if a.fph == WL.STRIKE_P:
        a.fph, a.ftm = WL.TURN_P, 0.0
    air_nova, rider_hit = False, False
    for _ in range(int(12 / 0.05)):
        hp_keep = float(u.hp[i])
        w.update(0.05)
        u.hp[i] = max(u.hp[i], hp_keep)
        air_nova |= a.mode == WL.AIR_NOVA and bool(u.air[i])
        if u.freeze[rider] > 0:
            rider_hit = True
            break
    report('날며 용기사에게도 눈보라를 던진다 (공중에 멈춰 모은다, 용기사도 얼어붙는다)', air_nova and rider_hit,
           f'공중 눈보라 {air_nova}, 용기사 맞음 {rider_hit}, 체력 {float(u.hp[rider]):.0f}')
    u.alive[rider] = False
    for j in inner + outer:
        u.alive[j] = True
    # 둘레에 아무도 없으면 내려앉는다
    for j in inner + outer:
        u.alive[j] = False
    for _ in range(int((fl['idle'] + 1.0) / 0.05)):
        w.update(0.05)
    report('둘레에 병사가 없으면 내려앉는다', a.mode != WL.FLY and not u.air[i], f'상태 {a.mode}')
    for j in inner + outer:
        u.alive[j] = True
    # 날다가 쓰러지면 땅으로 떨어진다
    a.mode = WL.FIGHT
    u.hp[i] = maxhp * (fl['phase'] - 0.05)
    w.update(0.05)
    u.hp[i] = maxhp * info['subdue'] - 1
    w.update(0.05)
    report('날다가 쓰러지면 땅으로 떨어진다', a.mode == WL.SUBDUED and not u.air[i], f'상태 {a.mode}, 날기 {bool(u.air[i])}')


def _raid(report, gm):
    """겨울 습격: every번째 겨울에 깨어 설원의 병사·건물을 친다 (거점은 빼고), 길들일 수 없다, 체력이 깎이면 둥지로 돌아가 잔다."""
    import sim.wildlife as WL
    from sim import tribes
    w = World(gm, 3, seed=3, map_seed=7)
    wild, u, b = w.wild, w.units, w.builds
    info = R.WILDLIFE[R.DRAGON]
    rd = info['raid']
    maxhp = R.UNIT_STATS[R.WILD_DRAGON]['hp']
    snow, _ = tribes.zones(gm)
    lr = wild.lairs[0]
    a = wild.animals[lr.aid]
    i = a.unit
    cx, cy = lr.x + 0.5, lr.y + 0.5
    cells = np.argwhere(snow & gm.walk)
    d = np.hypot(cells[:, 1] - cx, cells[:, 0] - cy)
    own0 = wild.raid_land()[cells[:, 0], cells[:, 1]] == 0
    far = cells[(d > 22) & (d < 35) & own0]                  # 둥지에서 22~35칸, 첫 둥지 몫 설원의 걸을 수 있는 칸
    hy, hx = far[0]
    fy, fx = min(far, key=lambda c: abs(np.hypot(c[1] - hx, c[0] - hy) - 12))   # 거점에서 12칸쯤 (첫 둥지 몫)
    hall = b.add(0, R.HALL, float(hx) + 0.5, float(hy) + 0.5, R.BUILD_STATS[R.HALL]['hp'], R.BUILD_STATS[R.HALL]['r'], prog=1.0)
    farm = b.add(0, R.FARM, float(fx) + 0.5, float(fy) + 0.5, R.BUILD_STATS[R.FARM]['hp'], R.BUILD_STATS[R.FARM]['r'], prog=1.0)
    hall_hp, farm_hp = float(b.hp[hall]), float(b.hp[farm])
    land = wild.raid_land()
    shares = [int((land == k).sum()) for k in range(len(wild.lairs))]
    near_ok = all(land[int(o.y), int(o.x)] in (k, -1) for k, o in enumerate(wild.lairs))
    from scipy import ndimage
    comp, _ = ndimage.label(snow, structure=np.ones((3, 3), bool))
    lair_c = {int(comp[int(o.y), int(o.x)]) for o in wild.lairs}
    joined = np.isin(comp, list(lair_c - {0}))
    report('습격 몫: 둥지와 이어진 설원만, 둥지마다 (가까운 쪽으로) 겹치지 않게 나눈다 (떨어진 설원은 빼고)',
           bool(((land >= 0) == joined).all()) and all(v > 0 for v in shares) and near_ok,
           f'둥지마다 칸 수 {shares}, 이어진 설원 {int(joined.sum())} / 설원 전체 {int(snow.sum())}')
    far_cell = None                                          # 첫 둥지 몫 중 둥지에서 가장 먼 설원 칸 (멀어도 이어져 있으면 친다)
    mine = np.argwhere((land == 0) & gm.walk)
    if len(mine):
        far_cell = mine[np.argmax(np.hypot(mine[:, 1] - cx, mine[:, 0] - cy))]
    other = np.argwhere((land == 1) & gm.walk) if len(wild.lairs) > 1 else np.zeros((0, 2), int)
    far_u = u.add(0, R.INFANTRY, float(far_cell[1]) + 0.5, float(far_cell[0]) + 0.5, 40.0) if far_cell is not None else -1
    oth_u = u.add(0, R.INFANTRY, float(other[0][1]) + 0.5, float(other[0][0]) + 0.5, 40.0) if len(other) else -1
    us1, _ = wild._raid_targets(lr)
    report('습격 대상: 제 몫이면 둥지에서 멀어도 (이어진 설원 끝까지), 다른 둥지 몫·떨어진 설원은 치지 않는다',
           far_u in us1 and oth_u not in us1, f'먼 칸까지 {float(np.hypot(far_cell[1] - cx, far_cell[0] - cy)) if far_cell is not None else 0:.0f}칸')
    for j in (far_u, oth_u):
        if j >= 0:
            u.alive[j] = False
    # 겨울이 온다: 남은 겨울 1번이면 이번 겨울에 나선다
    w.season_w = np.array([0.0, 0.0, 0.0, 1.0])
    wild.raid_wait, wild._winter = 1, False
    w.update(0.05)
    started = a.mode == WL.RAID and a.raid and bool(u.air[i])
    report('겨울이 오면 (every번째) 잠든 드래곤이 깨어 날아서 습격에 나선다', started, f'상태 {a.mode}, 날기 {bool(u.air[i])}')
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if not b.alive[farm]:
            break
    report('습격: 설원의 건물을 치고 거점은 치지 않는다', (not b.alive[farm] or b.hp[farm] < farm_hp) and b.hp[hall] >= hall_hp,
           f'농장 {float(b.hp[farm]):.0f}/{farm_hp:.0f} (남음 {bool(b.alive[farm])}), 거점 {float(b.hp[hall]):.0f}/{hall_hp:.0f}')
    # 습격 중 체력이 30% 아래: 쓰러지지 않고 (길들일 수 없다) 둥지로 돌아간다
    archers = [u.add(0, R.ARCHER, float(hx) + 2.5, float(hy) + 0.5, 26.0) for _ in range(3)]
    u.hp[i] = maxhp * info['subdue'] - 5
    w.update(0.05)
    home = a.mode == WL.HOMEWARD and a.raid
    report('습격 중엔 쓰러지지 않는다 (길들일 수 없다): 체력 30% 아래면 둥지로 돌아간다', home and a.mode != WL.SUBDUED, f'상태 {a.mode}')
    for _ in range(int(40 / 0.05)):
        w.update(0.05)
        if a.mode == WL.SLEEP:
            break
    back = a.mode == WL.SLEEP and not a.raid and not u.air[i] and np.hypot(u.x[i] - cx, u.y[i] - cy) < 0.5
    report('둥지로 돌아와 잔다 (체력을 heal까지 채운다)', back and u.hp[i] >= maxhp * rd['heal'] - 1,
           f'상태 {a.mode}, 둥지까지 {float(np.hypot(u.x[i] - cx, u.y[i] - cy)):.1f}, 체력 {float(u.hp[i]) / maxhp:.2f}')
    # 겨울이 끝나면 돌아간다
    for j in archers:
        u.alive[j] = False
    farm2 = b.add(0, R.FARM, float(fx) + 0.5, float(fy) + 0.5, R.BUILD_STATS[R.FARM]['hp'], R.BUILD_STATS[R.FARM]['r'], prog=1.0)
    assert wild.start_raid()
    for _ in range(30):                                      # 둥지를 떠나 날아간다
        w.update(0.05)
    w.season_w = np.array([1.0, 0.0, 0.0, 0.0])
    w.update(0.05)
    report('겨울이 끝나면 습격하던 드래곤은 둥지로 돌아간다', a.mode == WL.HOMEWARD, f'상태 {a.mode}')
    b.alive[farm2] = False

