"""브라우저 화면에 필요한 것: 규칙 수치·이름 (판 시작 때 JSON), 게임 규칙 지형 (지도마다 한 번, 이진).

게임 규칙 지형 (rules.bin, gzip):  'TSR1' | u16 W | u16 H | u8 flags[H*W] | u16 base_cost×1000[H*W] | u8 cover×100[H*W]
    flags 비트: 1 땅, 2 여울, 4 절벽 해안, 8 바다(항구를 지을 수 있는 물), 16 물
브라우저는 이것으로 마우스 아래 설명(걷는 속도, 엄폐, 여울)과 건물 자리 미리보기(지을 수 있나)를 바로 계산한다.
"""
from __future__ import annotations

import gzip
import struct

import numpy as np

from engine.render import materials as M
from sim import rules as R

MAT_NAMES = {
    M.GRASS: '초원', M.GRASS_YELLOW: '초원', M.GRASS_DEAD: '마른 초원', M.DRYGRASS: '마른 풀밭', M.SAVANNA: '사바나',
    M.STEPPE: '스텝', M.COLD_STEPPE: '추운 스텝', M.MOSS: '이끼', M.DIRT: '흙', M.SAND: '모래', M.DUNE: '사구',
    M.DESERT: '사막', M.FOREST: '숲', M.RAINFOREST: '열대우림', M.TAIGA: '침엽수림', M.SHRUB: '관목',
    M.MARSH: '습지', M.TUNDRA: '툰드라', M.ALPINE: '고산 초원', M.SCREE: '자갈 비탈', M.LIMESTONE: '석회암',
    M.ROCK: '바위산', M.ROCK_WARM: '바위산', M.ROCK_RED: '붉은 바위', M.SNOW: '눈', M.SNOW_OLD: '만년설', M.ICE: '빙하',
}


def rules_info() -> dict:
    from sim.terrain import FORD_COST, SEA_ICE_COST, SNOWY
    return {
        'res_names': list(R.RES_NAMES), 'unit_names': list(R.UNIT_NAMES), 'build_names': list(R.BUILD_NAMES),
        'unit_hp': [R.UNIT_STATS[k]['hp'] for k in range(len(R.UNIT_STATS))],
        'unit_cost': [list(R.UNIT_STATS[k]['cost']) for k in range(len(R.UNIT_STATS))],
        'unit_time': [R.UNIT_STATS[k]['time'] for k in range(len(R.UNIT_STATS))], 'warship_time': R.WARSHIP_TIME,
        'unit_speed': [R.UNIT_STATS[k]['speed'] for k in range(len(R.UNIT_STATS))],
        'unit_dmg': [R.UNIT_STATS[k]['dmg'] for k in range(len(R.UNIT_STATS))],
        'trainable': list(R.TRAINABLE), 'mounted': sorted(R.MOUNTED),
        'unit_fly': [R.UNIT_STATS[k]['fly'] for k in range(len(R.UNIT_STATS))],
        'stomp_r': R.STOMP['r'], 'taunt_r': R.TAUNT['r'],
        'wildlife': {str(k): {'name': a['name'], 'tame': a['tame'], 'mounts': {str(u): v for u, v in a.get('mounts', {}).items()},
                              'companion': a.get('companion', -1), 'food': a.get('food', 0),
                              'tamers': sorted(R.tamers_of(a)), 'calm': bool(a.get('calm')),
                              'hostile': bool(a.get('hostile')), 'limit': a.get('limit', 0),
                              'subdue': a.get('subdue', 0), 'subdue_time': a.get('subdue_time', 0)}
                     for k, a in R.WILDLIFE.items()},
        'build': {str(k): {'r': v['r'], 'cost': list(v['cost']), 'hp': v['hp'], 'sulfur': v.get('sulfur', 0)}
                  for k, v in R.BUILD_STATS.items()},
        'site_names': list(R.SITE_NAMES), 'fire': R.FIRE,
        'kinds': {'HALL': R.HALL, 'FARM': R.FARM, 'LUMBER': R.LUMBER, 'QUARRY': R.QUARRY, 'TOWER': R.TOWER,
                  'HARBOR': R.HARBOR, 'SULFUR_PIT': R.SULFUR_PIT, 'FIRE_TOWER': R.FIRE_TOWER, 'SULFUR': R.SULFUR,
                  'TRADE_POST': R.TRADE_POST},
        'trade': dict(R.TRADE), 'caravan_members': [m for m, _ in R.CARAVAN_MEMBERS], 'caravan_gap': R.CARAVAN_GAP,
        'store': {'base': R.STORE_BASE, 'hall': R.STORE_HALL, 'site': R.STORE_SITE},
        'site_building': {str(k): v for k, v in R.SITE_BUILDING.items()},
        'yield_res': {str(k): v[0] for k, v in R.YIELD.items()},
        'yield_base': {str(k): v[1] for k, v in R.YIELD.items()}, 'hall_yield': list(R.HALL_YIELD), 'sulfur_yield': R.SULFUR_YIELD,
        'season_yield': {str(k): list(v) for k, v in R.SEASON_YIELD.items()},
        'tower': {'dmg': R.TOWER_DMG, 'range': R.TOWER_RANGE, 'cd': R.TOWER_CD},
        'warship': {'dmg': R.WARSHIP_DMG, 'range': R.WARSHIP_RANGE, 'cd': R.WARSHIP_CD},
        'season_yield_food': list(R.SEASON_YIELD[R.FOOD]),
        'warship_cost': list(R.WARSHIP_COST), 'warship_hp': R.WARSHIP_HP, 'ferry_hp': R.FERRY_HP,
        'mat_names': {str(k): v for k, v in MAT_NAMES.items()}, 'snowy': list(SNOWY),
        'ford_cost': FORD_COST, 'sea_ice_cost': SEA_ICE_COST,
    }


def rules_bin(gmap) -> bytes:
    flags = (gmap.land.astype(np.uint8) * 1 | gmap.ford.astype(np.uint8) * 2 | gmap.cliff.astype(np.uint8) * 4
             | gmap.ocean.astype(np.uint8) * 8 | gmap.water.astype(np.uint8) * 16)
    cost = np.clip(np.rint(gmap.base_cost * 1000), 0, 65535).astype('<u2')
    cover = np.clip(np.rint(gmap.cover * 100), 0, 255).astype(np.uint8)
    head = b'TSR1' + struct.pack('<HH', gmap.W, gmap.H)
    return gzip.compress(head + flags.tobytes() + cost.tobytes() + cover.tobytes(), compresslevel=6)
