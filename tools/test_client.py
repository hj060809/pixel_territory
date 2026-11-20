"""서버 시험 클라이언트 (브라우저 대신): 서버를 띄우고 한 판을 진행하며 지연·대역폭·서버 계산 시간을 잰다.

python tools/test_client.py [--port 8765] [--seconds 30]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
from server.protocol import decode  # noqa: E402


def http(port, path, body=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method='POST' if body is not None else 'GET',
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
        return data if path.endswith(('.tsb', '.png')) else json.loads(data)


class ClientState:
    """받은 상태 메시지로 화면 쪽 상태를 맞춰 간다 (웹 클라이언트가 할 일과 같다)."""

    def __init__(self):
        self.units, self.builds, self.boats, self.nations = {}, {}, [], None
        self.tick = 0

    def apply(self, m):
        self.tick = m['tick']
        for u in m['units']:
            self.units[int(u['slot'])] = u
        for s in m['units_gone']:
            self.units.pop(int(s), None)
        for b in m['builds']:
            self.builds[int(b['slot'])] = b
        for s in m['builds_gone']:
            self.builds.pop(int(s), None)
        self.boats = m['boats']
        if 'nations' in m:
            self.nations = m['nations']


async def play(port, key, seconds, log):
    from websockets.asyncio.client import connect
    st = ClientState()
    sizes, sims, gaps = [], [], []
    async with connect(f'ws://127.0.0.1:{port}/ws', compression=None, max_size=None) as ws:
        t_join = time.perf_counter()
        await ws.send(json.dumps({'t': 'join', 'map': key, 'options': {'bots': 4, 'color': 2, 'name': '시험',
                                                                       'difficulty': '보통', 'season': 0}}))
        info = None
        while info is None:
            m = json.loads(await ws.recv())
            if m['t'] == 'start':
                info = m
            elif m['t'] == 'error':
                raise RuntimeError(m)
        log(f'판 시작까지 {time.perf_counter() - t_join:.2f}초 — 나라 {[n["name"] for n in info["nations"]]}, 자원지 {len(info["sites"])}개')

        async def recv_until(cond, timeout=5.0):
            end = time.perf_counter() + timeout
            last = time.perf_counter()
            while time.perf_counter() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(end - time.perf_counter(), 0.001))
                except TimeoutError:
                    return None
                now = time.perf_counter()
                if isinstance(raw, bytes):
                    m = decode(raw)
                    st.apply(m)
                    sizes.append(len(raw))
                    sims.append(m['sim_ms'])
                    gaps.append(now - last)
                    last = now
                    if cond('state', m):
                        return now
                else:
                    j = json.loads(raw)
                    if j['t'] == 'msg':
                        log('   알림: ' + ' / '.join(j['items']))
                    elif j['t'] == 'error':
                        log(f'   서버 오류: {j["error"]}')
                    if cond('json', j):
                        return now
            return None

        t_first = await recv_until(lambda k, m: k == 'state', 10.0)
        log(f'첫 상태 메시지까지 {1000 * (t_first - t_join):.0f} ms (판 시작 포함)')
        await recv_until(lambda k, m: False, 1.0)
        mine = [(s, int(u['gen'])) for s, u in st.units.items() if u['own'] == 0]
        log(f'내 병사 {len(mine)}명, 건물 {sum(b["own"] == 0 for b in st.builds.values())}채')
        # 1) 오른쪽 클릭: 가장 가까운 식량 자원지 → 짓기 + 나머지 곁 지키기
        ux = np.mean([st.units[s]['x'] for s, _ in mine]) / 64
        uy = np.mean([st.units[s]['y'] for s, _ in mine]) / 64
        food = min((s for s in info['sites'] if s['kind'] == 0), key=lambda s: (s['x'] - ux) ** 2 + (s['y'] - uy) ** 2)
        t0 = time.perf_counter()
        await ws.send(json.dumps({'t': 'command', 'id': 1, 'units': mine, 'ships': [], 'x': food['x'], 'y': food['y'],
                                  'attack': False, 'r': 3}))
        t_ack = await recv_until(lambda k, m: k == 'json' and m['t'] == 'ack')
        t_move = await recv_until(lambda k, m: k == 'state' and any(
            int(u['slot']) in dict(mine) and u['state'] != 0 for u in m['units']))
        log(f'명령 → 확인(ack) {1000 * (t_ack - t0):.0f} ms, 병사가 움직이기 시작한 상태가 오기까지 {1000 * (t_move - t0):.0f} ms')
        # 2) 훈련: 보병 둘
        await ws.send(json.dumps({'t': 'train', 'kind': 'infantry', 'buildings': []}))
        await ws.send(json.dumps({'t': 'train', 'kind': 'infantry', 'buildings': []}))
        await recv_until(lambda k, m: k == 'state' and any(b['own'] == 0 and b['qlen'] >= 2 for b in m['builds']), 2.0)
        q = max((b['qlen'] for b in st.builds.values() if b['own'] == 0), default=0)
        log(f'훈련 대기열 {q} (2면 정상)')
        # 3) 4배속으로 한동안
        await ws.send(json.dumps({'t': 'speed', 'value': 4}))
        sizes.clear(), sims.clear(), gaps.clear()
        t_run = time.perf_counter()
        await recv_until(lambda k, m: False, seconds)
        el = time.perf_counter() - t_run
        n_units = len(st.units)
        log(f'{seconds}초 (4배속): 상태 {len(sizes)}개 = 초당 {len(sizes) / el:.1f}개, 평균 {np.mean(sizes):.0f} B, 최대 {max(sizes)} B, '
            f'초당 {sum(sizes) / el / 1024:.1f} KB (병사 {n_units}명)')
        log(f'   서버 걸음 계산 평균 {np.mean(sims):.2f} ms, 최대 {max(sims):.2f} ms / 상태 간격 평균 {1000 * np.mean(gaps):.0f} ms, '
            f'최대 {1000 * max(gaps):.0f} ms')
        if st.nations:
            log(f'   나라: ' + ', '.join(f'{n["name"]} 병사 {nat[6]} 건물 {nat[7]}' for n, nat in zip(info['nations'], st.nations)))
        # 4) 같은 지도로 새 판
        await ws.send(json.dumps({'t': 'restart'}))
        t_r = time.perf_counter()
        await recv_until(lambda k, m: k == 'json' and m['t'] == 'start')
        log(f'새 판 {1000 * (time.perf_counter() - t_r):.0f} ms')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--seconds', type=float, default=30)
    args = p.parse_args()
    log = lambda s: print(s, flush=True)
    srv = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(args.port)], cwd=WEB,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                listing = http(args.port, '/api/maps')
                break
            except OSError:
                time.sleep(0.3)
        log(f'서버 켜짐. 데모 지도 {[m["name"] for m in listing["demo"]]}, 크기 {listing["sizes"]}')
        demo = listing['demo'][0]['key']
        t0 = time.perf_counter()
        blob = http(args.port, f'/api/maps/{demo}/bundle.tsb')
        log(f'지도 묶음 받기 {len(blob) / 1e6:.2f} MB, {1000 * (time.perf_counter() - t0):.0f} ms (같은 컴퓨터)')
        # 크기 상한
        r = http(args.port, '/api/maps', {'preset': None, 'size': 640, 'seed': 1})
        log(f'640 요청 → {r["state"]}: {r.get("error")}')
        # 직접 입력한 시드 (글자도 된다)
        t0 = time.perf_counter()
        r = http(args.port, '/api/maps', {'preset': 'island_arc', 'size': 384, 'seed': '들판의 깃발'})
        key = r['key']
        last = None
        while r['state'] != 'ready':
            if r.get('progress') != last:
                last = r.get('progress')
                log(f'   지도 만들기: {r["state"]} {last or ""}')
            if r['state'] == 'error':
                raise RuntimeError(r)
            time.sleep(0.5)
            r = http(args.port, f'/api/maps/{key}/status')
        log(f'직접 입력한 시드 지도 {key} 준비 {time.perf_counter() - t0:.1f}초')
        t0 = time.perf_counter()
        lay = http(args.port, f'/api/maps/{demo}/layout?bots=4&color=2')
        log(f'시작 배치 미리보기 {lay["starts"]}, 색 {lay["colors"]} ({1000 * (time.perf_counter() - t0):.0f} ms)')
        asyncio.run(play(args.port, demo, args.seconds, log))
        log('끝')
    finally:
        srv.terminate()


if __name__ == '__main__':
    main()
