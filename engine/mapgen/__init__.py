"""지형 생성.

    from engine.mapgen import WorldConfig, generate_world
    world = generate_world(WorldConfig(seed=1))         # World: height(HeightMap), coast, ocean, lakes, rivers, ...

폴더 구조
- config.py       WorldConfig (생성 설정)
- world.py        World (결과), WorldGenerator (단계를 차례로 돌린다), generate_world
- coast_types.py  해안 종류 번호 (셰이더와 같이 쓴다)
- cache.py        설정과 코드가 같으면 생성 결과를 다시 쓰는 캐시
- presets.py      presets/ 폴더의 설정 프리셋
- core/           높이맵, 노이즈, 마스크 도우미, 침식과 물 흐름 커널
- stages/         생성 단계: 땅 모양 → 높이 → 침식 → 물(강) → 해안 종류
"""
from engine.mapgen.cache import generate_cached
from engine.mapgen.config import WorldConfig
from engine.mapgen.core.height_map import HeightMap
from engine.mapgen.presets import list_presets, load_preset, preset_values
from engine.mapgen.world import World, WorldGenerator, generate_world

__all__ = ['WorldConfig', 'World', 'WorldGenerator', 'generate_world', 'HeightMap', 'generate_cached',
           'list_presets', 'load_preset', 'preset_values']
