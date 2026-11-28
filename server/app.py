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
    GET  /api/rooms                        열린 방 목록 (대기 중인 방만, server/rooms.py)
    GET  /api/resume?sid=&token=           이어 할 수 있는 판인가 (브라우저를 다시 열었을 때): {ok, map}
    GET  /api/status                       {busy}: 접속자가 상한(max_clients)에 닿았나 (로비가 안내를 띄운다)
    GET  /dashboard, /api/dashboard        서버 통계 (방문, 판, 서버 사용량: 숫자만, server/stats.py)
WebSocket /ws
    처음 메시지 (하나):
      {t:'join', map:키, options:{bots, color, name, difficulty, season, fog?, spot?, starts?, colors?}}   싱글 (사람 1 + AI)
      {t:'room_create', name, password?, cap, bots, start_mode:'pick'|'random', setup:{map, difficulty, season},
       player:{name, color}}                                                                      방 만들기 (방장)
      {t:'room_join', id | code, password?, player:{name, color}}                                방 들어가기
      {t:'resume', sid, token?} (연결이 끊겼던 판에 다시 접속: 그 자리로. 싱글은 token 없이도)
    대기실 (브라우저 → 서버): room_ready {on} · room_color {color} · room_spot {y, x} · room_leave {} · room_chat {text}
                              방장만: room_setup {바꿀 것} · room_kick {member} · room_start {}
    대기실 (서버 → 브라우저): room {방 상태 (server/rooms.py Room.view)}, room_error {error, busy?}, room_kicked {}, room_closed {},
                              room_chat {name, color, text} (대기실 대화: 방 안 모두에게, 판 안 대화와 같은 제한)
    상한 (접속자·판·방이 꽉 찼다): error / room_error에 busy: true (브라우저가 '접속자가 많아요' 안내를 띄운다)
    판 (시작한 뒤): 서버 → 브라우저: JSON(start, msg, over, ack, diplo, seats, error)과 이진 상태 메시지(protocol.py),
                     브라우저 → 서버: 명령 JSON (server/session.py)
    판이 끝난 뒤: room_back {} → 같은 방의 대기실로 (처음 돌아온 사람이 방장, 나머지는 돌아오는 대로 들어온다)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import lobby_art
from server.client_info import rules_bin, rules_info
from server.config import ServerConfig
from server.maps import MapStore
from server.rooms import Member, RoomManager
from server.session import CHAT_GAP, CHAT_MAX, GameSession
from server.stats import Stats
from sim import rules as R
from sim.spawn import choose_starts, pick_colors

BUSY_CLIENTS = '지금은 접속자가 많습니다. 잠시 뒤에 다시 해 주세요'
BUSY_GAMES = '지금 열린 판이 너무 많습니다. 잠시 뒤에 다시 해 주세요'
BUSY_ROOMS = '지금 열린 방이 너무 많습니다. 잠시 뒤에 다시 해 주세요'


def create_app(cfg: ServerConfig | None = None) -> FastAPI:
    cfg = cfg or ServerConfig()
    state = {'maps': None, 'sessions': {}, 'layout_maps': {}, 'lobby': None,     # sessions: sid → GameSession
             'clients': 0}                                                       # 게임·대기실에 들어와 있는 연결 수
    rooms = RoomManager()                                                         # 멀티 플레이 방
    stats = Stats(cfg.data_dir / 'stats.json')                                    # /dashboard
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

        async def keep_stats():                                                   # 통계는 1분마다 파일로
            while True:
                await asyncio.sleep(60)
                stats.save()
        saver = asyncio.create_task(keep_stats())
        yield
        saver.cancel()
        stats.save()
        for s in list(state['sessions'].values()):
            s.stop()
        state['maps'].close()

    app = FastAPI(title='Pixel Territory', lifespan=lifespan)
    maps = lambda: state['maps']

    # ------------------------------------------------------------- 로비
    @app.get('/api/lobby')
    async def lobby_info(request: Request):
        # 방문: 페이지를 열 때마다 로비가 한 번 부른다. 프록시(nginx) 뒤면 X-Forwarded-For의 맨 앞이 방문자
        ip = (request.headers.get('x-forwarded-for') or '').split(',')[0].strip() or (request.client.host if request.client else '')
        stats.visit(ip)
        return (await asyncio.to_thread(lobby))[0]

    @app.get('/dashboard')
    def dashboard_page():
        return FileResponse(Path(__file__).with_name('dashboard.html'), media_type='text/html',
                            headers={'Cache-Control': 'no-cache'})

    @app.get('/api/dashboard')
    def dashboard_data():
        """서버 통계: 숫자만 (판 번호·이름·방 코드는 넣지 않는다)."""
        games = []
        for s in list(state['sessions'].values()):
            try:
                w = s.world
                games.append({'multi': len(s.seats) > 1, 'humans': len(s.seats), 'online': sum(not x.away for x in s.seats),
                              'nations': len(w.nations), 'alive': sum(n.alive for n in w.nations),
                              'minutes': round((time.monotonic() - s.born) / 60, 1), 'step_ms': round(s.step_ms, 1),
                              'over': bool(s.match.over)})
            except AttributeError:
                continue
        return {'clients': state['clients'], 'rooms_waiting': sum(r.state == 'wait' for r in rooms.rooms.values()),
                'games': games, 'limits': {'clients': cfg.max_clients, 'games': cfg.max_sessions, 'rooms': cfg.max_rooms},
                'step_budget_ms': round(1000 / cfg.tick_hz, 1), 'days': stats.recent(14), 'usage': stats.usage()}

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

    @app.get('/api/rooms')
    def list_rooms():
        return rooms.listing()

    @app.get('/api/status')
    def status():
        return {'busy': state['clients'] >= cfg.max_clients}

    @app.get('/api/resume')
    def can_resume(sid: str = '', token: str = ''):
        """브라우저를 다시 열었을 때: 끊긴 채 기다리는 내 자리가 있는가 (그 판의 지도 키도)."""
        session = state['sessions'].get(sid)
        seat = session.seat_of(token or None) if session is not None else -1
        ok = session is not None and seat >= 0 and session.alive and not session.crashed and not session.match.over
        return {'ok': bool(ok), 'map': getattr(session.scene, 'map_key', '') if ok else ''}

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
        starts = choose_starts(gmap, n, rng, [player_spot] if player_spot else None, sites)   # 맨 앞 = 고른 사람 자리
        from sim.wildlife import lairs_for
        lairs = lairs_for(gmap, R.WILDLIFE[R.DRAGON]['cap'])               # 드래곤 둥지 (미리보기에 표시)
        from sim.tribes import classify
        return {'starts': [list(map(int, s)) for s in starts], 'colors': pick_colors(rng, n, color),
                'tribes': [classify(gmap, int(s[0]), int(s[1])) for s in starts],   # 자리마다 부족 (sim/tribes.py)
                'lairs': [list(map(int, p)) for p in lairs],
                'sulfur': [[s.y, s.x] for s in sites if s.kind == R.SULFUR]}                # 유황 웅덩이 (미리보기에 표시)

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
        session, seat, room, member = None, 0, None, None
        counted = False

        def send(item):                                     # 세션 스레드에서도 불린다
            loop.call_soon_threadsafe(out.put_nowait, item)

        async def writer():
            while True:
                item = await out.get()
                if isinstance(item, (bytes, bytearray)):
                    await ws.send_bytes(item)
                else:
                    await ws.send_text(json.dumps(item, ensure_ascii=False))

        async def fatal(text):
            await ws.send_text(json.dumps({'t': 'error', 'error': text, 'fatal': True}, ensure_ascii=False))

        wtask = asyncio.create_task(writer())
        try:
            try:
                first = json.loads(await ws.receive_text())
            except ValueError:
                first = {}
            t = first.get('t') if isinstance(first, dict) else None
            if t != 'resume' and state['clients'] >= cfg.max_clients:      # 접속자가 꽉 찼다 (하던 판에 다시 접속은 받는다)
                await ws.send_text(json.dumps({'t': 'error', 'error': BUSY_CLIENTS, 'fatal': True, 'busy': True}, ensure_ascii=False))
                return
            state['clients'] += 1
            counted = True
            stats.clients(state['clients'])
            if t == 'resume':                                               # 끊겼던 판에 다시 접속 (그 자리로)
                session = state['sessions'].get(str(first.get('sid')))
                seat = session.seat_of(first.get('token')) if session is not None else -1
                if session is None or seat < 0 or not session.alive or session.crashed:
                    await fatal('이어 할 판이 없습니다 (너무 오래 끊겼습니다)')
                    return
                session.attach(send, seat)
                r = getattr(session, 'room', None)                          # 방에서 시작한 판: 대기실로 돌아갈 수 있게
                if r is not None:
                    member = next((mm for mm in r.members if mm.game is session and mm.seat == seat), None)
                    if member is not None:
                        room, member.send, member.ws = r, send, ws
            elif t == 'join':                                               # 싱글: 사람 1명짜리 판을 바로
                session = await _start_single(first, send, ws)
                if session is None:
                    return
            elif t in ('room_create', 'room_join'):                         # 멀티: 대기실
                room, member = await _enter_room(first, send, ws)
                if room is None:
                    return
            else:
                await ws.send_text(json.dumps({'t': 'error', 'error': '처음에는 join, room_create, room_join을 보내세요'}))
                return
            while True:
                msg = await ws.receive_text()
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue                                                # 깨진 메시지는 버린다
                if not isinstance(m, dict) or str(m.get('t', '')).startswith('_'):
                    continue
                if room is not None and session is None and member.game is not None:   # 방장이 시작했다: 이제 판의 내 자리로
                    session, seat = member.game, member.seat
                if m.get('t') == 'room_back' and session is not None:     # 판이 끝났다: 같은 방의 대기실로
                    err = await _room_back(room, member, session, seat)
                    if err:
                        send({'t': 'room_error', 'error': err, 'fatal': True})
                    else:
                        session = None
                    continue
                if room is not None and session is None:
                    await _room_message(room, member, m)
                    if member not in room.members:                         # 나갔다
                        room = None
                        return
                    continue
                session.submit(m, seat)
        except WebSocketDisconnect:
            pass
        finally:
            wtask.cancel()
            if counted:
                state['clients'] -= 1
            if room is not None and session is None and member is not None and member.game is not None:
                session, seat = member.game, member.seat
            if session is not None:
                if session.alive and not session.crashed:               # 그 자리는 잠시 비운 채 다시 접속을 기다린다
                    session.detach(seat, send)
                    if session.abandoned:                               # 멀티: 모두 메뉴로 스스로 나갔다 → 바로 지운다
                        session.stop()
                        _forget(session)
                    else:
                        loop.call_later(cfg.resume_seconds, _expire, session)
                else:
                    session.stop()
                    _forget(session)
            elif room is not None and member is not None:              # 대기실에서 나갔다
                rooms.leave(room, member)
                await _broadcast(room)

    async def _start_single(join, send, ws):
        if len(state['sessions']) >= cfg.max_sessions:
            await ws.send_text(json.dumps({'t': 'error', 'error': BUSY_GAMES, 'fatal': True, 'busy': True}, ensure_ascii=False))
            return None
        key = join['map']
        if not await _wait_map(key, ws):
            return None
        scene = await asyncio.to_thread(maps().scene, key)
        session = await asyncio.to_thread(GameSession, scene, join.get('options', {}), send, cfg)
        state['sessions'][session.sid] = session
        stats.game(multi=False)
        session.start()
        return session

    async def _wait_map(key, ws) -> bool:
        """지도가 준비될 때까지 진행 상황을 보낸다. 쓸 수 없으면 알리고 False."""
        while maps().status(key)['state'] == 'building':
            await ws.send_text(json.dumps({'t': 'map_status', **maps().status(key)}, ensure_ascii=False))
            await asyncio.sleep(0.5)
        if maps().status(key)['state'] != 'ready':
            await ws.send_text(json.dumps({'t': 'error', 'error': f'지도를 쓸 수 없습니다: {maps().status(key)}',
                                           'fatal': True}, ensure_ascii=False))
            return False
        await ws.send_text(json.dumps({'t': 'map_status', 'state': 'loading', 'progress': '판 준비 중...'}, ensure_ascii=False))
        return True

    # ------------------------------------------------------------- 방 (대기실)
    async def _enter_room(first, send, ws):
        p = first.get('player') or {}
        member = Member(str(p.get('name') or '이름 없음'), int(p.get('color', 0)), send, ws)
        if first['t'] == 'room_create':
            r = rooms.create(first.get('name'), first.get('password'), first.get('cap', 4), first.get('bots', 0),
                             first.get('start_mode', 'random'), first.get('setup') or {}, cfg.max_rooms, BUSY_ROOMS)
            if isinstance(r, str):
                await ws.send_text(json.dumps({'t': 'room_error', 'error': r, 'fatal': True, 'busy': r == BUSY_ROOMS},
                                              ensure_ascii=False))
                return None, None
        else:
            r = rooms.find(first.get('id'), first.get('code'))
            if r is None:
                await ws.send_text(json.dumps({'t': 'room_error', 'error': '그런 방이 없습니다', 'fatal': True}, ensure_ascii=False))
                return None, None
        got = rooms.join(r, first.get('password'), member)
        if isinstance(got, str):
            await ws.send_text(json.dumps({'t': 'room_error', 'error': got, 'fatal': True}, ensure_ascii=False))
            return None, None
        await _broadcast(r)
        return r, member

    async def _broadcast(r):
        """방 상태를 모두에게 (사람마다 '나'가 다르다). 무작위 배치가 필요하면 먼저 정한다."""
        key = r.setup.get('map', '')
        status = maps().status(key) if key else {'state': 'error'}
        if r.start_mode == 'random' and status.get('state') == 'ready' and (r.layout is None or len(r.layout) != r.nations):
            gmap, sites = await asyncio.to_thread(_layout_map, key)
            from sim.spawn import choose_starts
            r.layout = [list(map(int, q)) for q in choose_starts(gmap, r.nations, np.random.default_rng(), None, sites)]
        tribes = None                                           # 미리보기: 배치·고른 자리마다 부족 (sim/tribes.py)
        if status.get('state') == 'ready':
            from sim.tribes import classify
            gmap, _ = await asyncio.to_thread(_layout_map, key)
            tribes = {'layout': [classify(gmap, int(q[0]), int(q[1])) for q in (r.layout or [])],
                      'spots': [classify(gmap, int(mm.spot[0]), int(mm.spot[1])) if mm.spot else None for mm in r.members]}
        for i, m in enumerate(r.members):
            m.send(r.view(i, status, tribes))

    async def _room_message(r, member, m):
        t = m.get('t')
        me = r.members.index(member)
        host = me == r.host
        err = None
        if r.state != 'wait':
            return
        if t == 'room_chat':                                    # 대기실 대화: 방 안 모두에게 (방 상태는 다시 보내지 않는다)
            text = ''.join(ch for ch in str(m.get('text', '')) if ch.isprintable()).strip()[:CHAT_MAX]
            now = time.monotonic()
            if not text:
                return
            if now - member.chat_at < CHAT_GAP:
                member.send({'t': 'room_error', 'error': '조금 천천히 보내 주세요'})
                return
            member.chat_at = now
            for mm in r.members:
                mm.send({'t': 'room_chat', 'name': member.name, 'color': member.color, 'text': text})
            return
        if t == 'room_leave':
            rooms.leave(r, member)
            member.send({'t': 'room_closed'})
        elif t == 'room_ready':
            member.ready = bool(m.get('on', True))
        elif t == 'room_color':
            err = rooms.set_color(r, member, int(m.get('color', -1)))
        elif t == 'room_spot':
            key = r.setup.get('map', '')
            if maps().status(key).get('state') != 'ready':
                err = '지도가 아직 준비되지 않았습니다'
            else:
                gmap, sites = await asyncio.to_thread(_layout_map, key)
                err = rooms.set_spot(r, member, int(m['y']), int(m['x']), lambda y, x: _check_spot(gmap, sites, y, x))
        elif t == 'room_setup' and host:
            err = rooms.set_setup(r, {k: v for k, v in m.items() if k != 't'})
        elif t == 'room_kick' and host:
            k = int(m.get('member', -1))
            if 0 <= k < len(r.members) and k != me:
                gone = r.members[k]
                rooms.leave(r, gone)
                gone.send({'t': 'room_kicked'})
                if gone.ws is not None:
                    asyncio.create_task(gone.ws.close())
        elif t == 'room_start' and host:
            err = r.can_start() or await _start_room(r)
            if err is None:
                return
        else:
            err = '방장만 할 수 있습니다' if t in ('room_setup', 'room_kick', 'room_start') else f'모르는 명령 {t}'
        if err:
            member.send({'t': 'room_error', 'error': err, 'busy': err in (BUSY_GAMES, BUSY_ROOMS)})
        if r.members:
            await _broadcast(r)

    async def _start_room(r) -> str | None:
        """방장이 시작: 지도를 확인하고 판(GameSession)을 만든다. 사람 자리 = 참가자 순서."""
        if len(state['sessions']) >= cfg.max_sessions:
            return BUSY_GAMES
        key = r.setup.get('map', '')
        if maps().status(key).get('state') != 'ready':
            return '지도가 아직 준비되지 않았습니다'
        r.state = 'starting'
        await _broadcast(r)
        try:
            scene = await asyncio.to_thread(maps().scene, key)
            players = [{'name': m.name, 'color': m.color, 'spot': list(m.spot) if (m.spot and r.start_mode == 'pick') else None}
                       for m in r.members]
            opts = {'bots': r.bots, 'difficulty': r.setup.get('difficulty', '보통'), 'season': int(r.setup.get('season', 0)),
                    'fog': bool(r.setup.get('fog', False)),
                    'players': players, 'room': True}
            if r.start_mode == 'random' and r.layout and len(r.layout) == len(r.members) + r.bots:
                opts['starts'] = r.layout                               # 대기실에서 보여 준 배치 그대로
            for i, m in enumerate(r.members):
                m.seat = i
            session = await asyncio.to_thread(GameSession, scene, opts, [m.send for m in r.members], cfg)
        except Exception as e:                                          # 판을 못 만들었다: 대기실로 되돌린다
            r.state = 'wait'
            return f'판을 만들지 못했습니다: {e}'
        state['sessions'][session.sid] = session
        session.room = r
        r.session = session
        stats.game(multi=True)
        for m in r.members:
            m.game = session
        r.state = 'play'
        session.start()
        return None

    async def _room_back(r, member, session, seat) -> str | None:
        """판이 끝난 뒤 대기실로: 처음 돌아온 사람이 방을 대기 상태로 되돌리고 (방장), 나머지는 돌아오는 대로 들어온다.
        지도·설정은 그대로, 준비·시작 자리는 다시. 모두 떠난 판은 바로 정리한다."""
        if r is None or member is None or rooms.rooms.get(r.id) is not r:
            return '방이 없어졌습니다'
        if not session.match.over:
            return '판이 아직 끝나지 않았습니다'
        if r.session is session:                                     # 처음 돌아온 사람
            r.state, r.session, r.last = 'wait', None, session
            r.members, r.host, r.layout, r.created = [], 0, None, time.monotonic()
        elif not (r.state == 'wait' and getattr(r, 'last', None) is session):
            return '방이 이미 새 판을 시작했습니다'
        if len(r.members) >= r.cap:
            return '방이 가득 찼습니다'
        session.release(seat)
        if session.away:                                             # 모두 떠났다: 판 정리
            session.stop()
            _forget(session)
        member.ready, member.spot, member.seat, member.game = False, None, -1, None
        if any(mm.color == member.color for mm in r.members):
            member.color = r.free_color()
        r.members.append(member)
        await _broadcast(r)
        return None

    def _forget(session):
        state['sessions'].pop(session.sid, None)
        r = getattr(session, 'room', None)
        if r is not None and r.session is session:                   # 대기실로 돌아간 방은 남긴다
            rooms.rooms.pop(r.id, None)

    def _expire(session):
        """사람이 모두 나간 뒤 다시 접속하지 않은 판을 정리한다 (방도 함께)."""
        if session.away and time.monotonic() - session.away_since >= cfg.resume_seconds - 0.5:
            session.stop()
            _forget(session)

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
    w = World(GameMap(scene), 3, seed=1, map_seed=scene.config.seed)
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
