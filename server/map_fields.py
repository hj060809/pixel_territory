"""지형 세부 설정 (설정 화면의 '고급 설정' 창): 보여 줄 항목, 이름, 묶음, 값 확인.

이름과 묶음은 데스크톱 뷰어의 설정 패널(viewer/config_panel.py)과 같다.
브라우저는 프리셋 기본값을 받아 고치고, 바꾼 값만 지도 요청에 실어 보낸다. 서버는 자료형에 맞게 읽고 범위를 확인한다.
"""
from __future__ import annotations

import math
from dataclasses import fields

from engine.mapgen.config import WorldConfig

LABELS = {
    'land_ratio': '육지 비율', 'landmasses': '땅덩어리 수', 'size_variety': '크기 차이 (0~1)',
    'elongation': '길쭉함 (0~1)', 'edge_ocean': '가장자리 바다 (0~1)', 'coast_roughness': '해안 굴곡 (0~1)',
    'coast_detail': '해안 잔굴곡', 'sharpness': '각진 정도 (0~1)', 'strait_width': '해협 폭',
    'coast_smoothing': '해안 다듬기 반지름', 'inland_sea_area': '내륙 호수로 남길 크기',
    'plates': '판 경계 수 (범위)', 'mountain_height': '산 높이', 'mountain_coverage': '산 지역 비율',
    'ridge_scale': '능선 간격', 'massif': '산괴 두께', 'hill_height': '언덕 높이', 'lowland': '저지대 넓이',
    'erosion_droplets': '침식 물방울 수 (auto)',
    'lakes': '호수 분지 수 (범위)', 'lake_radius': '호수 크기 (범위)', 'lake_min_area': '호수 최소 넓이',
    'lake_max_level': '호수 최고 높이', 'river_threshold': '강이 되는 물 모임', 'river_max_width': '강 최대 폭',
    'meander': '강 굽이', 'floodplain': '범람원 폭', 'oxbow_chance': '우각호 확률', 'deltas': '삼각주',
    'delta_min_width': '삼각주 최소 강폭',
    'coast_variety': '해안 종류 세기', 'cliffs': '절벽 비율', 'beaches': '모래사장 비율', 'sea_stacks': '바위기둥 양',
    'lagoons': '석호 최대 수',
    'climate_zones': '기후 영역 수', 'temperature_range': '기온 범위 (0~1)', 'moisture_range': '습도 범위 (0~1)',
    'zone_border': '경계 섞임 폭', 'zone_wobble': '경계 구불거림', 'zone_contrast': '이웃 영역 기온 차 한계',
    'temp_altitude': '고도 (높을수록 추움)', 'temp_coast': '바다 완화', 'temp_patches': '지역 얼룩 (기온)',
    'moist_patches': '지역 얼룩 (습도)', 'patch_scale': '얼룩 크기', 'moist_wind': '바람·비그늘',
    'wind_dir': '바람 방향 (도)', 'rain_shadow': '비그늘 세기',
    'freshwater_moisture': '강·호숫가 습도', 'coast_moisture': '바닷가 습도',
}
GROUPS = {'land_ratio': '땅 모양', 'coast_roughness': '해안선', 'plates': '높이',
          'erosion_droplets': '침식', 'lakes': '물', 'coast_variety': '해안 종류', 'climate_zones': '기후'}
HIDDEN = {'sea_level', 'size', 'seed', 'zones'}
INT_MAX = {'landmasses': 40, 'plates': 60, 'lakes': 60, 'lagoons': 20, 'climate_zones': 30, 'coast_smoothing': 6,
           'river_max_width': 8, 'lake_min_area': 20000, 'erosion_droplets': 2_000_000}


def _kind(f) -> str:
    t = str(f.type)
    if 'bool' in t:
        return 'bool'
    if 'tuple' in t:
        return 'range'
    if f.name == 'erosion_droplets':
        return 'auto'
    return 'int' if t.startswith('int') else 'float'


def field_list(cfg: WorldConfig) -> list[dict]:
    """고급 설정 창에 보일 항목: [{name, label, group(묶음 첫 항목만), kind, value}]."""
    out = []
    for f in fields(WorldConfig):
        if f.name in HIDDEN:
            continue
        v = getattr(cfg, f.name)
        out.append({'name': f.name, 'label': LABELS.get(f.name, f.name), 'group': GROUPS.get(f.name),
                    'kind': _kind(f), 'value': list(v) if isinstance(v, tuple) else v})
    return out


def parse_overrides(raw: dict | None) -> tuple[dict, str | None]:
    """브라우저가 보낸 바꾼 값 → (WorldConfig에 얹을 값, 오류 문구). 자료형에 맞게 읽고 범위를 본다."""
    if not raw:
        return {}, None
    known = {f.name: f for f in fields(WorldConfig) if f.name not in HIDDEN}
    out = {}
    for name, v in raw.items():
        f = known.get(name)
        if f is None:
            return {}, f'모르는 항목: {name}'
        label = LABELS.get(name, name)
        kind = _kind(f)
        try:
            if kind == 'bool':
                val = bool(v)
            elif kind == 'auto':
                val = None if v in (None, '', 'auto') else int(float(v))
            elif kind == 'range':
                a, b = (float(x) for x in v)
                if 'int' in str(f.type):
                    a, b = int(round(a)), int(round(b))
                val = (min(a, b), max(a, b))
            elif kind == 'int':
                val = int(round(float(v)))
            else:
                val = float(v)
        except (TypeError, ValueError):
            return {}, f'{label}: 값을 읽을 수 없습니다'
        nums = val if isinstance(val, tuple) else (() if val is None or isinstance(val, bool) else (val,))
        for x in nums:
            if not math.isfinite(x) or x < 0 and name != 'wind_dir':
                return {}, f'{label}: 0 이상의 숫자를 넣어 주세요'
            if isinstance(x, int) and x > INT_MAX.get(name, 10_000):
                return {}, f'{label}: {INT_MAX.get(name, 10_000)} 이하로 넣어 주세요'
            if isinstance(x, float) and abs(x) > 1000:
                return {}, f'{label}: 너무 큰 값입니다'
        out[name] = val
    return out, None
