"""판을 시작할 때: 나라 색 배정과 거점 자리. 설정 화면 미리보기와 게임이 같은 함수를 쓴다."""
from __future__ import annotations

import numpy as np

from sim import rules as R


def pick_colors(rng, n: int, first: int | None = None) -> list[int]:
    """나라 순서대로 rules.COLORS 번호. first를 주면 맨 앞 나라가 그 색, 나머지는 무작위 (설정 화면 미리보기: 맨 앞 = 고른 색)."""
    if first is None:
        return [int(c) for c in rng.permutation(len(R.COLORS))[:n]]
    others = [c for c in range(len(R.COLORS)) if c != first]
    return [first] + [int(c) for c in rng.permutation(others)[:n - 1]]


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


def choose_starts(gmap, n: int, rng, fixed=None, sites=None) -> list[tuple]:
    """나라 n개의 거점 자리 (y, x). 살 만한 섬들(start_islands)의 살 만한 곳 중 서로 충분히 떨어진 곳을 무작위로.
    섬마다 넓이에 비례해 후보가 뽑히므로 나라들이 여러 섬에 흩어진다 (한 섬에 여럿이 모일 수도 있다).
    fixed: 미리 고른 자리들 [(y, x)...] — 결과의 맨 앞 len(fixed)개가 그 자리 (못 쓰는 땅이면 가까운 곳).
    sites: 자원지 (없으면 가장 큰 땅만). 설정 화면 미리보기와 게임이 같은 결과를 쓴다."""
    fixed = [tuple(p) for p in (fixed or [])]
    nf = len(fixed)
    m = gmap
    if sites is None:
        area = np.bincount(m.comp[m.land & (m.comp > 0)])
        isl = np.array([int(area.argmax())])
    else:
        isl = start_islands(gmap, sites)
    on = m.land & np.isin(m.comp, isl)
    from sim.wildlife import LAIR_CLEAR, lairs_for
    for ly, lx in lairs_for(gmap):                      # 드래곤 둥지 가까이에서는 시작하지 않는다 (깨어 덤빈다)
        y0, y1, x0, x1 = max(ly - LAIR_CLEAR, 0), ly + LAIR_CLEAR + 1, max(lx - LAIR_CLEAR, 0), lx + LAIR_CLEAR + 1
        yy, xx = np.ogrid[y0:min(y1, m.H), x0:min(x1, m.W)]
        on[y0:y1, x0:x1] &= (yy - ly) ** 2 + (xx - lx) ** 2 > LAIR_CLEAR ** 2
    ys, xs = np.nonzero(on & (m.value > 0.45) & (m.base_cost <= 1.6))
    if len(ys) < 50:
        ys, xs = np.nonzero(on)
    k = rng.choice(len(ys), min(1500, len(ys)), replace=False)
    pts = np.stack([ys[k], xs[k]], 1).astype(float)
    if nf:
        pts = np.vstack([np.array(fixed, float), pts])
    # 서로 충분히 떨어진 자리를 무작위 순서로 고른다. 모자라면 간격을 조금씩 줄인다
    gap = np.sqrt(on.sum() / n) * 0.75
    while True:
        chosen = list(range(nf))
        for j in rng.permutation(len(pts)):
            if j < nf:
                continue
            if all(np.hypot(*(pts[j] - pts[c])) >= gap for c in chosen):
                chosen.append(j)
                if len(chosen) == n:
                    break
        if len(chosen) == n or gap < 10:
            break
        gap *= 0.9
    if not nf:
        chosen = [chosen[i] for i in rng.permutation(len(chosen))]

    def open_square(y, x, r=5):
        return (r <= y < m.H - r and r <= x < m.W - r and m.land[y - r:y + r + 1, x - r:x + r + 1].all()
                and all(np.hypot(y - a, x - b) >= 2 * r + 2 for a, b in out))

    out = []
    for i, j in enumerate(chosen):
        y, x = pts[j]
        spot = None
        if i < nf and open_square(int(y), int(x)):
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
