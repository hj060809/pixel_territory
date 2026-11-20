// OpenSimplex 2D 노이즈 — 파이썬 opensimplex 0.4.5(internals.py)를 그대로 옮겼다. 같은 시드, 같은 좌표면 같은 값.
// (배정밀도 계산 순서까지 같게 두었다. 초기화의 64비트 정수 연산은 BigInt로 한다.)

const STRETCH_CONSTANT2 = -0.211324865405187;
const SQUISH_CONSTANT2 = 0.366025403784439;
const NORM_CONSTANT2 = 47;
const GRADIENTS2 = new Int32Array([5, 2, 2, 5, -5, 2, -2, 5, 5, -2, 2, -5, -5, -2, -2, -5]);
const MUL = 6364136223846793005n;
const ADD = 1442695040888963407n;

export class OpenSimplex {
  readonly perm: Int32Array;

  constructor(seed: number) {
    this.perm = new Int32Array(256);
    const source = new Int32Array(256);
    for (let i = 0; i < 256; i++) source[i] = i;
    let s = BigInt(seed);
    const step = () => { s = BigInt.asIntN(64, s * MUL + ADD); };
    step(); step(); step();
    for (let i = 255; i >= 0; i--) {
      step();
      const n = BigInt(i + 1);
      let r = Number((((s + 31n) % n) + n) % n);      // 파이썬의 % (나누는 수의 부호를 따른다)
      if (r < 0) r += i + 1;
      this.perm[i] = source[r];
      source[r] = source[i];
    }
  }

  private extrapolate(xsb: number, ysb: number, dx: number, dy: number): number {
    const p = this.perm;
    const index = p[(p[xsb & 0xff] + ysb) & 0xff] & 0x0e;
    return GRADIENTS2[index] * dx + GRADIENTS2[index + 1] * dy;
  }

  noise2(x: number, y: number): number {
    const stretchOffset = (x + y) * STRETCH_CONSTANT2;
    const xs = x + stretchOffset;
    const ys = y + stretchOffset;
    let xsb = Math.floor(xs);
    let ysb = Math.floor(ys);
    const squishOffset = (xsb + ysb) * SQUISH_CONSTANT2;
    const xb = xsb + squishOffset;
    const yb = ysb + squishOffset;
    const xins = xs - xsb;
    const yins = ys - ysb;
    const inSum = xins + yins;
    let dx0 = x - xb;
    let dy0 = y - yb;
    let value = 0;

    const dx1 = dx0 - 1 - SQUISH_CONSTANT2;
    const dy1 = dy0 - 0 - SQUISH_CONSTANT2;
    let attn1 = 2 - dx1 * dx1 - dy1 * dy1;
    if (attn1 > 0) {
      attn1 *= attn1;
      value += attn1 * attn1 * this.extrapolate(xsb + 1, ysb + 0, dx1, dy1);
    }
    const dx2 = dx0 - 0 - SQUISH_CONSTANT2;
    const dy2 = dy0 - 1 - SQUISH_CONSTANT2;
    let attn2 = 2 - dx2 * dx2 - dy2 * dy2;
    if (attn2 > 0) {
      attn2 *= attn2;
      value += attn2 * attn2 * this.extrapolate(xsb + 0, ysb + 1, dx2, dy2);
    }

    let xsvExt: number, ysvExt: number, dxExt: number, dyExt: number;
    if (inSum <= 1) {
      const zins = 1 - inSum;
      if (zins > xins || zins > yins) {
        if (xins > yins) {
          xsvExt = xsb + 1; ysvExt = ysb - 1; dxExt = dx0 - 1; dyExt = dy0 + 1;
        } else {
          xsvExt = xsb - 1; ysvExt = ysb + 1; dxExt = dx0 + 1; dyExt = dy0 - 1;
        }
      } else {
        xsvExt = xsb + 1; ysvExt = ysb + 1;
        dxExt = dx0 - 1 - 2 * SQUISH_CONSTANT2; dyExt = dy0 - 1 - 2 * SQUISH_CONSTANT2;
      }
    } else {
      const zins = 2 - inSum;
      if (zins < xins || zins < yins) {
        if (xins > yins) {
          xsvExt = xsb + 2; ysvExt = ysb + 0;
          dxExt = dx0 - 2 - 2 * SQUISH_CONSTANT2; dyExt = dy0 + 0 - 2 * SQUISH_CONSTANT2;
        } else {
          xsvExt = xsb + 0; ysvExt = ysb + 2;
          dxExt = dx0 + 0 - 2 * SQUISH_CONSTANT2; dyExt = dy0 - 2 - 2 * SQUISH_CONSTANT2;
        }
      } else {
        dxExt = dx0; dyExt = dy0; xsvExt = xsb; ysvExt = ysb;
      }
      xsb += 1;
      ysb += 1;
      dx0 = dx0 - 1 - 2 * SQUISH_CONSTANT2;
      dy0 = dy0 - 1 - 2 * SQUISH_CONSTANT2;
    }

    let attn0 = 2 - dx0 * dx0 - dy0 * dy0;
    if (attn0 > 0) {
      attn0 *= attn0;
      value += attn0 * attn0 * this.extrapolate(xsb, ysb, dx0, dy0);
    }
    let attnExt = 2 - dxExt * dxExt - dyExt * dyExt;
    if (attnExt > 0) {
      attnExt *= attnExt;
      value += attnExt * attnExt * this.extrapolate(xsvExt, ysvExt, dxExt, dyExt);
    }
    return value / NORM_CONSTANT2;
  }
}
