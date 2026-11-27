"""게임 규칙 수치. 한 판 20~30분의 느긋한 템포 기준 (게임 속도 ×1).

자원: 식량(농장, 비옥한 들판) / 목재(벌목장, 숲) / 석재(채석장, 바위 지대) / 유황(유황 채취장, 사막의 유황 웅덩이).
화염탑: 불을 뿜는 범위 공격 건물 (유황을 연료로 쓴다, 드래곤에 강하다. sim/firetower.py).
야생 동물: 넓은 초원에 야생말이 흩어져 산다. 병사를 고르고 말을 오른쪽 클릭하면 가서 길들여 기병이 된다
  (보병 → 창기병, 궁수 → 기마궁수. sim/wildlife.py, WILDLIFE 표).
  넓은 설원의 가장 높은 곳에는 드래곤 둥지가 있다. 드래곤은 둥지를 지키며 서리 숨결을 뿜는다.
  체력을 깎아 제압하면 잠시 쓰러지고, 그동안 병사 하나가 길들이면 용기사가 된다 (날아다님, 나라마다 2기까지).
  넓은 사막에는 거대 바위거북이 1~2마리씩 산다. 병사가 가서 먹이(식량)를 주면 금방 길들여 함께 싸우는 탱커가 된다
  (발 구르기 범위 공격, 낮은 포효로 둘레 적의 어그로 끌기, 위험하면 껍질 속으로 숨어 버팀. sim/companions.py).
병사는 식량을 먹는다 (겨울에 더). 식량이 바닥나면 굶어서 조금씩 약해진다.
거점과 병사를 모두 잃으면 패배 (자원지·망루만 남아도).
"""
from __future__ import annotations

FOOD, WOOD, STONE = range(3)
RES_NAMES = ('식량', '목재', '석재')

# --- 유닛
INFANTRY, ARCHER, LANCER, HORSE_ARCHER, DRAGON_RIDER, WILD_DRAGON, TORTOISE = range(7)
UNIT_NAMES = ('보병', '궁수', '창기병', '기마궁수', '용기사', '드래곤', '바위거북')
NEUTRAL = 250             # 야생 (어느 나라도 아님): 야생 드래곤의 나라 번호. 병사들이 저절로 덤비지 않는다
TRAINABLE = (INFANTRY, ARCHER)            # 거점에서 훈련하는 병종. 기병은 야생말을 길들여야만 생긴다
#   체력, 공격, 사거리, 공격 간격(초), 속도(칸/초, 평지), 시야, 비용(식량, 목재, 석재), 훈련 시간,
#   terrain: 지형을 타는 정도 (걷는 속도 = 속도 × (지형 속도 배율)^terrain. 1 = 일반 병사와 같은 비율로 느려진다)
#   charge: 달려와 처음 치는 한 방의 배율, upkeep: 먹는 식량 배율
#   기병 = 탄 병사의 이동 속도 1.8배, 공격력 1.5배 (밸런스는 나중에), 체력은 그대로
#   fly: 움직이거나 싸울 때 난다 (지형·물 무시, 근접 공격을 받지 않는다: 활·망루·전함만 맞힌다).
#        할 일 없이 멈춰 있으면 땅에 내려앉고, 그동안은 누구에게나 맞는다,
#   splash: 범위 피해 반지름 (서리 숨결: 둘레에도 피해, 맞은 병사는 잠시 느려진다)
#   용기사 = 어느 병사가 탔든 같다 (공격은 용의 숨결뿐)
UNIT_STATS = {
    INFANTRY:     dict(hp=40.0, dmg=6.0, range=2.2, cd=1.0, speed=4.5, sight=14.0, cost=(40, 0, 0), time=7.0,
                       terrain=1.0, charge=1.0, upkeep=1.0, ranged=False, fly=False, splash=0.0),
    ARCHER:       dict(hp=26.0, dmg=4.0, range=13.0, cd=1.5, speed=4.5, sight=16.0, cost=(35, 30, 0), time=9.0,
                       terrain=1.0, charge=1.0, upkeep=1.0, ranged=True, fly=False, splash=0.0),
    LANCER:       dict(hp=40.0, dmg=9.0, range=2.4, cd=1.0, speed=8.1, sight=15.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.8, upkeep=1.5, ranged=False, fly=False, splash=0.0),     # 보병 + 말
    HORSE_ARCHER: dict(hp=26.0, dmg=6.0, range=13.0 * 1.2, cd=1.5, speed=8.1, sight=17.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.0, upkeep=1.5, ranged=True, fly=False, splash=0.0),      # 궁수 + 말
    DRAGON_RIDER: dict(hp=380.0, dmg=30.0, range=8.0, cd=2.5, speed=7.0, sight=18.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.0, upkeep=4.0, ranged=True, fly=True, splash=4.0),       # 병사 + 드래곤
    WILD_DRAGON:  dict(hp=1500.0, dmg=22.0, range=8.0, cd=3.5, speed=3.5, sight=16.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.0, upkeep=0.0, ranged=True, fly=False, splash=4.0),      # 둥지를 지키는 야생 드래곤
    TORTOISE:     dict(hp=600.0, dmg=5.0, range=2.2, cd=1.5, speed=4.0, sight=13.0, cost=(0, 0, 0), time=0.0,
                       terrain=1.0, charge=1.0, upkeep=3.0, ranged=False, fly=False, splash=0.0),     # 길든 거대 바위거북 (탱커)
}
# 상성: (치는 쪽, 맞는 쪽) → 피해 배율. 보병은 기병에 강하고 (막아선다), 창기병은 궁수에 강하다 (달려들어 흩는다)
UNIT_VS = {(INFANTRY, LANCER): 1.3, (INFANTRY, HORSE_ARCHER): 1.3, (LANCER, ARCHER): 1.5, (LANCER, HORSE_ARCHER): 1.2,
           (ARCHER, DRAGON_RIDER): 1.4, (HORSE_ARCHER, DRAGON_RIDER): 1.4,     # 활은 날아다니는 용기사에 강하다
           (ARCHER, TORTOISE): 0.6, (HORSE_ARCHER, TORTOISE): 0.6}             # 바위 껍질은 화살을 막는다
# 바위거북의 능력 (sim/companions.py)
#   발 구르기: 붙은 적이 있으면 cd초마다 앞발로 땅을 내리찍어 r칸 안의 땅의 적 모두에게 dmg, push칸 밀어낸다
#   낮은 포효 (어그로): cd초마다 r칸 안의 적 병사가 t초 동안 바위거북만 노린다 (명령받은 적도)
#   껍질 숨기: 체력이 hp 비율 아래면 t초 동안 껍질 속으로 숨어 받는 피해를 cut만큼 줄인다 (움직이지도 치지도 않는다, cd초에 한 번)
STOMP = dict(cd=3.5, r=4.0, dmg=10.0, push=0.8)
TAUNT = dict(cd=15.0, r=10.0, t=4.0)
HIDE = dict(hp=0.25, t=5.0, cut=0.7, cd=30.0)
HEAL_RIDER = 1.5           # 용기사가 어디서든 1초에 회복하는 체력
HEAL_ON_SNOW = 4.0         # 용기사가 눈 위에서 1초에 회복하는 체력 (설원에 진지를 둘 이유)
UPKEEP = 0.035             # 병사 하나가 1초에 먹는 식량 (겨울에는 1.5배까지)
STARVE = 0.4               # 식량이 바닥나면 병사가 1초에 잃는 체력
HEAL_NEAR_HALL = 0.6       # 거점 가까이서 1초에 회복하는 체력

# --- 건물
HALL, FARM, LUMBER, QUARRY, TOWER, HARBOR, SULFUR_PIT, FIRE_TOWER, PASTURE = range(9)
BUILD_NAMES = ('거점', '농장', '벌목장', '채석장', '망루', '항구', '유황 채취장', '화염탑', '목장')
#             체력, 크기(반지름, 칸), 비용(식량, 목재, 석재), 짓는 데 드는 일(병사×초), sulfur: 유황 비용
BUILD_STATS = {
#   비용은 목재와 석재로 나눈다 (목재를 조금 더: 건물 전체로 목재 : 석재 ≈ 1.45 : 1). 채석장만 목재로 (석재가 바닥나도 캘 수 있게)
    HALL:   dict(hp=700.0, r=5, cost=(0, 170, 130), work=90.0),
    FARM:   dict(hp=160.0, r=4, cost=(0, 40, 15), work=20.0),
    LUMBER: dict(hp=160.0, r=4, cost=(0, 30, 15), work=18.0),
    QUARRY: dict(hp=180.0, r=4, cost=(0, 60, 0), work=24.0),
    TOWER:  dict(hp=320.0, r=2, cost=(0, 60, 50), work=30.0),
    HARBOR: dict(hp=260.0, r=4, cost=(0, 70, 50), work=30.0),     # 해안에만. 이 땅의 병사가 여기 모여 배로 건너고, 전함을 만든다
    SULFUR_PIT: dict(hp=160.0, r=4, cost=(0, 40, 25), work=22.0),  # 사막의 유황 웅덩이에만
    FIRE_TOWER: dict(hp=520.0, r=2, cost=(0, 50, 70), work=35.0, sulfur=40),
    PASTURE: dict(hp=200.0, r=3, cost=(0, 55, 20), work=24.0),   # 목장 헛간 (자원 건물의 0.75배). 말·순록 떼에 짓는다 (sim/pasture.py)
}
# 화염탑: cd초마다 range칸 안의 가장 가까운 적에게 dmg (둘레 splash칸의 적에게는 splash_mul배). 유황이 없으면 weak배.
#   드래곤(용기사, 야생 드래곤)은 vs_dragon배 (얼음은 불에 약하다), 바위거북은 vs_tortoise배 (껍질이 견딘다).
#   용기사(체력 380, 회복 초당 1.5, 숨결 30/2.5초)와 1대1 (눈이 없는 땅): 화염탑(체력 520)이 불 20번(38초)에 이기고
#   그동안 숨결 16번(480)을 맞아 체력 약 40이 남는다 (아슬아슬하게). 눈 위에서는 용기사가 초당 4씩 회복해 용기사가 이긴다
#   사거리가 궁수(13칸, 건물 가장자리에서 = 가운데에서 15칸)보다 길어서 궁수가 밖에서 일방적으로 치지 못한다
FIRE = dict(cd=2.0, range=UNIT_STATS[ARCHER]['range'] * 1.25, dmg=14.0,     # 사거리: 궁수의 1.25배 (16.25칸, 탑 가운데에서)
            splash=4.0, splash_mul=0.6, weak=0.5, vs_dragon=1.6, vs_tortoise=0.7)

# --- 배
# 나룻배: 병사들이 있는 땅에 완성된 항구가 있으면, 바다 건너로 명령받은 병사들이 그 항구에 모여 차례로 타고
#         다 타면 함께 건넌다 (비용 없음, sim/boats.py)
BOAT_CAPACITY = 10
FERRY_HP = 10.0            # 전함 한 방(WARSHIP_DMG)에 가라앉는다
FERRY_SPEED = 4.5          # 칸/초 (병사가 평지를 걷는 속도와 같다)
# 전함: 항구에서 만든다. 다른 나라의 나룻배와 전함을 공격한다
WARSHIP = 'warship'        # 항구 대기열에 넣는 이름
WARSHIP_COST = (0, 70, 50)
WARSHIP_TIME = 20.0
WARSHIP_HP = 180.0
WARSHIP_SPEED = 5.0
WARSHIP_RANGE = 16.0
WARSHIP_DMG = 14.0
WARSHIP_CD = 1.6

SULFUR = 3                                                     # 자원지 종류: 유황 웅덩이 (자원 0~2와 따로 센다)
SITE_NAMES = ('식량', '목재', '석재', '유황')
SITE_BUILDING = {FOOD: FARM, WOOD: LUMBER, STONE: QUARRY, SULFUR: SULFUR_PIT}     # 자원지 종류 → 지을 건물
SITE_RES = {FOOD: FOOD, WOOD: WOOD, STONE: STONE, SULFUR: SULFUR}     # 자원지 종류 → 나는 자원 (유황은 따로)
SULFUR_YIELD = 0.25        # 유황 채취장이 1초에 모으는 유황 (× 풍부함)

# --- 야생 동물과 길들이기 (sim/wildlife.py). 동물 하나 = 표 한 줄 (사막 동물 등은 한 줄 더하면 된다)
#   habitat: 사는 땅 (재질 묶음, 평평한 곳만), group: 한 무리 마릿수, per_area: 사는 땅 이만큼(칸)마다 한 마리 (최대 cap),
#   regrow: 줄어든 뒤 새 무리가 생기는 간격 (겨울엔 거의 안 생긴다), tame: 길들이는 시간,
#   mounts: 어떤 병사가 길들이면 무엇이 되는지 (병사와 동물이 합쳐진 병종)
#   spread: 한 무리가 흩어져 생기는 반지름 (칸, 기본 3), herd_r: 한 번에 함께 길들이는 둘레 (칸, 기본 10)
#   사나운 동물 (hostile): 둥지(lair)에 하나씩 살며 지킨다. unit: 싸울 때의 병종, wake: 이만큼 다가오면 깬다,
#   guard: 둥지에서 이만큼 안의 병사를 친다, subdue: 체력이 이 비율 아래면 쓰러진다 (subdue_time초 동안,
#   그동안만 길들일 수 있고 맞지 않는다), regrow: 길들여진 뒤 둥지에 새로 나는 시간, limit: 나라마다 탈 수 있는 수
#   함께 싸우는 동물 (companion): 길들여도 병사는 그대로이고, 동물이 그 나라의 병사(companion 병종)가 된다.
#   food: 길들일 때 주는 먹이 (식량), tamers: 길들일 수 있는 병사, calm: 사람이 와도 달아나지 않는다
HORSE, DRAGON, TORTOISE_W, REINDEER = range(4)
_ANY = (INFANTRY, ARCHER, LANCER, HORSE_ARCHER)
WILDLIFE = {
    HORSE: dict(name='말', habitat='grass', group=(7, 12), spread=22.0, herd_r=26.0, per_area=700, cap=60, regrow=25.0, tame=11.0,
                mounts={INFANTRY: LANCER, ARCHER: HORSE_ARCHER}),
    DRAGON: dict(name='드래곤', habitat='lair', hostile=True, unit=WILD_DRAGON, cap=3, regrow=360.0, tame=15.0,
                 wake=8.0, guard=14.0, subdue=0.3, subdue_time=30.0, limit=2,
                 mounts={k: DRAGON_RIDER for k in _ANY},
                 # 체력에 따라 늘어나는 기술 (sim/wildlife.py _lairs): 2단계 (체력 phase 아래) 눈보라 폭발, 3단계 날아오르기.
                 #   nova: cd초마다, 자기를 치는 병사가 가장 많이 몰린 곳 (드래곤에서 reach칸 안, 반지름 r칸에 min명 넘게:
                 #         나는 용기사는 혼자서도 min명 몫)을 골라 wind초 동안 입 앞에 빛을 모았다가 그곳으로 던진다 (fly초 날아가 터진다).
                 #         반지름 r칸 안의 병사 (나는 용기사도)마다 얼음이 터진다: 최대 체력의 dmg_frac (큰 유닛은 dmg_max까지), freeze초 얼어붙는다.
                 #         날고 있을 때도 쓴다 (공중에 멈춰 모은다)
                 #   flight: 체력 phase 아래면 날아올라 쓰러질 때까지 치고 빠진다 (근접 병사는 못 친다, 활·망루·용기사만):
                 #         자기를 칠 수 있는 병사들의 반대쪽으로 날아 사거리 밖 (+margin칸)으로 빠졌다가 (둥지에서 guard+leash칸 안,
                 #         flee초까지), turn초 동안 돌아보고 (눈보라가 준비됐으면 이때 모은다), 가장 가까운 병사에게 날아가
                 #         숨결이 닿으면 서리 숨결 (드래곤 공격과 같은 피해·범위, breath초에 한 번까지) → hold초 동안 그 자리에서
                 #         뿜기를 마치고 (공격 중엔 물러나지 않는다: 뒷걸음질처럼 보이지 않게) → 다시 병사들 반대쪽으로 빠진다.
                 #         쓰러지면 땅으로 떨어진다. 둘레에 병사가 idle초 넘게 없으면 내려앉아 둥지로 돌아간다
                 nova=dict(phase=0.9, cd=12.0, wind=1.5, fly=0.45, reach=18.0, r=7.0, dmg_frac=0.55, dmg_max=50.0, freeze=2.0, min=3),
                 flight=dict(phase=0.5, speed=6.0, breath=2.5, idle=4.0, leash=12.0, margin=3.0, turn=0.5, flee=5.0, hold=0.9),
                 # 겨울 습격 (sim/wildlife.py _raids): 겨울이 every번 (그 사이 무작위) 올 때마다 잠든 드래곤 하나가 깨어
                 #   제 몫의 설원에 있는 나라 병사·건물 (거점은 빼고: 드래곤 때문에 망하지 않게)을 날아다니며 친다.
                 #   둥지가 있는 이어진 설원만 둥지마다 나눈다: 칸마다 그 설원 안 가장 가까운 둥지의 몫 (드래곤끼리 겹치지 않는다,
                 #   둥지가 없는 떨어진 설원은 습격하지 않는다).
                 #   치고 빠지기는 날기와 같다 (숨결, 눈보라). 건물에는 숨결 피해 ×bdmg.
                 #   체력이 subdue 아래로 떨어지거나, 칠 것이 없거나, 겨울이 끝나면 둥지로 날아 돌아가 잔다 (돌아오면 체력을 heal까지 채운다).
                 #   습격 중에는 쓰러지지 않는다 (길들일 수 없다: 둥지에서 깨웠을 때만)
                 raid=dict(every=(1, 2), bdmg=2.0, heal=0.6, sight=20.0)),
    TORTOISE_W: dict(name='바위거북', habitat='desert', group=(1, 2), per_area=2500, cap=8, regrow=360.0, tame=4.0,
                     food=240, companion=TORTOISE, tamers=_ANY, calm=True),   # 먹이는 처음 한도(STORE_BASE + STORE_HALL) 안에서
    # 순록: 설원·툰드라의 평평한 곳에 촘촘한 무리로. 길들이지 않는다 (병사로 탈 수 없다: 목장에 들인다, docs/PASTURE_PLAN.md)
    REINDEER: dict(name='순록', habitat='snow', group=(4, 7), spread=5.0, herd_r=12.0, per_area=900, cap=40, regrow=200.0),
}
MOUNTED = {v for a in WILDLIFE.values() for v in a.get('mounts', {}).values()}     # 동물을 탄 병종

# 목장 (sim/pasture.py, docs/PASTURE_PLAN.md): 목장을 고르고 말·순록 떼를 누르면 그 떼를 울타리 안에 들여 식량을 낸다
#   radius: 울타리 반지름 한도 (용 둥지쯤), find_r: 누른 자리에서 떼를 찾는 거리, herd_r: 한 떼로 치는 거리, min_herd: 이보다 작은 떼엔 못 짓는다,
#   search: 떼 가운데에서 헛간 자리를 고르는 거리, min_fill: 울타리 평균 반지름이 radius의 이만큼은 돼야 (너무 작거나 파인 울타리 막기),
#   cap: 목장마다 최대 마리, breed: 봄·여름에 새끼 한 마리까지 (초), keep: 말을 꺼내 탈 때 남기는 마리 (새끼를 치려면 둘),
#   food: 마리마다 1초에 내는 식량, winter: 겨울 배율 (순록은 이끼를 먹어 겨울에도 꽤 낸다)
PASTURE_RULES = dict(radius=15.0, find_r=8.0, herd_r=20.0, min_herd=3, search=12.0, cap=10, breed=120.0, min_fill=0.55, keep=2,
                     food={HORSE: 0.07, REINDEER: 0.12}, winter={HORSE: 0.4, REINDEER: 0.7})


def tamers_of(info: dict) -> set:
    """이 동물을 길들일 수 있는 병종."""
    return set(info['mounts']) if 'mounts' in info else set(info.get('tamers', ()))


def josa(word: str, a: str, b: str) -> str:
    """받침에 맞는 조사 (josa('말', '이', '가') → '말이', josa('목장', '을', '를') → '목장을')."""
    ch = word[-1]
    final = 0xAC00 <= ord(ch) <= 0xD7A3 and (ord(ch) - 0xAC00) % 28 != 0
    return word + (a if final else b)


TOWER_RANGE, TOWER_DMG, TOWER_CD = 22.0, 6.0, 1.4

# 1초에 나는 자원 (자원지 풍부함 1 기준). 거점도 조금씩 낸다 (아무것도 없어도 다시 일어설 수 있게)
YIELD = {FARM: (FOOD, 1.5), LUMBER: (WOOD, 0.9), QUARRY: (STONE, 0.65)}
HALL_YIELD = (0.45, 0.25, 0.0)
# 계절별 배율 (봄, 여름, 가을, 겨울). 추운 곳일수록 이 차이가 그대로, 열대는 거의 1
SEASON_YIELD = {FOOD: (0.6, 1.0, 1.7, 0.05), WOOD: (1.0, 1.0, 1.0, 0.7), STONE: (1.0, 1.0, 1.0, 0.8)}


# 자원 한도 (sim/storage.py): 자원마다 따로. 기본 STORE_BASE + 다 지은 거점마다 모든 자원 +STORE_HALL
#   + 다 지은 자원 건물마다 그 자원 +STORE_SITE (창고는 없다: 거점과 자원 건물이 창고를 겸한다, 무너지면 그 몫을 빼앗긴다)
STORE_BASE = 200.0
STORE_HALL = 50.0
STORE_SITE = 25.0

# 기후 효과 (sim/climate.py, 부족은 sim/tribes.py): 병사만 받는다
#   slow: 불리한 기후 지역에서 이동 배율, chance·every·dmg: 확률 피해 (every초에 한 번꼴로 chance 확률, 최대 체력의 dmg),
#   floor: 기후 피해로는 최대 체력의 이 비율 아래로 떨어지지 않는다, snow_take: 설원 부족이 설원 지역에서 받는 피해 배율,
#   desert_deal: 사막 부족이 설원 밖에서 주는 피해 배율, tame_*: 길들이는 시간 배율, temperate_train: 온대 부족의 병사 훈련 시간 배율,
#   thirst_upkeep: 사막 지역의 병사가 먹는 식량 배율 (갈증: 모든 부족, 겨울 배율은 그대로 곱한다)
CLIMATE = dict(slow=0.85, chance=0.5, every=3.0, dmg=0.02, floor=0.3, snow_take=0.85, desert_deal=1.2,
               tame_snow_tortoise=1.5, tame_desert_dragon=1.25, temperate_train=0.85, thirst_upkeep=1.2)

START_RES = (160.0, 160.0, 120.0)      # 석재를 넉넉히: 석재 자원지가 먼 곳에서 시작해도 첫 건물들을 짓게
START_UNITS = ((INFANTRY, 5), (ARCHER, 2))

COLORS = [  # 색 이름, 색 (스프라이트 옷/지붕), 밝은 색. 설정 화면에서 내 나라 색을 고르고, AI는 나머지를 쓴다
    ('붉은', (214, 70, 52), (255, 140, 110)),
    ('호박', (226, 160, 40), (255, 214, 110)),
    ('보라', (128, 84, 196), (190, 150, 255)),
    ('청록', (34, 156, 150), (110, 230, 216)),
    ('분홍', (220, 100, 160), (255, 170, 210)),
    ('은빛', (205, 210, 222), (255, 255, 255)),
    ('쪽빛', (62, 96, 206), (140, 170, 255)),
    ('먹빛', (70, 70, 86), (176, 176, 200)),     # 8번째 (최대 8나라). 초록 땅에 묻히지 않게 초록 대신 어두운 회색
]
ANIMALS = ('여우', '사슴', '까마귀', '수달', '두루미', '늑대', '곰', '매')   # AI 나라 이름: 색 + 동물
DIFFICULTY = {'쉬움': 0.75, '보통': 1.0, '어려움': 1.3}                      # AI 자원 수입 배율 (공격성도 조금)
