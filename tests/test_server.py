"""서버: 상태 메시지(바뀐 것만)를 받는 쪽에서 쌓으면 실제 세계와 같아지는지, 명령 해석이 동작하는지."""
import numpy as np

from engine.mapgen import generate_world
from engine.mapgen.defaults import default_config
from engine.render.seasons import SeasonCycle
from engine.scene import TerrainScene
from server.protocol import POS, StateEncoder, decode
from sim import rules as R
from sim.commands import PlayerCommands
from sim.terrain import GameMap
from sim.world import World


def _client_apply(units, builds, m):
    for u in m['units']:
        units[int(u['slot'])] = u
    for s in m['units_gone']:
        units.pop(int(s), None)
    for b in m['builds']:
        builds[int(b['slot'])] = b
    for s in m['builds_gone']:
        builds.pop(int(s), None)


def run(report, seconds=240, size=384):
    world_ = generate_world(default_config(size, 8767564))
    scene = TerrainScene(world_.height, world_.coast, world_.climate)
    w = World(GameMap(scene), 4, seed=7, map_seed=8767564)
    enc = StateEncoder(w)
    cyc = SeasonCycle(year=0.05, year_length=360)
    units, builds, total = {}, {}, 0
    cmd = PlayerCommands(w, 0)
    mine = [(int(i), int(w.units.gen[i])) for i in w.unit_ids(0)]
    site = min(w.sites, key=lambda s: np.hypot(s.x - w.units.x[mine[0][0]], s.y - w.units.y[mine[0][0]]))
    shown = cmd.command(mine, [], site.x, site.y)
    ok_cmd = shown == 'build' and any(w.builds.site[i] == site.id for i in w.building_ids(0))
    stale = cmd.units([(mine[0][0], mine[0][1] + 1)])          # 세대가 다르면 무시
    report('명령 해석: 자원지 오른쪽 클릭 → 짓기, 세대가 다른 병사는 무시', ok_cmd and len(stale) == 0)
    for step in range(int(seconds / 0.05)):
        cyc.advance(0.05 / 360)
        w.update(0.05, cyc.weights())
        blob = enc.encode({'hour': 12.0, 'year': cyc.year, 'flags': 0, 'speed': 1.0}, nations=step % 4 == 0, sim_ms=0)
        total += len(blob)
        _client_apply(units, builds, decode(blob))
    u, b = w.units, w.builds
    alive_u = set(np.flatnonzero(u.alive[:u.n] & (u.own[:u.n] < R.NEUTRAL)).tolist())   # 야생 드래곤은 동물 칸으로 간다
    alive_b = set(np.flatnonzero(b.alive[:b.n]).tolist())
    same_sets = set(units) == alive_u and set(builds) == alive_b
    pos_ok = all(abs(units[i]['x'] / POS - u.x[i]) <= 0.5 / POS + 1e-6 and int(units[i]['gen']) == int(u.gen[i])
                 for i in alive_u)
    report(f'바뀐 것만 보내도 받는 쪽 상태 = 실제 세계 ({seconds}초, 병사 {len(alive_u)}명, 건물 {len(alive_b)}채, '
           f'평균 {total / (seconds / 0.05):.0f} B/걸음)', same_sets and pos_ok)
    _lobby_art(report, scene)


def _lobby_art(report, scene):
    """로비 배경: 서버가 고른 조각과 장식 배치 = 데스크톱 로비(game/menu.py LobbyArt)."""
    from game.menu import LobbyArt                      # 최상위 원본
    from server import lobby_art
    info, png = lobby_art.build(scene)
    h = np.asarray(scene.height, dtype=np.float64)[:scene.day.shape[0], :scene.day.shape[1]]
    art = LobbyArt.__new__(LobbyArt)
    art._compose(scene.day, h < scene.shader.sea_level)
    crop = _read_png(png)
    same_img = crop.shape == art.img.shape and np.array_equal(crop, art.img)
    same_b = [(d['kind'], d['nat'], d['y'], d['x']) for d in info['buildings']] == [(k, n, y, x) for _, k, n, y, x in art.deco]
    same_w = all(a['kind'] == b['kind'] and a['nat'] == b['nat'] and np.allclose(a['a'], b['a']) and np.allclose(a['b'], b['b'])
                 and np.isclose(a['speed'], b['speed']) and np.isclose(a['phase'], b['phase'])
                 for a, b in zip(info['walkers'], art.walkers)) and len(info['walkers']) == len(art.walkers)
    same_s = [(s['kind'], s['nat'], tuple(s['a']), tuple(s['b'])) for s in info['ships']] == \
        [(s['kind'], s['nat'], tuple(s['a']), tuple(s['b'])) for s in art.ships]
    same_sp = np.allclose(np.array(info['sparkles']), np.array(art.sparkles))
    report(f'로비 배경 = 데스크톱 로비 (건물 {len(info["buildings"])}, 병사 {len(info["walkers"])}, 배 {len(info["ships"])}, '
           f'반짝임 {len(info["sparkles"])})', same_img and same_b and same_w and same_s and same_sp,
           f'그림 {same_img} 건물 {same_b} 병사 {same_w} 배 {same_s} 반짝임 {same_sp}')


def _read_png(data: bytes) -> np.ndarray:
    """engine.bake.png가 만든 PNG (RGB, 필터 없음) 풀기."""
    import struct
    import zlib
    pos, w, h, idat = 8, 0, 0, b''
    while pos < len(data):
        n, tag = struct.unpack('>I4s', data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b'IHDR':
            w, h = struct.unpack('>II', body[:8])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + n
    raw = np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, 1 + w * 3)
    return raw[:, 1:].reshape(h, w, 3)
