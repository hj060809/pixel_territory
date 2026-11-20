"""생성한 지형 캐시.

캐시 이름은 두 가지로 정한다.
- WorldConfig 값 전체 (size, seed, 침식 물방울 수 포함): 값이 하나라도 다르면 다른 캐시
- 지형 생성 코드(engine.mapgen 폴더 아래 모든 .py)의 내용: 코드를 고치면 옛 캐시를 자동으로 쓰지 않는다 (버전 번호를 손으로 올릴 필요 없음)

파일: <cache_dir>/world_<size>_<seed>_<해시>.npz  (높이, 해안 종류, 기온, 습도, 설정 JSON)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from engine.mapgen.config import WorldConfig
from engine.mapgen.core.height_map import HeightMap
from engine.mapgen.world import generate_world

_CODE_DIR = Path(__file__).resolve().parent
_code_hash: str | None = None


def _code_fingerprint() -> str:
    """engine.mapgen 폴더 소스 코드의 해시 (한 번만 계산)."""
    global _code_hash
    if _code_hash is None:
        h = hashlib.sha1()
        for p in sorted(_CODE_DIR.rglob('*.py')):
            h.update(p.relative_to(_CODE_DIR).as_posix().encode())
            h.update(p.read_bytes())
        _code_hash = h.hexdigest()
    return _code_hash


def config_json(cfg: WorldConfig) -> str:
    return json.dumps(asdict(cfg), sort_keys=True, ensure_ascii=False)


def cache_path(cfg: WorldConfig, cache_dir: str | Path = '.cache') -> Path:
    key = hashlib.sha1((config_json(cfg) + _code_fingerprint()).encode()).hexdigest()[:12]
    return Path(cache_dir) / f'world_{cfg.size}_{cfg.seed}_{key}.npz'


def generate_cached(cfg: WorldConfig, cache_dir: str | Path | None = '.cache',
                    progress=None):
    """캐시에 있으면 불러오고, 없으면 생성해서 저장한다. cache_dir=None이면 캐시를 쓰지 않는다.
    반환: (높이맵, 해안 종류 지도, 기후 (기온, 습도) 또는 None)"""
    report = progress or (lambda text: None)
    path = cache_path(cfg, cache_dir) if cache_dir is not None else None
    if path is not None and path.exists():
        try:
            report('캐시에서 불러오는 중...')
            data = np.load(path)
            climate = (data['temperature'], data['moisture']) if 'temperature' in data.files else None
            return HeightMap(data['height']), data['coast'], climate
        except Exception:                                # 깨진 파일이면 다시 만든다
            path.unlink(missing_ok=True)
    world = generate_world(cfg, progress=progress)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, height=world.height.map, coast=world.coast,
                            temperature=world.temperature.astype(np.float16),
                            moisture=world.moisture.astype(np.float16),
                            config=np.array(config_json(cfg)))
    return world.height, world.coast, world.climate
