"""판을 시작할 때: 나라 색 배정과 거점 자리. 설정 화면 미리보기와 게임이 같은 함수를 쓴다."""
from __future__ import annotations

import numpy as np

from sim import rules as R


def pick_colors(rng, n: int, player_color: int) -> list[int]:
    """나라 순서대로 rules.COLORS 번호 (내 색이 맨 앞, AI는 나머지에서 무작위)."""
    others = [c for c in range(len(R.COLORS)) if c != player_color]
    return [player_color] + [int(c) for c in rng.permutation(others)[:n - 1]]


MIN_ISLAND = 2500          # 시작할 수 있는 섬의 최소 넓이 (칸)


def start_islands(gmap, sites) -> np.ndarray:
    """시작할 수 있는 땅 덩어리 번호들: 넓이가 MIN_ISLAND 이상이고 식량 자원지가 있는 섬 (병사가 굶지 않게).
    목재는 거점이 조금씩 내고 시작 목재로 항구를 지을 수 있어서, 숲이 없는 섬이면 바다 건너 숲을 노리게 된다.
    없으면 가장 큰 땅 하나."""
    m = gmap
    area = np.bincount(m.comp[m.land & (m.comp > 0)], minlength=int(m.comp.max()) + 1)
    food = {int(m.comp[s.y, s.x]) for s in sites if s.kind == R.FOOD}
    ok = [int(c) for c in np.flatnonzero(area >= MIN_ISLAND) if int(c) in food]
    return np.array(ok if ok else [int(area.argmax())], np.int64)


def choose_starts(gmap, n: int, rng, player_spot=None, sites=None) -> list[tuple]:
    """나라 n개의 거점 자리 (y, x). 살 만한 섬들(start_islands)의 살 만한 곳 중 서로 충분히 떨어진 곳을 무작위로.
    섬마다 넓이에 비례해 후보가 뽑히므로 나라들이 여러 섬에 흩어진다 (한 섬에 여럿이 모일 수도 있다).
    player_spot을 주면 맨 앞(내 자리)은 그 자리. sites: 자원지 (없으면 가장 큰 땅만).
    설정 화면 미리보기와 게임이 같은 결과를 쓴다."""
    m = gmap
    if sites is None:
        area = np.bincount(m.comp[m.land & (m.comp > 0)])
        isl = np.array([int(area.argmax())])
    else:
        isl = start_islands(gmap, sites)
    on = m.land & np.isin(m.comp, isl)
    ys, xs = np.nonzero(on & (m.value > 0.45) & (m.base_cost <= 1.6))
    if len(ys) < 50:
        ys, xs = np.nonzero(on)
    k = rng.choice(len(ys), min(1500, len(ys)), replace=False)
    pts = np.stack([ys[k], xs[k]], 1).astype(float)
    if player_spot is not None:
        pts = np.vstack([np.array(player_spot, float)[None], pts])
    # 서로 충분히 떨어진 자리를 무작위 순서로 고른다. 모자라면 간격을 조금씩 줄인다
    gap = np.sqrt(on.sum() / n) * 0.75
    while True:
        chosen = [0] if player_spot is not None else []
        for j in rng.permutation(len(pts)):
            if player_spot is not None and j == 0:
                continue
            if all(np.hypot(*(pts[j] - pts[c])) >= gap for c in chosen):
                chosen.append(j)
                if len(chosen) == n:
                    break
        if len(chosen) == n or gap < 10:
            break
        gap *= 0.9
    if player_spot is None:
        chosen = [chosen[i] for i in rng.permutation(len(chosen))]

    def open_square(y, x, r=5):
        return (r <= y < m.H - r and r <= x < m.W - r and m.land[y - r:y + r + 1, x - r:x + r + 1].all()
                and all(np.hypot(y - a, x - b) >= 2 * r + 2 for a, b in out))

    out = []
    for i, j in enumerate(chosen):
        y, x = pts[j]
        spot = None
        if i == 0 and player_spot is not None and open_square(int(y), int(x)):
            spot = (int(y), int(x))                                    # 고른 자리 그대로
        for _ in range(60 if spot is None else 0):                     # 그 둘레 10칸쯤의 넓은 땅
            a = rng.uniform(0, 2 * np.pi)
            yy, xx = int(y + np.sin(a) * 10), int(x + np.cos(a) * 10)
            if open_square(yy, xx):
                spot = (yy, xx)
                break
        if spot is None:                                               # 못 찾으면 가장 가까운 시작할 수 있는 땅
            wy, wx = np.nonzero(on)
            q = int(np.argmin((wy - y) ** 2 + (wx - x) ** 2))
            spot = (int(wy[q]), int(wx[q]))
        out.append(spot)
    return out
