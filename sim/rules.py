"""게임 규칙 수치. 한 판 20~30분의 느긋한 템포 기준 (게임 속도 ×1).

자원: 식량(농장, 비옥한 들판) / 목재(벌목장, 숲) / 석재(채석장, 바위 지대).
야생 동물: 넓은 초원에 야생말이 흩어져 산다. 병사를 고르고 말을 오른쪽 클릭하면 가서 길들여 기병이 된다
  (보병 → 창기병, 궁수 → 기마궁수. sim/wildlife.py, WILDLIFE 표).
병사는 식량을 먹는다 (겨울에 더). 식량이 바닥나면 굶어서 조금씩 약해진다.
건물과 병사를 모두 잃으면 패배.
"""
from __future__ import annotations

FOOD, WOOD, STONE = range(3)
RES_NAMES = ('식량', '목재', '석재')

# --- 유닛
INFANTRY, ARCHER, LANCER, HORSE_ARCHER = range(4)
UNIT_NAMES = ('보병', '궁수', '창기병', '기마궁수')
TRAINABLE = (INFANTRY, ARCHER)            # 거점에서 훈련하는 병종. 기병은 야생말을 길들여야만 생긴다
#   체력, 공격, 사거리, 공격 간격(초), 속도(칸/초, 평지), 시야, 비용(식량, 목재, 석재), 훈련 시간,
#   terrain: 지형을 타는 정도 (걷는 속도 = 속도 × (지형 속도 배율)^terrain. 1 = 일반 병사와 같은 비율로 느려진다)
#   charge: 달려와 처음 치는 한 방의 배율, upkeep: 먹는 식량 배율
#   기병 = 탄 병사의 이동 속도 1.5배, 공격력 1.5배 (밸런스는 나중에), 체력은 그대로
UNIT_STATS = {
    INFANTRY:     dict(hp=40.0, dmg=6.0, range=2.2, cd=1.0, speed=4.5, sight=14.0, cost=(40, 0, 0), time=7.0,
                       terrain=1.0, charge=1.0, upkeep=1.0, ranged=False),
    ARCHER:       dict(hp=26.0, dmg=4.0, range=13.0, cd=1.5, speed=4.5, sight=16.0, cost=(30, 25, 0), time=9.0,
                       terrain=1.0, charge=1.0, upkeep=1.0, ranged=True),
    LANCER:       dict(hp=40.0, dmg=9.0, range=2.4, cd=1.0, speed=6.75, sight=15.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.8, upkeep=1.5, ranged=False),     # 보병 + 말
    HORSE_ARCHER: dict(hp=26.0, dmg=6.0, range=13.0, cd=1.5, speed=6.75, sight=17.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.0, upkeep=1.5, ranged=True),      # 궁수 + 말
}
# 상성: (치는 쪽, 맞는 쪽) → 피해 배율. 보병은 기병에 강하고 (막아선다), 창기병은 궁수에 강하다 (달려들어 흩는다)
UNIT_VS = {(INFANTRY, LANCER): 1.3, (INFANTRY, HORSE_ARCHER): 1.3, (LANCER, ARCHER): 1.5, (LANCER, HORSE_ARCHER): 1.2}
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

# --- 야생 동물과 길들이기 (sim/wildlife.py). 동물 하나 = 표 한 줄 (사막 동물 등은 한 줄 더하면 된다)
#   habitat: 사는 땅 (재질 묶음, 평평한 곳만), group: 한 무리 마릿수, per_area: 사는 땅 이만큼(칸)마다 한 마리 (최대 cap),
#   regrow: 줄어든 뒤 새 무리가 생기는 간격 (겨울엔 거의 안 생긴다), tame: 길들이는 시간,
#   mounts: 어떤 병사가 길들이면 무엇이 되는지 (병사와 동물이 합쳐진 병종)
HORSE = 0
WILDLIFE = {
    HORSE: dict(name='말', habitat='grass', group=(2, 4), per_area=1500, cap=36, regrow=45.0, tame=11.0,
                mounts={INFANTRY: LANCER, ARCHER: HORSE_ARCHER}),
}
MOUNTED = {v for a in WILDLIFE.values() for v in a['mounts'].values()}     # 동물을 탄 병종


def josa(word: str, a: str, b: str) -> str:
    """받침에 맞는 조사 (josa('말', '이', '가') → '말이', josa('목장', '을', '를') → '목장을')."""
    ch = word[-1]
    final = 0xAC00 <= ord(ch) <= 0xD7A3 and (ord(ch) - 0xAC00) % 28 != 0
    return word + (a if final else b)


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
