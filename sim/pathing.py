"""길찾기 캐시: 목표마다 거리 지도(flow field)를 슬롯에 담아 둔다. 같은 목표로 가는 명령은 함께 쓴다.
계산은 sim.kernels.flow (numba, GIL을 놓는다).

거리 지도 하나는 먼 목적지면 수십 ms라서, 계산은 보조 스레드에서 한다 (걸음을 막지 않게):
- get()은 슬롯을 바로 돌려주고 계산을 맡긴다. 그 슬롯은 '준비 중'(ready=False)이라 병사는 제자리에서 기다린다.
- 다음 world.update 맨 앞에서 wait()로 받아 '준비됨'으로 바꾼다. 서버는 걸음 사이에 쉬므로 그동안 대부분 끝나 있다.
  언제 준비되는지가 스레드 속도와 상관없이 늘 같아서, 같은 시드면 같은 판이 된다.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from sim.kernels.flow import INF, _flow

_POOL = ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) // 2), thread_name_prefix='flow')


def _compute(walk, cost, ty, tx, sy, sx, out):
    """(보조 스레드) 거리 지도를 out에 바로 쓴다. 버퍼는 작업마다 따로 (여러 판이 함께 써도 되게)."""
    n = walk.size
    _flow(walk, cost, ty, tx, sy, sx, out, np.zeros(n, np.uint8), np.empty(n * 3, np.float32), np.empty(n * 3, np.int64))


class FieldCache:
    """거리 지도 슬롯 모음. 병사는 슬롯 번호를 들고 다닌다."""

    def __init__(self, gmap, slots: int = 48):
        self.map = gmap
        H, W = gmap.H, gmap.W
        self.fields = np.full((slots, H, W), INF, np.float32)
        self.ready = np.ones(slots, np.bool_)          # False: 계산 중 (병사는 기다린다)
        self.keys = [None] * slots
        self.used = np.zeros(slots)
        self.clock = 0
        self._jobs: dict[int, object] = {}             # 슬롯 → 계산 작업

    def snap(self, y: float, x: float, r: int = 8):
        """(y, x) 가까이의 걸어갈 수 있는 칸."""
        m = self.map
        y, x = int(np.clip(y, 0, m.H - 1)), int(np.clip(x, 0, m.W - 1))
        if m.walk[y, x]:
            return y, x
        y0, y1, x0, x1 = max(y - r, 0), min(y + r + 1, m.H), max(x - r, 0), min(x + r + 1, m.W)
        ys, xs = np.nonzero(m.walk[y0:y1, x0:x1])
        if len(ys) == 0:
            return None
        k = np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2)
        return int(ys[k] + y0), int(xs[k] + x0)

    def get(self, ty: int, tx: int, sy, sx, busy, cost=None, tag=0) -> int:
        """목표 (ty, tx)로 가는 거리 지도 슬롯. sy, sx: 출발 칸들. busy: 지금 병사들이 쓰는 슬롯 (bool).
        cost: 걷는 비용 지도 (없으면 지도의 것), tag: 그 비용의 이름 (부족마다 다른 길: sim/climate.py path_cost).
        새로 계산해야 하면 보조 스레드에 맡기고 슬롯을 바로 돌려준다 (다음 update 때 준비된다)."""
        self.clock += 1
        key = (ty, tx, self.map.walk_version, tag)
        sy = np.asarray(sy, np.int64)
        sx = np.asarray(sx, np.int64)
        for s, k in enumerate(self.keys):
            if k == key and self.ready[s] and np.all(self.fields[s][sy, sx] < INF):
                self.used[s] = self.clock
                return s
        free = [s for s in range(len(self.keys)) if not busy[s] and s not in self._jobs]
        if free:
            s = min(free, key=lambda s: self.used[s])
        else:                                          # 모두 쓰는 중: 가장 오래 안 쓴 것 (계산 중인 것은 기다렸다가)
            s = int(np.argmin(self.used))
            if s in self._jobs:
                self._jobs.pop(s).result()
        self.ready[s] = False
        self._jobs[s] = _POOL.submit(_compute, self.map.walk, self.map.cost if cost is None else cost, ty, tx, sy, sx, self.fields[s])
        self.keys[s] = key
        self.used[s] = self.clock
        return s

    def wait(self) -> None:
        """맡겨 둔 계산을 모두 받아 '준비됨'으로 (world.update 맨 앞에서)."""
        for s, job in self._jobs.items():
            job.result()
            self.ready[s] = True
        self._jobs.clear()


class WalkCost:
    """걷는 비용 재기 (배를 탈지 정할 때): 병사가 실제로 쓰는 길찾기(_flow)로 목표에서 몇 곳까지의 비용을 잰다.
    재려는 곳에 모두 닿으면 멈추므로 대개 수 ms ~ 수십 ms. 비용은 평지 1칸 = 1 (걷는 시간 = 비용 / 걷는 속도)."""

    def __init__(self, gmap):
        self.map = gmap
        self._out = np.empty((gmap.H, gmap.W), np.float32)

    def _snap(self, y, x, r=6):
        m = self.map
        y, x = int(np.clip(y, 0, m.H - 1)), int(np.clip(x, 0, m.W - 1))
        if m.walk[y, x]:
            return y, x
        y0, x0 = max(y - r, 0), max(x - r, 0)
        ys, xs = np.nonzero(m.walk[y0:y + r + 1, x0:x + r + 1])
        if not len(ys):
            return None
        k = int(np.argmin((ys + y0 - y) ** 2 + (xs + x0 - x) ** 2))
        return int(ys[k] + y0), int(xs[k] + x0)

    def costs(self, ty, tx, points) -> list[float]:
        """(ty, tx)에서 points[(y, x), ...]까지 걷는 비용 (못 가면 inf)."""
        t = self._snap(ty, tx)
        pts = [self._snap(y, x) for y, x in points]
        if t is None:
            return [float('inf')] * len(points)
        ok = [q for q in pts if q is not None]
        if not ok:
            return [float('inf')] * len(points)
        m, n = self.map, self.map.walk.size
        _flow(m.walk, m.cost, t[0], t[1], np.array([q[0] for q in ok], np.int64), np.array([q[1] for q in ok], np.int64),
              self._out, np.zeros(n, np.uint8), np.empty(n * 3, np.float32), np.empty(n * 3, np.int64))
        return [float('inf') if q is None or self._out[q] >= INF else float(self._out[q]) for q in pts]
