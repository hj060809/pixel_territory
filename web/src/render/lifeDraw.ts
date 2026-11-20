// 새와 물고기를 지도 해상도 그림(litFB) 위에 칸 단위로 그린다 (GPU 혼합으로 곱하기/덮어쓰기/밝히기).

import type { LifeOps } from '../life/life.ts';
import { program } from './gl.ts';

const VS = `#version 300 es
in vec2 aPos;     // 지도 칸 (x, y)
in vec3 aCol;
uniform vec2 uSize;
out vec3 vCol;
void main() {
  gl_Position = vec4((aPos + 0.5) / uSize * 2.0 - 1.0, 0.0, 1.0);
  gl_PointSize = 1.0;
  vCol = aCol;
}`;
const FS = `#version 300 es
precision highp float;
in vec3 vCol;
out vec4 outColor;
void main() { outColor = vec4(vCol, 1.0); }`;

export class LifeDrawer {
  private gl: WebGL2RenderingContext;
  private prog: WebGLProgram;
  private vao: WebGLVertexArrayObject;
  private buf: WebGLBuffer;

  constructor(gl: WebGL2RenderingContext) {
    this.gl = gl;
    this.prog = program(gl, VS, FS);
    this.vao = gl.createVertexArray()!;
    this.buf = gl.createBuffer()!;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    const pos = gl.getAttribLocation(this.prog, 'aPos'), col = gl.getAttribLocation(this.prog, 'aCol');
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 20, 0);
    gl.enableVertexAttribArray(col);
    gl.vertexAttribPointer(col, 3, gl.FLOAT, false, 20, 8);
    gl.bindVertexArray(null);
  }

  private points(data: number[]) {
    const gl = this.gl;
    if (!data.length) return;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STREAM_DRAW);
    gl.drawArrays(gl.POINTS, 0, data.length / 5);
  }

  draw(fb: WebGLFramebuffer, W: number, H: number, groups: LifeOps[]) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.viewport(0, 0, W, H);
    gl.useProgram(this.prog);
    gl.uniform2f(gl.getUniformLocation(this.prog, 'uSize'), W, H);
    gl.bindVertexArray(this.vao);
    for (const g of groups) {
      // 곱하기 (그림자, 물속 물고기)
      const mul: number[] = [];
      for (let i = 0; i < g.mul.length; i += 3) mul.push(g.mul[i], g.mul[i + 1], g.mul[i + 2], g.mul[i + 2], g.mul[i + 2]);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.DST_COLOR, gl.ZERO);
      this.points(mul);
      // 덮어쓰기 (새 몸, 물보라)
      const set: number[] = [];
      for (let i = 0; i < g.set.length; i += 5) set.push(g.set[i], g.set[i + 1], g.set[i + 2] / 255, g.set[i + 3] / 255, g.set[i + 4] / 255);
      gl.disable(gl.BLEND);
      this.points(set);
      // 밝히기 (파문): 색 × 1.25 + 18
      if (g.brighten.length) {
        const a: number[] = [], b: number[] = [];
        for (let i = 0; i < g.brighten.length; i += 2) {
          a.push(g.brighten[i], g.brighten[i + 1], 0.25, 0.25, 0.25);
          b.push(g.brighten[i], g.brighten[i + 1], 18 / 255, 18 / 255, 18 / 255);
        }
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.DST_COLOR, gl.ONE);
        this.points(a);
        gl.blendFunc(gl.ONE, gl.ONE);
        this.points(b);
      }
    }
    gl.disable(gl.BLEND);
    gl.bindVertexArray(null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }
}
