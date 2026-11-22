"""HTTP + WebSocket 서버 (FastAPI).

HTTP
    GET  /api/maps                         데모 지도, 지형 프리셋, 열려 있는 지도 크기
    POST /api/maps {preset, size, seed, config?}    지도 준비 (데모/이미 만든 지도면 바로 ready, 아니면 만들기 시작)
                                           config: 고급 설정에서 바꾼 지형 값 (server/map_fields.py)
    GET  /api/mapconfig?preset=            고급 설정 창의 항목과 그 프리셋 기본값
    GET  /api/maps/{키}/status             ready | building(진행 문구) | error
    GET  /api/maps/{키}/bundle.tsb         지도 묶음 (브라우저가 화면을 그린다)
    GET  /api/maps/{키}/day.png            낮 이미지 (미리보기)
    GET  /api/maps/{키}/layout?bots=&color=&spot=y,x    시작 배치 미리보기 (나라 색과 거점 자리)
    GET  /api/maps/{키}/rules.bin          게임 규칙 지형 (client_info.py)
    GET  /api/lobby                        로비 배경 배치 + 설정 화면에 쓸 것 (나라 색, 난이도, 규칙 표)
    GET  /api/lobby.png                    로비 배경 지형 조각
WebSocket /ws
    처음 메시지: {t:'join', map:키, options:{bots, color, name, difficulty, season, spot?, starts?, colors?}}
                또는 {t:'resume', sid} (연결이 끊겼던 판에 다시 접속: cfg.resume_seconds 안이면 그 판을 이어 간다)
    그다음 서버 → 브라우저: JSON(start, msg, over, ack, error)과 이진 상태 메시지(protocol.py), 브라우저 → 서버: 명령 JSON
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import lobby_art
from server.client_info import rules_bin, rules_info
from server.config import ServerConfig
from server.maps import MapStore
from server.session import GameSession
from sim import rules as R
from sim.spawn import choose_starts, pick_colors


def create_app(cfg: ServerConfig | None = None) -> FastAPI:
    cfg = cfg or ServerConfig()
    state = {'maps': None, 'sessions': {}, 'layout_maps': {}, 'lobby': None}     # sessions: sid → GameSession
    lobby_lock = threading.Lock()

    def lobby():
        """로비 배경 (첫 데모 지도에서). 한 번 만들면 파일로 남겨 두고 (data/lobby/), 다음에 서버를 켤 때는 바로 읽는다."""
        with lobby_lock:
            if state['lobby'] is None:
                store = maps()
                key = next(iter(store.demo))
                folder = cfg.data_dir / 'lobby'
                jf, pf = folder / f'{key}.json', folder / f'{key}.png'
                if jf.exists() and pf.exists():
                    info, png = json.loads(jf.read_text(encoding='utf-8')), pf.read_bytes()
                else:
                    info, png = lobby_art.build(store.scene(key))
                    folder.mkdir(parents=True, exist_ok=True)
                    jf.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
                    pf.write_bytes(png)
                info.update(map=key, colors=[[w, list(c), list(l)] for w, c, l in R.COLORS],
                            difficulty=list(R.DIFFICULTY), rules=rules_info())
                state['lobby'] = (info, png)
            return state['lobby']

    @asynccontextmanager
    async def lifespan(app):
        state['maps'] = MapStore(cfg)
        asyncio.get_running_loop().run_in_executor(None, _warmup, state['maps'], lobby)   # 첫 판이 멈칫하지 않게
        yield
        for s in list(state['sessions'].values()):
            s.stop()
        state['maps'].close()

    app = FastAPI(title='Pixel Territory', lifespan=lifespan)
    maps = lambda: state['maps']

    # ------------------------------------------------------------- 로비
    @app.get('/api/lobby')
    async def lobby_info():
        return (await asyncio.to_thread(lobby))[0]

    @app.get('/api/lobby.png')
    async def lobby_png():
        from fastapi.responses import Response
        return Response((await asyncio.to_thread(lobby))[1], media_type='image/png',
                        headers={'Cache-Control': 'public, max-age=3600'})

    # ------------------------------------------------------------- 지도
    @app.get('/api/maps')
    def list_maps():
        return maps().listing()

    @app.post('/api/maps')
    def request_map(body: dict):
        return maps().request(body.get('preset'), int(body.get('size', 512)), body.get('seed', '8767564'),
                              body.get('config'))

    @app.get('/api/mapconfig')
    def map_config(preset: str | None = None):
        """고급 설정 창: 지형 세부 항목과 그 프리셋의 기본값."""
        try:
            return {'fields': maps().config_fields(preset)}
        except KeyError:
            raise HTTPException(404, f'모르는 지형 프리셋: {preset}')

    @app.get('/api/maps/{key}/status')
    def map_status(key: str):
        return maps().status(key)

    @app.get('/api/maps/{key}/layout')
    async def layout(key: str, bots: int = 4, color: int = 0, spot: str | None = None):
        """시작 배치 미리보기: 무작위(또는 고른 내 자리 + 나머지 무작위). 게임 시작 때 그대로 넘겨 받는다."""
        if maps().status(key)['state'] != 'ready':
            raise HTTPException(409, '지도가 아직 준비되지 않았습니다')
        gmap, sites = await asyncio.to_thread(_layout_map, key)
        n = min(max(bots, 1) + 1, len(R.COLORS))
        rng = np.random.default_rng()
        player_spot = None
        if spot:
            y, x = (int(v) for v in spot.split(','))
            err = _check_spot(gmap, sites, y, x)
            if err:
                return JSONResponse({'error': err}, status_code=422)
            player_spot = (y, x)
        starts = choose_starts(gmap, n, rng, player_spot, sites)
        from sim.wildlife import lairs_for
        lairs = lairs_for(gmap, R.WILDLIFE[R.DRAGON]['cap'])               # 드래곤 둥지 (미리보기에 표시)
        return {'starts': [list(map(int, s)) for s in starts], 'colors': pick_colors(rng, n, color),
                'lairs': [list(map(int, p)) for p in lairs]}

    def _layout_map(key):
        """(게임 지도, 자원지): 미리보기 배치용 (게임과 같은 자원지 → 같은 시작할 수 있는 섬). 하나만 둔다."""
        from sim.sites import find_sites
        from sim.terrain import GameMap
        if key not in state['layout_maps']:
            scene = maps().scene(key)
            gmap = GameMap(scene)
            state['layout_maps'] = {key: (gmap, find_sites(gmap, np.random.default_rng(scene.config.seed)))}
        return state['layout_maps'][key]

    @app.get('/api/maps/{key}/rules.bin')
    async def map_rules(key: str):
        """게임 규칙 지형 (걷기 비용, 엄폐, 땅/여울/절벽/바다). 브라우저가 마우스 아래 설명과 건물 자리 미리보기에 쓴다."""
        from fastapi.responses import Response
        if maps().status(key)['state'] != 'ready':
            raise HTTPException(409, '지도가 아직 준비되지 않았습니다')
        gmap, _ = await asyncio.to_thread(_layout_map, key)
        data = await asyncio.to_thread(rules_bin, gmap)
        return Response(data, media_type='application/octet-stream',
                        headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    @app.get('/api/maps/{key}/{name}')
    def map_file(key: str, name: str):
        p = maps().file(key, name)
        if p is None:
            raise HTTPException(404, '지도 파일이 없습니다')
        media = 'image/png' if name.endswith('.png') else 'application/octet-stream'
        return FileResponse(p, media_type=media, headers={'Cache-Control': 'public, max-age=31536000, immutable'})

    # ------------------------------------------------------------- 게임
    @app.websocket('/ws')
    async def ws_game(ws: WebSocket):
        await ws.accept()
        loop = asyncio.get_running_loop()
        out: asyncio.Queue = asyncio.Queue()
        session = None

        def send(item):                                     # 세션 스레드에서 불린다
            loop.call_soon_threadsafe(out.put_nowait, item)

        async def writer():
            while True:
                item = await out.get()
                if isinstance(item, (bytes, bytearray)):
                    await ws.send_bytes(item)
                else:
                    await ws.send_text(json.dumps(item, ensure_ascii=False))

        wtask = asyncio.create_task(writer())
        try:
            try:
                join = json.loads(await ws.receive_text())
            except ValueError:
                join = {}
            if join.get('t') == 'resume':                               # 끊겼던 판에 다시 접속
                session = state['sessions'].get(str(join.get('sid')))
                if session is None or not session.away or not session.alive:
                    session = None
                    await ws.send_text(json.dumps({'t': 'error', 'error': '이어 할 판이 없습니다 (너무 오래 끊겼습니다)',
                                                   'fatal': True}, ensure_ascii=False))
                    return
                session.attach(send)
            elif join.get('t') != 'join':
                await ws.send_text(json.dumps({'t': 'error', 'error': '처음에는 join을 보내세요'}))
                return
            else:
                if len(state['sessions']) >= cfg.max_sessions:
                    await ws.send_text(json.dumps({'t': 'error', 'error': '지금 열린 판이 너무 많습니다. 잠시 뒤에 다시 해 주세요',
                                                   'fatal': True}, ensure_ascii=False))
                    return
                key = join['map']
                while maps().status(key)['state'] == 'building':            # 지도를 만드는 중이면 진행 상황을 보낸다
                    await ws.send_text(json.dumps({'t': 'map_status', **maps().status(key)}, ensure_ascii=False))
                    await asyncio.sleep(0.5)
                if maps().status(key)['state'] != 'ready':
                    await ws.send_text(json.dumps({'t': 'error', 'error': f'지도를 쓸 수 없습니다: {maps().status(key)}',
                                                   'fatal': True}, ensure_ascii=False))
                    return
                await ws.send_text(json.dumps({'t': 'map_status', 'state': 'loading', 'progress': '판 준비 중...'},
                                              ensure_ascii=False))
                scene = await asyncio.to_thread(maps().scene, key)
                session = await asyncio.to_thread(GameSession, scene, join.get('options', {}), send, cfg)
                state['sessions'][session.sid] = session
                session.start()
            while True:
                msg = await ws.receive_text()
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue                                            # 깨진 메시지는 버린다
                if isinstance(m, dict) and not str(m.get('t', '')).startswith('_'):
                    session.submit(m)
        except WebSocketDisconnect:
            pass
        finally:
            wtask.cancel()
            if session is not None:
                if session.alive and not session.crashed:               # 잠시 멈춘 채 다시 접속을 기다린다
                    session.detach()
                    loop.call_later(cfg.resume_seconds, _expire, session)
                else:
                    session.stop()
                    state['sessions'].pop(session.sid, None)

    def _expire(session):
        """끊긴 뒤 다시 접속하지 않은 판을 정리한다."""
        if session.away and time.monotonic() - session.away_since >= cfg.resume_seconds - 0.5:
            session.stop()
            state['sessions'].pop(session.sid, None)

    # ------------------------------------------------------------- 정적 파일
    assets = cfg.demo_dir.parent                     # assets/ (데모 지도, 기준 그림, 검증 값)
    if assets.exists():
        app.mount('/assets', StaticFiles(directory=assets), name='assets')
    if (cfg.web_dir / 'index.html').exists():
        app.mount('/', PrecompressedStatic(directory=cfg.web_dir, html=True), name='web')
    else:
        @app.get('/')
        def placeholder():
            return HTMLResponse('<meta charset="utf-8"><h1>Pixel Territory 서버</h1><p>웹 클라이언트는 3단계에서 붙는다. '
                                'API: <a href="/api/maps">/api/maps</a></p>')
    return app


class PrecompressedStatic(StaticFiles):
    """웹 빌드가 만들어 둔 파일.gz가 있고 브라우저가 gzip을 받으면 그것을 보낸다 (JS/CSS/HTML이 1/3 크기).
    해시가 붙은 static/ 파일은 오래 캐시하고, 나머지(index.html, manifest.json, sw.js, 아이콘)는 매번 새 버전이 있는지
    확인하게 한다 (no-cache: 바뀌지 않았으면 304로 짧게). 그래야 다시 올린 뒤 휴대폰이 예전 화면을 붙들고 있지 않는다."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        static = path.replace(os.sep, '/').startswith('static/')     # 윈도우에서는 경로가 static\... 로 온다
        cache = 'public, max-age=31536000, immutable' if static else 'no-cache'
        if resp.status_code == 304:
            resp.headers['Cache-Control'] = cache
            return resp
        if resp.status_code != 200 or not hasattr(resp, 'path'):
            return resp
        resp.headers['Cache-Control'] = cache
        accept = dict(scope.get('headers') or []).get(b'accept-encoding', b'')
        gz = str(resp.path) + '.gz'
        if b'gzip' in accept and os.path.exists(gz):
            out = FileResponse(gz, media_type=resp.media_type, headers={'Content-Encoding': 'gzip', 'Vary': 'Accept-Encoding'})
            if 'Cache-Control' in resp.headers:
                out.headers['Cache-Control'] = resp.headers['Cache-Control']
            return out
        return resp


def _warmup(store, lobby):
    """로비 배경을 먼저 준비하고 (첫 화면), numba 계산 코드를 미리 불러 둔다 (처음 여는 판의 첫 걸음이 1초 넘게 멈추지 않게).
    데모 지도 하나로 작은 판을 몇 걸음 돌린다. 그 장면은 메모리에 남아 첫 판도 빨리 열린다."""
    import time
    from sim.terrain import GameMap
    from sim.world import World
    if not store.demo:
        return
    t0 = time.perf_counter()
    lobby()
    t1 = time.perf_counter()
    scene = store.scene(next(iter(store.demo)))
    w = World(GameMap(scene), 2, seed=1, map_seed=scene.config.seed)
    u = w.unit_ids(0)
    w.order_move(u, float(w.units.y[u].mean()) + 5, float(w.units.x[u].mean()) + 5)
    for _ in range(10):
        w.update(0.05)
    print(f'로비 배경 {t1 - t0:.1f}초, 예열 {time.perf_counter() - t1:.1f}초', flush=True)


def _check_spot(gmap, sites, y, x) -> str | None:
    """설정 화면에서 고른 시작 자리 확인: 땅 위, 시작할 수 있는 섬(넓고 식량 자원지가 있는 곳), 물가에서 떨어진 곳."""
    from sim.spawn import start_islands
    if not (8 <= y < gmap.H - 8 and 8 <= x < gmap.W - 8) or not gmap.land[y, x] or gmap.cliff[y, x]:
        return '땅 위를 골라 주세요'
    if gmap.comp[y, x] not in start_islands(gmap, sites):
        return '너무 작거나 식량 자원지가 없는 섬입니다. 더 큰 땅을 골라 주세요'
    if not gmap.land[y - 5:y + 6, x - 5:x + 6].all():
        return '조금 더 넓은 땅을 골라 주세요 (물가에서 떨어진 곳)'
    from sim.wildlife import LAIR_CLEAR, lairs_for
    if any((y - a) ** 2 + (x - b) ** 2 <= LAIR_CLEAR ** 2 for a, b in lairs_for(gmap)):
        return '드래곤 둥지에서 조금 더 떨어진 곳을 골라 주세요'
    return None


app = create_app()
