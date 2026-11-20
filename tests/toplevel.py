"""최상위 프로젝트(terrain_shader/)의 원본 코드를 함께 불러오는 도우미.
회귀 테스트에서 '옮기기 전' 결과와 비교할 때만 쓴다 (게임/서버 코드는 최상위를 참조하지 않는다)."""
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
TOP = WEB.parent
for p in (str(WEB), str(TOP)):
    if p not in sys.path:
        sys.path.insert(0, p)
