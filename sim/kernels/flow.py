"""길찾기: 목표 지점에서 거꾸로 퍼지는 '거리 지도'(flow field). 병사는 자기 칸 주변 8칸 중 거리가 가장 짧은 쪽으로 걷는다.

- 걸음 비용 = 지형 비용 (평지 1, 숲 1.5, 바위산 2.6, 여울 2.5, 눈 덮이면 더). 대각선은 1.41배, 모서리는 못 자른다.
- 명령받은 병사들의 칸에 모두 닿으면 더 넓히지 않고 멈춘다 (대부분 수 ms).
- 같은 목표로 가는 명령은 거리 지도를 함께 쓴다 (FieldCache).
"""
from __future__ import annotations

import numpy as np
from numba import njit

INF = np.float32(1e30)


@njit(cache=True, nogil=True)
def _flow(walk, cost, ty, tx, sy, sx, out, want, heap_d, heap_i):
    H, W = walk.shape
    out[:, :] = INF
    need = 0
    for k in range(len(sy)):
        i = sy[k] * W + sx[k]
        if want[i] == 0:
            want[i] = 1
            need += 1
    n = 0
    out[ty, tx] = 0.0
    heap_d[0] = 0.0
    heap_i[0] = ty * W + tx
    n = 1
    cap = heap_d.shape[0]
    while n > 0:
        d = heap_d[0]
        cur = heap_i[0]
        # pop
        n -= 1
        heap_d[0] = heap_d[n]
        heap_i[0] = heap_i[n]
        p = 0
        while True:
            l = 2 * p + 1
            if l >= n:
                break
            r = l + 1
            c = l if (r >= n or heap_d[l] < heap_d[r]) else r
            if heap_d[c] < heap_d[p]:
                heap_d[c], heap_d[p] = heap_d[p], heap_d[c]
                heap_i[c], heap_i[p] = heap_i[p], heap_i[c]
                p = c
            else:
                break
        y = cur // W
        x = cur % W
        if d > out[y, x]:
            continue
        if want[cur] == 1:
            want[cur] = 0
            need -= 1
            if need == 0:
                break
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0:
                    continue
                ny = y + dy
                nx = x + dx
                if ny < 0 or ny >= H or nx < 0 or nx >= W or not walk[ny, nx]:
                    continue
                step = 0.5 * (cost[y, x] + cost[ny, nx])
                if dy != 0 and dx != 0:
                    if not walk[y, nx] or not walk[ny, x]:
                        continue
                    step *= 1.4142
                nd = np.float32(d + step)       # 저장하는 정밀도(float32)로 비교해야 같은 값을 '더 짧다'고 착각하지 않는다
                if nd < out[ny, nx]:
                    out[ny, nx] = nd
                    if n >= cap:
                        continue
                    # push
                    q = n
                    heap_d[q] = nd
                    heap_i[q] = ny * W + nx
                    n += 1
                    while q > 0:
                        pp = (q - 1) // 2
                        if heap_d[pp] > heap_d[q]:
                            heap_d[pp], heap_d[q] = heap_d[q], heap_d[pp]
                            heap_i[pp], heap_i[q] = heap_i[q], heap_i[pp]
                            q = pp
                        else:
                            break
    # 못 닿은 출발 칸 표시 지우기
    for k in range(len(sy)):
        want[sy[k] * W + sx[k]] = 0


@njit(cache=True, nogil=True)
def sea_path(nav, goal, sy, sx, max_len):
    """배의 길: (sy, sx) 물 칸에서 배가 다닐 수 있는 물(8방향)로 넓혀 가다 goal 칸에 닿으면 그 길.
    반환: (N, 2) [y, x] — goal 칸에서 시작해 (sy, sx)로 끝난다. 못 찾으면 빈 배열."""
    H, W = nav.shape
    prev = np.full(H * W, -1, np.int64)
    dist = np.full(H * W, -1, np.int32)
    q = np.empty(H * W, np.int64)
    head, tail = 0, 0
    s = sy * W + sx
    q[tail] = s
    tail += 1
    dist[s] = 0
    found = -1
    while head < tail:
        cur = q[head]
        head += 1
        y, x = cur // W, cur % W
        if goal[y, x]:
            found = cur
            break
        if dist[cur] >= max_len:
            continue
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= H or nx < 0 or nx >= W or not nav[ny, nx]:
                    continue
                if dy != 0 and dx != 0 and not (nav[y, nx] and nav[ny, x]):
                    continue
                k = ny * W + nx
                if dist[k] >= 0:
                    continue
                dist[k] = dist[cur] + 1
                prev[k] = cur
                q[tail] = k
                tail += 1
    if found < 0:
        return np.empty((0, 2), np.int32)
    n = dist[found] + 1
    out = np.empty((n, 2), np.int32)
    cur = found
    for i in range(n):
        out[i, 0] = cur // W
        out[i, 1] = cur % W
        cur = prev[cur]
    return out
