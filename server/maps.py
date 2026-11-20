"""지도 저장소.

- 데모 지도: 미리 구워 둔 것 (assets/maps, python -m engine.bake)
- 직접 입력한 시드: 처음 요청 때 별도 프로세스에서 만들고 굽는다 (지형 생성은 수 초~수십 초). 진행 상황을 기록하고,
  다 되면 data/maps/<키>/에 남겨 다음부터는 바로 쓴다.
- 판을 열 때 쓰는 지도 장면(TerrainScene)은 메모리에 몇 개 둔다 (렌더에 1~2초).

지도 키: '<프리셋 또는 default>-<크기>-<시드>'. 고급 설정으로 값을 바꿨으면 '<프리셋>~<해시>-<크기>-<시드>'
(바꾼 값은 data/configs/<해시>.json에 남겨, 같은 설정으로 시드만 바꾼 지도(F6)도 만들 수 있다).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import zlib
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from engine.mapgen import list_presets, load_preset
from engine.mapgen.defaults import default_config


def parse_seed(text) -> int:
    """숫자면 그대로, 글자면 고정된 해시 (실행할 때마다 같은 값)."""
    s = str(text).strip()
    try:
        return int(s) % (2 ** 31)
    except ValueError:
        return zlib.crc32(s.encode('utf-8')) % (2 ** 31)


def map_key(preset, size, seed, variant=None) -> str:
    return f'{preset or "default"}{"~" + variant if variant else ""}-{int(size)}-{int(seed)}'


def make_config(preset, size, seed, overrides=None):
    from dataclasses import replace
    cfg = default_config(int(size), int(seed))
    cfg = load_preset(preset, cfg) if preset else cfg
    return replace(cfg, **overrides) if overrides else cfg


def _variant(overrides) -> str:
    text = json.dumps({k: list(v) if isinstance(v, tuple) else v for k, v in sorted(overrides.items())})
    return hashlib.sha1(text.encode()).hexdigest()[:8]


def _build_job(preset, size, seed, cache_dir, out_dir, overrides=None, variant=None):
    """(별도 프로세스) 지도를 만들고 굽는다. 진행 상황은 out_dir/progress.json."""
    from engine.bake import bake_scene
    from engine.scene import TerrainScene
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prog = out / 'progress.json'

    def progress(text):
        prog.write_text(json.dumps({'text': text, 'time': time.time()}, ensure_ascii=False), encoding='utf-8')

    progress('지형 만드는 중...')
    t0 = time.time()
    cfg = make_config(preset, size, seed, overrides)
    scene = TerrainScene.load(cfg, cache_dir, progress=progress)
    progress('굽는 중...')
    key = map_key(preset, size, seed, variant)
    info = bake_scene(scene, out, cfg, key)
    info.update(key=key, preset=preset, seed=int(seed), size=int(size), seconds=round(time.time() - t0, 1),
                overrides={k: list(v) if isinstance(v, tuple) else v for k, v in (overrides or {}).items()})
    (out / 'info.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
    prog.unlink(missing_ok=True)
    return info


class MapStore:
    def __init__(self, cfg):
        self.cfg = cfg
        self.presets = dict(list_presets())                   # 키 → 표시 이름
        self.demo = {}                                        # 지도 키 → 정보
        listing = cfg.demo_dir / 'maps.json'
        if listing.exists():
            for m in json.loads(listing.read_text(encoding='utf-8'))['maps']:
                k = map_key(m['preset'], m['W'], m['seed'])
                self.demo[k] = dict(m, key=k, dir=str(cfg.demo_dir / m['key']), size=m['W'])
        self._jobs = {}
        self._pool = ProcessPoolExecutor(max_workers=cfg.map_workers)
        self._scenes: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------- 요청
    def validate(self, preset, size, seed_text, raw_overrides=None):
        """반환: (키, 프리셋, 바꾼 값, 해시, 오류 문구 또는 None).
        preset이 '<프리셋>~<해시>'면 저장해 둔 바꾼 값을 쓴다 (F6: 같은 설정으로 시드만 바꾸기)."""
        from server.map_fields import parse_overrides
        preset = None if preset in (None, '', 'default') else str(preset)
        variant = None
        overrides, err = parse_overrides(raw_overrides)
        if preset and '~' in preset:
            preset, variant = preset.split('~', 1)
            preset = None if preset == 'default' else preset
            f = self._config_file(variant)
            if not f.exists():
                return None, None, None, None, '저장된 고급 설정을 찾을 수 없습니다'
            overrides = {k: tuple(v) if isinstance(v, list) else v
                         for k, v in json.loads(f.read_text(encoding='utf-8')).items()}
        if err:
            return None, None, None, None, err
        if preset is not None and preset not in self.presets:
            return None, None, None, None, f'모르는 지형 프리셋: {preset}'
        if int(size) not in self.cfg.sizes:
            return None, None, None, None, f'지도 크기는 {self.cfg.sizes} 중 하나'
        if overrides:                                         # 프리셋 값과 같은 것은 뺀다 (같은 지도면 같은 키)
            base = make_config(preset, size, 0)
            overrides = {k: v for k, v in overrides.items() if getattr(base, k) != v}
        if overrides and variant is None:
            variant = _variant(overrides)
            f = self._config_file(variant)
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps({k: list(v) if isinstance(v, tuple) else v for k, v in overrides.items()}),
                             encoding='utf-8')
        if not overrides:
            variant = None
        return map_key(preset, size, parse_seed(seed_text), variant), preset, overrides, variant, None

    def _config_file(self, variant) -> Path:
        return self.cfg.data_dir / 'configs' / f'{variant}.json'

    def request(self, preset, size, seed_text, raw_overrides=None) -> dict:
        key, preset, overrides, variant, err = self.validate(preset, size, seed_text, raw_overrides)
        if err:
            return {'key': None, 'state': 'error', 'error': err}
        st = self.status(key)
        if st['state'] in ('missing', 'error'):
            out = self._custom_dir(key)
            with self._lock:
                job = self._jobs.get(key)
                if job is None or (job.done() and job.exception() is not None):
                    self._jobs[key] = self._pool.submit(_build_job, preset, int(size), parse_seed(seed_text),
                                                        str(self.cfg.cache_dir), str(out), overrides, variant)
            st = self.status(key)
        return dict(st, key=key)

    def config_fields(self, preset) -> list[dict]:
        """고급 설정 창에 보일 항목과 그 프리셋의 기본값."""
        from server.map_fields import field_list
        preset = None if preset in (None, '', 'default') else preset
        if preset is not None and preset not in self.presets:
            raise KeyError(preset)
        return field_list(make_config(preset, 512, 0))

    def _custom_dir(self, key) -> Path:
        return self.cfg.data_dir / 'maps' / key

    def info(self, key) -> dict | None:
        if key in self.demo:
            return self.demo[key]
        f = self._custom_dir(key) / 'info.json'
        if f.exists():
            info = json.loads(f.read_text(encoding='utf-8'))
            info['dir'] = str(self._custom_dir(key))
            return info
        return None

    def status(self, key) -> dict:
        if self.info(key) is not None:
            return {'state': 'ready'}
        job = self._jobs.get(key)
        if job is None:
            return {'state': 'missing'}
        if job.done():
            err = job.exception()
            if err is not None:
                return {'state': 'error', 'error': str(err)}
            return {'state': 'ready'}
        prog = self._custom_dir(key) / 'progress.json'
        text = '대기 중...'
        if prog.exists():
            try:
                text = json.loads(prog.read_text(encoding='utf-8'))['text']
            except (ValueError, OSError):
                pass
        return {'state': 'building', 'progress': text}

    def file(self, key, name) -> Path | None:
        info = self.info(key)
        if info is None or name not in ('bundle.tsb', 'day.png'):
            return None
        p = Path(info['dir']) / name
        return p if p.exists() else None

    # ------------------------------------------------------------- 판에 쓸 장면
    def scene(self, key):
        """준비된 지도의 TerrainScene (메모리에 몇 개 둔다). 다른 스레드에서 불러도 된다."""
        from engine.scene import TerrainScene
        with self._lock:
            if key in self._scenes:
                self._scenes.move_to_end(key)
                return self._scenes[key]
        info = self.info(key)
        if info is None:
            raise KeyError(key)
        ov = {k: tuple(v) if isinstance(v, list) else v for k, v in (info.get('overrides') or {}).items()}
        cfg = make_config(info.get('preset'), info.get('size', info.get('W')), info['seed'], ov)
        scene = TerrainScene.load(cfg, self.cfg.cache_dir, progress=lambda s: None)
        scene.map_key, scene.config = key, cfg
        with self._lock:
            self._scenes[key] = scene
            while len(self._scenes) > self.cfg.scene_cache:
                self._scenes.popitem(last=False)
        return scene

    def listing(self) -> dict:
        return {'demo': [{k: v for k, v in m.items() if k != 'dir'} for m in self.demo.values()],
                'presets': [{'key': k, 'name': n} for k, n in self.presets.items()],
                'sizes': self.cfg.sizes, 'max_size': self.cfg.max_size}

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
