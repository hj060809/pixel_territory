"""판 하나: 자기 스레드에서 초당 tick_hz번 걸음을 돌리고, 걸음마다 사람 자리(Seat)마다 상태 메시지를 보낸다.

판 = 세계(World, 나라만 안다) + 나라마다 조종자 (sim/match.py): 사람 자리 Seat 또는 AI.
싱글 = 사람 1 + AI, 멀티 = 사람 N + AI (구조는 같다). 사람이 몇 번 나라를 맡을지는 무작위 (0번에 고정하지 않는다).

걸음 하나
1. 받은 명령을 적용한다 (자리마다 그 나라로. 받는 즉시 줄에 넣고 다음 걸음 맨 앞에서 처리: 최대 1걸음 대기)
2. 게임 시간을 진행한다. 속도·일시정지는 사람이 1명인 판에서만. 접속한 사람이 없으면 멈춘다.
   낮밤 시계, 1년 시계. 눈·얼음은 계절이 1/240년 움직이고 실제 1초가 지났을 때만 갱신한다
   (계산(수십 ms)은 보조 스레드에서 하고, 다 되면 걸음 맨 앞에서 바꿔 끼운다)
3. 세계 진행 (Match.update → world.update, 안에서 0.05초 걸음으로 나누고 AI가 돌아가며 생각한다)
4. 상태 메시지(이진)는 한 번만 만들어 모든 자리에 보낸다 (자리마다 다른 것은 머리의 flags 1바이트뿐).
   알림(JSON)은 그 자리의 나라에게 온 것만, 외교 상태는 그 나라의 눈으로.

명령 (JSON, 't'로 구분)
    command  {units:[[칸,세대]...], ships:[번호...], x, y, attack, r}   오른쪽 클릭 (r: 클릭 반경, 화면 배율에 따라)
    formation {spots:[[칸,세대,x,y]...], attack}                       진형: 병사마다 제 자리 (화면이 선·대형으로 계산)
    place    {kind:'tower'|'hall'|'harbor'|..., units, x, y}           건물 자리
    train    {kind:'infantry'|'archer'|'warship', buildings:[[칸,세대]...]}
    stop     {units}
    diplo    {act, to, ...}  외교 (상대 나라 번호 to)
    tribe    {accept}        개척 카드: 새 기후 부족으로 바꾸기 / 지금 부족 지키기 (sim/tribes.py Pioneer)
    surrender {}             항복 (내 나라를 모두 허물고 관전)
    leave    {}              판을 떠난다 (사람이 여럿인 판: 30초를 기다리지 않고 바로 조종자 없음)
    chat     {text}          대화 (판의 모든 사람에게 그대로: CHAT_MAX글자, CHAT_GAP초에 하나. 진 사람도. 기록은 남기지 않는다)
    pause    {on, auto?}     speed {value: 1|2|4}            restart {}  (같은 지도로 새 판) — 사람 1명인 판에서만

보내는 것 (JSON): start, msg, over, diplo, ack, error, fog {gw, gh, cell, rle | off} (전장의 안개 판: 0 안 가 봄, 1 가 봄, 2 보임), seats {away:[나라], gone:[나라]} (사람 나라의 접속 상태가 바뀔 때),
                 chat {from: 나라, text}, tribe {tribes: [나라마다 부족], offers: [내 카드의 기후], dropped: [버린 기후]}

연결이 끊기면 (detach) 그 자리는 잠시 비고, 같은 sid로 다시 접속하면 (attach) 전체 상태를 다시 보내고 이어 간다.
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
from sim.match import Match
from sim.spawn import pick_colors
from sim.terrain import GameMap
from sim.world import World

FLAGS_AT = 17                                    # 상태 메시지 머리에서 flags 바이트 자리 (protocol.encode: '<BIfffBBH')
DEV_SPAWN_MAX = 200                              # 개발 명령: 한 번에 소환하는 병사 수 한도
DEV_SPAWN_KINDS = (R.INFANTRY, R.ARCHER, R.LANCER, R.HORSE_ARCHER, R.DRAGON_RIDER, R.TORTOISE, R.GRENADIER, R.HORSE_GRENADIER)   # 소환할 수 있는 병종 (야생 드래곤은 빼고)
LEAVE_AFTER = 30.0                               # 사람이 2명 이상인 판: 이만큼 끊겨 있으면 그 나라는 조종자 없음
CHAT_MAX = 80                                    # 대화 한 줄 글자 수
CHAT_GAP = 0.7                                   # 대화 사이 최소 간격 (초, 도배 막기)


class Seat:
    """사람 자리: 접속 하나 = 나라 하나. 그 나라로 명령하고, 그 나라에게 온 알림·외교 상태를 받는다."""

    def __init__(self, send, name: str, color: int, spot=None):
        self.send = send
        self.name, self.color, self.spot = name, color, spot
        self.nid = -1                            # 판마다 정해진다
        self.cmd: PlayerCommands | None = None
        self.away = False                        # 연결이 끊겨 기다리는 중
        self.away_since = 0.0
        self.msg_seen = -1.0
        self.diplo_v, self.diplo_at = -1, -1e9
        self.tribe_v = -1                        # 마지막으로 보낸 부족·카드 판 (sim/tribes.py Pioneer)
        self.enc = None                          # 전장의 안개 판: 이 자리만의 상태 만들기 (보이는 것만)
        self.fog_v = None                        # 마지막으로 보낸 안개 격자 판
        self.over_sent = False
        self.left = False                        # 오래 끊겨 (또는 스스로 나가) '조종자 없음'이 됐다
        self.quit = False                        # 메뉴로 스스로 나갔다 (끊김과 달리 돌아오지 않는다)
        self.seats_v = -1                        # 마지막으로 보낸 접속 상태 판
        self.chat_at = -1e9                      # 마지막으로 말한 때 (도배 막기)
        self.token = secrets.token_urlsafe(9)    # 다시 접속할 때 이 자리를 찾는 표


def _rle(a) -> list:
    """[값, 길이, 값, 길이, ...] (안개 격자)."""
    a = np.asarray(a)
    if not len(a):
        return []
    cut = np.flatnonzero(a[1:] != a[:-1]) + 1
    starts = np.concatenate(([0], cut))
    lens = np.diff(np.concatenate((starts, [len(a)])))
    out = np.empty(len(starts) * 2, np.int64)
    out[0::2], out[1::2] = a[starts], lens
    return out.tolist()


class GameSession:
    def __init__(self, scene, options: dict, send, cfg):
        """scene: TerrainScene, send(bytes|dict): 브라우저로 보내기 (다른 스레드에서 불린다). 사람이 여럿이면 send의 목록.
        options: 판 설정 (bots: AI 수, difficulty, season, fog: 전장의 안개). 사람: name, color, spot (싱글, 미리보기의 starts/colors도)
                 또는 players: [{name, color, spot}...] (사람 여럿: send 목록과 같은 순서)."""
        self.scene, self.opts, self.cfg = scene, dict(options), cfg
        self.gmap = GameMap(scene)
        self.season = SeasonCycle(year=(SEASON_CENTERS[int(options.get('season', 0))] - 0.08) % 1.0,
                                  year_length=cfg.year_length)
        self.day = DayNightCycle(hour=9.0, day_length=cfg.day_length)
        self.gmap.set_season(self.season.weights())
        self._season_step = int(self.season.year * 240)
        self._season_at = time.perf_counter()
        self.paused, self.speed = False, 1.0
        self.auto_paused = False                 # 탭을 숨겨서 건 일시정지 (다시 접속하면 푼다: 새로고침 때 옛 탭이 걸고 간다)
        self.sid = secrets.token_urlsafe(9)     # 다시 접속할 때 쓰는 판 번호
        self.crashed = False
        self._resumed = False
        self._season_pool = ThreadPoolExecutor(1, thread_name_prefix='season')
        self._season_job = None
        self._inbox: deque = deque()             # (자리, 명령)
        self._stop = threading.Event()
        self._thread = None
        self.round = 0
        self.born = time.monotonic()             # 판을 연 때 (통계: 판이 돈 시간)
        self.step_ms = 0.0                       # 걸음 하나에 걸린 시간 (평균, 통계: 한 걸음 예산은 1000/tick_hz ms)
        self.rng = np.random.default_rng()
        self._seats_sig = None                   # 사람 나라의 접속 상태 (바뀌면 모두에게 seats)
        self._seats_v = 0
        sends = list(send) if isinstance(send, (list, tuple)) else [send]
        players = options.get('players') or [{'name': options.get('name') or '나', 'color': options.get('color', 0),
                                              'spot': options.get('spot')}]
        self.seats = [Seat(sd, p.get('name') or f'사람 {i + 1}', int(p.get('color', i)), tuple(p['spot']) if p.get('spot') else None)
                      for i, (sd, p) in enumerate(zip(sends, players))]
        self._new_world(first=True)

    # ------------------------------------------------------------- 사람 자리
    @property
    def tutorial(self) -> bool:
        """튜토리얼 판 (로비 '튜토리얼'): 나라 둘, 가만히 있는 적 (sim/tutorial.py)."""
        return bool(self.opts.get('tutorial')) and len(self.seats) == 1

    @property
    def fog(self) -> bool:
        """전장의 안개 판 (설정 화면·방에서 정한다, 게임 중엔 못 바꾼다. 튜토리얼은 없다): 사람 나라마다 보이는 것만 보낸다 (sim/vision.py)."""
        return bool(self.opts.get('fog')) and not self.tutorial

    def _see_all(self, s) -> bool:
        """안개를 걷는다: 진 사람 (관전), 판이 끝났을 때."""
        return self.match.over or s.nid in self.match.lost or not self.world.nations[s.nid].alive

    @property
    def solo(self) -> bool:
        """사람이 1명인 판 (싱글): 속도·일시정지·새 판을 쓸 수 있다."""
        return len(self.seats) == 1

    @property
    def dev(self) -> bool:
        """개발 명령 (` 콘솔: 자원·소환·습격)을 받는 판: 혼자 하는 판은 배포 서버에서도, 사람이 여럿인 판은 --dev 서버에서만 (치트 막기)."""
        return self.solo or bool(self.cfg.dev)

    @property
    def away(self) -> bool:
        """접속한 사람이 아무도 없다 (판을 멈춘다)."""
        return all(s.away for s in self.seats)

    @property
    def away_since(self) -> float:
        return max(s.away_since for s in self.seats)

    @property
    def send(self):                              # 싱글에서 쓰던 이름 (첫 자리)
        return self.seats[0].send

    # ------------------------------------------------------------- 판
    def _new_world(self, first=False):
        o, rng = self.opts, self.rng
        self.round += 1
        tut = self.tutorial
        n = 2 if tut else min(int(o.get('bots', 4)) + len(self.seats), len(R.COLORS))
        humans = [int(h) for h in rng.permutation(n)[:len(self.seats)]]   # 사람이 맡을 나라 (무작위: 0번 고정 아님)
        for seat, h in zip(self.seats, humans):
            seat.nid = h
        # 색·이름·시작 자리: 사람 자리는 고른 대로, 나머지는 무작위. 미리보기 배치는 첫 판에만 그대로
        # (미리보기 목록은 사람 자리 순서, 그다음 AI: k번째 → 나라 order[k])
        order = humans + [i for i in range(n) if i not in humans]
        starts = o.get('starts') if first else None
        pcolors = o.get('colors') if first else None
        if pcolors and len(pcolors) == n:
            colors = [0] * n
            for k, nid in enumerate(order):
                colors[nid] = int(pcolors[k])
        else:
            taken = {s.color for s in self.seats}
            rest = [c for c in pick_colors(rng, len(R.COLORS)) if c not in taken]
            colors = [0] * n
            for s in self.seats:
                colors[s.nid] = s.color
            it = iter(rest)
            for i in range(n):
                if i not in humans:
                    colors[i] = next(it)
        if tut:                                  # 튜토리얼: 정해 둔 자리 (내 거점, 가까운 적 거점) — sim/tutorial.py
            from sim import tutorial
            from sim.sites import sites_for
            mine, foe = tutorial.starts(self.gmap, sites_for(self.gmap, self.scene.config.seed))
            starts = [None, None]
            starts[humans[0]], starts[1 - humans[0]] = mine, foe
        elif starts and len(starts) == n:
            st = [None] * n
            for k, nid in enumerate(order):
                st[nid] = tuple(starts[k])
            starts = st
        else:
            starts = None
        names = [None] * n
        for s in self.seats:
            names[s.nid] = s.name
        spots = {s.nid: s.spot for s in self.seats if s.spot and first}
        seed = int(rng.integers(2 ** 31))
        self.world = World(self.gmap, n, seed=seed, map_seed=self.scene.config.seed,
                           starts=starts, colors=colors, names=names, spots=spots)
        self.match = Match(self.world, humans, difficulty=R.DIFFICULTY.get(o.get('difficulty', '보통'), 1.0))
        if tut:                                  # 튜토리얼의 적은 생각하지 않는다 (먼저 쳐들어오지 않는다)
            from sim import tutorial
            self.match.bots, self.match._order = {}, []
            tutorial.setup(self.world, humans[0], 1 - humans[0])
        self.encoder = StateEncoder(self.world) if first else (self.encoder.reset(self.world) or self.encoder)
        if self.fog:                             # 전장의 안개: 나라마다 시야, 자리마다 따로 만든 상태
            from sim.vision import Vision
            self.world.vision = Vision(self.world)
        for s in self.seats:
            s.enc = StateEncoder(self.world, s.nid) if self.fog else None
            s.fog_v = None
            s.cmd = PlayerCommands(self.world, s.nid)
            s.msg_seen = -1.0
            s.diplo_v, s.diplo_at = -1, -1e9
            s.tribe_v = -1
            s.over_sent = False
            s.seats_v = -1
            s.send({'t': 'start', **self.info(s)})

    def info(self, seat: Seat) -> dict:
        w = self.world
        return {
            'map': getattr(self.scene, 'map_key', ''), 'H': self.scene.H, 'W': self.scene.W, 'round': self.round,
            'tick_hz': self.cfg.tick_hz, 'me': seat.nid, 'humans': len(self.seats), 'room': bool(self.opts.get('room')),
            'tutorial': self.tutorial, 'fog': self.fog,
            'nations': [{'id': n.id, 'name': n.name, 'color': list(n.color), 'light': list(n.light), 'tribe': n.tribe} for n in w.nations],
            'sites': [{'id': s.id, 'kind': s.kind, 'x': s.x, 'y': s.y, 'rich': round(s.rich, 2), 'cold': round(s.cold, 3), 'snow': s.snow} for s in w.sites],
            'lairs': [[lr.y, lr.x] for lr in w.wild.lairs],
            'year_length': self.cfg.year_length, 'day_length': self.cfg.day_length,
            'rules': rules_info(), 'sid': self.sid, 'token': seat.token, 'resumed': self._resumed, 'dev': self.dev,
        }

    def seat_of(self, token: str | None) -> int:
        """다시 접속: 표로 자리를 찾는다 (없으면 싱글의 첫 자리, 못 찾으면 -1)."""
        if not token:
            return 0 if self.solo else -1
        return next((i for i, s in enumerate(self.seats) if s.token == token), -1)

    # ------------------------------------------------------------- 실행
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name='game-session')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._season_pool.shutdown(wait=False, cancel_futures=True)

    def submit(self, msg: dict, seat: int = 0):
        """명령을 줄에 넣는다 (seat: 자리 번호, 싱글은 0)."""
        if msg.get('t') == 'leave':              # 스스로 나감은 바로 표시 (곧 이어 연결이 닫힌다: abandoned)
            self.seats[seat].quit = True
        self._inbox.append((seat, msg))

    # ------------------------------------------------------------- 연결
    def detach(self, seat: int = 0, send=None):
        """연결이 끊겼다: 그 자리는 보내기를 멈추고 기다린다 (아무도 없으면 판이 멈춘다).
        send: 끊긴 연결의 보내기. 그 자리를 이미 새 연결이 넘겨받았으면 (새로고침) 아무것도 하지 않는다."""
        s = self.seats[seat]
        if send is not None and s.send is not send and not s.away:
            return
        s.send = lambda item: None
        s.away, s.away_since = True, time.monotonic()
        if not self.solo:                        # 모두에게 (30초 기다린다)
            self._inbox.append((seat, {'t': '_away'}))

    def release(self, seat: int):
        """판이 끝난 뒤 대기실로 돌아갔다: 그 자리는 더 보내지 않는다 (알림 없이)."""
        s = self.seats[seat]
        s.send = lambda item: None
        s.away, s.away_since, s.left, s.quit = True, time.monotonic(), True, True

    def attach(self, send, seat: int = 0):
        """다시 접속: 판 정보와 전체 상태를 다시 보내고 이어 간다 (다음 걸음부터)."""
        self._inbox.append((seat, {'t': '_attach', 'send': send}))

    @property
    def abandoned(self) -> bool:
        """사람이 여럿인 판에서 모두 메뉴로 스스로 나갔다 (끝난 판, 사람이 다 져서 AI만 남은 판 등): 기다리지 않고 바로 지운다.
        한 명이라도 끊겨서 나간 것이면 아니다 (RESUME_SECONDS 동안 다시 접속을 기다린다)."""
        return not self.solo and all(s.away and s.quit for s in self.seats)

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        period = 1.0 / self.cfg.tick_hz
        nxt = time.perf_counter()
        n = 0
        while not self._stop.is_set():
            try:
                self.step(period, n)
            except Exception:                       # 판을 멈추고 알린다 (서버는 계속 돈다)
                traceback.print_exc()
                self.crashed = True
                for s in self.seats:
                    s.send({'t': 'error', 'error': '서버에서 오류가 나서 판이 멈췄습니다. F10으로 로비에 가서 다시 시작해 주세요',
                            'fatal': True})
                break
            n += 1
            nxt += period
            delay = nxt - time.perf_counter()
            if delay > 0:
                self._stop.wait(delay)
            else:
                nxt = time.perf_counter()           # 밀렸으면 따라잡지 않고 다시 맞춘다

    def step(self, period: float, n: int = 0):
        """걸음 하나: 명령 → 진행 → 자리마다 보내기 (상태 메시지는 한 번만 만든다)."""
        t0 = time.perf_counter()
        self._apply_commands()
        m = self.match
        if not self.solo:                        # 오래 끊긴 사람의 나라: 조종자 없음 (병사·건물은 그대로, 알림만)
            now = time.monotonic()
            for s in self.seats:
                if s.away and not s.left and now - s.away_since >= LEAVE_AFTER:
                    s.left = True
                    m.leave(s.nid)
        paused = self.paused and self.solo
        speed = self.speed if self.solo else 1.0
        running = not paused and not self.away and not m.over
        gdt = period * speed if running else 0.0
        self.day.update(gdt)
        self.season.update(gdt)
        self._maybe_set_season()
        m.update(gdt, self.season.weights())
        if not self.solo:                        # 사람 나라의 접속 상태: 바뀌면 모두에게
            sig = (tuple(s.nid for s in self.seats if s.away and not s.left), tuple(sorted(m.gone)))
            if sig != self._seats_sig:
                self._seats_sig = sig
                self._seats_v += 1
        sim_ms = (time.perf_counter() - t0) * 1000
        base = int(paused or self.away) | (2 if m.over else 0)
        header = {'hour': self.day.hour, 'year': self.season.year, 'flags': base, 'speed': speed}
        if self.fog:
            self.world.vision.update()
        msg = None if self.fog else self.encoder.encode(header, nations=(n % 4 == 0), sim_ms=sim_ms)
        for s in self.seats:
            if s.away:
                continue
            out = msg if msg is not None else s.enc.encode(header, nations=(n % 4 == 0), sim_ms=sim_ms, fog=not self._see_all(s))
            if m.result.get(s.nid) == '승리':           # 자리마다 다른 것: 이긴 사람의 flags (4)
                out = bytearray(msg)
                out[FLAGS_AT] = base | 4
                out = bytes(out)
            s.send(out)
            self._send_messages(s)
        self.step_ms += ((time.perf_counter() - t0) * 1000 - self.step_ms) * 0.05

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

    def _dev_spawn(self, nid: int, kind: int, n: int, x: float, y: float) -> int:
        """(개발) kind 병사 n명을 (x, y)에서 가장 가까운 걸을 수 있는 칸부터 하나씩 (가운데가 물이면 가장 가까운 땅). 반환: 만든 수."""
        w, m = self.world, self.world.map
        x = float(np.clip(x, 0, m.W - 1)); y = float(np.clip(y, 0, m.H - 1))
        for r in (6, 12, 24, 48, 96):
            y0, y1, x0, x1 = max(int(y) - r, 0), min(int(y) + r + 1, m.H), max(int(x) - r, 0), min(int(x) + r + 1, m.W)
            ys, xs = np.nonzero(m.walk[y0:y1, x0:x1] & m.land[y0:y1, x0:x1])
            if len(ys) >= n or r == 96:
                break
        if not len(ys):
            return 0
        order = np.argsort((ys + y0 + 0.5 - y) ** 2 + (xs + x0 + 0.5 - x) ** 2)
        hp = R.UNIT_STATS[kind]['hp']
        got = 0
        for k in range(n):
            c = order[k % len(order)]
            if w.units.add(nid, kind, float(xs[c] + x0) + 0.5, float(ys[c] + y0) + 0.5, hp) >= 0:
                got += 1
        return got

    def _dev_ships(self, nid: int, n: int, x: float, y: float) -> int:
        """(개발) 전함 n척을 (x, y)에서 가장 가까운 배가 다닐 바다부터 (서로 4칸 넘게 떨어지게). 반환: 만든 수."""
        from sim.boats import WARSHIP, Boat
        w, m = self.world, self.world.map
        for r in (12, 24, 48, 96, 192):
            y0, y1, x0, x1 = max(int(y) - r, 0), min(int(y) + r + 1, m.H), max(int(x) - r, 0), min(int(x) + r + 1, m.W)
            ys, xs = np.nonzero(m.nav[y0:y1, x0:x1])
            if len(ys) >= n * 20 or r == 192:
                break
        if not len(ys):
            return 0
        order = np.argsort((ys + y0 + 0.5 - y) ** 2 + (xs + x0 + 0.5 - x) ** 2)
        placed: list = []
        for c in order:
            cy, cx = float(ys[c] + y0) + 0.5, float(xs[c] + x0) + 0.5
            if all(np.hypot(cy - py, cx - px) > 4.0 for py, px in placed):
                w.fleet._add(Boat(WARSHIP, nid, cy, cx, R.WARSHIP_HP))
                placed.append((cy, cx))
                if len(placed) >= n:
                    break
        return len(placed)

    def _send_messages(self, s: Seat):
        """그 자리의 나라에게 온 알림, 판 끝 (그 나라의 결과), 외교 상태 (바뀌었거나 1초 지났으면)."""
        w, m, nid = self.world, self.match, s.nid
        new = [text for text, t, to, skip in w.messages if t > s.msg_seen and (to is None or to == nid) and nid not in skip]
        if w.messages:
            s.msg_seen = w.messages[-1][1]
        if new:
            s.send({'t': 'msg', 'items': new})
        if not s.over_sent and (m.over or nid in m.lost):
            s.over_sent = True
            s.send({'t': 'over', 'result': m.result.get(nid, '패배')})
        if s.seats_v != self._seats_v and self._seats_sig is not None:
            s.seats_v = self._seats_v
            s.send({'t': 'seats', 'away': list(self._seats_sig[0]), 'gone': list(self._seats_sig[1])})
        d = w.diplo
        now = time.perf_counter()
        if d.version != s.diplo_v or now - s.diplo_at >= 1.0:
            s.diplo_v, s.diplo_at = d.version, now
            s.send({'t': 'diplo', **d.state_for(nid)})
        if self.fog and 0 <= nid < len(w.nations):           # 안개 격자: 바뀌었을 때만 (줄마다 같은 값이 이어지는 길이로 줄여서)
            see_all = self._see_all(s)
            fv = 'all' if see_all else int(w.vision.version[nid])
            if fv != s.fog_v:
                s.fog_v = fv
                if see_all:
                    s.send({'t': 'fog', 'off': True})
                else:
                    V = w.vision
                    s.send({'t': 'fog', 'gw': V.gw, 'gh': V.gh, 'cell': V.cell, 'rle': _rle(V.levels(nid).ravel())})
        pv = w.pioneer.version
        if pv != s.tribe_v and 0 <= nid < len(w.nations):     # 부족 (개척으로 바뀐다)과 내 카드
            s.tribe_v = pv
            nat = w.nations[nid]
            s.send({'t': 'tribe', 'tribes': [n.tribe for n in w.nations], 'offers': [o[0] for o in nat.offers], 'dropped': list(nat.dropped)})

    # ------------------------------------------------------------- 명령
    def _apply_commands(self):
        while self._inbox:
            seat, m = self._inbox.popleft()
            s = self.seats[seat]
            try:
                self._apply(s, m)
            except (KeyError, TypeError, ValueError) as e:
                s.send({'t': 'error', 'error': f'잘못된 명령: {e}'})

    def _chat(self, s: Seat, m: dict):
        """대화 한 줄을 판의 모든 사람에게 (보낸 사람 포함: 화면에 같은 순서로). 제어 문자는 빼고 CHAT_MAX글자까지."""
        text = ''.join(ch for ch in str(m.get('text', '')) if ch.isprintable()).strip()[:CHAT_MAX]
        if not text:
            return
        now = time.monotonic()
        if now - s.chat_at < CHAT_GAP:
            s.send({'t': 'error', 'error': '조금 천천히 보내 주세요'})
            return
        s.chat_at = now
        out = {'t': 'chat', 'from': s.nid, 'text': text}
        for x in self.seats:
            if not x.away:
                x.send(out)

    def _apply(self, s: Seat, m: dict):
        t, c, nid = m.get('t'), s.cmd, s.nid
        if t == '_away':                            # 연결이 끊겼다 (사람이 2명 이상인 판): 알림만. 이미 진 나라는 조용히 나간다
            if self.world.nations[nid].alive and not s.left and s.away:   # 그사이 돌아왔으면 알리지 않는다
                self.world.say(f'{self.world.nations[nid].name}의 연결이 끊겼습니다 ({LEAVE_AFTER:.0f}초 기다립니다)', skip=(nid,))
            return
        if t == '_attach':                          # 다시 접속 (서버 안에서만 쓰는 명령)
            if not s.away:                          # 아직 붙어 있는 연결을 넘겨받는다 (다른 창, 또는 끊김이 아직 안 닿은 새로고침)
                s.send({'t': 'error', 'error': '다른 창에서 이 판을 이어 합니다', 'fatal': True})
            s.send = m['send']
            s.away = False
            self._resumed = True
            self.encoder.reset()                    # 모두에게 다음 걸음은 전체 상태 (한 번 커질 뿐)
            if s.enc is not None:                   # 안개 판: 이 자리만 처음부터 (안개 격자도 다시)
                s.enc.reset()
            s.fog_v = None
            s.send({'t': 'start', **self.info(s)})
            self._resumed = False
            s.msg_seen = self.world.time
            s.diplo_v = -1                          # 외교 상태도 다시
            s.tribe_v = -1
            s.over_sent = False
            s.seats_v = -1
            s.quit = False
            if self.auto_paused:                    # 옛 탭이 숨으며 건 일시정지
                self.paused = self.auto_paused = False
            if not self.solo:
                if s.left:
                    s.left = False
                    self.match.back(nid)                # 판이 끝나기 전에 돌아왔다: 다시 조종한다
                else:
                    self.world.say(f'{R.josa(self.world.nations[nid].name, "이", "가")} 다시 접속했습니다', skip=(nid,))
            return
        if t == 'chat':                             # 대화: 진 사람(관전)도 말할 수 있다
            self._chat(s, m)
            return
        if nid in self.match.lost or nid in self.match.gone:   # 진 사람(관전)은 명령하지 못한다
            return
        if t == 'command':
            shown = c.command(m.get('units', []), m.get('ships', []), float(m['x']), float(m['y']),
                              bool(m.get('attack')), float(m.get('r', 2.0)))
            if 'id' in m:
                s.send({'t': 'ack', 'id': m['id'], 'shown': shown})
        elif t == 'formation':                       # 진형: 병사마다 제 자리 [(칸, 세대, x, y)]
            c.formation(m.get('spots', []), bool(m.get('attack')))
        elif t == 'place':
            c.place(m['kind'], m.get('units', []), float(m['x']), float(m['y']))
        elif t == 'train':
            c.train(m['kind'], m.get('buildings', []))
        elif t == 'stop':
            c.stop(m.get('units', []))
        elif t == 'surrender':
            self.match.surrender(nid)
        elif t == 'leave':                               # 메뉴에서 나간다: 사람이 여럿인 판이면 바로 조종자 없음
            if not self.solo and not s.left:
                s.left = True
                self.match.leave(nid, chose=True)
        elif t in ('pause', 'speed', 'restart'):    # 사람이 1명인 판에서만
            if not self.solo:
                return
            if t == 'pause':
                self.paused = bool(m.get('on', not self.paused))
                self.auto_paused = self.paused and bool(m.get('auto'))
            elif t == 'speed':
                self.speed = float(m['value']) if float(m['value']) in (1.0, 2.0, 4.0) else 1.0
            else:
                self._new_world()
        elif t == 'diplo':                               # 외교: 상대 나라 번호 to
            d, w, to = self.world.diplo, self.world, int(m.get('to', -1))
            act = m.get('act')
            if not (0 <= to < len(w.nations)) or to == nid:
                raise ValueError('나라 번호')
            if act == 'request':
                d.request(nid, to)
            elif act == 'reply':
                d.reply(nid, to, bool(m.get('accept')))
            elif act == 'extend':
                d.extend(nid, to)
            elif act == 'break':
                d.end(nid, to, betray=True)
            elif act == 'give':                          # 자원마다 보낼 비율 (0~1): 식량, 목재, 석재, 유황
                d.give_res(nid, to, [float(v) for v in m.get('pct', [0, 0, 0, 0])][:4])
            elif act == 'units':                         # 고른 병사
                d.give_units(nid, to, c.units(m.get('units', [])))
            elif act == 'target':
                d.target(nid, to)
            else:
                raise ValueError(f'모르는 외교 {act}')
            s.diplo_v = -1
        elif t == 'tribe':                               # 개척 카드: 새 기후 부족으로 바꾸기 (accept) / 지금 부족 지키기
            self.world.pioneer.pick(nid, bool(m.get('accept')))
        elif t == 'dev' and self.dev:                    # 개발 명령 (혼자 하는 판, 또는 --dev 서버)
            if m.get('cmd') == 'res':
                add = [float(min(max(v, -1e6), 1e6)) for v in (list(m.get('add', [])) + [0, 0, 0, 0])[:4]]
                nat = self.world.nations[nid]
                nat.res = [max(0.0, r + a) for r, a in zip(nat.res, add[:3])]
                nat.sulfur = max(0.0, nat.sulfur + add[3])
                self.world.say('개발: 자원 ' + ', '.join(f'{n} {a:+.0f}' for n, a in zip(('식량', '목재', '석재', '유황'), add) if a), to=nid)
            elif m.get('cmd') == 'raid':                     # 겨울 드래곤 습격을 지금 (겨울이 아니어도, 끝날 때까지)
                if not self.world.wild.start_raid(free=True):
                    self.world.say('개발: 습격할 드래곤이 없다 (잠든 드래곤, 둥지 둘레 설원에 칠 것이 있어야)', to=nid)
            elif m.get('cmd') == 'tribe':                    # 개척 카드를 지금: 첫 거점을 그 기후의 새 거점으로 친다
                w, c = self.world, int(m.get('c', -1))
                nat, halls = w.nations[nid], w.building_ids(nid, R.HALL, done=True)
                if c not in (0, 1, 2) or c == nat.tribe or c in nat.dropped or not len(halls):
                    w.say('개발: 그 기후는 고를 수 없다 (지금 부족이거나 버린 기후, 또는 거점 없음)', to=nid)
                else:
                    h = int(halls[0])
                    nat.offers = [o for o in nat.offers if o[0] != c] + [(c, h, int(w.builds.gen[h]))]
                    w.pioneer.version += 1
            elif m.get('cmd') == 'die':                      # 내 병사·건물을 모두 허문다 (진 뒤 관전 화면 시험)
                self.world.ruin(nid)
            elif m.get('cmd') == 'spawn_ship':               # 전함: (x, y)에서 가장 가까운 바다부터 (서로 떨어지게)
                n = int(min(max(int(m.get('n', 1)), 1), 20))
                got = self._dev_ships(nid, n, float(m.get('x', 0)), float(m.get('y', 0)))
                self.world.say(f'개발: 전함 {got}척 소환' if got else '개발: 가까운 바다가 없다', to=nid)
            elif m.get('cmd') == 'spawn':                    # 원하는 병사를 원하는 만큼: (x, y)에서 가장 가까운 걸을 수 있는 칸부터
                kind, n = int(m.get('kind', -1)), int(min(max(int(m.get('n', 1)), 1), DEV_SPAWN_MAX))
                if kind not in DEV_SPAWN_KINDS:
                    raise ValueError(f'소환할 수 없는 병종 {kind}')
                got = self._dev_spawn(nid, kind, n, float(m.get('x', 0)), float(m.get('y', 0)))
                self.world.say(f'개발: {R.UNIT_NAMES[kind]} {got}명 소환', to=nid)
        else:
            raise ValueError(f'모르는 명령 {t}')
