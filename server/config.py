"""서버 설정. 환경 변수로 바꿀 수 있다 (TS_로 시작). 지도 크기 상한은 나중에 늘릴 수 있게 값 하나로 둔다."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]


def _env(name, default, cast=str):
    v = os.environ.get(f'TS_{name}')
    return cast(v) if v is not None else default


@dataclass
class ServerConfig:
    demo_dir: Path = field(default_factory=lambda: Path(_env('DEMO_DIR', WEB / 'assets' / 'maps')))   # 미리 구운 데모 지도
    data_dir: Path = field(default_factory=lambda: Path(_env('DATA_DIR', WEB / 'data')))              # 직접 만든 지도
    cache_dir: Path = field(default_factory=lambda: Path(_env('CACHE_DIR', WEB / '.cache')))          # 지형 생성 캐시
    web_dir: Path = field(default_factory=lambda: Path(_env('WEB_DIR', WEB / 'web' / 'dist')))        # 웹 클라이언트 (3단계)
    max_size: int = field(default_factory=lambda: _env('MAX_SIZE', 512, int))       # 지도 크기 상한
    size_choices: tuple = (384, 512, 640, 768)                                      # 이 중 max_size 이하만 연다
    tick_hz: float = 20.0                                                           # 시뮬레이션 걸음 (초당)
    max_sessions: int = field(default_factory=lambda: _env('MAX_SESSIONS', 8, int))     # 동시에 도는 판 (싱글·멀티 모두)
    max_rooms: int = field(default_factory=lambda: _env('MAX_ROOMS', 60, int))          # 동시에 열린 대기실 (판은 위에서 따로 센다)
    max_clients: int = field(default_factory=lambda: _env('MAX_CLIENTS', 120, int))      # 동시 접속 (게임·대기실 연결 수, 다시 접속은 세지 않고 받는다)
    resume_seconds: float = field(default_factory=lambda: _env('RESUME_SECONDS', 60.0, float))   # 끊긴 판을 기다리는 시간
    map_workers: int = field(default_factory=lambda: _env('MAP_WORKERS', 1, int))   # 지도 만들기 동시 작업 수
    scene_cache: int = 3                                                            # 메모리에 둘 지도 장면 수
    year_length: float = 360.0                                                      # 1년 (게임 초)
    day_length: float = 240.0                                                       # 하루 (게임 초)
    dev: bool = field(default_factory=lambda: _env('DEV', '0') == '1')             # 개발용 명령 (자원 받기 등). python -m server --dev

    @property
    def sizes(self) -> list[int]:
        return [s for s in self.size_choices if s <= self.max_size]
