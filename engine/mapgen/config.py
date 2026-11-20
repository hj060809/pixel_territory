"""세계 생성 설정."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorldConfig:
    size: int = 512
    seed: int = 0
    sea_level: float = 0.40                                 # 셰이더의 sea_level과 같아야 한다

    # --- 1. 땅 모양 (engine.mapgen.stages.landmass). 길이는 지도 크기에 대한 비율
    land_ratio: float = 0.85                                # 육지 비율
    landmasses: int = 3                                     # 땅덩어리 수 (적으면 큰 대륙, 많으면 군도)
    size_variety: float = 0.5                               # 크기 차이: 0 = 비슷하게 나눠 가짐 ~ 1 = 큰 덩어리 몇 개와 아주 작은 섬 여럿
    elongation: float = 0.5                                # 길쭉함: 0 = 굵고 둥근 ~ 1 = 가늘고 긴 (덩어리마다 조금씩 다르게)
    edge_ocean: float = 0.15                                 # 가장자리 바다: 0 = 땅이 지도 밖으로 이어짐 (지역을 잘라낸 느낌) ~ 1 = 모든 땅이 지도 안
    coast_roughness: float = 0.8                            # 해안 굴곡: 만과 반도 (좌표 비틀기 + 중간 크기 노이즈)
    coast_detail: float = 0.35                              # 해안 잔굴곡
    sharpness: float = 0.5                                  # 각진 정도: 0 = 부드러운 해안 ~ 1 = 직선으로 꺾인 해안
    strait_width: float = 0.05                              # 땅덩어리 사이 최소 바다 폭
    coast_smoothing: int = 1                                # 한두 픽셀짜리 돌기와 틈을 없애는 반지름
    inland_sea_area: float = 0.006                          # 땅에 갇힌 물이 이 비율보다 크면 내륙 호수로 남긴다

    # --- 2. 높이 (engine.mapgen.stages.elevation)
    plates: tuple[int, int] = (7, 12)                        # 산맥이 잘 생기는 판 경계의 수
    mountain_height: float = 1.0
    mountain_coverage: float = 0.60                         # 육지 중 산이 생기는 지역 비율
    ridge_scale: float = 0.15                               # 능선 간격 (클수록 굵직한 능선)
    massif: float = 0.4                                     # 능선이 모인 곳이 두꺼운 산괴가 되는 정도
    hill_height: float = 0.10
    lowland: float = 1.1                                    # 클수록 낮은 평지가 넓어진다

    # --- 3. 침식 (engine.mapgen.stages.erosion)
    erosion_droplets: int | None = None                     # None이면 크기에 맞춰 자동 (512에서 30만)

    # --- 4. 물 (engine.mapgen.stages.water, engine.mapgen.stages.rivers)
    lakes: tuple[int, int] = (3, 8)                         # 내륙 저지대에 파는 호수 분지 수
    lake_radius: tuple[float, float] = (0.006, 0.05)        # 이 범위에서 로그 분포로 (작은 호수가 더 많다)
    lake_min_area: int = 60                                 # 이보다 작은 웅덩이는 메운다 (512 기준 픽셀 수)
    lake_max_level: float = 0.2                             # 해수면보다 이만큼 높은 곳까지만 호수 (산꼭대기 호수 방지)
    river_threshold: float = 0.05                          # 전체 칸 중 이 비율 이상 물이 모이면 강
    river_max_width: int = 3
    meander: float = 1.0                                    # 평지에서 강이 굽이치는 정도 (0이면 곧게)
    floodplain: float = 1.0                                 # 평지 강 양옆을 평평하게 고르는 폭 배율 (0이면 끔)
    oxbow_chance: float = 0.35                              # 크게 굽은 곳에 우각호가 생길 확률
    deltas: bool = True                                     # 큰 강 하구의 삼각주
    delta_min_width: float = 1.0                            # 이 폭 이상인 강만 삼각주를 만든다

    # --- 5. 해안 종류 (engine.mapgen.stages.coast)
    coast_variety: float = 1.0                              # 해안 종류별 지형 처리 세기 (0이면 끔)
    cliffs: float = 0.22                                    # 해안선 중 해식 절벽 비율 (곶, 산이 바다에 붙은 곳 위주)
    beaches: float = 0.30                                   # 해안선 중 넓은 모래사장 비율 (만 안쪽, 완만한 곳 위주). 나머지는 석회암 바위 해안
    sea_stacks: float = 1.0                                 # 절벽 앞바다 바위기둥 양
    lagoons: int = 2                                        # 모래톱으로 막힌 석호 최대 개수

    # --- 6. 기후 (engine.mapgen.stages.climate). 위치에만 따른다. 0 ≈ 추움/메마름, 1 ≈ 더움/아주 습함
    climate_zones: int = 5                                  # 자동 기후 영역 수 (1이면 지도 전체가 한 기후)
    temperature_range: tuple[float, float] = (0, 1)  # 자동 영역의 기온을 이 범위 안에서 고른다
    moisture_range: tuple[float, float] = (0, 1)        # 자동 영역의 습도를 이 범위 안에서 고른다
    zone_border: float = 0.12                               # 영역 경계가 섞이는 폭 (지도 크기 비율). 클수록 기후가 서서히 바뀐다
    zone_contrast: float = 0.45                             # 이웃한 자동 영역끼리 기온 차 한계 (아주 더운 곳과 아주 추운 곳이 맞붙지 않게)
    zone_wobble: float = 0.8                                # 영역 경계가 구불거리는 정도
    zones: tuple = ()                                       # 직접 지정한 영역 ((x, y, 기온, 습도[, 크기]), ...). 주면 자동 영역 대신
    # 영역 기후 위에 더하는 조정 (0이면 끔)
    temp_altitude: float = 0.4                              # 고도: 높을수록 추워짐
    temp_coast: float = 0.3                                 # 바다 완화: 해안은 극단이 누그러짐
    temp_patches: float = 0.3                               # 지역 얼룩 (기온)
    moist_patches: float = 0.3                              # 지역 얼룩 (습도)
    patch_scale: float = 0.3                                # 얼룩 크기 (지도 크기 비율)
    moist_wind: float = 0.5                                 # 바람과 비그늘: 바람 받는 산 앞은 습하고 산 너머는 마름
    wind_dir: float = 0.0                                   #   바람이 향하는 방향 (도, 0 = 동쪽, 90 = 남쪽)
    rain_shadow: float = 1.0                                #   산을 넘으며 비로 떨어지는 세기 (클수록 산 너머가 마름)
    freshwater_moisture: float = 0.5                        # 강·호수 가까이 더 습하게 (사막 속 강줄기에 초록 띠)
    coast_moisture: float = 0.2                             # 바닷가 가까이 더 습하게 (넓고 약하게)

    @classmethod
    def preset(cls, name: str, **overrides) -> 'WorldConfig':
        """presets/ 폴더의 프리셋 (engine.mapgen.presets 참고)."""
        from engine.mapgen.presets import load_preset
        return load_preset(name, cls(), **overrides)
