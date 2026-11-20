"""5단계 해안 종류: 해식 절벽, 모래사장(+사구), 석회암 바위 해안, 석호와 사주 (CoastShaper).

해안 칸마다
- 돌출도: 주변(반경 약 20칸)에 육지가 적을수록 곶, 많을수록 만
- 배후 경사: 해안에서 조금 들어간 곳이 얼마나 높은지
를 재고, 큰 노이즈를 섞어 같은 조건에서도 해안이 들쭉날쭉 바뀌게 한 점수로 종류를 나눈다.
점수가 부드러운 장(field)이라 같은 종류가 해안을 따라 자연스러운 구간으로 이어진다.
종류가 바뀌는 곳은 가중치를 부드럽게 섞어서 지형이 뚝 끊기지 않게 한다.

높이를 고쳐서 지형을 만들고(절벽은 솟게, 모래사장은 낮고 평평하게, 바위 해안은 잘게 들쭉날쭉하게),
셰이더가 색을 정할 수 있게 칸마다 해안 종류(engine.mapgen.coast_types)를 돌려준다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.coast_types import BEACH, CLIFF, DUNE, LAGOON, MARSH, ROCKY
from engine.mapgen.core.noise import fbm_offset, zscore


def shape_coasts(cfg, rng, gen, S, h, ocean, lakes):
    """반환: (고친 높이, 해안 종류 uint8 (S, S))."""
    return CoastShaper(cfg, rng, gen, S, h, ocean, lakes).run()


class CoastShaper:
    def __init__(self, cfg, rng, gen, S, h, ocean, lakes):
        self.cfg, self.rng, self.gen, self.S = cfg, rng, gen, S
        self.sea = cfg.sea_level
        self.h = h.copy()
        self.ocean, self.lakes = ocean, lakes
        self.coast = np.zeros((S, S), np.uint8)

    def run(self):
        if self.cfg.coast_variety <= 0:
            return self.h, self.coast
        self.land = (self.h >= self.sea) & (self.lakes == 0)
        self.d_land = ndimage.distance_transform_edt(~self.ocean)     # 육지(와 호수) 칸: 바다까지 거리
        self.d_sea = ndimage.distance_transform_edt(self.ocean)       # 바다 칸: 육지까지 거리
        self.shore = self.land & (self.d_land <= 1.5)                  # 바다에 닿은 육지 칸
        if not self.shore.any():
            return self.h, self.coast
        self._classify()
        self._cliffs()
        self._sea_stacks()
        self._beaches()
        self._rocky()
        if self.cfg.lagoons > 0:
            self._lagoons()
        return self.h, self.coast

    # --- 해안 성격 점수와 종류
    def _classify(self):
        cfg, S, gen, land, shore = self.cfg, self.S, self.gen, self.land, self.shore
        sea = self.sea
        k = max(int(S * 0.08) | 1, 9)
        frac = ndimage.uniform_filter(land.astype(np.float64), k, mode='nearest')    # 주변 육지 비율 (곶 0 ~ 만 1)
        rise = ndimage.maximum_filter(np.where(land, self.h, sea), max(int(S * 0.02), 5)) - sea   # 조금 안쪽 최고 높이
        self.rise = ndimage.uniform_filter(rise, 7)
        self.wob = fbm_offset(gen, S, S * 0.07, 3, 911.0)              # 같은 조건에서도 해안이 바뀌게
        # 작은 섬은 주변이 다 바다라 늘 곶으로 판정되므로, 땅덩어리 크기만큼 돌출도 비중을 줄이고
        # 낮은 땅은 절벽 점수를 깎는다 (뒤가 낮은데 절벽이 솟으면 담을 두른 것처럼 보인다)
        lab, n = ndimage.label(land)
        d_in = ndimage.distance_transform_edt(land)
        reach = ndimage.maximum(d_in, lab, np.arange(1, n + 1)) if n else np.zeros(0)
        size_f = np.clip(np.concatenate([[0.0], reach])[lab] / (S * 0.03), 0, 1)
        size_f = ndimage.grey_dilation(size_f, size=3)               # 해안 바로 앞 바다 칸에도 섬 크기를 넘긴다
        score = (0.9 * size_f * zscore(-frac, shore) + 0.8 * zscore(self.rise, shore)
                 + 1.1 * zscore(self.wob, shore) - 1.2 * np.clip(1 - self.rise / 0.05, 0, 1))
        score = ndimage.gaussian_filter(score, 2.0)

        s_shore = score[shore]
        self.cut_cliff = np.quantile(s_shore, 1 - cfg.cliffs)
        self.cut_beach = np.quantile(s_shore, cfg.beaches)
        kind_field = np.where(score >= self.cut_cliff, CLIFF,
                              np.where(score <= self.cut_beach, BEACH, ROCKY)).astype(np.uint8)

        # 해안 근처 칸은 가장 가까운 해안 칸의 종류를 따른다
        _, (self.iy, self.ix) = ndimage.distance_transform_edt(~shore, return_indices=True)
        self.near_kind = kind_field[self.iy, self.ix]
        self.near_score = score[self.iy, self.ix]
        self.d_shore = ndimage.distance_transform_edt(~shore)
        # 종류가 바뀌는 곳에서 지형이 뚝 끊기지 않게, 종류별 가중치를 해안을 따라 부드럽게 섞는다
        self.wC = ndimage.gaussian_filter((self.near_kind == CLIFF).astype(np.float64), 3.0)
        self.wB = ndimage.gaussian_filter((self.near_kind == BEACH).astype(np.float64), 3.0)
        self.wR = ndimage.gaussian_filter((self.near_kind == ROCKY).astype(np.float64), 3.0)
        self.edge_n = fbm_offset(gen, S, S * 0.03, 2, 233.0)           # 띠 폭과 앞바다 경계도 들쭉날쭉하게

    # --- 해식 절벽: 해안 띠를 들어 올려 바다에서 바로 솟게. 발치 바다는 깊게
    def _cliffs(self):
        h, sea, amt = self.h, self.sea, self.cfg.coast_variety
        land, ocean, d_shore, d_sea, wC = self.land, self.ocean, self.d_shore, self.d_sea, self.wC
        strong = np.clip(self.near_score - self.cut_cliff, 0, 1.5)
        cliff_w = 3.0 + 3.0 * strong + 1.5 * self.edge_n
        # 절벽 높이는 뒤쪽 실제 지형 높이를 넘지 않는다 (없던 담을 쌓지 않고 원래 경사를 가파르게 할 뿐)
        cliff_top = sea + np.minimum((0.045 + 0.035 * strong + 0.01 * self.wob) * amt, 0.85 * self.rise)
        fade = np.clip((cliff_w + 5 - d_shore) / 5.0, 0, 1) * wC
        target = sea + (cliff_top - sea) * (0.85 + 0.15 * np.clip(d_shore / np.maximum(cliff_w, 1), 0, 1))
        m = land & (fade > 0.01)
        h[m] = np.maximum(h[m], sea + (target[m] - sea) * fade[m])
        foot = ocean & (d_sea <= 4)
        deep = sea - 0.03 - 0.01 * d_sea
        h[foot] = np.minimum(h[foot], h[foot] + (deep[foot] - h[foot]) * np.clip(wC[foot] * 1.5 - 0.3, 0, 1))
        self.coast[land & (self.near_kind == CLIFF) & (d_shore <= cliff_w)] = CLIFF

    # --- 시스택: 절벽 앞바다 2~5칸에 2~5칸짜리 바위 덩어리를 드문드문
    def _sea_stacks(self):
        rng, S, h, sea, amt = self.rng, self.S, self.h, self.sea, self.cfg.coast_variety
        ocean, d_sea = self.ocean, self.d_sea
        cand = np.argwhere(ocean & (self.near_kind == CLIFF) & (self.wC > 0.7) & (d_sea >= 2.5) & (d_sea <= 5))
        n_stack = int(len(cand) * self.cfg.sea_stacks / 120)
        if not (n_stack and len(cand)):
            return
        for cy, cx in cand[rng.choice(len(cand), size=min(n_stack, len(cand)), replace=False)]:
            pts = [(cy, cx)]
            for _ in range(rng.integers(1, 5)):                  # 한 칸씩 이웃으로 자라는 작은 덩어리
                py, px = pts[rng.integers(len(pts))]
                dy, dx = [(0, 1), (1, 0), (0, -1), (-1, 0)][rng.integers(4)]
                pts.append((py + dy, px + dx))
            top = sea + min((0.03 + 0.03 * rng.random()) * amt, 0.85 * self.rise[cy, cx])
            for py, px in pts:
                if 0 <= py < S and 0 <= px < S and ocean[py, px]:
                    h[py, px] = top
                    self.coast[py, px] = CLIFF

    # --- 모래사장: 해안 띠를 해수면 바로 위로 낮고 평평하게, 앞바다도 얕게. 넓은 곳 뒤에는 사구
    def _beaches(self):
        S, gen, h, sea, amt = self.S, self.gen, self.h, self.sea, self.cfg.coast_variety
        land, ocean, d_shore, d_sea, wB = self.land, self.ocean, self.d_shore, self.d_sea, self.wB
        beach_w = (4.0 + 4.0 * np.clip(self.cut_beach - self.near_score, 0, 1.5) + 1.5 * self.edge_n) * amt
        t = np.clip(d_shore / np.maximum(beach_w, 1), 0, 1)
        flat = sea + 0.003 + 0.026 * t ** 1.5
        blend = np.clip((beach_w + 4 - d_shore) / 4.0, 0, 1) * wB
        m = land & (blend > 0.01)
        h[m] = np.minimum(h[m], h[m] + (flat[m] - h[m]) * blend[m])
        reach = 10.0 + 4.0 * self.edge_n
        shelf_w = np.clip(1.0 - d_sea / np.maximum(reach, 1), 0, 1) ** 0.7 * wB     # 바다 쪽으로 서서히
        shelf = ocean & (shelf_w > 0.01)
        shallow = sea - 0.006 - 0.022 * np.clip(d_sea / np.maximum(reach, 1), 0, 1)
        h[shelf] = np.maximum(h[shelf], h[shelf] + (shallow[shelf] - h[shelf]) * shelf_w[shelf])
        self.coast[land & (self.near_kind == BEACH) & (d_shore <= beach_w)] = BEACH
        # 사구: 넓은 모래사장 뒤쪽에 노이즈 얼룩으로
        dune_n = fbm_offset(gen, S, S * 0.02, 3, 377.0)
        dune = (land & (self.near_kind == BEACH) & (d_shore > beach_w * 0.6) & (d_shore < beach_w + 5)
                & (beach_w > 5.0) & (dune_n + 0.4 * np.clip(beach_w - 5, 0, 3) / 3 > 0.25))
        self.coast[dune] = DUNE

    # --- 석회암 바위 해안: 해안선을 잘게 들쭉날쭉하게 (작은 후미와 바위 곶). 모래가 생기지 않게 살짝 높인다
    def _rocky(self):
        S, gen, h, sea, amt = self.S, self.gen, self.h, self.sea, self.cfg.coast_variety
        land, ocean, d_shore, d_sea = self.land, self.ocean, self.d_shore, self.d_sea
        jag = fbm_offset(gen, S, S * 0.018, 3, 523.0)
        rocky_near = (self.near_kind == ROCKY) & (self.wR > 0.6)
        cove = land & rocky_near & (d_shore <= 2.5) & (jag > 0.42)
        cove = ndimage.binary_propagation(cove & ndimage.binary_dilation(ocean), mask=cove)   # 바다와 이어진 후미만
        h[cove] = sea - 0.008
        spur = ocean & rocky_near & (d_sea <= 2.5) & (jag < -0.42)
        spur = ndimage.binary_propagation(spur & ndimage.binary_dilation(land), mask=spur)    # 육지에 붙은 것만
        h[spur] = np.maximum(h[spur], sea + 0.03 * amt)
        land2 = (h >= sea) & (self.lakes == 0)
        raise_ = (sea + np.minimum((0.03 + 0.004 * d_shore) * amt, 0.7 * self.rise)
                  * np.clip((8.0 - d_shore) / 4.0, 0, 1) * self.wR)
        m = land2 & (d_shore <= 8)
        h[m] = np.maximum(h[m], raise_[m])
        self.coast[land2 & (self.near_kind == ROCKY) & (d_shore <= 3)] = ROCKY

    # --- 석호와 사주
    def _lagoons(self):
        """모래사장 해안 바로 뒤에 해안선을 따라 길쭉한 얕은 석호를 판다 (지중해 연안의 에탕처럼).

        바다 쪽 2~3칸은 모래톱(사주)으로 남기고, 그 뒤 땅을 낮춰 물을 채운다.
        석호 폭은 가운데가 넓고 양 끝으로 갈수록 가늘어지며 노이즈로 들쭉날쭉하다.
        모래톱 한 군데를 터서 바다와 통하는 물목을 두고, 뭍 쪽 기슭은 군데군데 염습지가 된다.
        """
        cfg, rng, S, gen = self.cfg, self.rng, self.S, self.gen
        h, sea, coast = self.h, self.sea, self.coast
        near_kind, d_shore, iy, ix, ocean = self.near_kind, self.d_shore, self.iy, self.ix, self.ocean
        shore_beach = (d_shore < 0.5) & (near_kind == BEACH) & (self.wB > 0.85)
        cand = np.argwhere(shore_beach)
        if not len(cand):
            return
        width_n = fbm_offset(gen, S, S * 0.012, 2, 733.0)
        marsh_n = fbm_offset(gen, S, S * 0.012, 3, 811.0)
        used = np.zeros((S, S), bool)
        made, tries = 0, 0
        while made < cfg.lagoons and tries < 40:
            tries += 1
            sy, sx = cand[rng.integers(len(cand))]
            if used[max(sy - 30, 0):sy + 30, max(sx - 30, 0):sx + 30].any():
                continue
            R = rng.uniform(10, 22)                                   # 해안을 따라 반 길이
            wmax = rng.uniform(3.5, 6.0)                              # 가장 넓은 곳 폭
            r = np.hypot(iy - sy, ix - sx)                            # 가장 가까운 해안 칸이 기준점에서 얼마나 먼지
            seg = (r < R) & (near_kind == BEACH)
            barrier = 2.0 + 0.8 * (width_n > 0.3)
            wl = wmax * np.clip(1 - (r / R) ** 2, 0, 1) + 1.2 * width_n
            lag = seg & ~ocean & (d_shore >= barrier) & (d_shore < barrier + wl) & (h < sea + 0.05)
            lag = ndimage.binary_opening(lag)                         # 한 칸짜리 가시 제거
            lab, n = ndimage.label(lag)
            if not n:
                continue
            sizes = ndimage.sum_labels(np.ones((S, S)), lab, np.arange(1, n + 1))
            lag = lab == (np.argmax(sizes) + 1)
            if lag.sum() < 25:
                continue
            inlet = self._inlet(lag, sy, sx, R, barrier)
            # 뭍 쪽 기슭의 염습지 (군데군데)
            outer = lag & ~ndimage.binary_erosion(lag)
            inland_edge = outer & (d_shore > barrier + 0.8)
            marsh = ndimage.binary_dilation(inland_edge) & lag & (marsh_n > 0.0)
            water = lag & ~marsh
            if water.sum() < 20:
                continue
            # 석호 둘레 땅은 낮게 이어지게 (갑자기 솟은 단면선이 생기지 않게)
            ring = ndimage.distance_transform_edt(~lag)
            near = ~ocean & ~lag & (ring <= 4)
            h[near] = np.minimum(h[near], sea + 0.004 + 0.007 * ring[near])
            bar = seg & ~ocean & (d_shore < barrier) & ~inlet
            h[bar] = np.minimum(np.maximum(h[bar], sea + 0.004), sea + 0.01)
            coast[bar] = BEACH
            dw = ndimage.distance_transform_edt(water)
            h[water] = sea - 0.004 - 0.012 * np.clip(dw[water] / 3.0, 0, 1)
            coast[water] = LAGOON
            h[inlet] = np.minimum(h[inlet], sea - 0.006)
            coast[inlet] = LAGOON
            h[marsh] = sea + 0.003
            coast[marsh] = MARSH
            used |= lag
            made += 1

    def _inlet(self, lag, sy, sx, R, barrier):
        """물목: 석호 한쪽(가운데에서 조금 비켜난 곳)에서 바다까지 모래톱을 튼다."""
        S, iy, ix = self.S, self.iy, self.ix
        ly, lx = np.argwhere(lag).T
        rr = np.hypot(iy[ly, lx] - sy, ix[ly, lx] - sx)
        pick = np.argsort(np.abs(rr - R * self.rng.uniform(0.3, 0.7)))[0]
        py, px = ly[pick], lx[pick]
        qy, qx = iy[py, px], ix[py, px]                            # 그 앞의 해안 칸
        inlet = np.zeros((S, S), bool)
        for t in np.linspace(0, 1.4, 20):                          # 해안 칸보다 조금 더 바다 쪽까지
            yy, xx = py + (qy - py) * t, px + (qx - px) * t
            y0, x0 = int(round(yy)), int(round(xx))
            inlet[max(y0 - 1, 0):y0 + 2, max(x0 - 1, 0):x0 + 2] = True
        return inlet & ~lag & (self.d_shore < barrier + 1.5)
