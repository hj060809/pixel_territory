"""서버 부하·안정성 시험: 서버를 띄우고 판 N개를 동시에 돌리며 상태 간격, 서버 걸음 시간, 서버 메모리를 잰다.

python tools/load_test.py --sessions 4 --seconds 120 --speed 4          # 동시 판 수
python tools/load_test.py --sessions 1 --seconds 3600 --report 300      # 한 시간 연속 (5분마다 보고, 판이 끝나면 새 판)
python tools/load_test.py --sessions 1 --seconds 30 --resume            # 중간에 끊었다가 같은 판에 다시 접속

판마다 내 병사들을 가끔 가장 가까운 자원지로 보내고 (명령 처리도 섞이게), AI 4나라와 함께 돌린다.
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
from server.protocol import POS, decode  # noqa: E402


def rss_mb(pid) -> float:
    """프로세스 메모리 (MB, Windows tasklist)."""
    try:
        out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], capture_output=True,
                             text=True, encoding='cp949', errors='replace').stdout
        return float(out.strip().split('","')[-1].strip('" K').replace(',', '').replace('\xa0', '')) / 1024
    except (ValueError, IndexError):
        return float('nan')


class Stats:
    def __init__(self):
        self.gaps, self.sims, self.sizes = [], [], []

    def reset(self):
        self.gaps.clear(), self.sims.clear(), self.sizes.clear()

    def line(self) -> str:
        if not self.gaps:
            return '상태 없음'
        g, s = np.array(self.gaps) * 1000, np.array(self.sims)
        return (f'상태 간격 평균 {g.mean():.0f} / p99 {np.percentile(g, 99):.0f} / 최대 {g.max():.0f} ms (100 ms 넘음 {int((g > 100).sum())}), '
                f'서버 걸음 평균 {s.mean():.1f} / p99 {np.percentile(s, 99):.1f} / 최대 {s.max():.1f} ms, '
                f'평균 {np.mean(self.sizes):.0f} B')


async def play(port, key, seconds, speed, stats: Stats, idx, resume=False, log=print):
    from websockets.asyncio.client import connect
    url = f'ws://127.0.0.1:{port}/ws'
    end = time.perf_counter() + seconds
    units, rounds, sid, info = {}, 0, None, None
    ws = await connect(url, compression=None, max_size=None)
    await ws.send(json.dumps({'t': 'join', 'map': key, 'options': {'bots': 4, 'color': idx % 7}}))
    last, cmd_at, resumed_ok = None, time.perf_counter() + 3, None
    cut_at = time.perf_counter() + seconds / 2 if resume else None
    try:
        while time.perf_counter() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except TimeoutError:
                log(f'  [판 {idx}] 5초 동안 아무것도 오지 않음')
                continue
            now = time.perf_counter()
            if isinstance(raw, bytes):
                m = decode(raw)
                for u in m['units']:
                    units[int(u['slot'])] = u
                for s in m['units_gone']:
                    units.pop(int(s), None)
                if last is not None:
                    stats.gaps.append(now - last)
                last = now
                stats.sims.append(m['sim_ms'])
                stats.sizes.append(len(raw))
                if now > cmd_at:                    # 내 병사를 가끔 움직인다
                    cmd_at = now + 8
                    mine = [[s, int(u['gen'])] for s, u in units.items() if u['own'] == 0]
                    if mine and info:
                        site = info['sites'][int(np.random.randint(len(info['sites'])))]
                        await ws.send(json.dumps({'t': 'command', 'units': mine, 'ships': [], 'x': site['x'],
                                                  'y': site['y'], 'attack': True, 'r': 3}))
                if cut_at and now > cut_at:         # 끊었다가 같은 판에 다시 접속
                    cut_at = None
                    n_before = len(units)
                    await ws.close()
                    await asyncio.sleep(2.0)
                    t0 = time.perf_counter()
                    ws = await connect(url, compression=None, max_size=None)
                    await ws.send(json.dumps({'t': 'resume', 'sid': sid}))
                    units.clear()
                    last = None
                    resumed_ok = (n_before, t0)
            else:
                j = json.loads(raw)
                if j['t'] == 'start':
                    info, sid = j, j['sid']
                    if j.get('resumed') and resumed_ok:
                        n_before, t0 = resumed_ok
                        await ws.send(json.dumps({'t': 'speed', 'value': speed}))
                        first = decode(await ws.recv())
                        log(f'  [판 {idx}] 다시 접속: {1000 * (time.perf_counter() - t0):.0f} ms 만에 이어 감, '
                            f'끊기 전 병사 {n_before}명 → 다시 받은 병사 {len(first["units"])}명 (한 번에 전체 상태)')
                        for u in first['units']:
                            units[int(u['slot'])] = u
                        resumed_ok = True
                        continue
                    rounds += 1
                    units.clear()
                    await ws.send(json.dumps({'t': 'speed', 'value': speed}))
                elif j['t'] == 'over':
                    await ws.send(json.dumps({'t': 'restart'}))
                elif j['t'] == 'error':
                    log(f'  [판 {idx}] 서버 오류: {j["error"]}')
                    if j.get('fatal'):
                        return rounds, resumed_ok
    finally:
        await ws.close()
    return rounds, resumed_ok


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8790)
    p.add_argument('--sessions', type=int, default=1)
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--speed', type=float, default=4)
    p.add_argument('--map', default='default-512-8767564')
    p.add_argument('--report', type=float, default=0, help='이 초마다 중간 보고 (0이면 끝에만)')
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    log = lambda s: print(s, flush=True)
    srv = subprocess.Popen([sys.executable, '-m', 'server', '--port', str(a.port)], cwd=WEB,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    try:
        for _ in range(200):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{a.port}/api/maps', timeout=2).read()
                break
            except OSError:
                time.sleep(0.3)
        time.sleep(3)                               # 예열이 끝나도록
        log(f'서버 켜짐 (메모리 {rss_mb(srv.pid):.0f} MB). 판 {a.sessions}개, {a.seconds:.0f}초, {a.speed:g}배속, 지도 {a.map}')
        stats = [Stats() for _ in range(a.sessions)]

        async def run():
            async def reporter():
                t0 = time.perf_counter()
                while a.report:
                    await asyncio.sleep(a.report)
                    log(f'[{(time.perf_counter() - t0) / 60:.0f}분] 서버 메모리 {rss_mb(srv.pid):.0f} MB')
                    for i, st in enumerate(stats):
                        log(f'   판 {i}: {st.line()}')
                        st.reset()
            rep = asyncio.create_task(reporter())
            res = await asyncio.gather(*[play(a.port, a.map, a.seconds, a.speed, stats[i], i, a.resume, log)
                                         for i in range(a.sessions)])
            rep.cancel()
            return res
        res = asyncio.run(run())
        log(f'끝: 서버 메모리 {rss_mb(srv.pid):.0f} MB, 판마다 라운드 수 {[r for r, _ in res]}')
        if not a.report:
            for i, st in enumerate(stats):
                log(f'   판 {i}: {st.line()}')
        if a.resume:
            log(f'다시 접속: {"모두 성공" if all(ok is True for _, ok in res) else "실패 " + str(res)}')
    finally:
        srv.terminate()
        try:
            err = srv.communicate(timeout=10)[1]
        except subprocess.TimeoutExpired:
            srv.kill()
            err = ''
        bad = [ln for ln in (err or '').splitlines() if 'Traceback' in ln or 'Error' in ln]
        if bad:
            log('서버 오류 기록:\n' + '\n'.join(bad[:20]))


if __name__ == '__main__':
    main()
