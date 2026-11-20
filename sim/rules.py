"""게임 규칙 수치. 한 판 20~30분의 느긋한 템포 기준 (게임 속도 ×1).

자원: 식량(농장, 비옥한 들판) / 목재(벌목장, 숲) / 석재(채석장, 바위 지대).
병사는 식량을 먹는다 (겨울에 더). 식량이 바닥나면 굶어서 조금씩 약해진다.
건물과 병사를 모두 잃으면 패배.
"""
from __future__ import annotations

FOOD, WOOD, STONE = range(3)
RES_NAMES = ('식량', '목재', '석재')

# --- 유닛
INFANTRY, ARCHER = range(2)
UNIT_NAMES = ('보병', '궁수')
#               체력, 공격, 사거리, 공격 간격(초), 속도(칸/초, 평지), 시야, 비용(식량, 목재, 석재), 훈련 시간
UNIT_STATS = {
    INFANTRY: dict(hp=40.0, dmg=6.0, range=2.2, cd=1.0, speed=4.5, sight=14.0, cost=(40, 0, 0), time=7.0),
    ARCHER:   dict(hp=26.0, dmg=4.0, range=13.0, cd=1.5, speed=4.5, sight=16.0, cost=(30, 25, 0), time=9.0),
}
UPKEEP = 0.035             # 병사 하나가 1초에 먹는 식량 (겨울에는 1.5배까지)
STARVE = 0.4               # 식량이 바닥나면 병사가 1초에 잃는 체력
HEAL_NEAR_HALL = 0.6       # 거점 가까이서 1초에 회복하는 체력

# --- 건물
HALL, FARM, LUMBER, QUARRY, TOWER, HARBOR = range(6)
BUILD_NAMES = ('거점', '농장', '벌목장', '채석장', '망루', '항구')
#             체력, 크기(반지름, 칸), 비용, 짓는 데 드는 일(병사×초)
BUILD_STATS = {
    HALL:   dict(hp=700.0, r=5, cost=(0, 200, 80), work=90.0),
    FARM:   dict(hp=160.0, r=4, cost=(0, 50, 0), work=20.0),
    LUMBER: dict(hp=160.0, r=4, cost=(0, 40, 0), work=18.0),
    QUARRY: dict(hp=180.0, r=4, cost=(0, 60, 0), work=24.0),
    TOWER:  dict(hp=320.0, r=2, cost=(0, 40, 80), work=30.0),
    HARBOR: dict(hp=260.0, r=4, cost=(0, 90, 20), work=30.0),     # 해안에만. 이 땅의 병사가 여기 모여 배로 건너고, 전함을 만든다
}

# --- 배
# 나룻배: 병사들이 있는 땅에 완성된 항구가 있으면, 바다 건너로 명령받은 병사들이 그 항구에 모여 차례로 타고
#         다 타면 함께 건넌다 (비용 없음, sim/boats.py)
BOAT_CAPACITY = 10
FERRY_HP = 10.0            # 전함 한 방(WARSHIP_DMG)에 가라앉는다
FERRY_SPEED = 4.5          # 칸/초 (병사가 평지를 걷는 속도와 같다)
# 전함: 항구에서 만든다. 다른 나라의 나룻배와 전함을 공격한다
WARSHIP = 'warship'        # 항구 대기열에 넣는 이름
WARSHIP_COST = (0, 80, 40)
WARSHIP_TIME = 20.0
WARSHIP_HP = 180.0
WARSHIP_SPEED = 5.0
WARSHIP_RANGE = 16.0
WARSHIP_DMG = 14.0
WARSHIP_CD = 1.6

SITE_BUILDING = {FOOD: FARM, WOOD: LUMBER, STONE: QUARRY}     # 자원지 종류 → 지을 건물
TOWER_RANGE, TOWER_DMG, TOWER_CD = 22.0, 6.0, 1.4

# 1초에 나는 자원 (자원지 풍부함 1 기준). 거점도 조금씩 낸다 (아무것도 없어도 다시 일어설 수 있게)
YIELD = {FARM: (FOOD, 1.5), LUMBER: (WOOD, 0.9), QUARRY: (STONE, 0.55)}
HALL_YIELD = (0.45, 0.25, 0.0)
# 계절별 배율 (봄, 여름, 가을, 겨울). 추운 곳일수록 이 차이가 그대로, 열대는 거의 1
SEASON_YIELD = {FOOD: (0.6, 1.0, 1.7, 0.05), WOOD: (1.0, 1.0, 1.0, 0.7), STONE: (1.0, 1.0, 1.0, 0.8)}

START_RES = (160.0, 160.0, 40.0)
START_UNITS = ((INFANTRY, 5), (ARCHER, 2))

COLORS = [  # 색 이름, 색 (스프라이트 옷/지붕), 밝은 색. 설정 화면에서 내 나라 색을 고르고, AI는 나머지를 쓴다
    ('붉은', (214, 70, 52), (255, 140, 110)),
    ('호박', (226, 160, 40), (255, 214, 110)),
    ('보라', (128, 84, 196), (190, 150, 255)),
    ('청록', (34, 156, 150), (110, 230, 216)),
    ('분홍', (220, 100, 160), (255, 170, 210)),
    ('은빛', (205, 210, 222), (255, 255, 255)),
    ('쪽빛', (62, 96, 206), (140, 170, 255)),
]
ANIMALS = ('여우', '사슴', '까마귀', '수달', '두루미', '늑대', '곰', '매')   # AI 나라 이름: 색 + 동물
DIFFICULTY = {'쉬움': 0.75, '보통': 1.0, '어려움': 1.3}                      # AI 자원 수입 배율 (공격성도 조금)
