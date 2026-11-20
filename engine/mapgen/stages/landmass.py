"""1단계 땅 모양: 육지 비율만큼의 땅을 정해진 수의 땅덩어리가 나눠 가지며 자라난다.

파라미터 (WorldConfig)
- land_ratio      육지 비율
- landmasses      땅덩어리 수. 적으면 큰 대륙, 많으면 군도
- size_variety    크기 차이. 0 = 비슷하게 나눠 가짐 ~ 1 = 큰 덩어리 몇 개와 아주 작은 섬 여럿
- elongation      길쭉함. 0 = 굵고 둥근 ~ 1 = 가늘고 긴 활 모양 (덩어리마다 조금씩 다르다)
- edge_ocean      가장자리 바다. 0 = 땅이 지도 밖으로 이어진다 (더 큰 세상의 한 지역을 잘라낸 느낌)
                  ~ 1 = 모든 땅이 지도 안에 놓이고, 자라다 가장자리에 가까워지면 안쪽으로 휘어 들어온다
- coast_roughness 해안 굴곡. 좌표 비틀기와 중간 크기 노이즈로 만과 반도를 만든다
- coast_detail    해안 잔굴곡
- sharpness       각진 정도. 클수록 덜 비틀고, 보로노이 칸 경계를 따라 직선으로 꺾인다
- strait_width    땅덩어리 사이 최소 바다 폭 (지도 크기 비율). 자라다 다른 덩어리를 만나면 비켜 간다
- coast_smoothing, inland_sea_area  한두 픽셀 돌기와 틈 정리, 땅에 갇힌 물 중 호수로 남길 크기

만드는 법 (LandmassBuilder)
1. 육지 비율이라는 파이를 로그정규 분포로 나눠 땅덩어리마다 넓이를 정한다 (가장 작은 것도 눈에 보이게)
2. 큰 것부터, 아직 빈 곳 중 그 굵기가 들어갈 만큼 넓은 자리에 놓는다
3. 자리에서 양쪽으로 구불구불 나아가며 굵기가 들쭉날쭉한 원을 이어 붙인다 (넓이가 맞도록 길이와 굵기를 정한다)
4. 해안까지 거리에 가까운 장(field)으로 합치고, 해안 굴곡과 각진 면을 더한다
5. 덩어리끼리 맞닿는 경계는 구불거리게 정해 해협으로 판다
그다음 land_shape가 육지 비율에 맞춰 자르고, 잔돌기를 다듬고, 땅에 갇힌 작은 물을 메운다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from engine.mapgen.core.fields import ocean_of, smooth_max
from engine.mapgen.core.noise import fbm, normalize, sample


# ---------------------------------------------------------------------- 땅 모양 전체
def land_shape(cfg, rng, gen, S):
    """땅 모양 (육지 마스크)과 해안 굴곡용으로 비튼 좌표 (산맥 결에도 쓴다). 반환: (land, wx, wy)"""
    wy, wx, pad = warp_coords(cfg, gen, S)
    mid = normalize(sample(fbm(gen, S, S * 0.15, 4, 60.0, pad=pad), wy, wx, pad))   # 만과 반도
    fine = normalize(fbm(gen, S, S * 0.03, 3, 70.0))                                 # 해안 잔굴곡
    F, channel = LandmassBuilder(cfg, rng, S, wy, wx, mid, fine).build()
    land = _cut_to_ratio(cfg, F, channel)
    land = _smooth_coast(cfg, land, channel)
    land = _fill_holes(cfg, land, S)
    return land, wx, wy


def warp_coords(cfg, gen, S):
    """해안 굴곡용으로 두 번 비튼 좌표. 반환: (wy, wx, 비틀림 폭만큼 넓힌 노이즈 여백)"""
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
    amp = 0.22 * float(np.clip(cfg.coast_roughness, 0, 1.5)) * S
    # 비튼 좌표가 지도 밖으로 나가도 실제로 이어지는 노이즈를 읽도록, 비틀림 폭만큼 넓게 만든다
    # (넓히지 않으면 가장자리에서 노이즈가 거울처럼 접혀 억지 해안이 생긴다)
    pad = int(np.ceil(amp * 1.6)) + 4
    # 좌표를 두 번 비튼다: 비튼 좌표로 다시 비틀기 노이즈를 읽어서 소용돌이치듯 자연스러운 모양
    qx, qy = fbm(gen, S, S * 0.36, 3, 10.0), fbm(gen, S, S * 0.36, 3, 20.0)
    rx = sample(fbm(gen, S, S * 0.24, 3, 30.0, pad=pad), yy + amp * 0.5 * qy, xx + amp * 0.5 * qx, pad)
    ry = sample(fbm(gen, S, S * 0.24, 3, 40.0, pad=pad), yy + amp * 0.5 * qy, xx + amp * 0.5 * qx, pad)
    return yy + amp * ry, xx + amp * rx, pad


def _cut_to_ratio(cfg, F, channel):
    """육지 비율 맞추기: 기준을 조금만 옮긴다 (지도 밖으로 이어질수록 더 옮겨도 된다). 해협은 반드시 바다."""
    lim = 14.0 + 14.0 * (1.0 - float(np.clip(cfg.edge_ocean, 0, 1)))
    t = float(np.clip(np.quantile(F, 1 - cfg.land_ratio), -lim, lim))
    return (F > t) & ~channel


def _smooth_coast(cfg, land, channel):
    """한두 픽셀짜리 돌기와 틈을 없앤다."""
    r = cfg.coast_smoothing
    if r <= 0:
        return land
    # 지도 밖을 물로 보면 테두리에 닿은 땅이 깎여 둘레에 물길이 생기므로, 가장자리를 늘여 붙인 뒤 다듬는다
    disk = np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r + 0.5
    p = r + 1
    padded = np.pad(land, p, mode='edge')
    padded = ndimage.binary_closing(ndimage.binary_opening(padded, disk), disk)
    return padded[p:-p, p:-p] & ~channel


def _fill_holes(cfg, land, S):
    """땅 안에 갇힌 물(노이즈 구멍)은 대부분 메운다. 아주 큰 것만 내륙 호수로 남긴다
    (다 남기면 땅이 구멍 뚫린 치즈처럼 된다)."""
    holes = ~land & ~ocean_of(~land)
    lab, n = ndimage.label(holes)
    if n:
        area = ndimage.sum_labels(np.ones((S, S)), lab, np.arange(1, n + 1))
        keep = area >= cfg.inland_sea_area * S * S
        land |= holes & ~np.concatenate([[False], keep])[lab]
    return land


# ---------------------------------------------------------------------- 땅덩어리 만들기
class LandmassBuilder:
    """땅덩어리들을 자라게 해서 '해안까지 거리(픽셀)'에 가까운 장을 만든다.
    build() 반환: (장, 해협 마스크). 장은 0보다 크면 땅. 해협은 반드시 바다."""

    def __init__(self, cfg, rng, S, wy, wx, noise_mid, noise_fine):
        """wy, wx: 해안 굴곡용으로 비튼 좌표. noise_mid, noise_fine: 평균 0, 표준편차 1인 노이즈."""
        self.cfg, self.rng, self.S = cfg, rng, S
        self.noise_mid, self.noise_fine = noise_mid, noise_fine
        self.n = max(int(cfg.landmasses), 1)
        self.yy, self.xx = np.mgrid[0:S, 0:S].astype(np.float32)
        self.sharp = float(np.clip(cfg.sharpness, 0, 1))
        self.edge = float(np.clip(cfg.edge_ocean, 0, 1))
        self.rough = float(np.clip(cfg.coast_roughness, 0, 1.5))
        # 각질수록 덜 비튼다 (비틀면 소용돌이치는 둥근 모양이 된다)
        bend = 1.0 - 0.7 * self.sharp
        self.py = (self.yy + (wy - self.yy) * bend).astype(np.float32)
        self.px = (self.xx + (wx - self.xx) * bend).astype(np.float32)
        self.edge_soft = S * 0.11 * self.edge                        # 가장자리에서 이만큼 안쪽부터 휘어 들어온다
        self.gap_px = cfg.strait_width * S
        self.taken = np.zeros((S, S), bool)                          # 이미 다른 덩어리가 차지한 곳 (+ 해협 폭)

    def build(self):
        areas = self._plan_areas()
        fields = np.full((self.n, self.S, self.S), -200.0, np.float32)
        for i in range(self.n):
            self._grow_one(areas[i], fields[i])
        F, owner = self._merge(fields)
        del fields
        F = self._bend_coast(F)
        F = self._facets(F)
        return self._straits(F, owner)

    # --- 1. 넓이
    def _plan_areas(self):
        """파이를 무작위로 나눠 가진다. 지도 밖으로 이어질수록 바깥에 걸치는 만큼 더 크게 만든다."""
        cfg, S, n = self.cfg, self.S, self.n
        sigma = 0.05 + 1.15 * float(np.clip(cfg.size_variety, 0, 1))
        share = self.rng.lognormal(0.0, sigma, n)
        share /= share.sum()
        total = cfg.land_ratio * S * S * (1.0 + 0.35 * (1.0 - self.edge))
        floor = max(0.15 * total / n, 150.0)                          # 가장 작은 것도 눈에 보이게
        areas = np.maximum(total * share, floor)
        return np.sort(areas * total / areas.sum())[::-1]            # 큰 것부터 자리 잡는다

    # --- 2~3. 한 덩어리: 굵기와 길이 → 자리 → 자라기 → 칠하기
    def _grow_one(self, A, f):
        rng = self.rng
        r0 = np.sqrt(A / np.pi)
        e = float(np.clip(self.cfg.elongation + rng.normal(0, 0.18), 0, 1))
        r = max(r0 / (1.0 + 2.6 * e), 1.5)                           # 굵기
        L = max(A / (2.0 * r) - r, r * 0.5)                          # 길이 (넓이가 맞도록)
        c = self._place(r)
        pts = self._walk(c, r, L, e)
        self._paint(f, pts)
        self.taken |= f > -self.gap_px                               # 이 덩어리와 해협 폭만큼은 다음 덩어리가 못 들어온다

    def _place(self, r):
        """가장자리 바다가 클수록 안쪽에. 0이면 중심이 지도 밖에 걸쳐도 된다."""
        rng, S, edge, taken = self.rng, self.S, self.edge, self.taken
        lo = (1.0 - edge) * (-0.08 * S) + edge * min(r * 1.3 + S * 0.08, S * 0.3)
        free = ndimage.distance_transform_edt(~taken) if taken.any() else np.full((S, S), float(S))
        a0, a1 = int(max(lo, 0)), int(min(S - lo, S))
        inner = np.zeros((S, S), bool)
        inner[a0:max(a1, a0 + 1), a0:max(a1, a0 + 1)] = True
        ok = np.argwhere(inner & (free > r * 1.2 + 2))
        if not len(ok):                                              # 자리가 없으면 지도 전체에서
            ok = np.argwhere(free > r * 0.8 + 2)
        if len(ok):
            cand = ok[rng.integers(len(ok), size=min(len(ok), 30))].astype(float)
            score = free[cand[:, 0].astype(int), cand[:, 1].astype(int)] + rng.uniform(0, S * 0.05, len(cand))
            c = cand[np.argmax(score)]
        else:
            c = np.array(np.unravel_index(np.argmax(free), (S, S)), float)
        if lo < 0:                                                   # 지도 밖으로 이어질 땐 가장자리 쪽으로 조금 밀어 낸다
            c = c + (c - S / 2) * rng.uniform(0.0, 0.25)
        return c

    def _walk(self, c, r, L, e):
        """자리에서 양쪽으로 구불구불 나아가며 굵기가 들쭉날쭉한 원을 놓는다. 반환: [(y, x, 반지름)]"""
        rng, S, sharp, taken = self.rng, self.S, self.sharp, self.taken
        heading = rng.uniform(0, 2 * np.pi)
        turn = rng.normal(0, 0.03 + 0.05 * e) * (1.0 - 0.6 * sharp)  # 활처럼 휘는 정도
        curl = 0.25 * (1.0 - 0.7 * sharp)                            # 각질수록 곧게
        knots = rng.uniform(0.65, 1.3, 6)
        pts = []
        for direction in (0.0, np.pi):
            y, x, h, s_, blocked = c[0], c[1], heading + direction, 0.0, 0
            while s_ < L / 2:
                t = 0.5 + (s_ / L if direction == 0 else -s_ / L)
                rr = max(r * np.interp(t * 5, np.arange(6), knots) * float(np.exp(rng.normal(0, 0.15))), 1.2)
                iy, ix = int(np.clip(y, 0, S - 1)), int(np.clip(x, 0, S - 1))
                if 0 <= y < S and 0 <= x < S and taken[iy, ix]:      # 다른 덩어리를 만나면 비켜 간다
                    blocked += 1
                    if blocked > 6:
                        break
                    h += rng.choice([-1, 1]) * rng.uniform(0.6, 1.2)
                    if pts:
                        y, x = pts[-1][0], pts[-1][1]
                    else:
                        y, x = y + np.sin(h) * 2.0, x + np.cos(h) * 2.0
                    continue
                pts.append((y, x, rr))
                step = max(rr * 0.4, 1.0)
                h += rng.normal(turn, curl)
                h = self._steer_inward(y, x, rr, h)
                y, x = y + np.sin(h) * step, x + np.cos(h) * step
                s_ += step
        if e < 0.35 and r > 6:                                       # 굵은 덩어리는 옆으로 혹을 붙여 울퉁불퉁하게
            for _ in range(rng.integers(2, 5)):
                a = rng.uniform(0, 2 * np.pi)
                d = r * rng.uniform(0.4, 0.9)
                pts.append((c[0] + np.sin(a) * d, c[1] + np.cos(a) * d, r * rng.uniform(0.45, 0.75)))
        return pts

    def _steer_inward(self, y, x, rr, h):
        """가장자리에 가까워지면 안쪽(지도 가운데)으로 휘어 들어온다."""
        if self.edge_soft <= 0:
            return h
        S = self.S
        near_edge = min(y, x, S - 1 - y, S - 1 - x) - rr
        if near_edge < self.edge_soft:
            to_c = np.arctan2(S / 2 - y, S / 2 - x)
            w = np.clip(1.0 - near_edge / self.edge_soft, 0, 1) * 0.8
            h += w * np.angle(np.exp(1j * (to_c - h)))
        return h

    def _paint(self, f, pts):
        """원들을 부드러운 최댓값으로 합쳐 한 덩어리의 장을 만든다."""
        S, py, px = self.S, self.py, self.px
        first = np.ones((S, S), bool)
        for (cy, cx, rr) in pts:
            pad = rr + 90
            y0, y1 = int(max(cy - pad, 0)), int(min(cy + pad, S))
            x0, x1 = int(max(cx - pad, 0)), int(min(cx + pad, S))
            if y0 >= y1 or x0 >= x1:
                continue
            v = rr - np.hypot(py[y0:y1, x0:x1] - cy, px[y0:y1, x0:x1] - cx)
            sub = f[y0:y1, x0:x1]
            fr = first[y0:y1, x0:x1]
            sub[...] = np.where(fr, np.maximum(sub, v), smooth_max(sub, v))
            fr[...] = False
        np.maximum(f, -200.0, out=f)

    # --- 4. 합치기와 해안
    def _merge(self, fields):
        """덩어리끼리 맞닿는 경계는 그대로면 곧은 선이므로 덩어리마다 다른 노이즈로 구불거리게 주인을 정한다."""
        S = self.S
        F = fields.max(0)
        owner = np.zeros((S, S), np.int32)
        best_v = np.full((S, S), -1e9, np.float32)
        for i in range(self.n):
            v = fields[i] + 10.0 * np.roll(self.noise_mid, (37 * i + 11, 53 * i + 7), axis=(0, 1))
            upd = v > best_v
            owner[upd], best_v[upd] = i, v[upd]
        return F, owner

    def _bend_coast(self, F):
        """해안 굴곡 (만과 반도) + 잔굴곡. 각질수록 부드러운 굴곡은 줄인다."""
        amp_mid = (6.0 + 26.0 * self.rough) * (1.0 - 0.55 * self.sharp)
        amp_fine = (3.0 + 10.0 * self.cfg.coast_detail) * (1.0 - 0.4 * self.sharp)
        # 땅에서 멀어질수록 굴곡을 줄인다 (먼 바다에 노이즈 점섬이 솟지 않게)
        atten = np.clip(1.0 + F / (2.5 * amp_mid + 1e-6), 0, 1)
        return F + (amp_mid * self.noise_mid + amp_fine * self.noise_fine) * atten

    def _facets(self, F):
        """각진 면: 보로노이 칸마다 높이를 조금씩 다르게 해서 해안선이 칸 경계(직선)를 따라 꺾인다."""
        if self.sharp <= 0:
            return F
        S = self.S
        cells = int(S * S / (40.0 ** 2))                             # 칸이 클수록 곧은 면이 길다
        seeds = self.rng.uniform(0, S, (cells, 2))
        _, idx = cKDTree(seeds).query(np.stack([self.yy.ravel(), self.xx.ravel()], 1), k=1)
        facet = self.rng.uniform(-1, 1, cells)[idx].reshape(S, S)
        near = np.exp(-(F / 18.0) ** 2)                              # 해안 근처만
        return F + 26.0 * self.sharp * facet * near

    # --- 5. 해협
    def _straits(self, F, owner):
        """주인이 바뀌는 경계에서 해협 폭의 절반 안쪽은 바다로 (폭은 곳곳에서 들쭉날쭉)."""
        S = self.S
        channel = np.zeros((S, S), bool)
        if self.n > 1 and self.gap_px > 0:
            border = np.zeros((S, S), bool)
            border[:, 1:] |= owner[:, 1:] != owner[:, :-1]
            border[1:, :] |= owner[1:, :] != owner[:-1, :]
            d_b = ndimage.distance_transform_edt(~border)
            local = self.gap_px / 2 * (0.65 + 0.7 * np.clip(self.noise_fine * 0.35 + 0.5, 0, 1))
            F = np.minimum(F, d_b - local)
            channel = d_b < local                                    # 육지 비율을 맞춘 뒤에도 반드시 바다로 남긴다
        return F, channel
