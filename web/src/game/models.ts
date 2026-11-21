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
  return v;
}

function torch(): Vol {
  const v = new Vol(2, 2, 6);
  v.box(0, 0, 0, 0, 0, 3, Mat.WOOD_D);
  v.set(0, 0, 4, Mat.METAL, 1);
  return v;
}

// ------------------------------------------------------------- 찾기
const BUILD = [hall, farm, lumber, quarry, tower, harbor];
const UNIT = [infantry, archer, lancer, horseArcher];
const cache = new Map<string, Vol>();

/** 모델 이름: u0~u3 (병종, frame 0/1), b0~b5 (건물), horse (frame 0~3), ferry, warship, torch. */
export function model(name: string, frame = 0): Vol {
  const key = `${name}:${frame}`;
  let v = cache.get(key);
  if (!v) {
    const k = Number(name.slice(1));
    v = name[0] === 'u' ? UNIT[k](frame) : name[0] === 'b' ? BUILD[k]()
      : name === 'horse' ? horse(frame) : name === 'ferry' ? ferry() : name === 'warship' ? warship() : torch();
    cache.set(key, v);
  }
  return v;
}

export const BUILD_MODELS = BUILD.length;
