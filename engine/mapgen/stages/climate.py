"""6단계 기후: 기온과 습도 지도 (0~1). 셰이더가 이것으로 바이옴(식생 팔레트, 수목한계선, 설선)을 고른다.

1. 바탕: 위치에 따른 '기후 영역'. 지도를 몇 개의 영역으로 나누고 영역마다 기후 하나(기온, 습도)를 준다.
   - 자동: climate_zones개 영역의 자리와 기후를 무작위로 정한다 (기후는 temperature_range, moisture_range 안에서).
     영역이 1개면 지도 전체가 한 기후 (범위 가운데).
   - 직접 지정: zones = ((x, y, 기온, 습도, 크기), ...) 를 주면 그 자리들이 영역이 된다 (x, y는 지도 크기 비율,
     크기는 생략하면 1. 클수록 영역이 넓다). 주면 자동 영역은 쓰지 않는다.
   - 경계: 가장 가까운 영역을 따르되(보로노이), zone_wobble만큼 노이즈로 구불거리고
     zone_border 폭(지도 크기 비율)만큼 서서히 섞인다.
2. 조정: 영역 기후 위에 국지적으로 더한다 (세기 0이면 끈다).
   - 고도 (temp_altitude): 높을수록 추워진다
   - 바다 완화 (temp_coast): 해안은 극단(아주 덥거나 추움)이 누그러진다
   - 지역 얼룩 (temp_patches, moist_patches, patch_scale): 영역 안에서도 지역마다 조금씩 다르게
   - 바람과 비그늘 (moist_wind, wind_dir, rain_shadow): 바람 받는 산 앞은 더 습하고, 산 너머는 더 마른다
   - 물가 (freshwater_moisture, coast_moisture): 강·호수 가까이는 좁고 세게, 바닷가는 넓고 약하게 습해진다

기온 0 ≈ 툰드라, 1 ≈ 사막/열대.  습도 0 ≈ 메마름, 1 ≈ 아주 습함.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from engine.mapgen.core.noise import fbm


def climate(cfg, gen, S, h, ocean, lakes, rivers):
    """반환: (기온, 습도) float32 (S, S), 0~1."""
    return ClimateBuilder(cfg, gen, S, h, ocean, lakes, rivers).run()


class ClimateBuilder:
    def __init__(self, cfg, gen, S, h, ocean, lakes, rivers):
        self.cfg, self.gen, self.S, self.h = cfg, gen, S, h
        self.ocean, self.lakes, self.rivers = ocean, lakes, rivers
        self.sea = cfg.sea_level

    def run(self):
        T, M = self._zones()
        T = self._altitude(T)
        T = self._coast_moderation(T)
        T, M = self._patches(T, M)
        M = self._wind(M)
        M = M + self._waterside() * (1.0 - M) * 0.6                    # 물가는 더 습하게 (영역 기후를 뒤집지 않을 만큼)
        return np.clip(T, 0, 1).astype(np.float32), np.clip(M, 0, 1).astype(np.float32)

    # --- 1. 바탕: 기후 영역
    def _zones(self):
        cfg, S = self.cfg, self.S
        zones = zone_list(cfg, land=~self.ocean)
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
        # 경계가 곧은 선이 되지 않게 좌표를 비튼다
        amp = cfg.zone_wobble * S * 0.12
        wy = yy + amp * fbm(self.gen, S, S * 0.25, 3, 8100.0)
        wx = xx + amp * fbm(self.gen, S, S * 0.25, 3, 8300.0)
        # 영역마다 거리 (크기가 클수록 같은 거리도 가깝게 친다). 가장 가까운 영역을 중심으로 부드럽게 섞는다
        d = np.stack([np.hypot(wx - x * S, wy - y * S) / max(size, 0.05) for x, y, _, _, size in zones])
        border = max(cfg.zone_border * S, 1e-3)
        w = np.exp(-(d - d.min(0)) / border)
        w /= w.sum(0)
        T = sum(wi * z[2] for wi, z in zip(w, zones))
        M = sum(wi * z[3] for wi, z in zip(w, zones))
        return T, M

    # --- 2. 조정
    def _altitude(self, T):
        """높을수록 추워진다 (가장 높은 곳에서 temp_altitude × 0.5만큼)."""
        if self.cfg.temp_altitude <= 0:
            return T
        alt = np.clip((self.h - self.sea) / (1 - self.sea), 0, 1)
        return T - self.cfg.temp_altitude * 0.5 * alt

    def _coast_moderation(self, T):
        """해안(땅)은 극단이 누그러진다: 바다 가까울수록 온화한 기온(0.55) 쪽으로 당긴다."""
        if self.cfg.temp_coast <= 0 or not self.ocean.any():
            return T
        d = ndimage.distance_transform_edt(~self.ocean) / self.S
        w = self.cfg.temp_coast * 0.6 * np.exp(-d / 0.05) * ~self.ocean   # 바다 자체는 그대로 (얼어야 할 바다가 녹지 않게)
        return T + (0.55 - T) * w

    def _patches(self, T, M):
        """지역 얼룩: 영역 안에서도 지역마다 조금씩 다르게."""
        cfg, S = self.cfg, self.S
        scale = max(S * cfg.patch_scale, 4.0)
        if cfg.temp_patches > 0:
            T = T + cfg.temp_patches * 0.15 * fbm(self.gen, S, scale, 3, 8500.0) * 1.4
        if cfg.moist_patches > 0:
            M = M + cfg.moist_patches * 0.2 * fbm(self.gen, S, scale, 3, 8700.0) * 1.4
        return T, M

    def _wind(self, M):
        """바람과 비그늘: 바람 받는 쪽은 더 습하고 산 너머는 더 마른다 (영역 습도를 ±로 조정)."""
        if self.cfg.moist_wind <= 0:
            return M
        return M + self.cfg.moist_wind * 0.35 * (self._wind_field() - 0.5)

    def _wind_field(self):
        """바람이 향하는 방향(wind_dir)으로 지도를 훑으며 수분을 옮긴다 (0~1, 클수록 습함).
        물 위에서는 수분이 채워지고, 땅에서는 조금씩, 오르막에서는 많이 비로 떨어진다."""
        cfg, S = self.cfg, self.S
        ang = cfg.wind_dir
        land = (self.h >= self.sea) & (self.lakes == 0) & ~self.ocean
        # 바람이 +x 방향으로 불도록 지도를 돌린다 (돌린 뒤 왼쪽에서 오른쪽으로 훑는다)
        pad_h = np.pad(self.h, S // 2, mode='edge')
        pad_w = np.pad((self.ocean | (self.lakes > 0)).astype(np.float64), S // 2, mode='edge')
        rh = ndimage.rotate(pad_h, ang, reshape=False, order=1, mode='nearest')
        rw = ndimage.rotate(pad_w, ang, reshape=False, order=0, mode='nearest') > 0.5
        n_rows, n_cols = rh.shape
        carried = np.ones(n_rows)
        rain = np.zeros_like(rh)
        prev = rh[:, 0]
        uplift = 60.0 * cfg.rain_shadow
        for x in range(n_cols):
            col = rh[:, x]
            over_water = rw[:, x]
            carried = np.where(over_water, carried + (1 - carried) * 0.08, carried)
            rise = np.maximum(col - prev, 0)
            r = np.where(over_water, 0.0, carried * np.clip(0.003 + uplift * rise, 0, 0.5))
            carried = carried - r
            rain[:, x] = carried + r * 8
            prev = col
        back = ndimage.rotate(rain, -ang, reshape=False, order=1, mode='nearest')
        p = S // 2
        out = ndimage.gaussian_filter(back[p:p + S, p:p + S], S * 0.025)
        ref = out[land] if land.any() else out
        a, b = np.percentile(ref, [2, 98])
        return np.clip((out - a) / max(b - a, 1e-6), 0, 1)

    def _waterside(self):
        """물가에서 더해지는 습도 비율 (0~1): 민물(강, 호수)은 좁고 세게, 바닷가는 넓고 약하게."""
        cfg, S = self.cfg, self.S
        out = np.zeros((S, S))
        fresh = (self.lakes > 0) | (self.rivers > 0)
        if cfg.freshwater_moisture > 0 and fresh.any():
            d = ndimage.distance_transform_edt(~fresh) / S
            out += cfg.freshwater_moisture * np.exp(-d / 0.025)
        if cfg.coast_moisture > 0 and self.ocean.any():
            d = ndimage.distance_transform_edt(~self.ocean) / S
            out += cfg.coast_moisture * np.exp(-d / 0.05)
        return np.clip(out, 0, 1)


def _farthest(rng, cand, n, first=None, weight=None):
    """후보 점들 중 서로 최대한 멀리 떨어진 n개를 차례로 고른다 (가장 먼 점 고르기).
    weight: 후보마다 거리에 곱하는 배율 (작으면 덜 뽑힌다)."""
    weight = np.ones(len(cand)) if weight is None else weight
    idx = [int(rng.integers(len(cand))) if first is None else first]
    d = np.linalg.norm(cand - cand[idx[0]], axis=1)
    while len(idx) < n:
        j = int(np.argmax(d * weight + rng.uniform(0, 1e-6, len(d))))   # 같은 거리면 무작위로
        idx.append(j)
        d = np.minimum(d, np.linalg.norm(cand - cand[j], axis=1))
    return cand[idx]


SEA_WEIGHT = 0.35          # 영역 중심 후보가 바다면 거리를 이만큼만 쳐 준다 (중심이 주로 육지에 오게)


def zone_list(cfg, land=None):
    """[(x, y, 기온, 습도, 크기)]. 직접 지정한 영역이 있으면 그것, 없으면 자동으로.

    자동일 때는 기후를 범위 안에서 서로 최대한 다르게 고른다 (범위 사각형의 모서리부터: 2개면 대각선 양 끝,
    4개면 네 모서리). 자리는 지도 위에 서로 멀리 떨어지게 놓되 주로 육지에 (land: 육지 마스크).
    어느 자리에 어느 기후를 둘지는 _assign (아주 더운 곳과 아주 추운 곳이 맞붙지 않게)."""
    if cfg.zones:
        out = []
        for z in cfg.zones:
            x, y, t, m = (float(v) for v in list(z)[:4])
            size = float(z[4]) if len(z) > 4 else 1.0
            out.append((x, y, t, m, size))
        return out
    rng = np.random.default_rng(cfg.seed + 7_777)                # 앞 단계의 난수와 섞이지 않게 따로
    n = max(int(cfg.climate_zones), 1)
    t_lo, t_hi = cfg.temperature_range
    m_lo, m_hi = cfg.moisture_range
    if n == 1:                                                   # 한 기후면 범위 가운데
        return [(0.5, 0.5, (t_lo + t_hi) / 2, (m_lo + m_hi) / 2, 1.0)]
    # 기후: 범위를 0~1로 펴서 격자 후보 중 서로 가장 먼 것들 (첫 점은 네 모서리 중 하나)
    g = np.linspace(0, 1, 9)
    cand = np.array([(a, b) for a in g for b in g])
    corners = [i for i, (a, b) in enumerate(cand) if a in (0, 1) and b in (0, 1)]
    picks = _farthest(rng, cand, n, first=corners[rng.integers(4)])
    ts = t_lo + (t_hi - t_lo) * picks[:, 0]
    ms = m_lo + (m_hi - m_lo) * picks[:, 1]
    # 자리: 지도 위 후보 중 서로 가장 먼 것들 (가장자리에서 조금 안쪽). 바다 후보는 덜 뽑힌다
    cand = rng.uniform(0.12, 0.88, (400, 2))
    weight, first = None, None
    if land is not None and land.any():
        H, W = land.shape
        on_land = land[(cand[:, 1] * H).astype(int), (cand[:, 0] * W).astype(int)]
        weight = np.where(on_land, 1.0, SEA_WEIGHT)
        if on_land.any():
            first = int(rng.choice(np.flatnonzero(on_land)))    # 첫 자리는 육지에서
    pos = _farthest(rng, cand, n, first=first, weight=weight)
    order = _assign(rng, pos, ts, cfg.zone_contrast)
    return [(pos[i, 0], pos[i, 1], ts[k], ms[k], 1.0) for i, k in enumerate(order)]


def _assign(rng, pos, ts, limit):
    """자리마다 어느 기후를 둘지 한 번에 정한다 (자리 i에 기후 order[i]). 방향은 정하지 않는다.

    1. 가장 더운 기후와 가장 추운 기후를 서로 가장 먼 두 자리에 (어느 쪽이 어디인지는 무작위).
    2. 나머지는 극단적인 기후(범위 가운데서 먼 것)부터, 이미 놓인 영역과 기온 차가 limit를 넘는 만큼
       가까울수록 무거운 벌점이 가장 적은 빈자리에 놓는다. 벌점이 같으면(맞붙을 걱정이 없으면) 무작위.
    3. 두 자리씩 맞바꿔 보며 벌점을 더 줄인다."""
    n = len(pos)
    dist = np.linalg.norm(pos[:, None] - pos[None], axis=2)
    near = 1.0 / (dist + 0.05) ** 2                                       # 가까울수록 크게
    order = np.full(n, -1)
    hot, cold = int(np.argmax(ts)), int(np.argmin(ts))
    a, b = np.unravel_index(np.argmax(dist), dist.shape)
    if rng.random() < 0.5:
        a, b = b, a
    order[a], order[b] = hot, cold
    rest = [k for k in np.argsort(-np.abs(ts - ts.mean())) if k not in (hot, cold)]
    for k in rest:
        free = np.flatnonzero(order < 0)
        placed = np.flatnonzero(order >= 0)
        over = np.maximum(np.abs(ts[k] - ts[order[placed]]) - limit, 0) ** 2
        cost = (over[None, :] * near[np.ix_(free, placed)]).sum(1)
        cost += rng.uniform(0, 1e-9, len(free))                           # 같으면 무작위
        order[free[int(np.argmin(cost))]] = k
    # 3. 다듬기: 두 자리의 기후를 맞바꿔 벌점이 줄면 바꾼다 (더 줄지 않을 때까지)
    def total(o):
        over = np.maximum(np.abs(ts[o][:, None] - ts[o][None]) - limit, 0) ** 2
        return (over * near).sum()
    cur = total(order)
    improved = True
    while improved:
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                order[[i, j]] = order[[j, i]]
                c = total(order)
                if c < cur - 1e-12:
                    cur, improved = c, True
                else:
                    order[[i, j]] = order[[j, i]]
    return order
