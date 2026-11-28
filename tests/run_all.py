"""회귀 테스트 모두 실행: python -m tests.run_all  (저장소 맨 위에서)"""
import sys
import time
import traceback

from tests import toplevel  # noqa: F401
from tests import test_bake, test_rules, test_server, test_smoke, test_wildlife, test_dragon, test_tortoise, test_firetower, test_defeat, test_diplomacy, test_multi, test_rooms, test_storage, test_tribes, test_climate, test_reindeer, test_pasture, test_formation, test_grenadier, test_shore, test_pioneer, test_fog

# 옛 데스크톱 코드(main.py 등)와 견주는 테스트: 그 코드가 옆에 있을 때만 (지금 저장소에는 없다)
parity = []
for name in ('test_engine_parity', 'test_render_parity', 'test_sim_parity'):
    try:
        parity.append(__import__(f'tests.{name}', fromlist=['run']))
    except ModuleNotFoundError as e:
        print(f'== {name}: 건너뜀 ({e})')

results = []


def report(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(f'  [{"통과" if ok else "실패"}] {name}' + (f'  ({detail})' if detail and not ok else ''), flush=True)


for mod in (*parity, test_bake, test_rules, test_wildlife, test_dragon, test_tortoise, test_firetower, test_defeat, test_diplomacy, test_storage, test_tribes, test_climate, test_reindeer, test_pasture, test_formation, test_grenadier, test_shore, test_pioneer, test_fog, test_multi, test_rooms, test_server, test_smoke):
    print(f'== {mod.__name__}', flush=True)
    t0 = time.time()
    try:
        mod.run(report)
    except Exception:
        traceback.print_exc()
        report(f'{mod.__name__} 실행', False)
    print(f'   ({time.time() - t0:.0f}초)', flush=True)

failed = [n for n, ok in results if not ok]
print(f'\n결과: {len(results) - len(failed)}/{len(results)} 통과' + (f' — 실패: {failed}' if failed else ''))
sys.exit(1 if failed else 0)
