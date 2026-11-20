"""로비 배경 (데스크톱 game/menu.py의 LobbyArt에서 자리 고르기와 장식 배치만 옮겼다).

실제로 생성한 지형에서 바다와 땅이 어우러진 조각을 골라, 그 위에 거점·망루·농장·항구와 병사(서 있거나 순찰),
오가는 나룻배와 전함, 물 위 반짝임 자리를 정한다. 브라우저는 조각 그림(PNG)과 이 배치를 받아 움직이며 그린다.
같은 지도면 데스크톱과 같은 조각, 같은 배치가 나온다 (난수 시드 7).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.bake.png import png_bytes
from sim import rules as R

CW, CH, MARGIN = 170, 106, 28           # 보이는 조각 크기 (지도 칸), 좌우로 흘러갈 여유


def build(scene) -> tuple[dict, bytes]:
    """반환: (배치 JSON, 조각 PNG). scene: engine.scene.TerrainScene."""
    img = scene.day
    h = np.asarray(scene.height, dtype=np.float64)[:img.shape[0], :img.shape[1]]
    water = h < scene.shader.sea_level
    rng = np.random.default_rng(7)
    y0, x0 = _choose(img, water, rng)
    ch, cw = CH, CW + MARGIN
    crop = np.ascontiguousarray(img[y0:y0 + ch, x0:x0 + cw])
    info = _decorate(water[y0:y0 + ch, x0:x0 + cw], rng)
    info.update(w=cw, h=ch, cw=CW, margin=MARGIN)
    return info, png_bytes(crop)


def _choose(img, water, rng):
    H, W = water.shape
    cw, ch = CW + MARGIN, CH
    best, bs = None, -1e9
    green = (img[..., 1].astype(int) > img[..., 0] + 8) & (img[..., 1] > img[..., 2])
    snow = img.min(-1) > 200
    for _ in range(500):                         # 바다와 땅이 반쯤, 해안이 길고, 푸르고, 눈은 적은 곳
        y, x = int(rng.integers(0, H - ch)), int(rng.integers(0, W - cw))
        wtr = water[y:y + ch, x:x + cw]
        land = 1 - wtr.mean()
        coast = (wtr[1:] != wtr[:-1]).mean() + (wtr[:, 1:] != wtr[:, :-1]).mean()
        right = 1 - water[y:y + ch, x + cw // 2:x + cw].mean()       # 오른쪽(장식 자리)에 땅
        s = (-abs(land - 0.55) * 3 + coast * 25 + green[y:y + ch, x:x + cw].mean() * 1.5
             - snow[y:y + ch, x:x + cw].mean() * 4 + right * 1.0)
        if s > bs:
            best, bs = (y, x), s
    return best


def _decorate(wtr, rng) -> dict:
    land = ~wtr
    ch, cw = wtr.shape
    dw = ndimage.distance_transform_edt(land)            # 땅 칸: 물까지 거리
    dl = ndimage.distance_transform_edt(wtr)             # 물 칸: 땅까지 거리
    yy, xx = np.mgrid[0:ch, 0:cw]

    def pick(mask, target, spread=6.0):
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            return None
        d = np.hypot(ys - target[0], xs - target[1]) + rng.uniform(0, spread, len(ys))
        k = int(np.argmin(d))
        return int(ys[k]), int(xs[k])

    out = {'buildings': [], 'walkers': [], 'ships': [], 'sparkles': []}
    deco = out['buildings']                             # {kind, nat, y, x}
    cx = MARGIN / 2 + CW * 0.68                          # 화면 오른쪽 가운데쯤 (왼쪽은 메뉴)
    hall = pick(land & (dw >= 6) & (dw <= 18) & (xx > cw * 0.45), (ch * 0.5, cx)) \
        or pick(land, (ch * 0.5, cx))
    if hall is None:
        return out
    hy, hx = hall
    near = lambda r0, r1: land & (np.hypot(yy - hy, xx - hx) >= r0) & (np.hypot(yy - hy, xx - hx) <= r1)
    bld = lambda kind, nat, p: deco.append({'kind': int(kind), 'nat': nat, 'y': p[0], 'x': p[1]})
    bld(R.HALL, 0, hall)
    for kind, r0, r1, extra in ((R.TOWER, 9, 14, dw >= 3), (R.FARM, 12, 20, dw >= 4), (R.TOWER, 18, 26, dw >= 3)):
        p = pick(near(r0, r1) & extra, (hy + rng.uniform(-10, 10), hx + rng.uniform(-14, 14)))
        if p:
            bld(kind, 0, p)
    harbor = pick(land & (dw <= 2) & (np.hypot(yy - hy, xx - hx) < 45), (hy, hx), 2)
    if harbor:
        bld(R.HARBOR, 0, harbor)
    walkers = out['walkers']                            # {kind, nat, a:[y,x], b:[y,x], speed, phase}
    walker = lambda kind, nat, a, b, speed, phase: walkers.append(
        {'kind': int(kind), 'nat': nat, 'a': [float(a[0]), float(a[1])], 'b': [float(b[0]), float(b[1])],
         'speed': float(speed), 'phase': float(phase)})
    # 병사: 거점 둘레에 서 있는 무리 + 순찰하는 무리
    for k in range(7):
        p = pick(near(5, 9), (hy + rng.uniform(-8, 8), hx + rng.uniform(-8, 8)), 4)
        if p:
            walker(k % 2, 0, p, p, 0.0, rng.uniform(0, 6))
    a = pick(near(10, 22), (hy - 8, hx - 18))
    b = pick(near(10, 22), (hy + 8, hx + 18))
    if a and b:
        for k in range(5):
            off = (rng.uniform(-2, 2), rng.uniform(-2, 2))
            walker(int(k == 4), 0, (a[0] + off[0], a[1] + off[1]), (b[0] + off[0], b[1] + off[1]), 0.035, k * 0.08)
    # 다른 나라 정찰대
    e = pick(land & (dw >= 3) & (xx > cw * 0.55), (ch * 0.85, cw * 0.9), 10)
    if e:
        for k in range(4):
            walker(k % 2, 1, (e[0] + rng.uniform(-3, 3), e[1] + rng.uniform(-3, 3)),
                   (e[0] + rng.uniform(-3, 3) - 6, e[1] + rng.uniform(-3, 3) - 10), 0.02, k * 0.1)
    # 배: 물 위 곧은 길을 오간다
    for kind, nat, row in (('ferry', 0, 0.35), ('warship', 2, 0.7), ('ferry', 1, 0.15)):
        seg = _water_segment(wtr & (dl >= 3), int(ch * row))
        if seg:
            out['ships'].append({'kind': kind, 'nat': nat, 'a': list(seg[0]), 'b': list(seg[1]),
                                 'speed': 0.012 + float(rng.uniform(0, 0.008)), 'phase': float(rng.uniform(0, 1))})
    # 물 위 반짝임
    ys, xs = np.nonzero(wtr & (dl >= 2))
    k = rng.choice(len(ys), min(90, len(ys)), replace=False) if len(ys) else []
    out['sparkles'] = [[int(ys[i]), int(xs[i]), float(rng.uniform(0, 6.28)), float(rng.uniform(0.6, 1.4))] for i in k]
    return out


def _water_segment(ok, row):
    """row 가까이에서 가로로 가장 긴 물 구간."""
    best = None
    for y in range(max(row - 20, 0), min(row + 20, ok.shape[0])):
        r = ok[y]
        x = 0
        while x < len(r):
            if r[x]:
                s = x
                while x < len(r) and r[x]:
                    x += 1
                if best is None or x - s > best[2]:
                    best = (y, s, x - s)
            x += 1
    if best is None or best[2] < 25:
        return None
    y, s, n = best
    return (y, s + 3), (y, s + n - 4)
