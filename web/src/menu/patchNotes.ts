// 패치노트: 로비에 들어오면 (페이지를 열고 처음 한 번) 창으로 보인다 (menu/lobby.ts showPatch).
// 하루 = 한 버전, 새 것이 위. 그림은 web/public/patch/<버전>.webp (게임 화면, 960×540).
// [그만보기]를 켜고 닫으면 쿠키에 지금 최신 버전을 적어 두고, 더 새 버전이 생길 때까지 보이지 않는다.
// 새 패치를 올릴 때: 맨 위에 항목을 더한다 (version이 바뀌면 그만본 사람에게도 다시 보인다).

/** title·sub·tags·accent: 배너 (menu/patchBanner.ts)의 한 줄 제목, 부제, 기능 태그, 강조색.
 *  focus: 그림에서 주인공이 있는 가로 자리 (0~1, 기본 0.5). 배너 오른쪽 (76%)에 오게 그림을 옮긴다. */
export interface Patch { version: string; date: string; image?: string; focus?: number; title?: string; sub?: string; tags?: string[]; accent?: number[]; items: string[] }

export const PATCHES: Patch[] = [
  {
    version: '0.7', date: '2026-11-28', image: '/patch/0.7.webp', focus: 0.52, accent: [255, 150, 70],
    title: 'SULFUR & SHADOWS', sub: 'Fire in the fog of war', tags: ['GRENADIER', 'FOG OF WAR', 'PIONEER', 'WARSHIP'],
    items: [
      '유황 척탄병: 거점에서 불붙인 유황 단지를 던지는 병사를 뽑습니다. 떨어진 자리에 불이 붙어 둘레의 적을 태웁니다. (E키, 식량 30·목재 25·유황 15, 사거리 9)',
      '척탄기마병: 척탄병이 말에 오르면 더 빠르게 달리고 더 멀리 던집니다. (사거리 1.2배)',
      '전장의 안개: 게임 설정에서 켜면 내 병사·건물 둘레만 보입니다. 가려진 곳의 적은 보이지 않고, 적 건물은 마지막으로 본 모습으로 남습니다. (동맹과 시야 공유, 게임 중엔 못 바꿈)',
      '개척: 다른 기후 지역에 거점을 세우면 그 땅의 부족으로 바꿀 수 있습니다. 스스로 버린 기후는 다시 고를 수 없습니다.',
      '전함 해안 포격: 적 배가 없으면 바닷가의 적 병사와 건물을 포격합니다. 거리를 두고 옆구리를 돌려 쏘며, 포탄이 떨어지는 순간 맞습니다. (건물 1.5배)',
      '땅에서 배로: 궁수·척탄병이 사거리 안의 적 배를 쏘고, 적 배를 눌러 공격시킬 수 있습니다. 원거리 병사는 가장 세게 맞는 적을 먼저 노립니다.',
      '예쁜 스크린샷: F12를 누르면 판 전체 지도를 한 장에 담습니다.',
    ],
  },
  {
    version: '0.6', date: '2026-11-27', image: '/patch/0.6.webp', accent: [140, 200, 255],
    title: 'FORMATIONS & WINTER RAIDS', sub: 'Draw the line. Hold the line.', tags: ['FORMATION', 'DRAGON UP', 'WINTER RAID'],
    items: [
      '진형: 오른쪽 버튼으로 선을 그으면 병사들이 그 선을 따라 섭니다. 보병은 앞, 궁수는 뒤. (모바일은 ▦ 진형 버튼을 켜고 한 손가락으로)',
      '둘레 방어선: 선을 시작점까지 이어 닫으면 둥글게 둘러섭니다.',
      '진형 지키기: 선 병사들은 함부로 대열을 벗어나지 않고 다가오는 적만 상대합니다. (근접은 제 자리 5칸 안까지)',
      '드래곤 강화: 몰린 병사들에게 눈보라 폭탄을 던지고, 궁지에 몰리면 날아올라 치고 빠집니다. (체력 1500, 날기는 체력 50% 아래)',
      '겨울 드래곤 습격: 설원의 겨울에 분노한 드래곤이 찾아옵니다. (1~2년에 1회, 거점은 치지 않음, 습격 중엔 길들일 수 없음)',
      '기마궁수: 더 멀리 쏩니다. (사거리 궁수의 1.2배)',
      '명령어 창: 혼자 하는 판에서 ` 키로 자원, 병사, 드래곤 습격을 불러올 수 있습니다.',
      '고친 것: 드래곤 숨결이 엉뚱한 곳에서 나오던 문제, 뒷걸음질, 나는 드래곤이 병사에 가려지던 문제.',
    ],
  },
  {
    version: '0.5', date: '2026-11-26', image: '/patch/0.5.webp', accent: [150, 220, 120],
    title: 'TRIBES & PASTURES', sub: 'The land shapes your people', tags: ['TRIBES', 'PASTURE', 'STORAGE CAP'],
    items: [
      '부족: 시작한 땅에 따라 설원·사막·온대 부족이 되어 저마다 강한 땅이 생깁니다.',
      '기후: 맞지 않는 땅에서는 추위와 더위에 지치고, 사막에선 목이 말라 식량을 더 먹습니다.',
      '목장: 말과 순록 떼를 울타리에 들여 식량을 얻고, 말을 꺼내 타 기병이 됩니다.',
      '자원 한도: 자원을 무한히 쌓을 수 없습니다. 거점과 자원 건물이 창고가 되고, 무너지면 빼앗깁니다.',
      '최적화: 큰 판에서도 멈칫거리지 않습니다. (화면 위에 FPS 표시)',
    ],
  },
  {
    version: '0.4', date: '2026-11-25', image: '/patch/0.4.webp', accent: [255, 170, 90],
    title: 'CLEAR SIGHT', sub: 'Your colors on every unit', tags: ['VISIBILITY'],
    items: [
      '시인성: 내 병사와 건물에 나라 색 고리가 생겨 한눈에 보입니다. (메뉴에서 끄고 켜기)',
    ],
  },
  {
    version: '0.3', date: '2026-11-23', image: '/patch/0.3.webp', accent: [200, 150, 255],
    title: 'TOGETHER OR APART', sub: 'Multiplayer, alliances and chat', tags: ['MULTIPLAYER', 'DIPLOMACY', 'CHAT'],
    items: [
      '멀티 플레이: 입장 코드로 친구를 불러 함께 겨룹니다. (사람과 AI 합쳐 8나라까지)',
      '대화: 게임 중에 말을 주고받고, 빠른 대화로 짧게 알립니다.',
      '동맹과 외교: 다른 나라와 손을 잡거나 등을 돌릴 수 있습니다.',
      '새 지형: 어장과 눈 덮인 숲.',
      '튜토리얼: 처음 하는 사람도 단계별로 조작을 익힙니다.',
    ],
  },
  {
    version: '0.2', date: '2026-11-22', image: '/patch/0.2.webp', focus: 0.3, accent: [120, 220, 230],
    title: 'INTO THE WILD', sub: 'Horses, tortoises and the ice dragon', tags: ['HORSES', 'TORTOISE', 'ICE DRAGON', 'FIRE TOWER'],
    items: [
      '야생말: 초원의 말을 길들여 기병이 됩니다.',
      '바위거북: 사막의 거북에게 먹이를 주면 함께 싸우는 든든한 동료가 됩니다.',
      '얼음 드래곤: 설원 둥지의 드래곤을 쓰러뜨려 길들이면 하늘을 나는 용기사가 됩니다.',
      '화염탑: 넓은 범위에 불을 뿜는 방어 건물. (유황 필요)',
    ],
  },
  {
    version: '0.1', date: '2026-11-21', image: '/patch/0.1.webp', accent: [255, 214, 120],
    title: 'FIRST LIGHT', sub: 'Grow a nation in living nature', tags: ['REAL-TIME STRATEGY', 'MOBILE'],
    items: [
      '첫 공개: 자연 속에서 나라를 키우는 실시간 전략 게임 Pixel Territory.',
      '모바일: 손가락 조작과 앱 설치를 지원합니다.',
    ],
  },
];

export const LATEST = PATCHES[0].version;
const COOKIE = 'pt_patch_seen';

/** '2026-11-27' → '2026년 11월 27일'. */
export const dateLabel = (d: string) => { const [y, m, day] = d.split('-').map(Number); return `${y}년 ${m}월 ${day}일`; };

/** 그만보기로 기억한 버전 (없으면 ''). */
export function seenVersion(): string {
  try { return document.cookie.split('; ').find((c) => c.startsWith(COOKIE + '='))?.slice(COOKIE.length + 1) ?? ''; } catch { return ''; }
}

/** 그만보기: 지금 최신 버전을 1년 동안 기억한다 (on=false면 지운다). */
export function rememberSeen(on: boolean) {
  try {
    document.cookie = on ? `${COOKIE}=${encodeURIComponent(LATEST)}; max-age=${365 * 86400}; path=/; SameSite=Lax`
      : `${COOKIE}=; max-age=0; path=/; SameSite=Lax`;
  } catch { /* 쿠키를 못 쓰면 다음에도 보인다 */ }
}

/** 보여 줄까: 그만본 버전이 최신이 아니면. */
export const shouldShowPatch = () => decodeURIComponent(seenVersion()) !== LATEST;
