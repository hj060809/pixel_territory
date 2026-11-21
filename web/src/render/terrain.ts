// 지형 그리기 (WebGL2).
// 1) 빛 단계: 지도 해상도 프레임버퍼에 '워커가 준 낮 그림 × 해/달 빛과 산 그림자 + 물에 비친 하늘'
//    (engine/render/daylight.py의 shade와 같은 계산. 빛/그늘 색표는 JS가 numpy와 같게 만들어 텍스처로 넘긴다)
//    밤의 횃불: 횃불 빛 지도(점마다 둥글게 더한 것)만큼 따뜻한 색을 섞는다 (setTorches)
// 2) 화면 단계: 카메라 위치와 배율로 가장 가까운 픽셀을 읽어 캔버스에 (도트가 번지지 않게)
// 텍스처 좌표: 지도 행 y = 텍스처 y (빛 단계 프레임버퍼도 같다). 화면 단계에서만 위아래를 맞춘다.

import type { Bundle } from '../bundle/tsb.ts';
import type { DayNightCycle } from '../sim/clock.ts';
import { FULLSCREEN_VS, framebuffer, program, texture } from './gl.ts';

const LIGHT_FS = `#version 300 es
precision highp float;
precision highp int;
uniform sampler2D uBase;      // 낮 그림 (계절 + 물결)
uniform sampler2D uSurf;      // 법선 xyz + 지평선 높이(tan)
uniform sampler2D uWater;     // 하늘이 비치는 물 (r > 0)
uniform sampler2D uTable;     // 512×1: 그늘 표(0~255) + 빛 표(256~511)
uniform vec4 uSrc[2];         // 해/달: (lx·cos a, ly·cos a, sin a, 비중)
uniform float uTan[2];        // tan a
uniform float uDiv[2];        // max(sin a, 0.2)
uniform int uOn[2];           // 이 빛을 쓰나
uniform float uBayer[16];
uniform ivec2 uSize;          // (W, H)
uniform vec3 uSkyA;           // 하늘색 × 비율 (float32)
uniform float uKeep;          // 1 - 비율 (float32)
uniform int uSkyOn;
uniform sampler2D uTorch;     // 횃불 빛 (r: 0~1)
uniform int uTorchOn;
uniform vec3 uWarm;           // 횃불 빛 색 (낮 그림 × 이것)
out vec4 outColor;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec4 s = texelFetch(uSurf, p, 0);
  float lit = 0.0;
  for (int k = 0; k < 2; k++) {
    if (uOn[k] == 0) continue;
    float ndl = s.x * uSrc[k].x + s.y * uSrc[k].y + s.z * uSrc[k].z;
    float amount = clamp(ndl / uDiv[k], 0.0, 1.0);
    if (!(s.w < uTan[k])) amount = 0.0;         // 산에 가려지면 그늘
    lit += uSrc[k].w * amount;
  }
  // 빛/그늘 디더: Bayer를 (1, 2)만큼 굴린 것 (light_thresh)
  int ry = ((p.y - 1) % uSize.y + uSize.y) % uSize.y;
  int rx = ((p.x - 2) % uSize.x + uSize.x) % uSize.x;
  float thr = uBayer[(ry % 4) * 4 + (rx % 4)];
  int off = lit > thr ? 256 : 0;
  ivec3 c = ivec3(texelFetch(uBase, p, 0).rgb * 255.0 + 0.5);
  vec3 o = vec3(texelFetch(uTable, ivec2(off + c.r, 0), 0).r,
                texelFetch(uTable, ivec2(off + c.g, 0), 0).g,
                texelFetch(uTable, ivec2(off + c.b, 0), 0).b) * 255.0;
  o = floor(o + 0.5);
  if (uSkyOn == 1 && texelFetch(uWater, p, 0).r > 0.0) o = floor(o * uKeep + uSkyA);
  if (uTorchOn == 1) {
    // 가운데서 멀어질수록 옅게 섞는다 (넓은 고른 땅에서 디더 체크무늬가 드러나지 않게. 땅의 결은 그대로)
    float t = clamp(texelFetch(uTorch, p, 0).r * (0.65 + 0.55 * max(s.z, 0.0)) * 1.25, 0.0, 1.0);
    if (t > 0.0) o = max(o, floor(mix(o, vec3(c) * uWarm, t)));
  }
  outColor = vec4(o / 255.0, 1.0);
}`;

const SCREEN_FS = `#version 300 es
precision highp float;
uniform sampler2D uImg;       // 지도 해상도 그림
uniform vec2 uCam;            // 화면 왼쪽 위의 지도 좌표
uniform float uZoom;          // 화면 픽셀 / 지도 칸
uniform vec2 uCanvas;         // 캔버스 크기 (화면 픽셀)
uniform vec2 uMap;            // (W, H)
uniform vec3 uBg;
out vec4 outColor;
void main() {
  vec2 sp = vec2(gl_FragCoord.x, uCanvas.y - gl_FragCoord.y);   // 화면: 위가 0
  vec2 m = uCam + sp / uZoom;
  if (m.x < 0.0 || m.y < 0.0 || m.x >= uMap.x || m.y >= uMap.y) { outColor = vec4(uBg, 1.0); return; }
  outColor = texelFetch(uImg, ivec2(floor(m)), 0);
}`;

const TORCH_VS = `#version 300 es
in vec3 aP;                   // 지도 x, y (칸), 세기
uniform vec2 uMap;
uniform float uR;
out float vS;
void main() {
  gl_Position = vec4(aP.xy / uMap * 2.0 - 1.0, 0.0, 1.0);
  gl_PointSize = uR * 2.0 + 2.0;
  vS = aP.z;
}`;

const TORCH_FS = `#version 300 es
precision highp float;
in float vS;
uniform float uR;
out vec4 outColor;
void main() {
  float d = length(gl_PointCoord - 0.5) * (uR * 2.0 + 2.0);
  float t = max(0.0, 1.0 - d / uR);
  outColor = vec4(vS * pow(t, 0.9), 0.0, 0.0, 1.0);
}`;

/** 횃불 빛: 반지름 (칸), 색. */
export const TORCH_R = 3.4;
const TORCH_WARM = [1.02, 0.78, 0.48];

export class TerrainRenderer {
  readonly W: number;
  readonly H: number;
  readonly litTex: WebGLTexture;
  readonly litFB: WebGLFramebuffer;
  private gl: WebGL2RenderingContext;
  private baseTex: WebGLTexture;
  private surfTex: WebGLTexture;
  private waterTex: WebGLTexture;
  private tableTex: WebGLTexture;
  private lightProg: WebGLProgram;
  private screenProg: WebGLProgram;
  private meta: any;
  private vao: WebGLVertexArrayObject;
  private torchTex: WebGLTexture;
  private torchFB: WebGLFramebuffer;
  private torchProg: WebGLProgram;
  private torchBuf: WebGLBuffer;
  private torchVao: WebGLVertexArrayObject;
  private torchOn = false;

  constructor(gl: WebGL2RenderingContext, bundle: Bundle) {
    this.gl = gl;
    const m = (this.meta = bundle.meta);
    const W = (this.W = m.W), H = (this.H = m.H), N = W * H;
    const A = bundle.arrays;
    // 법선(int16 → float32)과 지평선 높이를 한 텍스처에
    const nq = A.normal.data as Int16Array, hz = A.horizon.data as Float32Array, ns = m.quant.normal.scale;
    const surf = new Float32Array(N * 4);
    for (let i = 0; i < N; i++) {
      surf[i * 4] = Math.fround(nq[i] / ns);
      surf[i * 4 + 1] = Math.fround(nq[N + i] / ns);
      surf[i * 4 + 2] = Math.fround(nq[2 * N + i] / ns);
      surf[i * 4 + 3] = hz[i];
    }
    const fl = A.flags.data as Uint8Array;
    const water = new Uint8Array(N);
    for (let i = 0; i < N; i++) water[i] = fl[i] & m.flags.surf_water ? 255 : 0;
    this.surfTex = texture(gl, W, H, gl.RGBA32F, gl.RGBA, gl.FLOAT, surf);
    this.waterTex = texture(gl, W, H, gl.R8, gl.RED, gl.UNSIGNED_BYTE, water);
    this.baseTex = texture(gl, W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this.tableTex = texture(gl, 512, 1, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this.litTex = texture(gl, W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this.litFB = framebuffer(gl, this.litTex);
    this.lightProg = program(gl, FULLSCREEN_VS, LIGHT_FS);
    this.screenProg = program(gl, FULLSCREEN_VS, SCREEN_FS);
    this.vao = gl.createVertexArray()!;
    this.torchTex = texture(gl, W, H, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this.torchFB = framebuffer(gl, this.torchTex);
    this.torchProg = program(gl, TORCH_VS, TORCH_FS);
    this.torchBuf = gl.createBuffer()!;
    this.torchVao = gl.createVertexArray()!;
    gl.bindVertexArray(this.torchVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.torchBuf);
    const loc = gl.getAttribLocation(this.torchProg, 'aP');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 3, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
  }

  /** 밤의 횃불: [x, y, 세기]... (지도 칸, 0~1). 빈 배열이면 끈다. 다음 빛 단계부터 쓰인다. */
  setTorches(pts: Float32Array) {
    const gl = this.gl;
    this.torchOn = pts.length > 0;
    if (!this.torchOn) return;
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.torchFB);
    gl.viewport(0, 0, this.W, this.H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.useProgram(this.torchProg);
    gl.uniform2f(gl.getUniformLocation(this.torchProg, 'uMap'), this.W, this.H);
    gl.uniform1f(gl.getUniformLocation(this.torchProg, 'uR'), TORCH_R);
    gl.bindVertexArray(this.torchVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.torchBuf);
    gl.bufferData(gl.ARRAY_BUFFER, pts, gl.DYNAMIC_DRAW);
    gl.drawArrays(gl.POINTS, 0, pts.length / 3);
    gl.bindVertexArray(null);
    gl.disable(gl.BLEND);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  /** 워커가 준 낮 그림 (RGBA, H*W*4). */
  setBase(rgba: Uint8Array) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.baseTex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, this.W, this.H, gl.RGBA, gl.UNSIGNED_BYTE, rgba);
  }

  /** 빛 단계: litFB에 지금 시각의 빛을 입힌 지도 그림. */
  light(cycle: DayNightCycle) {
    const gl = this.gl, p = this.lightProg;
    const { sky, skyAmount } = cycle.keyframe();
    gl.bindTexture(gl.TEXTURE_2D, this.tableTex);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, 512, 1, gl.RGBA, gl.UNSIGNED_BYTE, cycle.table());
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.litFB);
    gl.viewport(0, 0, this.W, this.H);
    gl.disable(gl.BLEND);
    gl.useProgram(p);
    const tex = [[this.baseTex, 'uBase'], [this.surfTex, 'uSurf'], [this.waterTex, 'uWater'], [this.tableTex, 'uTable'],
                 [this.torchTex, 'uTorch']] as const;
    tex.forEach(([t, name], k) => {
      gl.activeTexture(gl.TEXTURE0 + k);
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.uniform1i(gl.getUniformLocation(p, name), k);
    });
    const [lx, ly] = this.meta.light.light_xy;
    const src: number[] = [], tan: number[] = [], div: number[] = [], on: number[] = [];
    for (const [alt, weight] of cycle.sources()) {
      const a = (alt * Math.PI) / 180;
      src.push(lx * Math.cos(a), ly * Math.cos(a), Math.sin(a), weight);
      tan.push(Math.tan(a));
      div.push(Math.max(Math.sin(a), 0.2));
      on.push(weight > 0 && alt > 0 ? 1 : 0);
    }
    gl.uniform4fv(gl.getUniformLocation(p, 'uSrc'), src);
    gl.uniform1fv(gl.getUniformLocation(p, 'uTan'), tan);
    gl.uniform1fv(gl.getUniformLocation(p, 'uDiv'), div);
    gl.uniform1iv(gl.getUniformLocation(p, 'uOn'), on);
    gl.uniform1fv(gl.getUniformLocation(p, 'uBayer'), this.meta.shader.bayer4.flat());
    gl.uniform2i(gl.getUniformLocation(p, 'uSize'), this.W, this.H);
    const a32 = Math.fround(skyAmount);
    gl.uniform3fv(gl.getUniformLocation(p, 'uSkyA'), sky.map((c) => Math.fround(Math.fround(c) * a32)));
    gl.uniform1f(gl.getUniformLocation(p, 'uKeep'), Math.fround(1 - skyAmount));
    gl.uniform1i(gl.getUniformLocation(p, 'uSkyOn'), skyAmount > 0 ? 1 : 0);
    gl.uniform1i(gl.getUniformLocation(p, 'uTorchOn'), this.torchOn ? 1 : 0);
    gl.uniform3fv(gl.getUniformLocation(p, 'uWarm'), TORCH_WARM);
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  /** 화면 단계: litTex를 카메라에 맞춰 캔버스에. camX/camY: 왼쪽 위 지도 좌표, zoom: 화면 픽셀/칸. */
  present(canvasW: number, canvasH: number, camX: number, camY: number, zoom: number, bg = [12 / 255, 14 / 255, 20 / 255]) {
    const gl = this.gl, p = this.screenProg;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvasW, canvasH);
    gl.disable(gl.BLEND);
    gl.useProgram(p);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.litTex);
    gl.uniform1i(gl.getUniformLocation(p, 'uImg'), 0);
    gl.uniform2f(gl.getUniformLocation(p, 'uCam'), camX, camY);
    gl.uniform1f(gl.getUniformLocation(p, 'uZoom'), zoom);
    gl.uniform2f(gl.getUniformLocation(p, 'uCanvas'), canvasW, canvasH);
    gl.uniform2f(gl.getUniformLocation(p, 'uMap'), this.W, this.H);
    gl.uniform3fv(gl.getUniformLocation(p, 'uBg'), bg);
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  /** litFB를 읽는다 (비교 시험용). RGBA, 지도 행 순서. */
  readLit(): Uint8Array {
    const gl = this.gl;
    const out = new Uint8Array(this.W * this.H * 4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.litFB);
    gl.readPixels(0, 0, this.W, this.H, gl.RGBA, gl.UNSIGNED_BYTE, out);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return out;
  }
}
