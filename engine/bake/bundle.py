"""지도 한 장 → 웹용 묶음 (meta + 배열). 브라우저는 이것과 '지도와 상관없는 노이즈'(직접 생성)로 화면을 그린다.

묶음에 넣는 것 (모두 (H, W) 격자, 정밀도를 조금 줄여 저장 — QUANT 참고):
- 계절 칠하기: pre(눈 없는 재질), idx(명암 단계), idx_land(바다 얼음일 때의 명암 단계), flags(비트),
  snow_cover / snow_old / sea_ice(눈·묵은 눈·바다 얼음이 되기까지의 여유), temperature(계절 폭), alt(고도 색조)
- 낮밤: normal(3, H, W), horizon(지평선 높이)
- 물결: widx(물 색 단계), wdelta(3, H, W 색 차이), wshore(해안 거리), wdepth(수심)
- palettes: (4계절, 재질, 명암 단계, RGB)
머리말(meta): 셰이더·빛·물결 수치, 재질 번호, Bayer 표, 물결의 지도별 값(margin, std1, std2, cut, band, d_ref).

브라우저가 직접 만드는 것 (지도 내용과 상관없다): 색 노이즈(shader._color_noise_delta),
물결 흐름 노이즈(water.water_noise_fields), 마루 텍스처 바탕 노이즈(water.ridge_noise). 모두 OpenSimplex(시드 고정).
"""
from __future__ import annotations

import dataclasses

import numpy as np

from engine.render import shader as SH
from engine.render.daylight import LIGHT_KEYS, MAX_MOON_ALT, MAX_SUN_ALT
from engine.render.seasons import season_palettes
from engine.render.water import JUMP, N_ORIENT

FORMAT_VERSION = 1

# 정밀도 줄이기 (굽기/풀기가 같은 규칙을 쓴다)
QUANT = {
    'margin': ('int16', 8192.0, 3.99),   # 눈/묵은 눈/바다 얼음 여유: 부호만 중요하고 계절로 움직이는 폭은 ±2.5 이하
    'unit16': ('uint16', 65535.0, None),  # 0~1 값 (기온, 고도)
    'normal': ('int16', 32767.0, None),  # 법선 성분 -1~1
}
FLAG_WATER, FLAG_NEAR_LAND, FLAG_ICE_ZONE, FLAG_SURF_WATER, FLAG_WAVE = 1, 2, 4, 8, 16


def encode(kind, a):
    dtype, scale, lim = QUANT[kind]
    a = np.asarray(a, np.float64)
    if lim is not None:
        a = np.clip(a, -lim, lim)
    elif dtype == 'uint16':
        a = np.clip(a, 0, 1)
    return np.rint(a * scale).astype(dtype)


def decode(kind, q):
    dtype, scale, _ = QUANT[kind]
    return (q.astype(np.float32) / np.float32(scale)).astype(np.float32)


def _jsonable(v):
    if isinstance(v, (tuple, list)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def bake(scene, frame, cfg=None, name: str = '') -> tuple[dict, dict]:
    """scene: TerrainScene, frame: FrameRenderer(scene) (빛과 물결 준비를 함께 쓴다). 반환: (meta, arrays)."""
    L, sh, surf, water = scene.layers, scene.shader, frame.surface, frame.water
    H, W = scene.H, scene.W
    flags = np.zeros((H, W), np.uint8)
    flags |= L['water'].astype(np.uint8) * FLAG_WATER
    flags |= L['near_land'].astype(np.uint8) * FLAG_NEAR_LAND
    flags |= L['ice_zone'].astype(np.uint8) * FLAG_ICE_ZONE
    flags |= surf.water.astype(np.uint8) * FLAG_SURF_WATER
    wave = np.zeros((H, W), bool)
    wave[surf.wy, surf.wx] = True
    flags |= wave.astype(np.uint8) * FLAG_WAVE

    widx = np.zeros((H, W), np.uint8)
    widx[surf.wy, surf.wx] = surf.widx
    wdelta = np.zeros((3, H, W), np.int8)
    wdelta[:, surf.wy, surf.wx] = surf.wdelta.T
    wshore = np.zeros((H, W), np.uint8)
    wshore[surf.wy, surf.wx] = surf.wshore
    wdepth = np.zeros((H, W), np.float16)
    wdepth[surf.wy, surf.wx] = surf.wdepth

    arrays = {
        'pre': L['pre'].astype(np.uint8), 'idx': L['idx'].astype(np.uint8), 'idx_land': L['idx_land'].astype(np.uint8),
        'flags': flags,
        'snow_cover': encode('margin', L['snow_cover']), 'snow_old': encode('margin', L['snow_old']),
        'sea_ice': encode('margin', L['ice']),
        'temperature': encode('unit16', L['temperature']), 'alt': encode('unit16', L['alt']),
        'normal': encode('normal', surf.normal), 'horizon': surf.horizon.astype(np.float16),
        'widx': widx, 'wdelta': wdelta, 'wshore': wshore, 'wdepth': wdepth,
        'palettes': season_palettes(sh.palette),
    }
    meta = {
        'version': FORMAT_VERSION, 'name': name, 'H': H, 'W': W,
        'config': _jsonable(dataclasses.asdict(cfg)) if cfg is not None else None,
        'shader': {'snow_blend': sh.snow_blend, 'foam': bool(sh.foam), 'color_noise': sh.color_noise,
                   'color_noise_scale': sh.color_noise_scale, 'altitude_tint': sh.altitude_tint, 'seed': sh.seed,
                   'foam_color': _jsonable(SH.DEFAULT_FOAM), 'warm': _jsonable(SH._WARM),
                   'bright': _jsonable(SH._BRIGHT), 'cool': _jsonable(SH._COOL), 'bayer4': _jsonable(SH._BAYER_4)},
        'materials': {'ICE': SH.ICE, 'SNOW': SH.SNOW, 'SNOW_OLD': SH.SNOW_OLD, 'SEA_ICE': SH.SEA_ICE,
                      'n_mat': int(sh.palette.shape[0]), 'n_shade': int(sh.palette.shape[1]),
                      'vegetation': list(SH.VEGETATION)},
        'light': {'light_xy': list(surf.light_xy), 'keys': _jsonable(LIGHT_KEYS),
                  'max_sun_alt': MAX_SUN_ALT, 'max_moon_alt': MAX_MOON_ALT},
        'water': {'params': water.params, 'scalars': water.scalars(), 'ramp': _jsonable(surf.ramp),
                  'n_orient': N_ORIENT, 'jump': JUMP, 'update_hz': water.update_hz},
        'flags': {'water': FLAG_WATER, 'near_land': FLAG_NEAR_LAND, 'ice_zone': FLAG_ICE_ZONE,
                  'surf_water': FLAG_SURF_WATER, 'wave': FLAG_WAVE},
        'quant': {k: {'dtype': d, 'scale': s, 'limit': lim} for k, (d, s, lim) in QUANT.items()},
    }
    return meta, arrays
