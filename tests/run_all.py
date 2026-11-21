"""회귀 테스트 모두 실행: python -m tests.run_all  (web_game 폴더에서)"""
import sys
import time
import traceback

from tests import toplevel  # noqa: F401
from tests import test_bake, test_engine_parity, test_render_parity, test_rules, test_server, test_sim_parity, test_smoke, test_wildlife

results = []


def report(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(f'  [{"통과" if ok else "실패"}] {name}' + (f'  ({detail})' if detail and not ok else ''), flush=True)


for mod in (test_engine_parity, test_render_parity, test_bake, test_sim_parity, test_rules, test_wildlife, test_server, test_smoke):
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
