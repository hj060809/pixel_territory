# web_game — Pixel Territory (웹 싱글플레이 데모)

python -m server --port 8000

최상위 프로젝트에서 필요한 부분만 옮겨 만든 새 프로젝트. 전체 계획과 단계는 [PLAN.md](PLAN.md).

## 구조

```
engine/                 지형 엔진 (게임과 무관하게 쓸 수 있다)
  mapgen/               지형 생성: 설정(config), 기본 설정(defaults), 프리셋, 캐시, 단계별 생성(stages), 공통 계산(core)
  presets/              지형 프리셋 JSON
  render/
    shader.py           픽셀아트 렌더 (지도마다 한 번)
    seasons.py          계절: SeasonCycle(1년 시계), SeasonPainter(state: 눈·얼음 재질 / paint: 낮 이미지)
    materials.py        재질 번호 (게임 규칙은 이것만 본다)
    surface.py          낮밤·물결 준비 (법선, 지평선 높이, 물 칸 정보)
    daylight.py         낮밤 빛과 그림자, 물에 비친 하늘
    water.py            물결과 해안 거품 (+ 지도와 상관없는 노이즈 함수)
    frame.py            FrameRenderer: 화면 한 장 = 계절 칠하기 → 물결 → 낮밤 (웹 셰이더의 정답 그림)
  scene.py              TerrainScene: 지도 한 장 (생성 → 렌더 → 계절 준비)
  bake/                 지도 → 웹용 묶음
    container.py        묶음 파일 형식 (.tsb: gzip 이진, 머리말 JSON + 배열)
    bundle.py           묶음에 넣을 것과 정밀도 줄이기
    client_ref.py       묶음만으로 화면을 그리는 파이썬판 = 웹 클라이언트가 옮길 사양
    __main__.py         python -m engine.bake → assets/maps/<지도>/ (bundle.tsb, day.png, ref/기준 그림)

sim/                    게임 시뮬레이션 (화면 없음, 서버가 돌린다)
  rules.py              규칙 수치 (자원, 병사, 건물, 배, 색, 난이도)
  terrain.py            GameMap: 지형 → 게임 규칙 (걷기, 비용, 비옥함, 엄폐, 바다, 절벽). set_season(계절)
  sites.py              자원지 찾기
  spawn.py              시작 자리와 나라 색
  entities.py           병사·건물 배열과 병사 상태
  pathing.py            길찾기 캐시 (거리 지도 슬롯)
  kernels/              numba 계산 (nogil): combat(병사·망루 한 걸음), flow(길찾기·바닷길), rng(난수 시드)
  boats.py              나룻배와 전함, 항구
  world.py              World: 나라·자원·명령·진행·승패
  ai.py                 AI 나라

  commands.py           플레이어 명령 해석 (오른쪽 클릭/건물 자리/훈련 → 세계 명령, 데스크톱과 같은 규칙)

server/                 서버: 판마다 스레드 하나로 시뮬레이션, 브라우저와 WebSocket
  config.py             설정 (지도 크기 상한 512 등, 환경 변수 TS_*)
  maps.py               지도 저장소 (데모 지도 + 직접 입력한 시드는 별도 프로세스에서 만들고 굽기)
  protocol.py           상태 메시지 형식 (이진, 바뀐 것만) — 웹이 같은 형식을 읽는다
  session.py            판 하나 (초당 20걸음, 명령 처리, 보내기)
  client_info.py        브라우저에 주는 규칙 표(이름, 비용, 체력…)와 지도 통행 정보(rules.bin)
  lobby_art.py          로비 배경: 지형 조각과 장식 배치 (데스크톱 LobbyArt와 같은 결과)
  app.py                HTTP + WebSocket (FastAPI)

web/                    브라우저 클라이언트 (Vite + TypeScript + WebGL2)
  src/bundle/           지도 묶음 읽기
  src/noise/            OpenSimplex(파이썬과 비트 단위 동일), 색 노이즈·물결 노이즈, numpy와 같은 반올림 도우미
  src/terrain/          계절 칠하기·물결 (CPU, 웹 워커) = client_ref를 옮긴 것, 장면(TerrainScene)
  src/render/           WebGL2: 낮밤 빛·그림자·하늘 반사 셰이더, 화면 확대, 새와 물고기 그리기
  src/sim/              시계(낮밤, 1년), 카메라
  src/life/             새와 물고기 (viewer/life.py를 옮김)
  src/game/             게임: 스프라이트(spriteData는 sprites.py에서 자동 생성), 상태 해석·보간, 선택·명령(즉시 핑),
                        그리기(Canvas2D 위층), HUD(HTML)
  src/menu/             로비(배경, 게임 방법), 설정(지도 만들기 + 미리보기, 이름·색, 시작 자리, AI, 계절), 버튼 등 부품
  src/pages/            game(로비 → 설정 → 게임, index.html), viewer(지형 화면), parity(기준 그림 비교)
  tests/                Node 검사: noise_check(노이즈), terrain_check(계절 칠하기·물결)

tests/                  회귀 테스트 (최상위 원본과 결과 비교)
tools/                  make_noise_vectors.py: 웹이 옮길 노이즈의 정답 값 (assets/test/noise_vectors.json)
                        test_client.py: 서버를 띄우고 한 판을 진행하며 지연·대역폭을 재는 시험 클라이언트
                        load_test.py: 판 여러 개 동시 / 한 시간 연속 / 끊었다가 다시 접속 시험
                        make_terrain_vectors.py: 웹 CPU 단계의 정답 그림 (assets/test/terrain)
                        browser_check.mjs: 설치된 Chrome으로 기준 그림 비교 / 화면 스크린샷
assets/                 maps/ (구운 데모 지도, 다시 만들 수 있다), test/ (검증용 값)
```

의존 방향: `sim → engine` (engine은 sim을 모른다). `sim`은 엔진을 `engine.scene.TerrainScene`, `engine.render.materials`,
`engine.mapgen`으로만 쓴다.

## 쓰는 법 (지금 단계)

```python
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene
from sim.terrain import GameMap
from sim.world import World

scene = TerrainScene.load(default_config(512, 8767564), cache_dir='.cache')
gmap = GameMap(scene)
world = World(gmap, n_bots=4, seed=1, map_seed=8767564)
gmap.set_season(weights)          # 계절이 움직일 때 (눈 덮인 길, 얼어붙은 바다)
world.update(dt, weights)         # 진행 (안에서 0.05초 걸음으로 나눈다)
```

같은 `seed`면 같은 판이 된다 (numba 안의 난수도 판 시드로 정한다).

## 지도 굽기

```
python -m engine.bake            # 데모 지도 5개 (기본, 대륙, 열대 섬, 열도, 다양한 기후) → assets/maps/
python tools/make_noise_vectors.py
```

묶음은 지도마다 다른 것만 담는다 (512 지도에 2~3.3 MB). 색 노이즈와 물결 노이즈는 지도 내용과 상관없어서
웹이 같은 알고리즘(OpenSimplex, 고정 시드)으로 직접 만든다. 일부 값은 정밀도를 줄여 저장해서, 묶음으로 그린 그림은
엔진 그림과 99.98% 이상 같다 (경계의 몇 칸).

## 서버

```
python -m server --port 8000          # http://127.0.0.1:8000  (API: /api/maps, 게임: ws://.../ws)
python tools/test_client.py           # 서버를 띄워 한 판 시험 (지연, 대역폭, 서버 계산 시간)
python tools/load_test.py --sessions 4 --seconds 120     # 동시 판 수 (상태 간격, 서버 걸음, 메모리)
python tools/load_test.py --seconds 3600 --report 300    # 한 시간 연속
python tools/load_test.py --seconds 30 --resume          # 끊었다가 같은 판에 다시 접속
```

- HTTP: 지도 목록, 지도 준비(직접 입력한 시드는 만들기 시작, 진행 상황), 지도 묶음/낮 이미지, 시작 배치 미리보기,
  게임 규칙 지형(rules.bin), 로비 배경(/api/lobby)
- WebSocket: join → start(나라, 자원지) → 걸음마다 상태(이진) + 알림(JSON). 명령은 JSON (session.py 맨 위 설명)
- 지도 크기 상한은 `TS_MAX_SIZE` (기본 512). 서버를 켜면 로비 배경을 먼저 준비하고 (data/lobby/에 남김),
  numba 계산을 미리 불러 둔다 (첫 판이 멈칫하지 않게)
- 연결이 끊긴 판은 `TS_RESUME_SECONDS`(기본 60초) 동안 멈춘 채 남아, 브라우저가 같은 판에 자동으로 다시 접속한다
- 무거운 계산은 걸음 밖에서: 계절 눈·얼음은 보조 스레드, 길찾기 거리 지도는 계산 스레드 묶음 (다음 걸음에 받는다)
- 웹 빌드는 JS·CSS·HTML의 .gz를 함께 만들고, 서버가 gzip을 받는 브라우저에게 그것을 보낸다

## 웹 클라이언트

```
cd web && npm install && npm run build          # dist/ → 파이썬 서버가 그대로 내보낸다 (http://127.0.0.1:8000)
npm run dev                                     # 개발: http://localhost:5173 (API는 파이썬 서버 8000으로)
node --experimental-strip-types tests/noise_check.mts
python ../tools/make_terrain_vectors.py && node --experimental-strip-types tests/terrain_check.mts
node ../tools/browser_check.mjs parity          # 브라우저 그림 vs 파이썬 기준 그림 (데모 지도 5 × 6장면)
node ../tools/browser_game_check.mjs <폴더>     # 화면 없는 Chrome으로 한 판 조작 (선택, 명령 지연, 훈련, 속도) + 스크린샷
node ../tools/browser_menu_check.mjs <폴더>     # 로비 → 설정 → 게임 → 로비 흐름 (배치 미리보기, 자리 고르기, F6, F10)
```

`http://127.0.0.1:8000/` 로비 → 게임 시작 → 설정 → 게임. 게임 안에서 F5 같은 지도로 새 판, F6 새 지도(시드+1),
F10(끝난 뒤엔 Enter) 로비로.
조작: 하단 버튼 막대 — 건물 1 거점, 2 망루, 3 항구, 4 농장, 5 벌목장, 6 채석장 (누르면 반투명 건물이 커서에 붙고 땅을 클릭해 놓는다.
자원지 건물은 빈 자원지에 붙는다. 고른 병사가 없으면 가까운 쉬는 병사 3명이 짓는다. Shift+클릭: 여러 개, 오른쪽 클릭·Esc: 취소),
병종 Q 보병, W 궁수, E 전함 (고른 건물, 아니면 내 건물들에서 돌아가며). 7~9, R·T·Y는 나중 건물·병종용.
Ctrl+숫자 부대 지정, Shift+숫자 부대 부르기, A 공격 이동, S 정지, Space 화면 이동, P 일시정지, `.` 속도.
메뉴 없이 바로 판 열기 (개발·시험용): `/?quick=1&color=<0~6>&name=<이름>&bots=<수>` 또는 `/?map=<지도 키>&...`

화면 나누기: 계절 칠하기와 물결은 웹 워커의 CPU(파이썬과 비트 단위 동일), 낮밤 빛은 GPU 셰이더(매 프레임),
확대는 가장 가까운 픽셀. 새와 물고기는 CPU로 움직이고 GPU 혼합으로 그린다.

## 테스트

```
pip install -r requirements.txt
python -m tests.run_all
```

- 엔진: 지형 생성 · 렌더 · 계절 칠하기가 최상위 원본과 **비트 단위로 같은지** (5가지 지형)
- 화면 합성(낮밤·물결·계절)이 최상위 뷰어 화면과 **비트 단위로 같은지** (7장면 × 2지형)
- 묶음: 파일 왕복, 묶음만으로 그린 그림이 엔진 그림과 99.9% 이상 같은지, 크기
- 시뮬레이션: 같은 시드면 같은 판인지 (기본 지형 420초, 배가 뜨는 열도 900초). 판 규칙은 web_game에서 바뀌어 원본과는 비교하지 않는다
- 판 규칙: 나룻배(항구에 모여 차례로 타고 다 타면 함께 출발, 항구 없으면 안 건넘), 여러 섬에서 시작 (tests/test_rules.py)
- 서버: 바뀐 것만 보낸 상태를 쌓으면 실제 세계와 같은지, 명령 해석
- 한 판 (512 지도, 900초): 오류 없이 돌고 걸음당 10 ms 미만인지

테스트만 최상위 원본을 불러온다 (`tests/toplevel.py`). 엔진과 시뮬레이션은 최상위를 참조하지 않는다.