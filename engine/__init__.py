"""지형 엔진: 지형 생성(mapgen) → 픽셀아트 렌더와 계절(render) → 지도 한 장(scene).

게임(sim)은 엔진을 이 창구로만 쓴다:
    engine.scene.TerrainScene      지도 한 장 (낮 이미지, 계절 칠하기, 재질/높이/해안/기후)
    engine.render.materials        재질 번호
    engine.mapgen                  지형 설정과 생성, 프리셋
"""
