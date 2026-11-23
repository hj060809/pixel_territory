"""서버 통계 (/dashboard): 날마다 방문·순 방문자·시작한 판(싱글/멀티)·최대 동시 접속, 그리고 지금 서버 사용량.

공개 주소에서 보이므로 숫자만 모은다: IP·이름·방 코드·판 번호는 남기지도 보여 주지도 않는다.
순 방문자는 그날의 무작위 소금으로 IP를 해시해 메모리에만 둔다 (자정이면 버린다, 서버를 다시 켜면 그날 것은 조금 더 셀 수 있다).
날짜별 숫자는 data/stats.json에 남긴다 (최근 DAYS일).
서버 사용량은 리눅스의 /proc에서 읽는다 (도커 서버). 다른 곳(윈도우 개발)에서는 없는 값은 None.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
DAYS = 60


def today() -> str:
    return datetime.now(KST).strftime('%Y-%m-%d')


class Stats:
    def __init__(self, path: Path):
        self.path = path
        self.days: dict[str, dict] = {}
        try:
            self.days = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        self._day, self._salt, self._seen = '', b'', set()
        self.started = time.time()
        self._cpu_prev = None                       # (/proc/stat 합, 쉼) 지난번
        self._proc_prev = (time.monotonic(), time.process_time())

    def _today(self) -> dict:
        d = today()
        if d != self._day:                          # 날이 바뀌었다: 순 방문자 세기를 새로
            self._day, self._salt, self._seen = d, secrets.token_bytes(16), set()
        return self.days.setdefault(d, {'visits': 0, 'visitors': 0, 'single': 0, 'multi': 0, 'peak_clients': 0})

    # ------------------------------------------------------------- 기록
    def visit(self, ip: str) -> None:
        day = self._today()
        day['visits'] += 1
        h = hashlib.sha256(self._salt + ip.encode()).digest()[:8]
        if h not in self._seen:
            self._seen.add(h)
            day['visitors'] += 1

    def game(self, multi: bool) -> None:
        self._today()['multi' if multi else 'single'] += 1

    def clients(self, n: int) -> None:
        day = self._today()
        day['peak_clients'] = max(day['peak_clients'], n)

    def save(self) -> None:
        keep = sorted(self.days)[-DAYS:]
        self.days = {k: self.days[k] for k in keep}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.days, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.path)
        except OSError:
            pass

    def recent(self, n: int = 14) -> list[dict]:
        """최근 n일 (없는 날은 0으로)."""
        self._today()
        now = datetime.now(KST)
        out = []
        for k in range(n - 1, -1, -1):
            d = (now - timedelta(days=k)).strftime('%Y-%m-%d')
            out.append({'date': d, **self.days.get(d, {'visits': 0, 'visitors': 0, 'single': 0, 'multi': 0, 'peak_clients': 0})})
        return out

    # ------------------------------------------------------------- 서버 사용량
    def usage(self) -> dict:
        """CPU (서버 전체 %, 이 서버 프로그램 % (코어 하나 = 100)), 메모리, 부하, 코어 수, 켜진 지."""
        out = {'cores': os.cpu_count(), 'uptime': round(time.time() - self.started), 'cpu': None, 'proc_cpu': None,
               'mem_used': None, 'mem_total': None, 'proc_mem': None, 'load': None}
        now, pt = time.monotonic(), time.process_time()
        t0, p0 = self._proc_prev
        if now - t0 > 0.5:
            out['proc_cpu'] = round((pt - p0) / (now - t0) * 100, 1)
        self._proc_prev = (now, pt)
        try:
            with open('/proc/stat') as f:
                v = [int(x) for x in f.readline().split()[1:]]
            total, idle = sum(v), v[3] + (v[4] if len(v) > 4 else 0)
            if self._cpu_prev and total > self._cpu_prev[0]:
                dt, di = total - self._cpu_prev[0], idle - self._cpu_prev[1]
                out['cpu'] = round((1 - di / dt) * 100, 1)
            self._cpu_prev = (total, idle)
            mem = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    k, val = line.split(':', 1)
                    mem[k] = int(val.split()[0]) * 1024
            out['mem_total'] = mem.get('MemTotal')
            if 'MemAvailable' in mem:
                out['mem_used'] = mem['MemTotal'] - mem['MemAvailable']
            with open('/proc/self/status') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        out['proc_mem'] = int(line.split()[1]) * 1024
            out['load'] = [round(x, 2) for x in os.getloadavg()]
        except (OSError, ValueError, AttributeError):
            pass
        return out
