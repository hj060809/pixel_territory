"""강 다듬기: 굽이치는 강, 범람원, 우각호, 삼각주 (RiverRefiner).

물이 모이는 경로(D8)로 찾은 강은 격자를 따라 곧게 뻗는다. 여기서는
1. 강을 상류에서 하류로 이어지는 중심선으로 뽑고 (본류 먼저, 지류는 본류에 합류)
2. 평지일수록 크게 옆으로 굽이치게 하고 (경사가 급하면 거의 그대로, 큰 강일수록 굽이가 크고 길다)
3. 평지 구간의 강 양옆을 강 높이 근처로 평평하게 골라 범람원을 만들고
4. 크게 굽은 곳 바깥에 가끔 떨어져 나간 초승달 호수(우각호)를 두고
5. 큰 강이 평지를 지나 바다로 들어가는 곳에 부채꼴 퇴적지와 여러 갈래 물길(삼각주)을 만든다.

run()이 돌려주는 것은 '고친 높이맵', '물길이 지나는 칸', '그 폭', '우각호 칸'이다.
실제로 해수면 아래로 파는 건 engine.mapgen.stages.water가 한다.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.core.noise import smooth_1d


def trace_paths(river: np.ndarray, down: np.ndarray, S: int) -> list[np.ndarray]:
    """강 칸들을 상류→하류 선들로. 긴 강부터 그려서 지류는 이미 그린 강에 닿으면 멈춘다 (합류점 포함)."""
    rf = river.ravel()
    idx = np.flatnonzero(rf)
    has_parent = np.zeros(S * S, bool)
    d = down[idx]
    ok = d >= 0
    has_parent[d[ok][rf[d[ok]]]] = True
    heads = idx[~has_parent[idx]]

    def follow(h, visited=None):
        path, cur = [], h
        while cur >= 0 and rf[cur] and (visited is None or not visited[cur]):
            path.append(cur)
            if visited is not None:
                visited[cur] = True
            cur = down[cur]
        if cur >= 0:
            path.append(cur)                      # 합류점이나 바다/호수로 나가는 칸까지
        return path

    order = sorted(heads, key=lambda h: -len(follow(h)))
    visited = np.zeros(S * S, bool)
    return [np.array(p) for p in (follow(h, visited) for h in order) if len(p) >= 2]


class RiverRefiner:
    def __init__(self, cfg, rng, S, h, river, flow, down, thr, ocean, lakes):
        self.cfg, self.rng, self.S = cfg, rng, S
        self.sea = cfg.sea_level
        self.h = h.copy()
        self.river, self.flow, self.down, self.thr = river, flow, down, thr
        self.ocean, self.lakes = ocean, lakes
        self.water = (self.h < self.sea) | (lakes > 0)
        self.land = ~self.water
        # 강이 촘촘한 곳에서는 덜 굽이친다 (가까운 지류끼리 굽이치다 서로 얽히지 않게)
        self.crowd = np.clip(1.5 - ndimage.uniform_filter(river.astype(np.float32), 15) * 9.0, 0.15, 1.0)

        self.chan = np.zeros((S, S), bool)
        self.chan_w = np.zeros((S, S), np.float32)
        self.oxbow = np.zeros((S, S), bool)
        self.newpos = {}                                   # 원래 칸 → 굽이친 뒤 위치 (지류가 본류에 이어지도록)
        self.plain_amp = np.zeros((S, S), np.float32)      # 범람원 폭을 정할 굽이 크기 (원래 강 칸에 기록)
        self.river_h = np.zeros((S, S), np.float32)
        self.mouths = []                                   # 삼각주 후보 하구 [(위치, 방향, 폭)]

    def run(self):
        """반환: (고친 높이, 물길 칸 bool, 물길 폭 float, 우각호 칸 bool)"""
        for path in trace_paths(self.river, self.down, self.S):
            self._refine_path(path)
        self._floodplains()
        if self.cfg.deltas:
            self._deltas()
        return self.h, self.chan, self.chan_w, self.oxbow

    def _width_of(self, f):
        return np.clip(np.log2(np.maximum(f, self.thr) / self.thr) * 0.6, 0, self.cfg.river_max_width)

    def _mark(self, y, x, w):
        """물길 칸 표시 (폭은 지나간 강 중 가장 넓은 것)."""
        yi, xi = int(round(y)), int(round(x))
        if 0 <= yi < self.S and 0 <= xi < self.S:
            self.chan[yi, xi] = True
            self.chan_w[yi, xi] = max(self.chan_w[yi, xi], w)

    # --- 강 하나
    def _refine_path(self, path):
        S = self.S
        ys, xs = np.divmod(path, S)
        pts = np.stack([ys, xs], 1).astype(np.float64)
        n = len(pts)
        w = self._width_of(self.flow.ravel()[path])
        if n >= 10:
            new, flat = self._meander(path, ys, xs, pts, w)
        else:
            new, flat = pts, np.zeros(n)

        # 굽이친 중심선을 촘촘히 이어서 물길로 (지나가는 칸마다 폭 기록)
        for i in range(len(new) - 1):
            a, b = new[i], new[i + 1]
            k = int(np.ceil(np.linalg.norm(b - a) * 2)) + 1
            for t in np.linspace(0, 1, k):
                self._mark(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, w[i])

        # 바다로 들어가는 큰 강의 하구 (삼각주 후보). 하구 근처가 평지인 강만 (가파른 해안은 제외)
        ey, ex = divmod(int(path[-1]), S)
        if self.ocean[ey, ex] and n >= 15 and w[-1] >= self.cfg.delta_min_width and flat[-15:].mean() > 0.2:
            seg = pts[-10:]
            direction = seg[-1] - seg[0]
            self.mouths.append((new[-1].copy(), direction / (np.linalg.norm(direction) + 1e-9), float(w[-1])))

    def _meander(self, path, ys, xs, pts, w):
        """평지일수록 크게 옆으로 굽이친 중심선. 반환: (새 중심선, 평지 정도)"""
        cfg, rng, S = self.cfg, self.rng, self.S
        n = len(pts)
        sm = ndimage.uniform_filter1d(pts, size=7, axis=0, mode='nearest')     # 계단을 펴서 부드럽게
        tan = np.gradient(sm, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)
        ds = np.linalg.norm(np.diff(sm, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(ds)])
        # 평지일수록 크게 굽이친다 (강을 따라 높이가 거의 안 변하는 곳)
        hp = ndimage.uniform_filter1d(self.h.ravel()[path], size=9, mode='nearest')
        slope = np.abs(np.gradient(hp)) / (np.gradient(s) + 1e-6)
        flat = np.clip(1.0 - slope / 0.0025, 0, 1)
        flat = ndimage.uniform_filter1d(flat, size=15, mode='nearest')
        # 굽이 크기는 노이즈로 들쭉날쭉하게 (규칙적인 물결무늬가 되지 않게)
        # 작은 실개천은 조금만, 큰 강은 크게
        amp = (cfg.meander * (1.5 + 3.5 * w) * flat * self.crowd.ravel()[path]
               * np.clip(0.75 + 0.45 * smooth_1d(rng, n, 30), 0.3, 1.2))
        lam = 12.0 + 8.0 * w
        phase = 2 * np.pi * np.cumsum(np.concatenate([[0], ds]) / lam[:]) + rng.uniform(0, 2 * np.pi)
        taper = np.clip(np.minimum(s, s[-1] - s) / 6.0, 0, 1)       # 양 끝은 원래 자리에 맞춘다
        disp = amp * np.sin(phase) * taper
        new = sm + nrm * disp[:, None]
        # 굽이친 자리가 물(바다, 호수)이면 그만큼 덜 굽이친다
        for _ in range(2):
            yi = np.clip(np.rint(new[:, 0]).astype(int), 0, S - 1)
            xi = np.clip(np.rint(new[:, 1]).astype(int), 0, S - 1)
            bad = self.water[yi, xi]
            bad[-3:] = False
            disp[bad] *= 0.3
            new = sm + nrm * disp[:, None]
        # 지류 끝은 이미 굽이친 본류 위치로 이어 붙인다
        end = path[-1]
        if end in self.newpos:
            tgt = np.array(self.newpos[end])
            k = min(12, n)
            wgt = np.linspace(0, 1, k)[:, None]
            new[-k:] = new[-k:] * (1 - wgt) + tgt * wgt
        for c, p in zip(path, new):
            self.newpos.setdefault(int(c), (float(p[0]), float(p[1])))
        self.plain_amp[ys, xs] = np.maximum(self.plain_amp[ys, xs], (amp * flat).astype(np.float32))
        self.river_h[ys, xs] = self.h[ys, xs]

        self._oxbows(new, nrm, amp, phase, taper, disp)
        return new, flat

    def _oxbows(self, new, nrm, amp, phase, taper, disp):
        """크게 굽은 곳(굽이 꼭짓점) 바깥쪽에 가끔 초승달 호수."""
        S, rng = self.S, self.rng
        peaks = np.flatnonzero((np.abs(np.sin(phase)) > 0.98) & (amp > 3.0) & (taper > 0.9))
        last = -100
        for i in peaks:
            if i - last < 6 or rng.random() > self.cfg.oxbow_chance:
                continue
            last = i
            side = np.sign(disp[i]) or 1.0
            r = 0.7 * amp[i] + 1.5
            c = new[i] + nrm[i] * side * (r + 3.0)
            a0 = np.arctan2(nrm[i, 1] * side, nrm[i, 0] * side)          # 강 반대쪽으로 열린 초승달
            for a in np.linspace(a0 - 1.9, a0 + 1.9, 30):
                py, px = c[0] - np.cos(a) * r, c[1] - np.sin(a) * r
                yi, xi = int(round(py)), int(round(px))
                if 0 <= yi < S and 0 <= xi < S and self.land[yi, xi]:
                    self.oxbow[yi, xi] = True

    # --- 범람원
    def _floodplains(self):
        """평지 구간 강 양옆을 강 높이 근처로 평평하게."""
        cfg, h, sea = self.cfg, self.h, self.sea
        if not (cfg.floodplain > 0 and self.plain_amp.max() > 0):
            return
        src = self.plain_amp > 0
        d, (iy, ix) = ndimage.distance_transform_edt(~src, return_indices=True)
        amp_near = self.plain_amp[iy, ix]
        width = (3.0 + 1.6 * amp_near) * cfg.floodplain
        hr = self.river_h[iy, ix]
        inside = self.land & (d < width) & (amp_near > 0.5)
        target = hr + 0.003 + 0.02 * (d / np.maximum(width, 1e-6)) ** 2
        h[inside] = np.minimum(h[inside], np.maximum(target[inside], sea + 0.003))

    # --- 삼각주
    def _deltas(self):
        """하구에서 바다 쪽으로 갈래 물길을 먼저 뻗고, 그 물길을 따라 땅이 쌓인다 (새발 모양)."""
        for (my, mx), dvec, w in self.mouths:
            lines = self._distributaries(my, mx, dvec, w)
            if not lines:
                continue
            self._levees(np.array(lines), w)
            self.land = (self.h >= self.sea) & (self.lakes == 0)

    def _distributaries(self, my, mx, dvec, w):
        """갈래 물길 점들 [(y, x, 하구에서 얼마나 왔는지 0~1)]."""
        rng = self.rng
        R = 14.0 + 8.0 * w                                      # 갈래 물길 길이
        n_d = rng.integers(2, 4)
        lines = []
        for k in range(n_d):
            a = np.arctan2(dvec[0], dvec[1]) + (k - (n_d - 1) / 2) * (1.3 / max(n_d - 1, 1)) + rng.normal(0, 0.15)
            py, px = float(my), float(mx)
            for step in range(int(R)):
                a += rng.normal(0, 0.18)
                py, px = py + np.sin(a), px + np.cos(a)
                lines.append((py, px, step / R))
        return lines

    def _levees(self, L, w):
        """물길 양옆에 쌓이는 땅: 하구 쪽은 넓고 끝으로 갈수록 가늘다. 하구 쪽은 모래보다 높아 풀이 자라고, 끝만 모래톱."""
        S, sea = self.S, self.sea
        y0, y1 = int(max(L[:, 0].min() - 8, 0)), int(min(L[:, 0].max() + 9, S))
        x0, x1 = int(max(L[:, 1].min() - 8, 0)), int(min(L[:, 1].max() + 9, S))
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        best = np.full(yy.shape, -1.0)                          # 가장 두꺼운 둑까지의 여유 (양수면 땅)
        prog = np.zeros(yy.shape)
        for py, px, t in L:
            reach = 1.5 + (4.0 + 2.0 * w) * (1.0 - t)
            m = reach - np.hypot(yy - py, xx - px)
            upd = m > best
            best[upd], prog[upd] = m[upd], t
        sub_ocean = self.ocean[y0:y1, x0:x1]
        bank = (best > 0) & sub_ocean
        hs = self.h[y0:y1, x0:x1]
        hs[bank] = sea + 0.004 + 0.035 * (1.0 - prog[bank]) * np.clip(best[bank] / 3.0, 0.3, 1.0)
        for py, px, t in L:
            self._mark(py, px, max(w * (1.0 - t) * 0.6, 0.0))
