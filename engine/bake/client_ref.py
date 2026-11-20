"""브라우저 사양 (실행할 수 있는 파이썬판): 지도 묶음만으로 화면 한 장을 그린다.

엔진의 장면/셰이더 객체는 쓰지 않는다. 쓰는 것은
- 묶음 (meta, arrays)
- 지도와 상관없는 노이즈를 만드는 함수: shader._fbm(색 노이즈), water.water_noise_fields / ridge_noise (물결)
- 물결 표본 계산 (water._sample_loop)
웹 클라이언트(3단계 TypeScript/WebGL)는 이 파일을 그대로 옮긴다. engine.render.frame.FrameRenderer와 같은 그림이 나와야 한다
(묶음의 정밀도를 줄인 만큼 경계의 몇 칸은 다를 수 있다 — tests/test_bake.py가 비율을 잰다).
"""
from __future__ import annotations

import numpy as np
import opensimplex

from engine.bake.bundle import decode
from engine.render.shader import _fbm
from engine.render.water import _sample_loop, ridge_noise, water_noise_fields

try:
    from numba import njit
    _sample = njit(cache=True, nogil=True)(_sample_loop)
except ImportError:
    _sample = _sample_loop


def bayer(meta, H, W):
    b = np.asarray(meta['shader']['bayer4'], np.float64)
    return np.tile(b, (H // 4 + 1, W // 4 + 1))[:H, :W]


class BundleRenderer:
    def __init__(self, meta: dict, arrays: dict):
        self.meta, self.A = meta, arrays
        H, W = self.H, self.W = meta['H'], meta['W']
        F = meta['flags']
        fl = arrays['flags']
        self.water_l = (fl & F['water']) > 0                 # 셰이더가 물로 칠한 칸 (layers['water'])
        self.near_land = (fl & F['near_land']) > 0
        self.ice_zone = (fl & F['ice_zone']) > 0
        self.surf_water = (fl & F['surf_water']) > 0         # 빛/하늘 반사용 물 (Surface.water)
        self.wave = (fl & F['wave']) > 0
        self.thresh = bayer(meta, H, W)
        self._season_prepare()
        self._light_prepare()
        self._water_prepare()

    # ------------------------------------------------------------- 계절 칠하기 (seasons.SeasonPainter.paint)
    def _season_prepare(self):
        m, A, s = self.meta, self.A, self.meta['shader']
        M = m['materials']
        self.pal = A['palettes']
        self.flat_pal = self.pal.reshape(-1, 3)
        self.n_mat, self.n_shade = M['n_mat'], M['n_shade']
        T = decode('unit16', A['temperature'])
        self.amp = np.clip((0.85 - T) / 0.35, 0, 1).astype(np.float32)
        self.amp_ice = np.clip((0.35 - T) / 0.25, 0, 1).astype(np.float32)
        self.dither = np.roll(self.thresh.astype(np.float32), (1, 3), axis=(0, 1))
        self.mat0 = A['pre'].astype(np.int32)
        self.idx0 = A['idx'].astype(np.int32)
        self.idx_land = A['idx_land'].astype(np.int32)
        self.snow_ok = ~self.water_l & (A['pre'] != M['ICE'])
        self.snow_cover = decode('margin', A['snow_cover'])
        self.snow_old = decode('margin', A['snow_old'])
        self.sea_ice = decode('margin', A['sea_ice'])
        self.veg_mask = np.isin(np.arange(self.n_mat), M['vegetation'])
        self.foam = self.water_l & self.near_land
        alt = decode('unit16', A['alt'])
        cool = np.asarray(s['cool'], np.float64)
        self.tint = (alt - 0.3)[..., None] * cool * s['altitude_tint'] if s['altitude_tint'] > 0 else None
        # 색 노이즈 (지도와 상관없다: 크기와 시드로만 정해진다)
        if s['color_noise'] > 0:
            gen = opensimplex.OpenSimplex(s['seed'])
            warm = _fbm(gen, self.H, self.W, s['color_noise_scale'], 3, 0.0)
            bright = _fbm(gen, self.H, self.W, s['color_noise_scale'] * 0.7, 3, 1000.0)
            delta = (warm[..., None] * np.asarray(s['warm']) + bright[..., None] * np.asarray(s['bright']) * 0.6) * s['color_noise']
            self.noise_delta = delta                          # 셰이더처럼 배정밀도 그대로
        else:
            self.noise_delta = None

    def paint(self, weights=None):
        """(봄, 여름, 가을, 겨울) 비중으로 칠한 낮 이미지와 바다 얼음 마스크."""
        s, M = self.meta['shader'], self.meta['materials']
        neutral = weights is None
        w = np.array([0.0, 1.0, 0.0, 0.0]) if neutral else np.asarray(weights, float)
        mat, idx = self.mat0, self.idx0
        if neutral:
            variant = np.ones(mat.shape, np.int32)
        else:
            a, u = self.amp, self.dither
            p_wi, p_au, p_sp = w[3] * a, w[2] * a, w[0] * a
            variant = np.select([u < p_wi, u < p_wi + p_au, u < p_wi + p_au + p_sp], [3, 2, 0], 1).astype(np.int32)
        shift = 0.0 if neutral else self.amp * (w[3] * 1.0 + w[2] * 0.25 + w[0] * 0.3 - w[1] * 0.3) * 0.10
        cover = self.snow_cover + shift / s['snow_blend']
        old = self.snow_old - shift / (4 * s['snow_blend'])
        snow = self.snow_ok & (cover > 0)
        snow_mat = np.where(self.ice_zone, M['ICE'], np.where(old > 0, M['SNOW_OLD'], M['SNOW']))
        ice_shift = 0.0 if neutral else self.amp_ice * (w[3] - 0.6 * w[1] + 0.2 * w[2] + 0.2 * w[0]) * 0.4
        ice = self.water_l & (self.sea_ice + ice_shift > 0)
        mat = np.where(snow, snow_mat, mat)
        variant = np.where(snow, 1, variant)
        mat = np.where(ice, M['SEA_ICE'], mat)
        idx = np.where(ice, self.idx_land, idx)
        variant = np.where(ice, 1, variant)
        img = self.flat_pal[(variant * self.n_mat + mat) * self.n_shade + idx].astype(np.float64)
        if s['foam']:
            img[self.foam & ~ice] = s['foam_color']
        if s['color_noise'] > 0 or s['altitude_tint'] > 0:
            if self.noise_delta is not None:
                img += self.noise_delta
            if self.tint is not None:
                img += self.tint * self.veg_mask[mat][..., None]
        np.clip(img, 0, 255, out=img)
        return img.astype(np.uint8), ice

    # ------------------------------------------------------------- 낮밤 (daylight.DayNightCycle.shade)
    def _light_prepare(self):
        self.normal = decode('normal', self.A['normal'])
        self.horizon = self.A['horizon'].astype(np.float32)
        self.light_thresh = np.roll(self.thresh, (1, 2), axis=(0, 1))
        self.water_y, self.water_x = np.nonzero(self.surf_water)

    def _keyframe(self, alt):
        keys = self.meta['light']['keys']
        alts = [k[0] for k in keys]
        i = int(np.clip(np.searchsorted(alts, alt, side='right') - 1, 0, len(keys) - 2))
        a0, a1 = keys[i], keys[i + 1]
        t = float(np.clip((alt - a0[0]) / (a1[0] - a0[0]), 0, 1))
        mix = lambda u, v: np.asarray(u, float) * (1 - t) + np.asarray(v, float) * t
        return mix(a0[1], a1[1]), mix(a0[2], a1[2]), mix(a0[3], a1[3]), a0[4] * (1 - t) + a1[4] * t

    def shade(self, img, hour):
        Lm = self.meta['light']
        sun = Lm['max_sun_alt'] * np.sin(np.pi * (hour - 6.0) / 12.0)
        moon = Lm['max_moon_alt'] * np.sin(np.pi * (hour - 18.0) / 12.0)
        light, shadow, sky, sky_amount = self._keyframe(sun)
        lx, ly = Lm['light_xy']
        nx, ny, nz = self.normal
        lit = np.zeros((self.H, self.W), dtype=np.float32)
        for alt, weight in ((sun, np.clip(sun / 3.0, 0, 1)),
                            (moon, np.clip((-sun - 6.0) / 6.0, 0, 1) * np.clip(moon / 3.0, 0, 1))):
            if weight <= 0 or alt <= 0:
                continue
            a = np.radians(alt)
            ndl = nx * (lx * np.cos(a)) + ny * (ly * np.cos(a)) + nz * np.sin(a)
            amount = np.clip(ndl / max(np.sin(a), 0.2), 0, 1)
            amount *= self.horizon < np.tan(a)
            lit += weight * amount
        litm = lit > self.light_thresh
        v = np.arange(256, dtype=np.float64)[:, None]
        table = np.clip(np.concatenate([v * shadow, v * light]), 0, 255).astype(np.uint8)
        offset = litm.astype(np.uint16) * 256
        out = np.empty_like(img)
        for c in range(3):
            out[..., c] = table[:, c][img[..., c] + offset]
        if sky_amount > 0 and len(self.water_y):
            wy, wx = self.water_y, self.water_x
            w = out[wy, wx].astype(np.float32)
            out[wy, wx] = (w * (1 - sky_amount) + np.asarray(sky, np.float32) * sky_amount).astype(np.uint8)
        return out

    # ------------------------------------------------------------- 물결 (water.WaterAnimator)
    def _water_prepare(self):
        W_ = self.meta['water']
        sc = W_['scalars']
        self.wempty = sc.get('empty', False)
        if self.wempty:
            return
        p, A = W_['params'], self.A
        H, W = self.H, self.W
        ys, xs = np.nonzero(self.wave)
        self.wy, self.wx = ys, xs
        F = water_noise_fields(H, W, p)
        at = lambda name: F[name][ys, xs].astype(np.float32)
        angle = at('angle_a') * np.pi * 1.6 + at('angle_b') * np.pi
        speed = p['flow_speed'] * (0.9 + 0.4 * at('speed'))
        travel = speed * p['flow_period']
        self.vx = (np.cos(angle) * travel).astype(np.float32)
        self.vy = (np.sin(angle) * travel).astype(np.float32)
        self.phase = (at('phase') * 0.5 + 0.5).astype(np.float32)
        self.phase2 = (at('phase2') * 0.5 + 0.5).astype(np.float32)
        n_or = W_['n_orient']
        crest = (angle + np.pi / 2) % np.pi
        pos = crest / (np.pi / n_or)
        k0 = np.floor(pos).astype(np.int32) % n_or
        self.o_w = (pos - np.floor(pos)).astype(np.float32)
        self.density = np.clip(0.6 + at('density') * 1.2, 0.15, 1.0).astype(np.float32)
        margin, jump = sc['margin'], W_['jump']
        th, tw = H + 2 * margin + jump, W + 2 * margin + jump
        self.tw, tsize = tw, th * tw
        self.tex1 = self._crest(th, tw, p['ripple_size'], p['ripple_length'], 400.0, sc['std1'], n_or, p)
        self.tex2 = self._crest(th, tw, p['ripple_size'] * 1.8, p['ripple_length'] * 0.8, 600.0, sc['std2'], n_or, p)
        self.base = ((ys + margin) * tw + (xs + margin)).astype(np.int32)
        self.off0 = (k0 * tsize).astype(np.int32)
        self.off1 = (((k0 + 1) % n_or) * tsize).astype(np.int32)
        self.dissolve = np.roll(self.thresh, (2, 1), axis=(0, 1))[ys, xs].astype(np.float32)
        self.cut, self.band, self.jump = sc['cut'], sc['band'], jump
        wshore = A['wshore'][ys, xs]
        self.foam_zone, self.rim_zone = wshore <= 3, wshore <= 5
        self.depth_n = (A['wdepth'][ys, xs].astype(np.float64) / (0.35 * sc['d_ref'])).astype(np.float32)
        self.surf_phase = (at('surf') * 0.6 + 0.5).astype(np.float32)
        self.widx = A['widx'][ys, xs].astype(np.intp)
        self.wdelta = A['wdelta'][:, ys, xs].T.astype(np.int16)
        self.w_thresh = self.thresh[ys, xs].astype(np.float32)
        self.ramp = np.asarray(W_['ramp'], np.int16)
        self.flat = (ys * W + xs).astype(np.intp)

    @staticmethod
    def _crest(th, tw, size, length, off, std, n_or, p):
        side = int(np.ceil(np.hypot(th, tw))) + 4
        n = ridge_noise(side, size, length, off, p)
        ridge = np.clip(1.0 - np.abs(n) / (std * 1.2), 0, 1) ** 2
        yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
        yy -= th / 2
        xx -= tw / 2
        out = np.empty((n_or, th * tw), np.float32)
        for k in range(n_or):
            b = np.pi * k / n_or
            u = xx * np.cos(b) + yy * np.sin(b)
            v = -xx * np.sin(b) + yy * np.cos(b)
            sx = np.clip(np.rint(u + side / 2), 0, side - 1).astype(np.int32)
            sy = np.clip(np.rint(v + side / 2), 0, side - 1).astype(np.int32)
            out[k] = ridge[sy, sx].ravel()
        return out.ravel()

    def _layer(self, tex, phase, t, speed_mul):
        out = np.empty_like(phase)
        period = self.meta['water']['params']['flow_period']
        _sample(tex, self.base, self.off0, self.off1, self.o_w, self.vx, self.vy, phase, self.dissolve,
                np.float32(t / period * speed_mul), np.float32(speed_mul), np.int32(self.tw), np.int32(self.jump - 1), out)
        return out

    def waves(self, base, t):
        out = base.copy()
        if self.wempty:
            return out
        p = self.meta['water']['params']
        r = np.maximum(self._layer(self.tex1, self.phase, t, 1.0), self._layer(self.tex2, self.phase2, t, 0.6) * np.float32(0.85))
        pr = np.clip((r - np.float32(self.cut)) / np.float32(self.band), 0, 1) * self.density
        lift = (pr > self.w_thresh).astype(np.intp)
        s = self.surf_phase + np.float32(t / p['surf_period'])
        s -= np.floor(s)
        breath = np.where(s < 0.3, s * np.float32(1 / 0.3), (np.float32(1.0) - s) * np.float32(1 / 0.7))
        breath *= np.sqrt(breath)
        wet = (np.float32(0.3) + np.float32(p['surf_reach']) * breath) * np.float32(1 / 0.35) - self.depth_n
        foam = self.foam_zone & (wet > self.w_thresh)
        rim = self.rim_zone & ~foam & (wet > self.w_thresh - 1.3)
        lift = np.maximum(lift, rim.astype(np.intp))
        k = np.clip(self.widx + lift, 0, len(self.ramp) - 1)
        changed = k != self.widx
        flat = out.reshape(-1, 3)
        flat[self.flat[changed]] = np.clip(self.ramp[k[changed]] + self.wdelta[changed], 0, 255).astype(np.uint8)
        flat[self.flat[foam]] = self.meta['shader']['foam_color']
        return out

    # ------------------------------------------------------------- 한 장면 (frame.FrameRenderer.render)
    def render(self, hour, season=None, wave_t=0.0):
        if season is not None:
            day, ice = self.paint(season)
        else:
            day, ice = self.paint(None)[0], None
        base = day
        if wave_t is not None:
            base = self.waves(day, wave_t)
            if ice is not None and ice.any():
                base[ice] = day[ice]
        return self.shade(base, hour % 24)
