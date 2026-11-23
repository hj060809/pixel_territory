"""멀티 플레이 방 (server/rooms.py, server/app.py의 /ws): 브라우저 둘을 흉내 낸다.
- 방 만들기 → 목록에 보인다 → 코드로 들어가기 (색이 겹치면 다른 색으로) → 비밀번호가 틀리면 못 들어간다.
- 모두 준비해야 시작 → 시작하면 둘 다 start (서로 다른 나라, 사람 2명), 그다음 상태 메시지.
- 한쪽이 끊기면 다른 쪽에 알림, 같은 판의 같은 자리로 다시 접속 (sid + token, /api/resume으로 먼저 확인).
- 판이 끝나면 대기실로 (room_back): 처음 돌아온 사람이 방장, 다른 사람도 들어와 다시 시작.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

PORT = 8791
ROOT = Path(__file__).resolve().parent.parent


class _Ws:
    """websockets 동기 연결을 시험에 맞게 (보내기 = JSON, 받기 = 텍스트/바이트)."""

    def __init__(self, url):
        self.c = connect(url, max_size=None)

    def send_text(self, t):
        self.c.send(t)

    def receive(self):
        m = self.c.recv(timeout=30)
        return {'bytes': m} if isinstance(m, (bytes, bytearray)) else {'text': m}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.c.close()


def _recv(ws, want, limit=6000):
    """want(메시지 dict)가 참인 JSON 메시지가 올 때까지 읽는다 (상태 메시지는 건너뛴다)."""
    for _ in range(limit):
        m = ws.receive()
        if m.get('text'):
            d = json.loads(m['text'])
            if want(d):
                return d
    raise AssertionError('기다린 메시지가 오지 않았습니다')


def _get(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}{path}', timeout=30) as r:
        return json.loads(r.read())


def run(report):
    srv = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(PORT)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            try:
                _get('/api/maps')
                break
            except OSError:
                time.sleep(0.3)
        _run(report)
    finally:
        srv.terminate()


def _run(report):
    url = f'ws://127.0.0.1:{PORT}/ws'
    key = _get('/api/maps')['demo'][0]['key']
    with _Ws(url) as a:
        a.send_text(json.dumps({'t': 'room_create', 'name': '시험 방', 'password': 'abc', 'cap': 2, 'bots': 1,
                                'start_mode': 'random', 'setup': {'map': key}, 'player': {'name': '가', 'color': 0}}))
        ra = _recv(a, lambda d: d.get('t') == 'room')
        listed = any(r['id'] == ra['id'] and r['locked'] for r in _get('/api/rooms'))
        with _Ws(url) as bad:
            bad.send_text(json.dumps({'t': 'room_join', 'code': ra['code'], 'password': 'x', 'player': {'name': '다'}}))
            wrong = _recv(bad, lambda d: d.get('t') == 'room_error')
        report('방 만들기 → 목록에 보인다, 비밀번호가 틀리면 못 들어간다', listed and '비밀번호' in wrong['error'], wrong['error'])
        with _Ws(url) as b:
            b.send_text(json.dumps({'t': 'room_join', 'code': ra['code'].lower(), 'password': 'abc', 'player': {'name': '나', 'color': 0}}))
            rb = _recv(b, lambda d: d.get('t') == 'room')
            colors = [m['color'] for m in rb['members']]
            report('코드로 들어가기 (색이 겹치면 다른 색), 무작위 배치를 보여 준다',
                   rb['me'] == 1 and len(set(colors)) == 2 and rb['layout'] is not None and len(rb['layout']) == 3,
                   f'색 {colors}, 배치 {rb["layout"]}')
            a.send_text(json.dumps({'t': 'room_start'}))
            early = _recv(a, lambda d: d.get('t') == 'room_error')
            b.send_text(json.dumps({'t': 'room_ready', 'on': True}))
            _recv(a, lambda d: d.get('t') == 'room' and d['members'][1]['ready'])
            a.send_text(json.dumps({'t': 'room_start'}))
            sa = _recv(a, lambda d: d.get('t') == 'start')
            sb = _recv(b, lambda d: d.get('t') == 'start')
            got_state = b.receive().get('bytes') is not None or b.receive().get('bytes') is not None
            report('모두 준비해야 시작, 시작하면 둘 다 판으로 (서로 다른 나라, 사람 2명)',
                   '준비' in early['error'] and sa['me'] != sb['me'] and sa['humans'] == 2 and len(sa['nations']) == 3
                   and sa['sid'] == sb['sid'] and got_state, f'가 → {sa["me"]}, 나 → {sb["me"]}')
            b.send_text(json.dumps({'t': 'diplo', 'act': 'request', 'to': sa['me']}))
            req = _recv(a, lambda d: d.get('t') == 'diplo' and sb['me'] in d.get('incoming', []))
            report('판 안에서 사람끼리 외교 (나의 동맹 요청이 가에게)', req is not None)
        # 나가 끊겼다: 가에게 알림
        away = _recv(a, lambda d: d.get('t') == 'msg' and any('연결이 끊겼습니다' in x for x in d['items']))
        can = _get(f'/api/resume?sid={sb["sid"]}&token={sb["token"]}')
        with _Ws(url) as b2:
            b2.send_text(json.dumps({'t': 'resume', 'sid': sb['sid'], 'token': sb['token']}))
            back = _recv(b2, lambda d: d.get('t') in ('start', 'error'))
        report('끊기면 다른 사람에게 알림, 같은 자리로 다시 접속', away is not None and can['ok'] and can['map'] == key
               and back.get('t') == 'start' and back['me'] == sb['me'], f'{can} {back.get("t")} {back.get("me")}')
    _again(report, url, key)


def _again(report, url, key):
    """사람 둘·AI 없는 방: 나가 항복 → 판 끝 → 둘 다 대기실로 돌아와 다시 시작."""
    with _Ws(url) as a, _Ws(url) as b:
        a.send_text(json.dumps({'t': 'room_create', 'name': '두 번', 'cap': 2, 'bots': 0, 'start_mode': 'random',
                                'setup': {'map': key}, 'player': {'name': '가', 'color': 0}}))
        ra = _recv(a, lambda d: d.get('t') == 'room')
        b.send_text(json.dumps({'t': 'room_join', 'code': ra['code'], 'player': {'name': '나', 'color': 1}}))
        _recv(b, lambda d: d.get('t') == 'room')
        b.send_text(json.dumps({'t': 'room_ready', 'on': True}))
        _recv(a, lambda d: d.get('t') == 'room' and len(d['members']) == 2 and d['members'][1]['ready'])
        a.send_text(json.dumps({'t': 'room_start'}))
        sa = _recv(a, lambda d: d.get('t') == 'start')
        _recv(b, lambda d: d.get('t') == 'start')
        b.send_text(json.dumps({'t': 'surrender'}))
        oa = _recv(a, lambda d: d.get('t') == 'over')
        _recv(b, lambda d: d.get('t') == 'over')
        a.send_text(json.dumps({'t': 'room_back'}))
        r1 = _recv(a, lambda d: d.get('t') in ('room', 'room_error'))
        listed = any(r['id'] == ra['id'] for r in _get('/api/rooms'))
        b.send_text(json.dumps({'t': 'room_back'}))
        r2 = _recv(b, lambda d: d.get('t') in ('room', 'room_error'))
        b.send_text(json.dumps({'t': 'room_ready', 'on': True}))
        _recv(a, lambda d: d.get('t') == 'room' and len(d['members']) == 2 and d['members'][1]['ready'])
        a.send_text(json.dumps({'t': 'room_start'}))
        s2a = _recv(a, lambda d: d.get('t') in ('start', 'room_error'))
        s2b = _recv(b, lambda d: d.get('t') in ('start', 'room_error'))
        report('항복으로 판 끝 → 대기실로 돌아와 (처음 온 사람이 방장) 다시 시작',
               oa['result'] == '승리' and r1.get('t') == 'room' and r1['state'] == 'wait' and r1['me'] == r1['host'] == 0 and listed
               and r2.get('t') == 'room' and r2['me'] == 1 and s2a.get('t') == 'start' and s2b.get('t') == 'start'
               and s2a['sid'] != sa['sid'], f'{oa} {r1.get("t")} {r2.get("t")} {s2a.get("t")}')
