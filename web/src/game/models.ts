// 유닛·건물·배·동물의 복셀 모델 (sim/rules.py 번호 순서). 모두 앞이 +x (유닛·배·동물: 가는 방향으로 돌린다),
// 건물은 앞(문, 부두)이 +y(화면 아래)다.
// 크기 기준: 한 칸 = 그림 한 점, 화면 배율 k = 확대 / 2.4 → 건물 너비 ≈ 2r × 2.4 점.

import { Mat, Vol } from './voxel.ts';

const hash = (x: number, y: number, z: number) => {
  let h = (x * 374761393 + y * 668265263 + z * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};

// ------------------------------------------------------------- 사람
/** 서 있는 사람: 앞뒤 x0..x0+1, 몸 너비 3 (가운데 yc), 발 z0. frame: 0 서기, 1 걷기 (다리를 앞뒤로). */
function person(v: Vol, x0: number, yc: number, z0: number, frame: number, hat: 'helmet' | 'hood') {
  for (const [y, fwd] of [[yc - 1, 1], [yc + 1, -1]]) {                // 다리
    if (frame) { v.box(x0 + fwd, y, z0, x0 + 1 + fwd, y, z0, Mat.LEATHER, -1); v.box(x0, y, z0 + 1, x0 + 1, y, z0 + 1, Mat.LEATHER, -1); }
    else v.box(x0, y, z0, x0 + 1, y, z0 + 1, Mat.LEATHER, -1);
  }
  v.box(x0, yc - 1, z0 + 2, x0 + 1, yc + 1, z0 + 2, Mat.LEATHER);       // 허리
  v.box(x0, yc - 1, z0 + 3, x0 + 1, yc + 1, z0 + 5, Mat.CLOTH);         // 몸통 (나라 색)
  for (const y of [yc - 2, yc + 2]) {                                    // 팔
    v.set(x0 + 1, y, z0 + 3, Mat.SKIN);
    v.box(x0 + 1, y, z0 + 4, x0 + 1, y, z0 + 5, Mat.CLOTH, -1);
  }
  v.box(x0, yc - 1, z0 + 6, x0 + 1, yc + 1, z0 + 7, Mat.SKIN);          // 머리
  v.set(x0 + 1, yc, z0 + 6, Mat.SKIN, -1);
  if (hat === 'helmet') {
    v.box(x0, yc - 1, z0 + 8, x0 + 1, yc + 1, z0 + 8, Mat.METAL, 1);
    v.box(x0, yc - 1, z0 + 7, x0, yc + 1, z0 + 7, Mat.METAL);
  } else {
    v.box(x0, yc - 1, z0 + 8, x0 + 1, yc + 1, z0 + 8, Mat.CLOTH, -1);
    v.box(x0, yc - 1, z0 + 6, x0, yc + 1, z0 + 7, Mat.CLOTH, -1);
  }
}

function infantry(frame: number): Vol {
  const v = new Vol(11, 7, 11);
  person(v, 4, 3, 0, frame, 'helmet');
  v.box(6, 5, 3, 6, 5, 6, Mat.WOOD);                                   // 몽둥이
  v.box(6, 5, 7, 6, 5, 8, Mat.WOOD_D, 1); v.set(7, 5, 8, Mat.WOOD_D);
  v.box(6, 0, 2, 6, 2, 5, Mat.CLOTH, 1);                               // 방패 (나라 색)
  v.box(6, 1, 3, 6, 1, 4, Mat.METAL, 1);
  return v;
}

function archer(frame: number): Vol {
  const v = new Vol(11, 7, 11);
  person(v, 4, 3, 0, frame, 'hood');
  for (const [x, z] of [[6, 2], [7, 3], [7, 4], [7, 5], [7, 6], [6, 7]]) v.set(x, 1, z, Mat.WOOD_D, 1);   // 활
  v.box(6, 1, 3, 6, 1, 6, Mat.SAIL, 1);                                // 시위
  v.box(3, 4, 3, 3, 4, 6, Mat.LEATHER);                                // 화살통
  v.set(3, 4, 7, Mat.WOOD, 1); v.set(3, 3, 7, Mat.SAIL);
  return v;
}

/** 유황 척탄병: 머리에 천을 두르고 (나라 색), 등에 유황 단지 꾸러미, 손에 불붙인 단지. frame 2: 단지를 머리 위로 들어 던진다. */
function grenadier(frame: number): Vol {
  const v = new Vol(11, 7, 12);
  person(v, 4, 3, 0, frame === 1 ? 1 : 0, 'hood');
  v.box(3, 4, 4, 3, 5, 6, Mat.LEATHER);                                // 등 꾸러미
  v.set(2, 4, 5, Mat.TILE); v.set(2, 5, 6, Mat.TILE); v.set(2, 4, 7, Mat.TILE, 1);   // 단지들
  v.set(2, 5, 5, Mat.SULFUR, 1);
  if (frame === 2) {                                                   // 던지기: 팔을 들고 단지를 머리 위로
    v.box(5, 5, 6, 5, 5, 8, Mat.CLOTH, -1);
    v.box(5, 5, 9, 6, 5, 10, Mat.TILE); v.set(6, 5, 11, Mat.SULFUR, 1); v.set(6, 6, 11, Mat.GLOW);
  } else {                                                             // 손에 든 단지와 심지 불
    v.box(6, 5, 3, 6, 5, 4, Mat.TILE); v.set(7, 5, 4, Mat.TILE, -1);
    v.set(6, 5, 5, Mat.SULFUR, 1); v.set(6, 5, 6, Mat.GLOW);
  }
  return v;
}

// ------------------------------------------------------------- 말
/** 말 (앞이 +x, 몸 너비 3: y 2..4). frame: 0 서기, 1 달리기, 2 풀 뜯기, 3 앞발 들기. */
function horseBody(v: Vol, frame: number, m: Mat = Mat.HORSE) {
  const legs = (pts: [number, number][]) => {
    for (const [x, y] of pts) { v.box(x, y, 1, x, y, 2, m, -1); v.set(x, y, 0, Mat.HORSE_D); }
  };
  if (frame === 3) {                                                    // 뒷다리로 서서 앞을 든다
    legs([[4, 2], [4, 4]]);
    v.box(4, 2, 3, 6, 4, 4, m); v.box(7, 2, 4, 8, 4, 5, m); v.box(9, 2, 5, 10, 4, 6, m);
    v.box(10, 2, 7, 11, 4, 8, m); v.box(11, 2, 9, 12, 4, 9, m, 1); v.set(13, 3, 9, Mat.HORSE_D);
    v.set(10, 3, 9, Mat.HORSE_D); v.set(12, 2, 10, m); v.set(12, 4, 10, m);
    v.box(11, 2, 5, 11, 2, 6, m, -1); v.box(12, 4, 5, 12, 4, 6, m, -1); v.set(12, 2, 4, Mat.HORSE_D); v.set(13, 4, 4, Mat.HORSE_D);
    v.box(3, 3, 3, 3, 3, 4, Mat.HORSE_D); v.set(2, 3, 2, Mat.HORSE_D);
    return;
  }
  legs(frame === 1 ? [[11, 2], [9, 4], [5, 2], [3, 4]] : [[10, 2], [10, 4], [4, 2], [4, 4]]);
  v.box(4, 2, 3, 10, 4, 4, m);                                          // 몸
  v.box(5, 2, 5, 9, 4, 5, m, 1);                                        // 등
  if (frame === 2) {                                                    // 고개 숙여 풀 뜯기
    v.box(11, 2, 3, 11, 4, 4, m); v.box(12, 2, 1, 12, 4, 2, m, 1); v.set(13, 3, 1, Mat.HORSE_D);
    v.set(11, 3, 5, Mat.HORSE_D);
  } else {
    v.box(10, 2, 5, 11, 4, 6, m); v.box(11, 2, 7, 12, 4, 7, m, 1); v.set(13, 3, 7, Mat.HORSE_D); v.set(13, 3, 6, Mat.HORSE_D);
    v.set(10, 3, 7, Mat.HORSE_D); v.set(9, 3, 6, Mat.HORSE_D);         // 갈기
    v.set(12, 2, 8, m); v.set(12, 4, 8, m);                             // 귀
  }
  v.box(3, 3, 3, 3, 3, 4, Mat.HORSE_D); v.set(2, 3, 2, Mat.HORSE_D);   // 꼬리
}

function horse(frame: number): Vol {
  const v = new Vol(15, 7, 12);
  horseBody(v, frame);
  return v;
}

/** 순록 (앞이 +x, 몸 너비 3: y 2..4, 말보다 조금 작고 다부지다). frame: 0 서기, 1 걷기, 2 풀 뜯기.
 *  회갈색 털, 크림빛 목털·엉덩이·발목, 짙은 발굽과 코, 머리 위로 뒤로 휘었다 앞으로 갈래진 뿔 (양쪽 2칸 두께: 돌려 그려도 남게). */
function reindeer(frame: number): Vol {
  const v = new Vol(15, 7, 14), m = Mat.REINDEER, W = Mat.REINDEER_W, D = Mat.HORSE_D, A = Mat.ANTLER;
  const legs = frame === 1 ? [[10, 2], [8, 4], [5, 2], [3, 4]] : [[9, 2], [9, 4], [4, 2], [4, 4]];
  for (const [x, y] of legs) { v.set(x, y, 0, D); v.set(x, y, 1, W, -1); v.set(x, y, 2, m, -1); }   // 발굽, 흰 발목, 다리
  v.box(4, 2, 3, 9, 4, 4, m);                                           // 몸
  v.box(5, 2, 5, 8, 4, 5, m, 1);                                        // 등
  v.box(3, 2, 3, 3, 4, 4, W); v.set(2, 3, 4, W, 1);                     // 흰 엉덩이, 짧은 꼬리
  const antler = (x: number, z: number) => {                           // 뿔 한 쌍: (x, z)는 머리 꼭대기. 위로 오르며 양옆으로 벌어진다 (위에서 보면 넓은 U)
    for (const s of [-1, 1]) {
      const y1 = 3 + s, y2 = 3 + 2 * s, y3 = 3 + 3 * s;
      v.set(x, y1, z, A); v.set(x - 1, y1, z, A);                       // 뿌리 (앞뒤 2칸: 돌려 그려도 남게)
      v.box(x - 1, y2, z + 1, x, y2, z + 2, A);                         // 뒤로 기울며 오르는 줄기
      v.set(x + 1, y2, z + 1, A, 1);                                    // 이마 위로 뻗는 갈래
      v.box(x - 1, y3, z + 3, x, y3, z + 3, A, 1);                      // 벌어진 위쪽
      v.set(x + 1, y3, z + 4, A, 1); v.set(x - 2, y3, z + 4, A, 1);     // 앞뒤 끝 갈래
    }
  };
  if (frame === 2) {                                                    // 고개 숙여 이끼를 뜯는다
    v.box(10, 2, 3, 10, 4, 4, m); v.box(11, 2, 2, 11, 4, 3, W);         // 목, 목털
    v.box(12, 2, 1, 12, 4, 2, m, 1); v.set(13, 3, 1, D);                // 머리, 코
    antler(12, 3);
  } else {
    v.box(10, 2, 4, 10, 4, 6, m); v.box(11, 2, 4, 11, 4, 5, W, 1);      // 목, 늘어진 흰 목털
    v.box(11, 2, 6, 12, 4, 7, m, 1); v.set(13, 3, 6, D);                // 머리, 코
    v.set(12, 2, 8, m); v.set(12, 4, 8, m);                             // 귀
    antler(11, 8);
  }
  return v;
}

/** 말 탄 사람 (몸 x 7..8, 너비 3). */
function rider(v: Vol, hat: 'helmet' | 'hood') {
  v.box(6, 2, 5, 9, 4, 5, Mat.CLOTH, -1);                               // 안장 깔개 (나라 색)
  v.box(7, 1, 3, 7, 1, 4, Mat.LEATHER, -1); v.box(7, 5, 3, 7, 5, 4, Mat.LEATHER, -1);   // 다리
  v.box(7, 2, 6, 8, 4, 7, Mat.CLOTH);                                   // 몸통
  v.set(8, 1, 6, Mat.SKIN); v.set(8, 1, 7, Mat.CLOTH, -1); v.set(8, 5, 6, Mat.SKIN); v.set(8, 5, 7, Mat.CLOTH, -1);
  v.box(7, 2, 8, 8, 4, 9, Mat.SKIN);
  if (hat === 'helmet') { v.box(7, 2, 10, 8, 4, 10, Mat.METAL, 1); v.box(7, 2, 9, 7, 4, 9, Mat.METAL); }
  else { v.box(7, 2, 10, 8, 4, 10, Mat.CLOTH, -1); v.box(7, 2, 8, 7, 4, 9, Mat.CLOTH, -1); }
}

function lancer(frame: number): Vol {
  const v = new Vol(15, 7, 12);
  horseBody(v, frame);
  rider(v, 'helmet');
  for (let x = 5; x <= 13; x++) v.set(x, 5, 8, Mat.WOOD, x === 13 ? 1 : 0);   // 창 (옆구리에 끼고 앞으로)
  v.set(14, 5, 8, Mat.METAL, 1);
  v.set(12, 5, 9, Mat.CLOTH, 1); v.set(11, 5, 9, Mat.CLOTH);            // 창 깃발
  return v;
}

function horseArcher(frame: number): Vol {
  const v = new Vol(15, 7, 12);
  horseBody(v, frame);
  rider(v, 'hood');
  for (const [x, z] of [[10, 6], [11, 7], [11, 8], [11, 9], [10, 10]]) v.set(x, 1, z, Mat.WOOD_D, 1);
  v.box(10, 1, 7, 10, 1, 9, Mat.SAIL, 1);
  v.box(6, 3, 6, 6, 3, 8, Mat.LEATHER); v.set(6, 3, 9, Mat.WOOD, 1);
  return v;
}

/** 척탄기마병: 말 위의 척탄병 (등에 단지 꾸러미, 손에 불붙인 단지). frame 0~3 말, 4: 단지를 머리 위로 들어 던진다. */
function horseGrenadier(frame: number): Vol {
  const v = new Vol(15, 7, 13);
  horseBody(v, frame === 4 ? 1 : frame);
  rider(v, 'hood');
  v.box(6, 3, 6, 6, 4, 8, Mat.LEATHER);                                // 등 꾸러미
  v.set(5, 3, 7, Mat.TILE); v.set(5, 4, 8, Mat.TILE, 1); v.set(5, 4, 7, Mat.SULFUR, 1);
  if (frame === 4) {                                                   // 던지기: 팔을 들고 단지를 머리 위로
    v.box(8, 5, 8, 8, 5, 10, Mat.CLOTH, -1);
    v.box(8, 5, 11, 9, 5, 12, Mat.TILE); v.set(9, 6, 12, Mat.GLOW);
  } else {
    v.box(9, 5, 6, 9, 5, 7, Mat.TILE); v.set(9, 5, 8, Mat.SULFUR, 1); v.set(10, 5, 8, Mat.GLOW);
  }
  return v;
}

// ------------------------------------------------------------- 건물 (앞이 +y)
function flag(v: Vol, x: number, y: number, z0: number, h: number, dir = -1) {
  v.box(x, y, z0, x, y, z0 + h, Mat.WOOD_D);
  v.box(Math.min(x + dir, x + dir * 3), y, z0 + h - 2, Math.max(x + dir, x + dir * 3), y, z0 + h, Mat.CLOTH);
  v.set(x + dir * 3, y, z0 + h - 2, Mat.EMPTY);
}

function timberWalls(v: Vol, x0: number, y0: number, x1: number, y1: number, z0: number, z1: number) {
  v.walls(x0, y0, z0, x1, y1, z1, Mat.PLASTER);
  for (let z = z0; z <= z1; z++) {                                      // 기둥
    for (const x of [x0, x1]) for (const y of [y0, y1]) v.set(x, y, z, Mat.WOOD_D);
    for (let x = x0 + 4; x < x1; x += 4) { v.set(x, y0, z, Mat.WOOD_D); v.set(x, y1, z, Mat.WOOD_D); }
  }
  for (let x = x0; x <= x1; x++) { v.set(x, y0, z1, Mat.WOOD_D); v.set(x, y1, z1, Mat.WOOD_D); }
  for (let y = y0; y <= y1; y++) { v.set(x0, y, z1, Mat.WOOD_D); v.set(x1, y, z1, Mat.WOOD_D); }
}

function hall(): Vol {
  const v = new Vol(24, 20, 20);
  for (let y = 3; y <= 17; y++) for (let x = 2; x <= 21; x++) v.box(x, y, 0, x, y, 1, Mat.STONE, hash(x, y, 1) < 0.3 ? -1 : 0);
  timberWalls(v, 3, 4, 20, 16, 2, 7);
  v.box(11, 16, 2, 12, 16, 4, Mat.DARK);                                // 문
  v.box(10, 16, 5, 13, 16, 5, Mat.WOOD_D);
  for (const x of [6, 16]) v.box(x, 16, 4, x + 1, 16, 5, Mat.DARK);    // 창
  for (const y of [8, 12]) { v.box(3, y, 4, 3, y + 1, 5, Mat.DARK); v.box(20, y, 4, 20, y + 1, 5, Mat.DARK); }
  v.gable(2, 2, 21, 18, 8, Mat.ROOF, true);
  v.box(16, 7, 8, 17, 8, 16, Mat.STONE);                                // 굴뚝
  v.box(10, 17, 2, 13, 18, 2, Mat.STONE, 1);                            // 문 앞 계단
  flag(v, 20, 10, 14, 5);
  return v;
}

function farm(): Vol {
  const v = new Vol(20, 20, 12);
  for (let y = 9; y <= 18; y++) for (let x = 2; x <= 17; x++) {         // 밭: 이랑과 고랑
    if (y % 2) { v.set(x, y, 0, Mat.CROP, -1); if (hash(x, y, 3) < 0.75) v.set(x, y, 1, Mat.CROP, hash(x, y, 4) < 0.4 ? 1 : 0); }
    else v.set(x, y, 0, Mat.WOOD, -1);
  }
  for (let x = 1; x <= 18; x += 3) { v.box(x, 8, 0, x, 8, 2, Mat.WOOD_D); v.box(x, 19, 0, x, 19, 2, Mat.WOOD_D); }   // 울타리
  for (let x = 1; x <= 18; x++) { v.set(x, 8, 1, Mat.WOOD); v.set(x, 19, 1, Mat.WOOD); }
  for (let y = 8; y <= 19; y += 3) { v.box(1, y, 0, 1, y, 2, Mat.WOOD_D); v.box(18, y, 0, 18, y, 2, Mat.WOOD_D); }
  for (let y = 8; y <= 19; y++) { v.set(1, y, 1, Mat.WOOD); v.set(18, y, 1, Mat.WOOD); }
  timberWalls(v, 3, 2, 10, 6, 0, 3);                                    // 오두막
  v.box(6, 6, 0, 7, 6, 2, Mat.DARK);
  v.gable(2, 1, 11, 7, 4, Mat.THATCH, true);
  v.cyl(14.5, 4.5, 2.4, 0, 2, Mat.THATCH);                              // 짚더미
  v.cone(14.5, 4.5, 2.4, 3, 3, Mat.THATCH, 1);
  flag(v, 11, 6, 0, 8);
  return v;
}

function lumber(): Vol {
  const v = new Vol(20, 20, 14);
  for (let z = 0; z <= 4; z++) {                                        // 통나무집
    const b = z % 2 ? 0 : -1;
    for (let x = 3; x <= 11; x++) { v.set(x, 3, z, Mat.WOOD, b); v.set(x, 10, z, Mat.WOOD, b); }
    for (let y = 3; y <= 10; y++) { v.set(3, y, z, Mat.WOOD, b + 1); v.set(11, y, z, Mat.WOOD, b + 1); }
  }
  v.box(6, 10, 0, 7, 10, 2, Mat.DARK);
  v.gable(2, 2, 12, 11, 5, Mat.ROOF, true);
  for (const [y, z] of [[13, 0], [15, 0], [17, 0], [14, 1], [16, 1], [15, 2]]) v.log(4, 14, y, z);   // 통나무 더미
  v.cyl(16, 6, 1.6, 0, 1, Mat.WOOD, 1);                                 // 그루터기와 도끼
  v.box(16, 6, 2, 17, 6, 2, Mat.METAL, 1); v.set(15, 6, 2, Mat.WOOD_D);
  flag(v, 12, 10, 0, 9);
  return v;
}

function quarry(): Vol {
  const v = new Vol(20, 20, 16);
  for (let i = 0; i < 40; i++) {                                         // 깬 돌 부스러기
    const x = 2 + Math.floor(hash(i, 1, 9) * 16), y = 9 + Math.floor(hash(i, 2, 9) * 10);
    v.set(x, y, 0, Mat.STONE, hash(i, 3, 9) < 0.5 ? -1 : 1);
  }
  v.box(3, 12, 0, 6, 15, 3, Mat.STONE); v.box(4, 12, 4, 6, 14, 5, Mat.STONE, 1);   // 쌓은 돌덩이
  v.box(8, 14, 0, 10, 16, 2, Mat.STONE, -1); v.box(11, 15, 0, 12, 17, 1, Mat.STONE);
  for (let z = 0; z <= 11; z++) {                                        // 기중기 (A자 다리 둘)
    const t = z / 11;
    v.set(Math.round(12 + 3 * t), 6, z, Mat.WOOD_D); v.set(Math.round(18 - 3 * t), 6, z, Mat.WOOD_D);
  }
  for (let y = 6; y <= 12; y++) v.set(15, y, 11 - Math.round((y - 6) * 0.3), Mat.WOOD);
  v.box(15, 12, 5, 15, 12, 8, Mat.DARK);                                 // 밧줄과 매단 돌
  v.box(14, 12, 3, 16, 13, 4, Mat.STONE, 1);
  v.walls(2, 2, 0, 8, 7, 3, Mat.WOOD); v.box(4, 7, 0, 5, 7, 2, Mat.DARK);   // 창고
  v.gable(1, 1, 9, 8, 4, Mat.ROOF, true);
  flag(v, 9, 7, 0, 8);
  return v;
}

function tower(): Vol {
  const v = new Vol(10, 10, 26);
  for (let z = 0; z <= 14; z++) for (let y = 2; y <= 7; y++) for (let x = 2; x <= 7; x++) {
    if (x === 2 || x === 7 || y === 2 || y === 7) v.set(x, y, z, Mat.STONE, (z % 3 === 0) ? -1 : hash(x, y, z) < 0.2 ? 1 : 0);
  }
  v.box(4, 7, 7, 5, 7, 9, Mat.DARK);                                     // 활 쏘는 구멍
  v.box(4, 7, 1, 5, 7, 3, Mat.DARK);
  v.box(1, 1, 15, 8, 8, 15, Mat.WOOD_D);                                  // 망대 바닥
  for (const [x, y] of [[1, 1], [8, 1], [1, 8], [8, 8], [4, 1], [1, 4], [8, 5], [5, 8]]) v.box(x, y, 16, x, y, 17, Mat.WOOD);
  v.cone(5, 5, 5.2, 18, 6, Mat.ROOF);
  v.box(5, 5, 24, 5, 5, 25, Mat.WOOD_D);
  return v;
}

function harbor(): Vol {
  const v = new Vol(20, 24, 14);
  timberWalls(v, 3, 2, 12, 8, 0, 4);                                     // 창고
  v.box(7, 8, 0, 8, 8, 2, Mat.DARK);
  v.gable(2, 1, 13, 9, 5, Mat.ROOF, true);
  for (let y = 9; y <= 23; y++) for (let x = 8; x <= 12; x++) v.set(x, y, 0, Mat.WOOD, y % 2 ? 0 : -1);   // 부두 (바다 쪽 +y)
  for (const y of [11, 16, 21]) { v.box(8, y, 0, 8, y, 1, Mat.WOOD_D, 1); v.box(12, y, 0, 12, y, 1, Mat.WOOD_D, 1); }
  v.box(9, 12, 1, 10, 13, 2, Mat.WOOD_D); v.box(11, 18, 1, 11, 18, 1, Mat.WOOD_D);   // 상자
  v.box(15, 10, 0, 15, 10, 10, Mat.WOOD_D);                              // 기중기
  for (let y = 10; y <= 15; y++) v.set(15, y, 10, Mat.WOOD);
  v.box(15, 15, 5, 15, 15, 9, Mat.DARK); v.box(15, 15, 3, 16, 15, 4, Mat.WOOD_D, 1);
  flag(v, 3, 9, 0, 9, 1);
  return v;
}


/** 유황 채취장: 노랗게 끓는 유황 웅덩이 위의 나무 도르래 틀, 둘레의 유황 결정, 쌓은 자루. */
function sulfurPit(): Vol {
  const v = new Vol(20, 20, 13);
  for (let y = 4; y <= 15; y++) for (let x = 4; x <= 15; x++) {          // 웅덩이 (가장자리는 굳은 껍질)
    const d = Math.hypot(x + 0.5 - 10, (y + 0.5 - 10) * 1.1) + hash(x, y, 21) * 1.2;
    if (d < 4.6) v.set(x, y, 0, Mat.SULFUR, hash(x, y, 22) < 0.3 ? 1 : 0);
    else if (d < 6.2) v.set(x, y, 0, Mat.SULFUR, -2);
  }
  for (const [x, y, h] of [[4, 5, 3], [15, 4, 2], [16, 13, 3], [5, 15, 2], [11, 3, 2]]) {   // 유황 결정
    for (let z = 0; z < h; z++) v.set(x, y, z, Mat.SULFUR, z === h - 1 ? 2 : 1);
    v.set(x + 1, y, 0, Mat.SULFUR, 1);
  }
  for (const [x, y] of [[6, 6], [13, 6], [6, 13], [13, 13]]) v.box(x, y, 0, x, y, 7, Mat.WOOD_D);   // 도르래 틀
  for (let x = 6; x <= 13; x++) { v.set(x, 6, 8, Mat.WOOD, 1); v.set(x, 13, 8, Mat.WOOD, 1); }
  for (let y = 6; y <= 13; y++) v.set(9, y, 9, Mat.WOOD_D, 1);
  v.box(9, 9, 3, 9, 9, 8, Mat.DARK);                                      // 밧줄과 두레박
  v.box(9, 9, 1, 10, 10, 2, Mat.WOOD_D, 1);
  for (const [x, y, z] of [[16, 8, 0], [17, 9, 0], [16, 10, 0], [17, 8, 1]]) v.box(x, y, z, x, y, z, Mat.SAIL, z ? 1 : 0);   // 자루
  flag(v, 3, 10, 0, 8);
  return v;
}

/** 화염탑: 검은 띠를 두른 돌탑, 꼭대기의 쇠 화로와 앞을 보는 용머리 분사구, 옆에 늘어뜨린 나라 깃발. */
function fireTower(): Vol {
  const v = new Vol(12, 12, 24);
  for (let z = 0; z <= 15; z++) {                                         // 위로 조금 좁아지는 팔각 돌탑
    const r = 4.6 - z * 0.08;
    for (let y = 0; y < 12; y++) for (let x = 0; x < 12; x++) {
      const dx = Math.abs(x + 0.5 - 6), dy = Math.abs(y + 0.5 - 6);
      if (Math.max(dx, dy) > r || dx + dy > r * 1.4) continue;
      const band = z % 5 === 4;
      v.set(x, y, z, band ? Mat.BASALT : Mat.STONE, band ? 0 : hash(x, y, z) < 0.25 ? -1 : 0);
    }
  }
  v.box(5, 10, 3, 6, 10, 5, Mat.DARK);                                    // 문
  for (let z = 16; z <= 18; z++) for (let y = 1; y <= 10; y++) for (let x = 1; x <= 10; x++) {   // 쇠 화로
    const d = Math.hypot(x + 0.5 - 6, y + 0.5 - 6);
    if (d <= 5 && (d > 3.8 || z === 16)) v.set(x, y, z, Mat.METAL, z === 18 ? 1 : 0);
    else if (d <= 3.8 && z === 17) v.set(x, y, z, Mat.GOLD, 2);          // 화로 속 불씨
  }
  for (let k = 0; k <= 3; k++) v.box(5, 10 + Math.min(k, 1), 17 + (k > 1 ? 1 : 0), 6, 10 + Math.min(k, 1), 17 + (k > 1 ? 1 : 0), Mat.METAL, 1);   // 용머리 분사구
  v.box(5, 11, 17, 6, 11, 18, Mat.METAL, 1); v.set(5, 11, 19, Mat.METAL, 2); v.set(6, 11, 19, Mat.METAL, 2);
  v.box(5, 11, 16, 6, 11, 16, Mat.DARK);
  v.box(10, 6, 9, 10, 6, 14, Mat.CLOTH, 1); v.box(10, 7, 10, 10, 7, 14, Mat.CLOTH);   // 나라 깃발
  return v;
}

// ------------------------------------------------------------- 배 (앞이 +x)
function ferry(): Vol {
  const v = new Vol(12, 6, 8);
  v.box(2, 2, 0, 9, 3, 0, Mat.WOOD_D);
  v.box(1, 1, 1, 10, 4, 1, Mat.WOOD, -1);
  v.walls(1, 1, 2, 10, 4, 2, Mat.WOOD, 1);
  v.box(11, 2, 1, 11, 3, 2, Mat.WOOD, 1);
  v.box(6, 2, 2, 6, 2, 7, Mat.WOOD_D);
  v.box(6, 0, 4, 6, 5, 6, Mat.CLOTH);
  return v;
}

function warship(): Vol {
  const v = new Vol(22, 8, 16);
  v.box(3, 3, 0, 18, 4, 0, Mat.WOOD_D);
  v.box(2, 2, 1, 19, 5, 1, Mat.WOOD_D);
  v.box(1, 1, 2, 20, 6, 2, Mat.WOOD, -1);
  v.walls(1, 1, 3, 20, 6, 3, Mat.WOOD, 1);
  v.box(21, 3, 2, 21, 4, 4, Mat.WOOD, 1);                                // 이물
  v.box(1, 1, 4, 4, 6, 4, Mat.WOOD); v.walls(1, 1, 5, 4, 6, 5, Mat.WOOD_D);   // 고물 망대
  v.box(11, 3, 3, 11, 3, 15, Mat.WOOD_D);                                // 큰 돛대
  v.box(11, 0, 7, 11, 7, 13, Mat.CLOTH); v.box(11, 0, 10, 11, 7, 10, Mat.SAIL);
  v.box(16, 3, 3, 16, 3, 11, Mat.WOOD_D);
  v.box(16, 1, 7, 16, 6, 10, Mat.CLOTH);
  for (const x of [6, 9, 14]) { v.set(x, 0, 2, Mat.WOOD_D); v.set(x, 7, 2, Mat.WOOD_D); }   // 노
  for (const x of [7, 10, 13, 18]) { v.set(x, 0, 3, Mat.METAL); v.set(x, 7, 3, Mat.METAL); }   // 양옆 포문의 대포 (옆으로 돌아 쏜다)
  return v;
}

function torch(): Vol {
  const v = new Vol(2, 2, 6);
  v.box(0, 0, 0, 0, 0, 3, Mat.WOOD_D);
  v.set(0, 0, 4, Mat.METAL, 1);
  return v;
}


// ------------------------------------------------------------- 서리 드래곤 (사나운 야생 동물, 용기사)
// 크고 각진 서리 드래곤: 팔각 단면의 몸통, S자로 솟은 목, 쐐기형 머리와 뒤로 휜 뿔, 목에서 꼬리까지 얼음 가시,
// 줄진 배 비늘, 손가락뼈가 있는 날개막(뒷전이 물결), 굵은 다리와 발톱, 끝이 부채꼴 가시인 꼬리.
// frame: 0 서기 (날개 반쯤 들고 접음), 1 날갯짓 위, 2 날갯짓 아래, 3 잠 (몸을 맒), 4 쓰러짐,
//        5 서서 숨결 (날개를 펴고 목을 앞으로 내밀어 입을 크게 벌린다), 6 날며 숨결, 7·8 걷기 (다리를 엇갈린다).
const DCY = 30;                     // 몸 가운데 y

/** 각진 덩어리: 가운데 (cx, cy, cz), 반지름 r (z는 rz배). 팔각으로 깎는다. */
function chunk(v: Vol, cx: number, cy: number, cz: number, r: number, m: Mat, b = 0, rz = 1, belly = -2) {
  for (let z = Math.floor(cz - r * rz); z <= Math.ceil(cz + r * rz); z++) {
    for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
      const dx = Math.abs(x + 0.5 - cx), dy = Math.abs(y + 0.5 - cy), dz = Math.abs(z + 0.5 - cz) / rz;
      if (Math.max(dx, dy, dz) > r || dx + dy + dz > r * 1.55) continue;
      const under = (z + 0.5 - cz) / (r * rz) < belly;
      v.set(x, y, z, under ? Mat.MEMBRANE : m, under ? (x % 2 ? 1 : -1) : b + (hash(x, y, z) < 0.25 ? -1 : hash(x, y, z) > 0.85 ? 1 : 0));
    }
  }
}

/** 두 점 사이를 덩어리로 잇는다 (반지름 r0 → r1). */
function limb(v: Vol, p: number[], q: number[], r0: number, r1: number, m: Mat, b = 0, belly = -2) {
  const n = Math.max(1, Math.ceil(Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]) * 2));
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    chunk(v, p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t, r0 + (r1 - r0) * t, m, b, 1, belly);
  }
}

/** 가시 하나: 밑 (x, y, z)에서 (dx, dy, dz) 쪽으로 len만큼 (얼음빛). */
function spike(v: Vol, x: number, y: number, z: number, dx: number, dy: number, dz: number, len: number, m: Mat = Mat.WING) {
  for (let k = 0; k < len; k++) v.set(x + dx * k, y + dy * k, z + dz * k, m, k === len - 1 ? 2 : 1);
}

/** 날개 하나 (s: -1 왼쪽 / 1 오른쪽). spread: 편 날개 (lift: 바깥으로 갈수록 오르내림), 아니면 반쯤 들어 접은 날개. */
function wing(v: Vol, s: number, sx: number, sz: number, spread: boolean, lift: number, droop = false) {
  const B = Mat.DRAGON, M = Mat.WING;
  if (spread || droop) {
    const zAt = (d: number) => Math.round(sz + Math.max(0, d - 5) * lift);
    const shoulder = [sx, 5], wrist = [sx - 4, 19];
    const tips = [[sx - 1, 29], [sx - 8, 28], [sx - 15, 24], [sx - 19, 16], [sx - 18, 8]];
    const poly = [shoulder, wrist, tips[0]];
    for (let i = 1; i < tips.length; i++) {                          // 뒷전: 손가락 끝 사이가 안으로 파인 물결
      const a = tips[i - 1], c = tips[i];
      poly.push([(a[0] + c[0]) / 2 + 2.5, (a[1] + c[1]) / 2 - 2.5], c);
    }
    poly.push([sx - 16, 4]);
    const inside = (px: number, py: number) => {
      let c = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const [xi, yi] = poly[i], [xj, yj] = poly[j];
        if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) c = !c;
      }
      return c;
    };
    for (let d = 3; d <= 30; d++) for (let x = sx - 26; x <= sx + 2; x++) {
      if (!inside(x + 0.5, d + 0.5)) continue;
      const z = zAt(d), zn = zAt(d + 1);
      for (let zz = Math.min(z, zn); zz <= Math.max(z, zn); zz++) v.set(x, DCY + s * d, zz, M, hash(x, d, 7) < 0.2 ? -1 : 0);
    }
    const bone = (p: number[], q: number[], r: number) => {
      const n = Math.ceil(Math.hypot(q[0] - p[0], q[1] - p[1]) * 2);
      for (let i = 0; i <= n; i++) {
        const t = i / n, x = p[0] + (q[0] - p[0]) * t, d = p[1] + (q[1] - p[1]) * t;
        for (let w = 0; w < r; w++) v.set(x, DCY + s * (d + w * 0.6), zAt(d) + (r > 1 ? 1 : 0), B, w === 0 ? 1 : 0);
      }
    };
    bone(shoulder, wrist, 2);                                          // 팔
    for (const t of tips) bone(wrist, t, 1);                           // 손가락
    spike(v, wrist[0], DCY + s * wrist[1], zAt(wrist[1]) + 1, 1, 0, 1, 3, Mat.PLASTER);   // 날개 발톱
    return;
  }
  // 반쯤 들어 접은 날개: 어깨에서 뒤·위로 팔, 팔과 등 사이에 막 (화면에 넓은 면으로 보이게 거의 세운다)
  const sh = [sx, DCY + s * 5, sz], el = [sx - 7, DCY + s * 9, sz + 10], wr = [sx - 15, DCY + s * 8, sz + 15];
  limb(v, sh, el, 1.4, 1.0, B, 1);
  limb(v, el, wr, 1.0, 0.7, B, 1);
  spike(v, wr[0], wr[1], wr[2], 1, 0, 1, 3, Mat.PLASTER);
  for (let i = 0; i <= 40; i++) for (let j = 0; j <= 40; j++) {        // 막: 팔(어깨→팔꿈치→손목)과 등 사이
    const a = i / 40, c = j / 40;
    if (a + c > 1) continue;
    const p = a < 0.5 ? [sh, el] : [el, wr], f = a < 0.5 ? a * 2 : a * 2 - 1;
    const ax = p[0][0] + (p[1][0] - p[0][0]) * f, ay = p[0][1] + (p[1][1] - p[0][1]) * f, az = p[0][2] + (p[1][2] - p[0][2]) * f;
    const bx = sx - 18, by = DCY + s * 4, bz = sz - 1;                  // 등 뒤쪽 붙는 곳
    const x = ax + (bx - ax) * c, y = ay + (by - ay) * c, z = az + (bz - az) * c;
    v.set(x, y, z, M, hash(Math.round(x), Math.round(y), 3) < 0.2 ? -1 : 0);
  }
}

function dragonBody(v: Vol, frame: number) {
  const S = Mat.DRAGON, Bn = Mat.PLASTER, cy = DCY;
  const fly = frame === 1 || frame === 2 || frame === 6, low = frame === 3 || frame === 4;
  const bz = low ? 6 : fly ? 12 : 13;
  // 몸통: 엉덩이 → 허리 → 가슴 (팔각 덩어리를 이어서)
  const torso: [number, number][] = [[18, 4.4], [22, 4.6], [26, 4.0], [30, 4.8], [34, 5.4], [38, 5.0], [40, 4.4]];
  for (let i = 1; i < torso.length; i++) {
    const [x0, r0] = torso[i - 1], [x1, r1] = torso[i];
    limb(v, [x0, cy, bz], [x1, cy, bz + (x1 > 30 ? 1 : 0)], r0, r1, S, 0, -0.45);
  }
  for (let x = 18; x <= 40; x += 2) spike(v, x, cy, Math.round(bz + 5 + (x > 30 ? 1 : 0)), -0.5, 0, 1, x % 4 ? 2 : 3);   // 등가시
  // 꼬리: 엉덩이에서 뒤로, 좌우로 휘며 가늘어진다. 위로 가시, 끝은 부채꼴
  const tail: number[][] = [];
  for (let k = 0; k <= 12; k++) {
    const t = k / 12, x = 18 - t * 18;
    const sway = frame === 7 ? 0.5 : frame === 8 ? -0.5 : 0;
    const y = cy + (frame === 3 ? t * t * 18 : Math.sin(t * 2.6 + sway) * 5);
    const z = frame === 3 ? 3 : bz - 1 - t * (bz - 3) + (t > 0.8 ? (t - 0.8) * 8 : 0);
    tail.push([x, y, z]);
  }
  for (let k = 1; k < tail.length; k++) {
    const r = 3.4 * (1 - k / 13) + 0.6;
    limb(v, tail[k - 1], tail[k], r + 0.3, r, S, 0, -0.5);
    if (k % 2 === 0 && k < 12) spike(v, tail[k][0], tail[k][1], Math.round(tail[k][2] + r + 0.5), -0.5, 0, 1, 2);
  }
  const tip = tail[tail.length - 1];
  for (const [dy, dz] of [[-1, 0.4], [1, 0.4], [-1, -0.3], [1, -0.3], [0, 1]]) spike(v, tip[0], tip[1], tip[2], -0.6, dy, dz, 4);
  // 목과 머리
  let head: number[];
  if (frame === 3) {                                                   // 잠: 목을 옆으로 둘러 머리를 꼬리 곁 땅에
    const pts = [[40, cy, bz + 1], [44, cy + 6, 5], [40, cy + 13, 4], [32, cy + 16, 3]];
    for (let k = 1; k < pts.length; k++) limb(v, pts[k - 1], pts[k], 3.0 - k * 0.3, 2.8 - k * 0.3, S, 0, -0.4);
    head = [30, cy + 16, 3];
  } else if (frame === 4) {                                            // 쓰러짐: 목을 앞으로 땅에 뻗는다
    limb(v, [40, cy, bz + 1], [50, cy - 2, 4], 3.2, 2.4, S, 0, -0.4);
    head = [52, cy - 2, 4];
  } else {
    const breath = frame === 5 || frame === 6;
    const top = breath ? [52, cy, bz + 7] : [50, cy, bz + 17];          // 숨결: 주둥이가 모델 안에 들어오게 (끝 x 62)
    const mid = breath ? [46, cy, bz + 9] : [47, cy, bz + 9];
    limb(v, [40, cy, bz + 2], mid, 3.4, 2.8, S, 0, -0.2);
    limb(v, mid, top, 2.8, 2.3, S, 0, -0.2);
    for (let k = 0; k <= 4; k++) {                                     // 목 가시
      const t = k / 4, x = 40 + (top[0] - 40) * t, z = bz + 2 + (top[2] - bz - 2) * t;
      spike(v, Math.round(x - 1.5), cy, Math.round(z + 2.8), -0.6, 0, 1, 3);
    }
    head = top;
  }
  const [hx, hy, hz] = head;
  const dir = frame === 3 ? -1 : 1;                                    // 잠들면 머리가 뒤를 본다
  const open = frame === 5 || frame === 6;
  const X = (d: number) => hx + dir * d;
  for (let d = 0; d <= 4; d++) {                                       // 두개골: 쐐기
    const w = 3 - d * 0.3, h = 2.4 - d * 0.2;
    for (let y = Math.round(hy - w); y <= Math.round(hy + w); y++) for (let z = Math.round(hz - h); z <= Math.round(hz + h); z++) v.set(X(d), y, z, S, z >= hz + h - 1 ? 1 : 0);
  }
  for (let d = 5; d <= 10; d++) {                                      // 주둥이: 가늘어진다 (위턱 / 아래턱)
    const w = Math.max(1, 2.2 - (d - 5) * 0.3), gap = open ? Math.round((d - 4) * 0.5) : 0;   // 벌리면 앞으로 갈수록 벌어진다
    for (let y = Math.round(hy - w); y <= Math.round(hy + w); y++) {
      v.set(X(d), y, hz + gap, S, 1);
      v.set(X(d), y, hz - 1 - gap, Mat.MEMBRANE, 0);
    }
    if (open && d <= 8) for (let z = hz - gap; z < hz + gap; z++) v.set(X(d), hy, z, Mat.GLOW, 2);   // 빛나는 목구멍 (서리)
  }
  for (const s of [-1, 1]) {
    v.set(X(3), hy + s * 2, hz + 2, Mat.GLOW, 2);                      // 눈
    v.set(X(4), hy + s * 2, hz + 3, S, 1);                             // 눈썹 능선
    for (let k = 0; k < 8; k++) v.set(X(1 - k * 1.1), hy + s * (2 + k * 0.35), hz + 2 + k * 0.7, Bn, k > 5 ? 2 : 1);   // 뒤로 휜 뿔
    for (let k = 0; k < 4; k++) v.set(X(2 - k), hy + s * (3 + k * 0.6), hz - 1 + k * 0.2, Mat.WING, 1);                 // 볼 가시
    if (open) v.set(X(9), hy + s, hz - 1, Bn, 2);                      // 송곳니
  }
  // 다리 (서 있을 때 / 날 때 접음)
  if (!low) {
    for (const s of [-1, 1]) {
      const front = [37, cy + s * 4.5, bz], hind = [21, cy + s * 4.8, bz - 1];
      if (fly) {
        limb(v, hind, [15, cy + s * 4, bz - 3], 2.8, 1.4, S, -1);
        limb(v, front, [40, cy + s * 4, bz - 4], 2.0, 1.1, S, -1);
        continue;
      }
      // 걷기: 왼쪽 뒷다리와 오른쪽 앞다리가 함께 앞으로 (7), 반대로 (8). 앞으로 내딛는 발은 조금 든다
      const st = frame === 7 ? s : frame === 8 ? -s : frame === 5 ? 0.6 : 0;
      const hf = 23 + st * 4, hu = st > 0.7 ? 2 : 0, ff = 39 - st * 4 + (frame === 5 ? 3 : 0), fu = -st > 0.7 ? 2 : 0;
      chunk(v, hind[0], hind[1], hind[2], 3.4, S, 0);                 // 허벅지
      limb(v, [22, cy + s * 5, bz - 3], [20 + st * 2, cy + s * 5.5, 4 + hu], 2.2, 1.6, S, -1);
      limb(v, [20 + st * 2, cy + s * 5.5, 4 + hu], [hf, cy + s * 5.5, 1 + hu], 1.6, 1.4, S, -1);
      chunk(v, front[0], front[1], front[2], 2.8, S, 0);              // 어깨
      limb(v, [38, cy + s * 5, bz - 2], [ff, cy + s * 5.5, 2 + fu], 1.9, 1.4, S, -1);
      for (const [fx, f, up] of [[hf, hind, hu], [ff, front, fu]] as [number, number[], number][]) {
        for (const dy of [-1, 0, 1]) spike(v, fx + 1, f[1] + dy * 1.2, up, 1, dy * 0.2, 0, 3, Bn);   // 발톱
      }
    }
  } else {
    for (const s of [-1, 1]) { chunk(v, 22, cy + s * 4.5, 3, 2.6, S, -1); chunk(v, 37, cy + s * 4.5, 3, 2.2, S, -1); }
  }
  // 날개
  const lift = frame === 2 ? -0.09 : 0.06;            // 거의 수평 (기울면 계단이 줄무늬로 보인다)
  for (const s of [-1, 1]) {
    if (fly) wing(v, s, 34, bz + 3, true, lift);
    else if (frame === 5) wing(v, s, 34, bz + 4, true, 0.22);         // 숨결: 날개를 펴 들고 버틴다
    else if (frame === 4) wing(v, s, 34, 2, false, 0, true);          // 쓰러짐: 날개를 땅에 늘어뜨린다
    else if (frame === 3) {                                            // 잠: 등에 납작하게 접는다
      limb(v, [34, cy + s * 5, bz + 3], [22, cy + s * 7, bz + 3], 1.2, 0.8, S, 1);
      for (let x = 20; x <= 33; x++) for (let d = 4; d <= 6 + Math.round((x - 20) * 0.1); d++) v.set(x, cy + s * d, bz + 3, Mat.WING, -1);
    } else wing(v, s, 34, bz + 3, false, 0);
  }
}

/** 숨결 자세(5 서서, 6 날며)의 입 자리 (모델 좌표 x, y, z: 벌린 턱 사이). */
export const DRAGON_MOUTH: Record<number, number[]> = { 5: [59, DCY, 20], 6: [59, DCY, 19] };
export const DRAGON_SIZE = [64, 62];
/** 숨결이 닿는 땅: 입에서 앞으로 이만큼 (모델 점). 숨결은 목표가 아니라 입 앞쪽 땅을 향해 내뱉는다. */
export const BREATH_REACH = 16;

function dragon(frame: number): Vol {
  const v = new Vol(64, 62, 36);
  dragonBody(v, frame);
  return v;
}

/** 용기사: 목 뿌리(어깨 위)에 탄 병사와 나라 깃발. */
function dragonRider(frame: number): Vol {
  const v = new Vol(64, 62, 40);
  dragonBody(v, frame);
  const low = frame === 3 || frame === 4, fly = frame === 1 || frame === 2 || frame === 6;
  const z0 = (low ? 6 : fly ? 12 : 13) + 6;
  v.box(35, DCY - 3, z0 - 1, 39, DCY + 3, z0 - 1, Mat.CLOTH, -1);       // 안장 깔개 (나라 색)
  v.box(35, DCY - 2, z0, 35, DCY + 2, z0 + 1, Mat.LEATHER);             // 안장 뒤턱
  person(v, 36, DCY, z0, 0, 'helmet');
  v.box(34, DCY, z0 + 3, 34, DCY, z0 + 14, Mat.WOOD_D);                 // 깃대와 나라 깃발
  v.box(30, DCY, z0 + 10, 33, DCY, z0 + 14, Mat.CLOTH, 1);
  v.set(30, DCY, z0 + 10, Mat.EMPTY);
  return v;
}

/** 드래곤 둥지: 검은 현무암 바위 고리, 두툼한 짚 둥지, 흩어진 뼈, 얼음 결정. */
function lair(): Vol {
  const v = new Vol(74, 74, 16), c = 37;
  for (let y = 0; y < 74; y++) for (let x = 0; x < 74; x++) {
    const d = Math.hypot(x + 0.5 - c, (y + 0.5 - c) / 0.92), n = hash(x, y, 11);
    if (d < 21) v.set(x, y, 0, Mat.STRAW, n < 0.3 ? -1 : n > 0.85 ? 1 : 0);           // 바닥 짚
    else if (d < 28) {                                                                  // 짚 둔덕 (가운데가 높다)
      const h = Math.round(2.6 - Math.abs(d - 24.5) * 0.6 + n * 1.4);
      for (let z = 0; z <= h; z++) v.set(x, y, z, Mat.STRAW, z === h ? (n > 0.6 ? 1 : 0) : -1);
      if (n > 0.93) v.set(x, y, h + 1, Mat.STRAW, 2);                                    // 삐죽 나온 짚
    }
  }
  for (let a = 0; a < 26; a++) {                                                         // 바위 고리
    const t = (a / 26) * Math.PI * 2 + hash(a, 1, 5) * 0.2, r = 30.5 + hash(a, 2, 5) * 3;
    const x = c + Math.cos(t) * r, y = c + Math.sin(t) * r * 0.92, s = 1.6 + hash(a, 3, 5) * 1.8;
    chunk(v, x, y, s * 0.6, s, Mat.BASALT, 0, 0.9, -9);
    if (a % 4 === 1) limb(v, [x, y, 1], [x + (c - x) * 0.08, y + (c - y) * 0.08, 6 + hash(a, 4, 5) * 5], 1.6, 0.6, Mat.BASALT, 1, -9);   // 솟은 바위
  }
  for (const [x, y, h] of [[11, 15, 10], [62, 13, 12], [64, 56, 8], [9, 56, 9], [37, 3, 7], [70, 34, 6]]) {   // 얼음 결정
    for (let z = 0; z < h; z++) {
      const w = Math.max(0, Math.round((h - z) / h * 1.6));
      for (let dy = -w; dy <= w; dy++) for (let dx = -w; dx <= w; dx++) if (Math.abs(dx) + Math.abs(dy) <= w) v.set(x + dx, y + dy, z, Mat.GLOW, z > h - 3 ? 2 : 0);
    }
  }
  for (const [x, y, dx, dy] of [[19, 37, 1, 0.3], [44, 17, 0.4, 1], [50, 46, 1, -0.5], [27, 52, -0.6, 1], [55, 30, 0.2, 1]]) {   // 뼈
    for (let k = 0; k < 6; k++) v.set(x + dx * k, y + dy * k, 1, Mat.PLASTER, k === 0 || k === 5 ? 2 : 1);
  }
  for (const [x, y] of [[20, 24], [54, 52], [58, 22]]) chunk(v, x, y, 1.2, 1.3, Mat.PLASTER, 1, 0.8, -9);     // 해골·알 껍데기
  return v;
}


// ------------------------------------------------------------- 거대 바위거북 (사막, 함께 싸우는 탱커)
// 바위로 된 높은 등껍질: 사암빛 판이 육각으로 갈라지고 이음매는 어둡다. 등마루에는 검은 바위가 솟고, 가장자리는 톱니처럼.
// 굵은 기둥 같은 다리와 뭉툭한 발톱, 부리 같은 입의 묵직한 머리, 짧은 꼬리.
// frame: 0 서기, 1 걷기, 2 껍질 속으로 숨기, 3 발 구르기 (앞발을 들어 올린다), 4 낮은 포효 (고개를 들고 입을 벌린다)
const TCY = 13;

/** 등껍질 판: 육각에 가깝게 엇갈린 칸, 이음매는 어둡고 판 가운데는 밝다. */
function shellBias(x: number, y: number) {
  const row = Math.floor((y + 0.5) / 4.2), xs = x + 0.5 + (row % 2) * 2.5;
  const fx = (xs % 5) / 5, fy = ((y + 0.5) % 4.2) / 4.2;
  const edge = Math.min(fx, 1 - fx) < 0.14 || Math.min(fy, 1 - fy) < 0.12;
  return edge ? -2 : Math.abs(fx - 0.5) + Math.abs(fy - 0.5) < 0.3 ? 1 : 0;
}

function tortoiseBody(v: Vol, frame: number) {
  const Sh = Mat.SHELL, Sk = Mat.HIDE, cy = TCY;
  const hide = frame === 2, stomp = frame === 3, roar = frame === 4;
  const lift = stomp ? 1.5 : 0, base = hide ? 1 : 3;                     // 발 구르기: 앞이 들린다 / 숨기: 껍질이 땅에 내려앉는다
  // 등껍질: 높은 돔 (앞이 들리면 앞쪽이 위로)
  const sc = [15, cy], rx = 10, ry = 8.2, rz = 7.4;
  for (let x = 4; x <= 26; x++) for (let y = cy - 9; y <= cy + 9; y++) {
    const dx = (x + 0.5 - sc[0]) / rx, dy = (y + 0.5 - sc[1]) / ry, d2 = dx * dx + dy * dy;
    if (d2 > 1) continue;
    const tilt = lift * ((x - 4) / 22);
    const top = base + tilt + rz * Math.sqrt(1 - d2);
    const rim = d2 > 0.82;                                               // 가장자리: 톱니처럼 들쭉날쭉
    for (let z = Math.floor(base + tilt - 1); z <= Math.round(top); z++) {
      if (z < 0) continue;
      const under = z < base + tilt;
      if (under) { v.set(x, y, z, Sk, -1); continue; }                    // 배딱지 (어두운 살)
      if (rim && z > base + tilt + 1 && (x + y) % 3 === 0) continue;
      v.set(x, y, z, Sh, rim ? -1 : shellBias(x, y));
    }
  }
  for (const [x, y, h] of [[13, 0, 2.6], [17, 0, 2.2], [10, 2, 1.6], [19, -2, 1.8], [15, 3, 1.4]]) {   // 등마루의 검은 바위
    const zt = base + lift * ((x - 4) / 22) + rz * Math.sqrt(Math.max(0, 1 - ((x + 0.5 - sc[0]) / rx) ** 2 - (y / ry) ** 2));
    chunk(v, x, cy + y, zt + 0.4, h, Mat.BASALT, 0, 0.9, -9);
  }
  if (hide) {                                                            // 숨기: 머리와 다리를 넣었다 (구멍 안에 어둠만)
    v.box(26, cy - 1, base, 26, cy + 1, base + 1, Mat.DARK);
    return;
  }
  // 다리: 굵은 기둥, 뭉툭한 발톱 (걸을 때 엇갈린다, 발 구르기는 앞발을 든다)
  for (const [x, s, front] of [[8, -1, 0], [8, 1, 0], [22, -1, 1], [22, 1, 1]] as [number, number, number][]) {
    const step = frame === 1 ? (front ? s : -s) * 1.5 : 0;
    const up = stomp && front ? 3 : 0;
    const fx = Math.round(x + step + (stomp && front ? 1 : 0)), y = cy + s * 7;
    v.box(fx, y - 1, up, fx + 2, y + 1, base + 2 + up, Sk, 0);
    for (const dy of [-1, 0, 1]) v.set(fx + 3, y + dy, up, Mat.PLASTER, 1);
  }
  // 목과 머리: 묵직하게 앞으로 (포효: 고개를 쳐들고 입을 벌린다)
  const hz = base + 3 + lift + (roar ? 3 : 0), hx = roar ? 28 : 29;
  limb(v, [25, cy, base + 2 + lift], [hx, cy, hz], 2.2, 1.9, Sk, 0, -9);
  for (let d = 0; d <= 3; d++) {
    const w = 2 - d * 0.3;
    for (let y = Math.round(cy - w); y <= Math.round(cy + w); y++) {
      v.set(hx + d, y, hz + 1, Sk, d === 0 ? 1 : 0);
      v.set(hx + d, y, hz, Sk, 0);
      v.set(hx + d, y, hz - 1 - (roar ? 1 : 0), Sk, -1);
    }
  }
  v.set(hx + 4, cy, hz + (roar ? 1 : 0), Mat.DARK);                       // 부리 끝
  if (roar) for (let d = 1; d <= 3; d++) v.set(hx + d, cy, hz - 1, Mat.DARK);   // 벌린 입
  for (const s of [-1, 1]) { v.set(hx + 1, cy + s * 2, hz + 1, Mat.DARK); v.set(hx + 1, cy + s * 2, hz + 2, Mat.GLOW, 1); }   // 눈
  v.box(3, cy, base, 4, cy, base + 1, Sk, -1);                            // 짧은 꼬리
}

function tortoise(frame: number): Vol {
  const v = new Vol(34, 26, 16);
  tortoiseBody(v, frame);
  return v;
}

// ------------------------------------------------------------- 목장
/** 목장 헛간 (자원 건물의 0.75배): 널빤지 벽, 나라색 박공지붕, 앞의 문, 곁의 건초 더미와 여물통. 울타리는 fence.ts가 땅에 따로 그린다. */
function pastureShed(): Vol {
  const v = new Vol(15, 15, 11);
  for (let z = 0; z <= 4; z++) {                                        // 벽 (널빤지: 층마다 결이 다르다)
    const b = z % 2 ? 0 : -1;
    for (let x = 3; x <= 10; x++) { v.set(x, 4, z, Mat.WOOD, b); v.set(x, 10, z, Mat.WOOD, b); }
    for (let y = 5; y <= 9; y++) { v.set(3, y, z, Mat.WOOD, b); v.set(10, y, z, Mat.WOOD, b); }
  }
  v.box(6, 10, 0, 7, 10, 2, Mat.DARK);                                  // 문
  v.box(5, 10, 3, 8, 10, 3, Mat.WOOD_D, 1);                             // 문 위 들보
  for (let z = 5; z <= 9; z++) {                                        // 박공지붕 (앞뒤로 비탈, 나라색)
    const k = z - 5, y0 = 3 + k, y1 = 11 - k;
    if (y0 > y1) break;
    for (let x = 2; x <= 11; x++) { v.set(x, y0, z, Mat.ROOF, y0 === y1 ? 1 : 0); v.set(x, y1, z, Mat.ROOF, -1); }
    for (let y = y0 + 1; y < y1; y++) { v.set(3, y, z, Mat.WOOD, -1); v.set(10, y, z, Mat.WOOD, -1); }   // 박공 벽
  }
  v.box(11, 9, 0, 13, 11, 1, Mat.STRAW); v.box(12, 10, 2, 12, 10, 2, Mat.STRAW, 1);   // 건초 더미
  v.box(11, 4, 0, 13, 5, 1, Mat.WOOD_D); v.box(12, 4, 1, 12, 5, 1, Mat.HORSE_D);       // 여물통
  return v;
}

// ------------------------------------------------------------- 찾기
const BUILD = [hall, farm, lumber, quarry, tower, harbor, sulfurPit, fireTower, pastureShed];   // sim/rules.py 건물 번호 순서
const UNIT = [infantry, archer, lancer, horseArcher, dragonRider, dragon, tortoise, grenadier, horseGrenadier];   // sim/rules.py 병종 번호 순서
const cache = new Map<string, Vol>();

/** 모델 이름: u0~u8 (병종: 걷는 병사 frame 0/1, 용기사·드래곤 frame 0~8, 바위거북 frame 0~4, 척탄병 frame 2·척탄기마병 frame 4 던지기), b0~b5 (건물), horse (frame 0~3), dragon, lair, tortoise,
 *  ferry, warship, torch. */
export function model(name: string, frame = 0): Vol {
  const key = `${name}:${frame}`;
  let v = cache.get(key);
  if (!v) {
    const k = Number(name.slice(1));
    v = name[0] === 'u' ? UNIT[k](frame) : name[0] === 'b' ? BUILD[k]()
      : name === 'dragon' ? dragon(frame) : name === 'lair' ? lair() : name === 'tortoise' ? tortoise(frame)
      : name === 'horse' ? horse(frame) : name === 'reindeer' ? reindeer(frame) : name === 'ferry' ? ferry() : name === 'warship' ? warship() : torch();
    cache.set(key, v);
  }
  return v;
}

export const BUILD_MODELS = BUILD.length;
