"""방 (멀티 플레이 대기실). 방 하나 = 참가자들 + 판 설정, 방장이 시작하면 판(GameSession) 하나가 된다.

- 방 번호(id)와 입장 코드(code, 6글자: 헷갈리는 글자 0/O/1/I는 빼고). 목록에는 대기 중인 방만.
- 비밀번호: 보안용이 아니라 한 판용 방 코드 (그대로 저장·비교).
- 인원: 사람 정원(cap) + AI 수(bots) ≤ 나라 수 상한 (rules.COLORS 수, 8).
- 참가자마다 이름·색(겹치지 않게)·준비·고른 시작 자리. 방장은 설정을 바꾸고, 내보내고, 시작한다.
- 시작 자리: 'pick' (각자 지도를 눌러 고른다: 시작할 수 있는 땅, 서로 SPOT_GAP칸 넘게) / 'random' (서버가 정해 보여 준다).
- 방장이 나가면 다음 사람이 방장, 아무도 없으면 방을 지운다. 오래(STALE초) 시작하지 않은 대기실도 지운다.
여기는 방의 상태와 확인만 한다 (접속·판 만들기는 server/app.py).
"""
from __future__ import annotations

import secrets
import time

from sim import rules as R

CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_LEN = 6
MAX_NATIONS = len(R.COLORS)
SPOT_GAP = 40.0          # 고른 시작 자리끼리 이만큼(칸) 넘게
STALE = 1800.0           # 이만큼(초) 시작하지 않은 대기실은 지운다
NAME_LEN = 16


class Member:
    def __init__(self, name: str, color: int, send, ws=None):
        self.name = (name or '이름 없음')[:NAME_LEN]
        self.color = int(color)
        self.ready = False
        self.spot: tuple[int, int] | None = None
        self.send = send                         # 이 사람에게 보내기 (JSON)
        self.ws = ws                             # 내보낼 때 닫는다
        self.seat = -1                           # 판이 시작되면 자리 번호
        self.game = None                         # 그 자리가 있는 판 (GameSession). 대기실로 돌아오면 None
        self.chat_at = -1e9                      # 대기실에서 마지막으로 말한 때 (도배 막기)


class Room:
    def __init__(self, rid: str, code: str, name: str, password: str, cap: int, bots: int, start_mode: str, setup: dict):
        self.id, self.code = rid, code
        self.name = (name or '이름 없는 방')[:24]
        self.password = str(password or '')
        self.cap, self.bots = cap, bots
        self.start_mode = start_mode if start_mode in ('pick', 'random') else 'random'
        self.setup = dict(setup)                 # map (지도 키), difficulty, season, fog (전장의 안개), vis (시인성 강조 기본값, 화면에만)
        self.members: list[Member] = []
        self.host = 0                            # 방장: members 번호
        self.state = 'wait'                      # wait | starting | play
        self.session = None                      # 판 (시작한 뒤)
        self.last = None                         # 끝난 판 (그 판에서 대기실로 돌아오는 사람을 받는다)
        self.layout: list | None = None          # 'random'일 때 보여 줄 배치 [(y, x)...] (사람 자리 순서 다음 AI)
        self.created = time.monotonic()

    @property
    def nations(self) -> int:
        return min(len(self.members) + self.bots, MAX_NATIONS)

    def public(self) -> dict:
        """방 목록 한 줄."""
        h = self.members[self.host].name if self.members else ''
        return {'id': self.id, 'name': self.name, 'host': h, 'humans': len(self.members), 'cap': self.cap,
                'bots': self.bots, 'locked': bool(self.password), 'map': self.setup.get('map', ''),
                'start_mode': self.start_mode}

    def view(self, me: int, map_status: dict | None = None, tribes: dict | None = None) -> dict:
        """대기실 화면에 보낼 것 (me: 받는 사람의 members 번호)."""
        return {'t': 'room', 'id': self.id, 'code': self.code, 'name': self.name, 'host': self.host, 'me': me,
                'cap': self.cap, 'bots': self.bots, 'start_mode': self.start_mode, 'setup': self.setup,
                'locked': bool(self.password), 'state': self.state, 'layout': self.layout,
                'members': [{'name': m.name, 'color': m.color, 'ready': m.ready, 'spot': list(m.spot) if m.spot else None}
                            for m in self.members],
                'map_status': map_status or {}, 'tribes': tribes or {}}

    def free_color(self) -> int:
        used = {m.color for m in self.members}
        return next(c for c in range(len(R.COLORS)) if c not in used)

    def can_start(self) -> str | None:
        """방장이 시작할 수 없으면 그 까닭."""
        if self.state != 'wait':
            return '이미 시작했습니다'
        if len(self.members) < 2:
            return '사람이 2명 이상이어야 시작할 수 있습니다'
        if any(not m.ready for i, m in enumerate(self.members) if i != self.host):
            return '모두 준비해야 시작할 수 있습니다'
        return None


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    # ------------------------------------------------------------- 찾기
    def listing(self) -> list[dict]:
        self.sweep()
        return [r.public() for r in self.rooms.values() if r.state == 'wait']

    def find(self, rid: str | None = None, code: str | None = None) -> Room | None:
        if rid and rid in self.rooms:
            return self.rooms[rid]
        if code:
            code = str(code).strip().upper()
            return next((r for r in self.rooms.values() if r.code == code), None)
        return None

    def sweep(self) -> list[Room]:
        """오래 시작하지 않은 대기실과 빈 방을 지운다. 반환: 지운 방 (남은 사람에게 알리려고)."""
        now, gone = time.monotonic(), []
        for rid, r in list(self.rooms.items()):
            if r.state == 'wait' and (not r.members or now - r.created > STALE):
                gone.append(self.rooms.pop(rid))
        return gone

    def _code(self) -> str:
        used = {r.code for r in self.rooms.values()}
        while True:
            c = ''.join(secrets.choice(CODE_CHARS) for _ in range(CODE_LEN))
            if c not in used:
                return c

    # ------------------------------------------------------------- 만들기 · 들어가기 · 나가기
    def create(self, name, password, cap, bots, start_mode, setup, max_rooms: int = 60,
               busy: str = '지금 열린 방이 너무 많습니다. 잠시 뒤에 다시 해 주세요') -> Room | str:
        cap, bots = int(cap), int(bots)
        if not (2 <= cap <= MAX_NATIONS) or bots < 0 or cap + bots > MAX_NATIONS:
            return f'사람 정원은 2~{MAX_NATIONS}명, 사람과 AI를 합쳐 {MAX_NATIONS}나라까지입니다'
        if not setup.get('map'):
            return '지도를 먼저 정하세요'
        self.sweep()
        if sum(r.state == 'wait' for r in self.rooms.values()) >= max_rooms:
            return busy
        r = Room(secrets.token_urlsafe(6), self._code(), name, password, cap, bots, start_mode, setup)
        self.rooms[r.id] = r
        return r

    def join(self, r: Room, password, member: Member) -> int | str:
        """반환: members 번호, 또는 들어갈 수 없는 까닭."""
        if r.state != 'wait':
            return '이미 시작한 방입니다'
        if r.password and str(password or '') != r.password:
            return '비밀번호가 틀렸습니다'
        if len(r.members) >= r.cap:
            return '방이 가득 찼습니다'
        if any(m.color == member.color for m in r.members):
            member.color = r.free_color()
        r.members.append(member)
        return len(r.members) - 1

    def leave(self, r: Room, member: Member) -> None:
        if member not in r.members:
            return
        i = r.members.index(member)
        r.members.pop(i)
        if i < r.host:
            r.host -= 1
        elif i == r.host:                                    # 방장이 나갔다: 다음 사람 (맨 앞)
            r.host = 0
        if r.host >= len(r.members):
            r.host = 0
        if not r.members and r.state == 'wait':
            self.rooms.pop(r.id, None)

    # ------------------------------------------------------------- 바꾸기
    def set_color(self, r: Room, member: Member, color: int) -> str | None:
        if not (0 <= color < len(R.COLORS)):
            return '없는 색입니다'
        if any(m.color == color and m is not member for m in r.members):
            return '다른 사람이 고른 색입니다'
        member.color = color
        return None

    def set_spot(self, r: Room, member: Member, y: int, x: int, check) -> str | None:
        """check(y, x) -> 까닭 | None: 지도로 보는 확인 (시작할 수 있는 땅인가, server/app.py _check_spot)."""
        if r.start_mode != 'pick':
            return '이 방은 시작 자리를 무작위로 정합니다'
        err = check(y, x)
        if err:
            return err
        for m in r.members:
            if m is not member and m.spot and (m.spot[0] - y) ** 2 + (m.spot[1] - x) ** 2 < SPOT_GAP ** 2:
                return f'{m.name}의 자리와 너무 가깝습니다'
        member.spot = (int(y), int(x))
        return None

    def set_setup(self, r: Room, changes: dict) -> str | None:
        """방장이 설정을 바꾼다 (name, password, cap, bots, start_mode, map, difficulty, season, fog, vis)."""
        cap = int(changes.get('cap', r.cap))
        bots = int(changes.get('bots', r.bots))
        if not (2 <= cap <= MAX_NATIONS) or bots < 0 or cap + bots > MAX_NATIONS:
            return f'사람 정원은 2~{MAX_NATIONS}명, 사람과 AI를 합쳐 {MAX_NATIONS}나라까지입니다'
        if cap < len(r.members):
            return '지금 들어온 사람보다 정원을 줄일 수 없습니다'
        r.cap, r.bots = cap, bots
        if 'name' in changes:
            r.name = (str(changes['name']) or r.name)[:24]
        if 'password' in changes:
            r.password = str(changes['password'] or '')
        if changes.get('start_mode') in ('pick', 'random'):
            r.start_mode = changes['start_mode']
        map_changed = 'map' in changes and changes['map'] != r.setup.get('map')
        for k in ('map', 'difficulty', 'season'):
            if k in changes:
                r.setup[k] = changes[k]
        if 'fog' in changes:                                 # 전장의 안개: 판 규칙 (게임 중엔 못 바꾼다)
            r.setup['fog'] = bool(changes['fog'])
        if 'vis' in changes:                                 # 시인성 강조: 판을 시작할 때의 기본값 (게임 중엔 각자 바꾼다)
            r.setup['vis'] = bool(changes['vis'])
            if set(changes) == {'vis'}:                      # 화면에만 쓰는 값: 준비를 풀지 않는다
                return None
        if map_changed or r.start_mode == 'random':          # 지도가 바뀌면 고른 자리는 무르고 다시
            for m in r.members:
                m.spot = None
        r.layout = None
        for i, m in enumerate(r.members):                    # 설정이 바뀌면 준비도 다시
            if i != r.host:
                m.ready = False
        return None
