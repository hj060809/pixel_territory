"""물의 흐름 계산 (numba로 컴파일).

- priority_flood: 바다(배수구)에서부터 물을 채워 들어가며, 움푹한 곳을 넘칠 때까지 채운 높이를 구한다.
  채운 높이 - 원래 높이 > 0 인 곳이 호수 후보다. 평평한 곳도 물이 빠지도록 아주 작은 경사를 준다.
- flow_accumulate: 높은 곳부터 가장 가파른 아래쪽 이웃으로 물을 보내며, 각 칸에 모이는 물의 양을 센다.
  많이 모이는 경로가 강이 된다.
"""
from __future__ import annotations

import heapq

import numpy as np
from numba import njit

_DY = np.array([-1, -1, -1, 0, 0, 1, 1, 1], dtype=np.int64)
_DX = np.array([-1, 0, 1, -1, 1, -1, 0, 1], dtype=np.int64)
_DIST = np.array([1.41421356, 1.0, 1.41421356, 1.0, 1.0, 1.41421356, 1.0, 1.41421356])


@njit(cache=True)
def priority_flood(h: np.ndarray, outlet: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """outlet(바다)에서 시작해 움푹한 곳을 넘칠 높이까지 채운 높이맵."""
    H, W = h.shape
    filled = h.copy()
    closed = np.zeros((H, W), dtype=np.bool_)
    heap = [(0.0, np.int64(0))]
    heap.pop()
    for y in range(H):
        for x in range(W):
            if outlet[y, x]:
                closed[y, x] = True
                heapq.heappush(heap, (filled[y, x], np.int64(y * W + x)))
    while len(heap) > 0:
        z, idx = heapq.heappop(heap)
        y = idx // W
        x = idx % W
        for k in range(8):
            ny = y + _DY[k]
            nx = x + _DX[k]
            if ny < 0 or ny >= H or nx < 0 or nx >= W or closed[ny, nx]:
                continue
            closed[ny, nx] = True
            if filled[ny, nx] <= z:
                filled[ny, nx] = z + eps      # 평평한 곳도 배수구 쪽으로 물이 빠지게
            heapq.heappush(heap, (filled[ny, nx], np.int64(ny * W + nx)))
    return filled


@njit(cache=True)
def flow_accumulate(filled: np.ndarray, order: np.ndarray, active: np.ndarray):
    """높은 칸부터(order) 가장 가파른 아래 이웃으로 물을 보낸다. (모인 양, 내려가는 칸 번호)."""
    H, W = filled.shape
    flat = filled.ravel()
    act = active.ravel()
    acc = np.ones(H * W)
    down = np.full(H * W, -1, dtype=np.int64)
    for idx in order:
        if not act[idx]:
            continue
        y = idx // W
        x = idx % W
        best = -1
        best_drop = 0.0
        for k in range(8):
            ny = y + _DY[k]
            nx = x + _DX[k]
            if ny < 0 or ny >= H or nx < 0 or nx >= W:
                continue
            n = ny * W + nx
            drop = (flat[idx] - flat[n]) / _DIST[k]
            if drop > best_drop:
                best_drop = drop
                best = n
        if best >= 0:
            down[idx] = best
            acc[best] += acc[idx]
    return acc.reshape(H, W), down
