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
    army = [u.add(0, R.ARCHER if k % 3 == 0 else R.INFANTRY, *spots[k % len(spots)], 9999.0) for k in range(18)]
    for i in army:
        u.hp[i] = R.UNIT_STATS[int(u.kind[i])]['hp'] * 3                  # 시험용: 질기게
    w.order_attack(np.array(army), unit=a.unit)
    woke = subdued = False
    for _ in range(int(60 / 0.05)):
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
    for _ in range(int(19 / 0.05)):
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
    started, aimed, thrown, bursts = False, None, False, []
    for _ in range(int((nova['wind'] + nova['fly'] + 1.0) / 0.05)):
        t0 = w.time
        w.update(0.05)
        new = [r for r in w.recent if r[0] > t0 - 1e-9]       # 이번 걸음의 공격 기록 (기록은 0.3초 뒤 지워진다)
        started |= a.mode == WL.NOVA
        if aimed is None and a.mode == WL.NOVA:
            aimed = (a.tx, a.ty)
        thrown |= any(r[5] == 13 for r in new)
        bursts += [r for r in new if r[5] == 10]
        if thrown and not wild.bombs:
            break
    fin = [float(u.hp[j]) for j in inner]
    fout = [float(u.hp[j]) for j in outer]
    froze = bool((u.freeze[inner] > 0).all() and (u.freeze[inner] < 999).all())     # 눈보라로 얼었다 (시험용 묶음이 풀리고 freeze초)
    want = min(nova['dmg_frac'] * R.UNIT_STATS[R.INFANTRY]['hp'], nova['dmg_max'])     # 보병: 최대 체력의 65%
    on_cluster = aimed is not None and np.hypot(aimed[0] - (cx0 + 0.4), aimed[1] - (cy0 + 0.4)) < 1.0
    report('눈보라: 병사가 가장 많이 몰린 곳을 겨눠 던지고, 원 안의 병사마다 터진다 (최대 체력의 65%, 얼어붙는다)',
           started and on_cluster and thrown and froze and len(bursts) >= len(inner)
           and all(abs((400 - v) - want) < 1.0 for v in fin) and all(v == 400 for v in fout),
           f'겨눈 곳 {None if aimed is None else (round(aimed[0], 1), round(aimed[1], 1))} (무리 {cx0 + 0.4:.1f}, {cy0 + 0.4:.1f}), '
           f'몰린 곳 {[round(v) for v in fin]} (잃음 {want:.0f}), 떨어진 곳 {[round(v) for v in fout]}, 얼음 {froze}')
    xy = [(float(u.x[j]), float(u.y[j])) for j in inner]
    w.order_move(np.array(inner), a.y + 30, a.x)
    w.update(0.5)
    still = all(abs(float(u.x[j]) - p[0]) < 1e-4 and abs(float(u.y[j]) - p[1]) < 1e-4 for j, p in zip(inner, xy))
    report('얼어붙은 병사는 움직이지 못한다', still)

    # 3단계: 날아오른다 (근접 병사는 못 친다), 숨결 줄, 내려앉아 지침 (받는 피해 더)
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
    breaths = 0
    for _ in range(int(20 / 0.05)):
        hp_keep = float(u.hp[i])
        t0 = w.time
        w.update(0.05)
        breaths += sum(1 for r in w.recent if r[0] > t0 - 1e-9 and r[5] == 3)   # 날며 뿜은 숨결 (기록은 0.3초 뒤 지워진다)
        u.hp[i] = max(u.hp[i], hp_keep)                    # 시험용: 날기를 끝까지 보게 (안 쓰러지게)
        if a.mode != WL.FLY:
            break
    still = a.mode == WL.FLY and bool(u.air[i])
    report('날아오르기 (체력 50% 아래): 쓰러질 때까지 둥지를 돌며 날고 숨결을 뿜는다, 근접 병사는 못 친다',
           flying and melee_off and breaths >= 3 and still, f'날기 {flying}, 근접 못 침 {melee_off}, 20초 날며 숨결 {breaths}번, 아직 남 {still}')
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
