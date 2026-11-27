"""사람 여럿 (server/session.py + sim/match.py): 판은 나라만 알고, 사람 자리마다 그 나라로만 명령하고 그 나라 것만 받는다.
- 사람이 맡을 나라는 무작위 (0번 고정 아님), 자리마다 start의 me가 그 나라.
- 내 명령은 내 병사에게만 (남의 병사를 넣어도 무시).
- 알림은 받는 나라에게만, 외교 요청은 상대 사람의 외교 상태에 들어오고 수락하면 동맹.
- 진 사람은 관전 (패배를 받고 판은 계속), 나라가 하나만 남으면 판 끝 (남은 사람이 승리, 상태 메시지 flags에 4).
- 사람이 2명 이상이면 속도·일시정지가 먹지 않는다.
- 끊기면 다른 사람에게 접속 상태(seats)가 가고, 돌아오면 풀린다. 항복하면 나라가 허물어지고 관전.
- 모두 메뉴로 스스로 나가면 판을 바로 지운다 (끊긴 사람이 있으면 기다린다).
- 대화는 판의 모든 사람에게, 너무 빨리 보내면 막는다.
"""
import numpy as np

from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from server.config import ServerConfig
from server.session import FLAGS_AT, GameSession


def run(report, cache_dir='.cache'):
    cfg = default_config(512, 7)
    scene = TerrainScene.load(cfg, cache_dir, progress=lambda s: None)
    scene.config = cfg                                         # 서버의 지도 장면처럼 (server/maps.py)
    got = [[], []]
    sends = [got[0].append, got[1].append]
    gs = GameSession(scene, {'bots': 2, 'players': [{'name': '가', 'color': 0}, {'name': '나', 'color': 3}]}, sends, ServerConfig())
    w, m = gs.world, gs.match
    a, b = gs.seats[0].nid, gs.seats[1].nid
    starts = [next(x for x in g if isinstance(x, dict) and x.get('t') == 'start') for g in got]
    report('사람 자리마다 다른 나라 (start의 me), 이름·색도 그 나라에',
           a != b and starts[0]['me'] == a and starts[1]['me'] == b and w.nations[a].name == '가' and w.nations[b].name == '나'
           and len(w.nations) == 4 and m.humans == {a, b}, f'가 → {a}, 나 → {b}')

    # 개발 명령 (` 콘솔): 사람이 여럿인 판에서는 --dev 서버가 아니면 받지 않는다 (혼자 하는 판은 배포 서버에서도 받는다)
    res0 = list(w.nations[a].res)
    gs.submit({'t': 'dev', 'cmd': 'res', 'add': [5000, 5000, 5000, 0]}, seat=0)
    gs.step(0.05, 0)
    report('개발 명령: 멀티 판에서는 --dev 서버가 아니면 콘솔도 명령도 없다',
           gs.cfg.dev or (not starts[0]['dev'] and w.nations[a].res[0] < res0[0] + 1000), f"dev {starts[0]['dev']}, 식량 {res0[0]:.0f} → {w.nations[a].res[0]:.0f}")

    # 명령: 가가 나의 병사를 움직이려 하면 무시, 자기 병사는 움직인다
    u = w.units
    ua = [[int(i), int(u.gen[i])] for i in w.unit_ids(a)[:2]]
    ub = [[int(i), int(u.gen[i])] for i in w.unit_ids(b)[:2]]
    pb = (u.x[w.unit_ids(b)[:2]].copy(), u.y[w.unit_ids(b)[:2]].copy())
    hx, hy = float(u.x[ua[0][0]]) + 6, float(u.y[ua[0][0]])
    gs.submit({'t': 'command', 'units': ua + ub, 'x': hx, 'y': hy}, seat=0)
    for k in range(40):
        gs.step(0.05, k)
    moved_a = any(u.state[i] != 0 or abs(u.x[i] - hx) < 3 for i, _ in ua)
    still_b = np.allclose(u.x[w.unit_ids(b)[:2]], pb[0], atol=1.0) and np.allclose(u.y[w.unit_ids(b)[:2]], pb[1], atol=1.0)
    report('명령은 그 자리의 나라 병사에게만', bool(moved_a and still_b))

    # 알림: 받는 나라에게만
    for g in got:
        g.clear()
    w.say('가에게만', to=a)
    w.say('모두에게')
    gs.step(0.05, 0)
    msgs = [sum((x['items'] for x in g if isinstance(x, dict) and x.get('t') == 'msg'), []) for g in got]
    report('알림은 받는 나라에게만', '가에게만' in msgs[0] and '가에게만' not in msgs[1] and '모두에게' in msgs[0] and '모두에게' in msgs[1], str(msgs))

    # 외교: 가 → 나 동맹 요청, 나의 외교 상태에 들어오고, 수락하면 동맹
    gs.submit({'t': 'diplo', 'act': 'request', 'to': b}, seat=0)
    gs.step(0.05, 0)
    dip = [x for x in got[1] if isinstance(x, dict) and x.get('t') == 'diplo']
    incoming = bool(dip) and a in dip[-1]['incoming']
    gs.submit({'t': 'diplo', 'act': 'reply', 'to': a, 'accept': True}, seat=1)
    gs.step(0.05, 0)
    report('사람끼리 동맹 요청 → 상대 화면에 요청 → 수락하면 동맹', incoming and w.diplo.allied(a, b))

    # 속도·일시정지: 사람이 2명 이상이면 먹지 않는다
    gs.submit({'t': 'speed', 'value': 4}, seat=0)
    gs.submit({'t': 'pause', 'on': True}, seat=1)
    t0 = w.time
    gs.step(0.05, 0)
    report('사람이 2명 이상이면 속도·일시정지 없음', abs(w.time - t0 - 0.05) < 1e-6 and not gs.solo)

    # 대화: 판의 모든 사람에게 (보낸 사람도), 너무 빨리 보내면 막는다
    for g in got:
        g.clear()
    gs.submit({'t': 'chat', 'text': '  안녕하세요  '}, seat=0)
    gs.submit({'t': 'chat', 'text': '또'}, seat=0)
    gs.step(0.05, 0)
    chats = [[x for x in g if isinstance(x, dict) and x.get('t') == 'chat'] for g in got]
    slow = any(isinstance(x, dict) and x.get('t') == 'error' for x in got[0])
    report('대화는 모든 사람에게 (제어 문자 빼고), 너무 빨리 보내면 막는다',
           [c['text'] for c in chats[1]] == ['안녕하세요'] and chats[0] == chats[1] and chats[1][0]['from'] == a and slow, str(chats))

    # 나가 끊겼다 → 가에게 접속 상태 (seats), 돌아오면 풀린다
    seats = lambda: [x for x in got[0] if isinstance(x, dict) and x.get('t') == 'seats']
    got[0].clear()
    gs.detach(1)
    gs.step(0.05, 0)
    away = seats()
    gs.attach(got[1].append, 1)
    gs.step(0.05, 0)
    report('끊기면 다른 사람에게 접속 상태, 돌아오면 풀린다',
           bool(away) and away[-1]['away'] == [b] and seats()[-1]['away'] == [], str(seats()))

    # 나가 항복: 나라가 허물어지고 패배를 받고 관전, 판은 계속 (가에게 항복 알림)
    for g in got:
        g.clear()
    gs.submit({'t': 'surrender'}, seat=1)
    for k in range(12):                                      # 망한 나라 정리는 0.5초마다
        gs.step(0.05, k)
    over_b = [x for x in got[1] if isinstance(x, dict) and x.get('t') == 'over']
    over_a = [x for x in got[0] if isinstance(x, dict) and x.get('t') == 'over']
    told = any('항복했습니다' in t for x in got[0] if isinstance(x, dict) and x.get('t') == 'msg' for t in x['items'])
    report('항복하면 나라가 허물어지고 패배 · 관전 (판은 계속, 다른 사람에게 알림)',
           bool(over_b) and over_b[0]['result'] == '패배' and not over_a and not m.over and b in m.lost and told
           and not w.nations[b].alive and len(w.unit_ids(b)) == 0)

    # AI도 모두 망하면 가만 남는다: 판 끝, 가가 승리 (상태 메시지 flags에 4)
    for n in w.nations:
        if n.id != a:
            u.alive[w.unit_ids(n.id)] = False
            w.builds.alive[w.building_ids(n.id)] = False
    w._census()
    for g in got:
        g.clear()
    gs.step(0.05, 0)
    st = [x for x in got[0] if isinstance(x, (bytes, bytearray))]
    over_a = [x for x in got[0] if isinstance(x, dict) and x.get('t') == 'over']
    report('나라가 하나만 남으면 판 끝, 남은 사람이 승리',
           m.over and w.winner == a and bool(over_a) and over_a[0]['result'] == '승리' and bool(st) and st[-1][FLAGS_AT] & 4 == 4,
           f'남은 나라 {w.winner}')

    # 판 삭제: 모두 메뉴로 스스로 나갔으면 바로 (abandoned), 한 명이라도 끊긴 것이면 기다린다
    gs.submit({'t': 'leave'}, seat=0)
    gs.detach(0)
    gs.detach(1)
    waits = not gs.abandoned
    gs.submit({'t': 'leave'}, seat=1)
    report('모두 스스로 나가면 판을 바로 지우고, 끊긴 사람이 있으면 기다린다', waits and gs.abandoned)
    gs.stop()
