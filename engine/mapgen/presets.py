"""세계 설정 프리셋 (engine/presets/ 폴더의 JSON 파일).

파일 하나가 프리셋 하나다:
    {
      "name": "대륙",                      # 패널과 도움말에 보이는 이름
      "order": 1,                         # 패널 버튼 순서 (선택)
      "description": "...",               # 설명 (선택)
      "config": {"land_ratio": 0.62, ...}  # WorldConfig에서 바꿀 값만 (나머지는 기본값). 범위 값은 [5, 9]처럼
    }
새 프리셋은 이 형식으로 파일을 추가하면 된다 (파일 이름이 프리셋 키).
"""
from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

from engine.mapgen.config import WorldConfig

PRESET_DIR = Path(__file__).resolve().parent.parent / 'presets'


def list_presets() -> list[tuple[str, str]]:
    """[(키, 이름)] order 순 (없으면 파일 이름 순)."""
    out = []
    for p in sorted(PRESET_DIR.glob('*.json')):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            out.append((d.get('order', 999), p.stem, d.get('name', p.stem)))
        except (OSError, json.JSONDecodeError):
            continue
    return [(k, n) for _, k, n in sorted(out)]


def preset_values(key: str) -> dict:
    """프리셋이 바꾸는 값 (WorldConfig 형태로: 리스트는 튜플로). 모르는 항목은 무시한다."""
    path = PRESET_DIR / f'{key}.json'
    if not path.exists():
        names = ', '.join(k for k, _ in list_presets())
        raise ValueError(f'프리셋 없음: {key} (가능: {names})')
    data = json.loads(path.read_text(encoding='utf-8'))
    known = {f.name for f in fields(WorldConfig)}
    vals = {}
    for k, v in data.get('config', {}).items():
        if k in known and k not in ('size', 'seed'):
            vals[k] = tuple(v) if isinstance(v, list) else v
    return vals


def load_preset(key: str, base: WorldConfig | None = None, **overrides) -> WorldConfig:
    """base(기본: WorldConfig())에 프리셋 값을 얹고, overrides를 마지막에 얹는다."""
    return replace(base or WorldConfig(), **{**preset_values(key), **overrides})
