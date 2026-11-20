// numpy와 같은 결과를 내기 위한 도우미.
// - f32: 단정밀도로 반올림 (numpy float32 연산 한 번 = JS 배정밀도 연산 뒤 Math.fround)
// - rint: numpy.rint처럼 반올림 (반은 짝수 쪽)

export const f32 = Math.fround;

export function rint(x: number): number {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 !== 0 ? r - 1 : r;      // JS round는 반을 위로, numpy는 짝수 쪽으로
}

export function clip(x: number, lo: number, hi: number): number {
  return x < lo ? lo : x > hi ? hi : x;
}

/** 4x4 Bayer 임계값을 (h, w)로 깐 것 (shader.bayer와 같다). */
export function bayer(meta: any, h: number, w: number, rollY = 0, rollX = 0): Float64Array {
  const b: number[][] = meta.shader.bayer4;
  const out = new Float64Array(h * w);
  for (let y = 0; y < h; y++) {
    const sy = (((y - rollY) % h) + h) % h;
    for (let x = 0; x < w; x++) {
      const sx = (((x - rollX) % w) + w) % w;
      out[y * w + x] = b[sy % 4][sx % 4];
    }
  }
  return out;
}
