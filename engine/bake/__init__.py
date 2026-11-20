"""지도 굽기: 지도 한 장 → 웹용 묶음(.tsb) + 낮 이미지(PNG) + 기준 그림.

- container: 묶음 파일 형식 (gzip 이진, 브라우저에서 바로 읽는다)
- bundle: 묶음에 넣을 것 (정밀도 줄이기 포함)
- client_ref: 묶음만으로 화면을 그리는 파이썬판 — 웹 클라이언트가 옮길 사양
- 실행: python -m engine.bake  (데모 지도를 assets/maps/에 굽는다)
"""
from __future__ import annotations

from pathlib import Path

from engine.bake.bundle import bake
from engine.bake.container import pack, unpack
from engine.bake.png import save_png
from engine.render.frame import FrameRenderer


def bake_scene(scene, out_dir, cfg=None, name='', reference=()) -> dict:
    """scene을 out_dir에 굽는다: bundle.tsb, day.png, ref/*.png (reference: [(이름, 시각, 계절, 물결 시각)]).
    반환: 크기 정보."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = FrameRenderer(scene)
    meta, arrays = bake(scene, frame, cfg, name)
    blob = pack(meta, arrays)
    (out / 'bundle.tsb').write_bytes(blob)
    save_png(out / 'day.png', scene.day)
    if reference:
        (out / 'ref').mkdir(exist_ok=True)
        for ref_name, hour, season, wave_t in reference:
            save_png(out / 'ref' / f'{ref_name}.png', frame.render(hour, season, wave_t))
    raw = sum(a.nbytes for a in arrays.values())
    return {'name': name, 'bundle_bytes': len(blob), 'raw_bytes': raw, 'H': scene.H, 'W': scene.W}


__all__ = ['bake', 'bake_scene', 'pack', 'unpack']
