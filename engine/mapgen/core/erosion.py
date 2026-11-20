"""물방울 기반 수력 침식 커널 (numba로 컴파일, 없으면 순수 파이썬으로 느리게 돈다).

물방울을 무작위 위치에 떨어뜨려, 관성과 경사를 섞은 방향으로 굴리며
내리막에서는 반경 안을 깎아 퇴적물을 싣고, 오르막이나 실을 수 있는 양을 넘으면 내려놓는다.
"""
from __future__ import annotations

import numpy as np

try:
    from numba import njit
except ImportError:  # numba가 없으면 순수 파이썬으로 돈다 (느림)
    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return lambda f: f


@njit(cache=True)
def _height_and_gradient(h, x, y):
    """(x, y) 위치의 높이와 기울기를 주변 4칸 bilinear 보간으로 구한다."""
    ix, iy = int(x), int(y)
    fx, fy = x - ix, y - iy
    h00 = h[iy, ix]
    h10 = h[iy, ix + 1]
    h01 = h[iy + 1, ix]
    h11 = h[iy + 1, ix + 1]
    gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
    gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
    height = (h00 * (1 - fx) * (1 - fy) + h10 * fx * (1 - fy)
              + h01 * (1 - fx) * fy + h11 * fx * fy)
    return height, gx, gy


@njit(cache=True)
def erode_droplets(h, droplets, seed, inertia, capacity, min_capacity, deposit_rate,
                   erode_rate, evaporate_rate, gravity, max_steps, radius):
    """h를 제자리에서 깎는다."""
    H, W = h.shape
    np.random.seed(seed)

    for _ in range(droplets):
        x = np.random.random() * (W - 1)
        y = np.random.random() * (H - 1)
        dx = 0.0
        dy = 0.0
        speed = 1.0
        water = 1.0
        sediment = 0.0

        for _ in range(max_steps):
            ix, iy = int(x), int(y)
            fx, fy = x - ix, y - iy
            height, gx, gy = _height_and_gradient(h, x, y)

            # 관성과 경사를 섞어서 진행 방향 결정
            dx = dx * inertia - gx * (1 - inertia)
            dy = dy * inertia - gy * (1 - inertia)
            length = np.sqrt(dx * dx + dy * dy)
            if length == 0.0:
                break
            dx /= length
            dy /= length

            nx, ny = x + dx, y + dy
            if nx < 0 or nx >= W - 1 or ny < 0 or ny >= H - 1:
                break

            new_height, _, _ = _height_and_gradient(h, nx, ny)
            dh = new_height - height  # 내려가면 음수

            cap = max(-dh * speed * water * capacity, min_capacity)

            if sediment > cap or dh > 0:
                # 오르막이면 구덩이를 메우고, 아니면 넘치는 만큼 내려놓는다
                amount = min(dh, sediment) if dh > 0 else (sediment - cap) * deposit_rate
                sediment -= amount
                h[iy, ix] += amount * (1 - fx) * (1 - fy)
                h[iy, ix + 1] += amount * fx * (1 - fy)
                h[iy + 1, ix] += amount * (1 - fx) * fy
                h[iy + 1, ix + 1] += amount * fx * fy
            else:
                # 반경 안의 칸들을 거리 가중치로 깎는다 (한 칸만 깎으면 뾰족한 구멍이 생김)
                amount = min((cap - sediment) * erode_rate, -dh)
                total_w = 0.0
                for oy in range(-radius, radius + 1):
                    for ox in range(-radius, radius + 1):
                        cx, cy = ix + ox, iy + oy
                        if 0 <= cx < W and 0 <= cy < H:
                            total_w += max(0.0, radius - np.sqrt(ox * ox + oy * oy))
                if total_w > 0:
                    for oy in range(-radius, radius + 1):
                        for ox in range(-radius, radius + 1):
                            cx, cy = ix + ox, iy + oy
                            if 0 <= cx < W and 0 <= cy < H:
                                w = max(0.0, radius - np.sqrt(ox * ox + oy * oy)) / total_w
                                d = min(h[cy, cx], amount * w)
                                h[cy, cx] -= d
                                sediment += d

            speed = np.sqrt(max(0.0, speed * speed - dh * gravity))
            water *= 1 - evaporate_rate
            x, y = nx, ny
