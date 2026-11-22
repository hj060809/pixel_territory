// 서버 상태 메시지 읽기 (형식은 server/protocol.py 맨 위 설명과 같다, little-endian).

export const POS = 64;

export interface UnitRec { slot: number; gen: number; x: number; y: number; own: number; kind: number; hp: number; state: number; bits: number }
export interface BuildRec { slot: number; gen: number; x: number; y: number; kind: number; own: number; hp: number; prog: number; qlen: number; qkind: number; qtime: number; site: number; qbits: number }
/** 야생 동물. state: 0 풀 뜯기 1 거닒 2 달아남 3 길들이러 오는 병사를 기다림 4 길드는 중 5 잠 6 싸움 7 쓰러짐.
 *  prog: 길든 정도 0~1, hp: 체력 비율 (사나운 동물), sub: 쓰러져 있는 남은 초. */
export interface AnimalRec { id: number; kind: number; x: number; y: number; state: number; prog: number; dir: number; hp: number; sub: number }
export interface BoatRec { id: number; kind: number; own: number; x: number; y: number; hp: number; dir: number; state: number; cargo: number; bits: number }
export interface ShotRec { x0: number; y0: number; x1: number; y1: number; kind: number }
export interface NationRec { res: number[]; rate: number[]; nUnits: number; nBuildings: number; alive: boolean; starving: boolean }

export interface StateMsg {
  tick: number; time: number; hour: number; year: number; flags: number; speed: number; simMs: number;
  units: UnitRec[]; unitsGone: number[]; builds: BuildRec[]; buildsGone: number[];
  boats: BoatRec[]; shots: ShotRec[]; animals: AnimalRec[]; animalsGone: number[]; nations: NationRec[] | null;
}

export const BOAT_STATES = ['idle', 'move', 'hunt', 'pickup', 'wait', 'cross', 'return', 'load', 'ahead', 'anchor'];

export function decodeState(buf: ArrayBuffer): StateMsg {
  const v = new DataView(buf);
  let o = 0;
  const u8 = () => v.getUint8(o++);
  const i8 = () => v.getInt8(o++);
  const u16 = () => { const r = v.getUint16(o, true); o += 2; return r; };
  const i16 = () => { const r = v.getInt16(o, true); o += 2; return r; };
  const u32 = () => { const r = v.getUint32(o, true); o += 4; return r; };
  const f32 = () => { const r = v.getFloat32(o, true); o += 4; return r; };
  u8();                                      // 종류 = 1
  const tick = u32(), time = f32(), hour = f32(), year = f32();
  const flags = u8(), speed = u8() / 10, simMs = u16() / 100;
  const units: UnitRec[] = [];
  for (let n = u16(); n > 0; n--) {
    units.push({ slot: u16(), gen: u16(), x: u16() / POS, y: u16() / POS, own: u8(), kind: u8(), hp: u8() / 255, state: u8(), bits: u8() });
  }
  const unitsGone: number[] = [];
  for (let n = u16(); n > 0; n--) unitsGone.push(u16());
  const builds: BuildRec[] = [];
  for (let n = u16(); n > 0; n--) {
    builds.push({ slot: u16(), gen: u16(), x: u16() / 2, y: u16() / 2, kind: u8(), own: u8(), hp: u8() / 255,
                  prog: u8() / 255, qlen: u8(), qkind: u8(), qtime: u16() / 10, site: i16(), qbits: u16() });
  }
  const buildsGone: number[] = [];
  for (let n = u16(); n > 0; n--) buildsGone.push(u16());
  const boats: BoatRec[] = [];
  for (let n = u16(); n > 0; n--) {
    boats.push({ id: u32(), kind: u8(), own: u8(), x: u16() / POS, y: u16() / POS, hp: u8() / 255, dir: i8(),
                 state: u8(), cargo: u8(), bits: u8() });
  }
  const shots: ShotRec[] = [];
  for (let n = u16(); n > 0; n--) shots.push({ x0: u16() / POS, y0: u16() / POS, x1: u16() / POS, y1: u16() / POS, kind: u8() });
  const animals: AnimalRec[] = [];
  for (let n = u16(); n > 0; n--) {
    animals.push({ id: u32(), kind: u8(), x: u16() / POS, y: u16() / POS, state: u8(), prog: u8() / 255, dir: i8(),
                   hp: u8() / 255, sub: u8() });
  }
  const animalsGone: number[] = [];
  for (let n = u16(); n > 0; n--) animalsGone.push(u32());
  let nations: NationRec[] | null = null;
  if (u8()) {
    nations = [];
    for (let n = u8(); n > 0; n--) {
      const res = [f32(), f32(), f32()], rate = [f32(), f32(), f32()];
      nations.push({ res, rate, nUnits: u16(), nBuildings: u16(), alive: !!u8(), starving: !!u8() });
    }
  }
  return { tick, time, hour, year, flags, speed, simMs, units, unitsGone, builds, buildsGone, boats, shots, animals, animalsGone, nations };
}
