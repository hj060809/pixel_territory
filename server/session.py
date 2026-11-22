"""판 하나: 자기 스레드에서 초당 tick_hz번 걸음을 돌리고, 걸음마다 상태 메시지를 보낸다.

걸음 하나
1. 받은 명령을 적용한다 (브라우저 → JSON, 받는 즉시 줄에 넣고 다음 걸음 맨 앞에서 처리: 최대 1걸음 대기)
2. 게임 시간을 진행한다 (일시정지/속도). 낮밤 시계, 1년 시계. 눈·얼음은 계절이 1/240년 움직이고
   실제 1초가 지났을 때만 갱신한다. 계산(수십 ms)은 보조 스레드에서 하고, 다 되면 걸음 맨 앞에서 바꿔 끼운다
3. 세계 진행 (world.update, 안에서 0.05초 걸음으로 나눈다)
4. 상태 메시지(이진)와 새 알림(JSON)을 보낸다

명령 (JSON, 't'로 구분)
    command  {units:[[칸,세대]...], ships:[번호...], x, y, attack, r}   오른쪽 클릭 (r: 클릭 반경, 화면 배율에 따라)
    place    {kind:'tower'|'hall'|'harbor', units, x, y}               건물 자리
    train    {kind:'infantry'|'archer'|'warship', buildings:[[칸,세대]...]}
    stop     {units}
    pause    {on}            speed {value: 1|2|4}            restart {}  (같은 지도로 새 판)

연결이 끊기면 (detach) 판은 멈춘 채 잠시 남아 있고, 같은 sid로 다시 접속하면 (attach) 전체 상태를 다시 보내고 이어 간다.
걸음 안에서 오류가 나면 브라우저에 알리고 판을 멈춘다 (서버 로그에 자세히).
"""
from __future__ import annotations

import secrets
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from engine.render.daylight import DayNightCycle
from engine.render.seasons import SEASON_CENTERS, SeasonCycle
from server.client_info import rules_info
from server.protocol import StateEncoder
from sim import rules as R
from sim.commands import PlayerCommands
from sim.terrain import GameMap
from sim.world import World


class GameSession:
    def __init__(self, scene, options: dict, send, cfg):
        """scene: TerrainScene, send(bytes|dict): 브라우저로 보내기 (다른 스레드에서 불린다)."""
        self.scene, self.opts, self.send, self.cfg = scene, dict(options), send, cfg
        self.gmap = GameMap(scene)
        self.season = SeasonCycle(year=(SEASON_CENTERS[int(options.get('season', 0))] - 0.08) % 1.0,
                                  year_length=cfg.year_length)
        self.day = DayNightCycle(hour=9.0, day_length=cfg.day_length)
        self.gmap.set_season(self.season.weights())
        self._season_step = int(self.season.year * 240)
        self._season_at = time.perf_counter()
        self.paused, self.speed = False, 1.0
        self.away = False                       # 연결이 끊겨 기다리는 중 (다시 접속하면 이어 간다)
        self.away_since = 0.0
        self.sid = secrets.token_urlsafe(9)     # 다시 접속할 때 쓰는 판 번호
        self.crashed = False
        self._resumed = False
        self._season_pool = ThreadPoolExecutor(1, thread_name_prefix='season')
        self._season_job = None
        self._inbox: deque = deque()
        self._stop = threading.Event()
        self._thread = None
        self.round = 0
        self._new_world(first=True)

    # ------------------------------------------------------------- 판
    def _new_world(self, first=False):
        o = self.opts
        self.round += 1
        seed = int(np.random.default_rng().integers(2 ** 31))
        starts = o.get('starts') if first else None                 # 미리보기로 본 배치는 첫 판에만
        colors = o.get('colors') if first else None
        self.world = World(self.gmap, int(o.get('bots', 4)), seed=seed, map_seed=self.scene.config.seed,
                           player_spot=tuple(o['spot']) if o.get('spot') and first else None,
                           player_color=int(o.get('color', 0)), player_name=o.get('name') or '나',
                           difficulty=R.DIFFICULTY.get(o.get('difficulty', '보통'), 1.0),
                           starts=[tuple(s) for s in starts] if starts else None, colors=colors)
        self.cmd = PlayerCommands(self.world, 0)
        self.encoder = StateEncoder(self.world) if first else (self.encoder.reset(self.world) or self.encoder)
        self._msg_seen = 0.0
        self._over_sent = False
        self.send({'t': 'start', **self.info()})

    def info(self) -> dict:
        w = self.world
        return {
            'map': getattr(self.scene, 'map_key', ''), 'H': self.scene.H, 'W': self.scene.W, 'round': self.round,
            'tick_hz': self.cfg.tick_hz, 'me': 0,
            'nations': [{'id': n.id, 'name': n.name, 'color': list(n.color), 'light': list(n.light)} for n in w.nations],
            'sites': [{'id': s.id, 'kind': s.kind, 'x': s.x, 'y': s.y, 'rich': round(s.rich, 2)} for s in w.sites],
            'lairs': [[lr.y, lr.x] for lr in w.wild.lairs],
            'year_length': self.cfg.year_length, 'day_length': self.cfg.day_length,
            'rules': rules_info(), 'sid': self.sid, 'resumed': self._resumed, 'dev': bool(self.cfg.dev),
        }

    # ------------------------------------------------------------- 실행
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name='game-session')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._season_pool.shutdown(wait=False, cancel_futures=True)

    def submit(self, msg: dict):
        self._inbox.append(msg)

    # ------------------------------------------------------------- 연결
    def detach(self):
        """연결이 끊겼다: 보내기를 멈추고 판을 멈춘 채 기다린다."""
        self.send = lambda item: None
        self.away, self.away_since = True, time.monotonic()

    def attach(self, send):
        """다시 접속: 판 정보와 전체 상태를 다시 보내고 이어 간다 (다음 걸음부터)."""
        self._inbox.append({'t': '_attach', 'send': send})

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
    def _run(self):
        period = 1.0 / self.cfg.tick_hz
        nxt = time.perf_counter()
        n = 0
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                self._apply_commands()
                w = self.world
                running = not self.paused and not self.away and w.phase == 'play'
                gdt = period * self.speed if running else 0.0
                self.day.update(gdt)
                self.season.update(gdt)
                self._maybe_set_season()
                w.update(gdt, self.season.weights())
                sim_ms = (time.perf_counter() - t0) * 1000
                flags = int(self.paused or self.away) | (2 if w.phase == 'over' else 0) | (4 if w.result == '승리' else 0)
                self.send(self.encoder.encode({'hour': self.day.hour, 'year': self.season.year, 'flags': flags,
                                               'speed': self.speed}, nations=(n % 4 == 0), sim_ms=sim_ms))
                self._send_messages()
            except Exception:                       # 판을 멈추고 알린다 (서버는 계속 돈다)
                traceback.print_exc()
                self.crashed = True
                self.send({'t': 'error', 'error': '서버에서 오류가 나서 판이 멈췄습니다. F10으로 로비에 가서 다시 시작해 주세요',
                           'fatal': True})
                break
            n += 1
            nxt += period
            delay = nxt - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)
            else:
                nxt = time.perf_counter()           # 밀렸으면 따라잡지 않고 다시 맞춘다

    def _maybe_set_season(self):
        """눈·얼음 갱신: 계산은 보조 스레드에서 (걸음을 막지 않게), 다 되면 여기서 바꿔 끼운다."""
        job = self._season_job
        if job is not None:
            if job.done():
                self._season_job = None
                self.gmap.install_season(job.result())
            return
        step = int(self.season.year * 240)
        now = time.perf_counter()
        if step != self._season_step and now - self._season_at >= 1.0:
            self._season_step, self._season_at = step, now
            self._season_job = self._season_pool.submit(self.gmap.compute_season, self.season.weights())

    def _send_messages(self):
        w = self.world
        new = [(text, t) for text, t in w.messages if t > self._msg_seen]
        if new:
            self._msg_seen = new[-1][1]
            self.send({'t': 'msg', 'items': [text for text, _ in new]})
        if w.phase == 'over' and not self._over_sent:
            self._over_sent = True
            self.send({'t': 'over', 'result': w.result})

    # ------------------------------------------------------------- 명령
    def _apply_commands(self):
        while self._inbox:
            m = self._inbox.popleft()
            try:
                self._apply(m)
            except (KeyError, TypeError, ValueError) as e:
                self.send({'t': 'error', 'error': f'잘못된 명령: {e}'})

    def _apply(self, m: dict):
        t, c = m.get('t'), self.cmd
        if t == '_attach':                          # 다시 접속 (서버 안에서만 쓰는 명령)
            self.send = m['send']
            self.away = False
            self._resumed = True
            self.encoder.reset()
            self.send({'t': 'start', **self.info()})
            self._resumed = False
            self._msg_seen = self.world.time
            if self.world.phase == 'over':
                self.send({'t': 'over', 'result': self.world.result})
            return
        if t == 'command':
            shown = c.command(m.get('units', []), m.get('ships', []), float(m['x']), float(m['y']),
                              bool(m.get('attack')), float(m.get('r', 2.0)))
            if 'id' in m:
                self.send({'t': 'ack', 'id': m['id'], 'shown': shown})
        elif t == 'place':
            c.place(m['kind'], m.get('units', []), float(m['x']), float(m['y']))
        elif t == 'train':
            c.train(m['kind'], m.get('buildings', []))
        elif t == 'stop':
            c.stop(m.get('units', []))
        elif t == 'pause':
            self.paused = bool(m.get('on', not self.paused))
        elif t == 'speed':
            self.speed = float(m['value']) if float(m['value']) in (1.0, 2.0, 4.0) else 1.0
        elif t == 'restart':
            self._new_world()
        elif t == 'dev' and self.cfg.dev:                # 개발용 (서버를 --dev로 켰을 때만)
            if m.get('cmd') == 'res':
                add = [float(min(max(v, -1e6), 1e6)) for v in m.get('add', [0, 0, 0])[:3]]
                nat = self.world.nations[0]
                nat.res = [max(0.0, r + a) for r, a in zip(nat.res, add)]
                self.world.say('개발: 자원 ' + ', '.join(f'{n} {a:+.0f}' for n, a in zip(('식량', '목재', '석재'), add) if a))
        else:
            raise ValueError(f'모르는 명령 {t}')
