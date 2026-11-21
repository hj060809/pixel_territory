// 지형 장면 하나: 묶음 받기 → 워커 준비 → 렌더러. 매 프레임 update(dt)로 시간/계절/물결을 진행하고 draw()로 그린다.
// 뷰어와 게임이 함께 쓴다.

import { gunzip, parseBundle, type Bundle } from '../bundle/tsb.ts';
import { TerrainRenderer } from '../render/terrain.ts';
import { LifeDrawer } from '../render/lifeDraw.ts';
import type { Life } from '../life/life.ts';
import { DayNightCycle, SeasonCycle } from '../sim/clock.ts';
import { TerrainClient } from './client.ts';

export class TerrainScene {
  readonly bundle: Bundle;
  readonly renderer: TerrainRenderer;
  readonly cycle: DayNightCycle;
  readonly season: SeasonCycle;
  wavesOn = true;
  waveFps = 1.0;                 // 물결 속도 배율 (A/D)
  waveT = 0;                     // 물결 시각 (초)
  ice: Uint8Array | null = null; // 마지막으로 칠한 바다 얼음
  mat: Uint8Array | null = null; // 마지막으로 칠한 재질 (눈·얼음 포함)
  private client: TerrainClient;
  private paintedYear = -1;
  private paintWeights: number[] | null = null;
  private since = 1;             // 마지막 물결 갱신 뒤 지난 시간
  private dirty = true;          // 새 그림을 받았다
  private lastHour = -1;
  updateHz: number;              // 물결 그림 갱신 (초당, 모바일은 낮춘다)
  private lifeDrawer: LifeDrawer;

  private constructor(bundle: Bundle, client: TerrainClient, gl: WebGL2RenderingContext, opts: SceneOptions) {
    this.bundle = bundle;
    this.client = client;
    this.renderer = new TerrainRenderer(gl, bundle);
    this.cycle = new DayNightCycle(bundle.meta.light, opts.hour ?? 12, opts.dayLength ?? 120);
    this.season = new SeasonCycle(opts.year ?? 0.35, opts.yearLength ?? 240);
    this.updateHz = bundle.meta.water.update_hz ?? 12;
    this.lifeDrawer = new LifeDrawer(gl);
  }

  static async load(gl: WebGL2RenderingContext, url: string, opts: SceneOptions = {},
                    progress: (t: string) => void = () => {}): Promise<TerrainScene> {
    progress('지도 받는 중...');
    const r = await fetch(url);
    if (!r.ok) throw new Error(`지도를 받지 못했습니다 (${r.status})`);
    progress('지도 푸는 중...');
    const raw = await gunzip(await r.arrayBuffer());
    const bundle = parseBundle(raw.slice(0));
    const client = await TerrainClient.create(raw, progress);
    const scene = new TerrainScene(bundle, client, gl, opts);
    await scene.refresh(true);
    return scene;
  }

  get W() { return this.renderer.W; }
  get H() { return this.renderer.H; }

  /** 시간 진행. gdt: 게임 시간(초, 일시정지면 0), dt: 실제 시간 (물결은 실제 시간으로 흐른다). */
  update(gdt: number, dt: number) {
    this.cycle.update(gdt);
    this.season.update(gdt);
    if (this.wavesOn) this.waveT += dt * this.waveFps;
    this.since += dt;
    const d = Math.abs(this.season.year - this.paintedYear);
    const seasonMoved = Math.min(d, 1 - d) >= 1 / 240;      // 1년의 1/240 움직이면 다시 칠한다
    if (!this.client.busy && (seasonMoved || (this.wavesOn && this.since >= 1 / this.updateHz))) {
      this.since = 0;
      void this.refresh(seasonMoved);
    }
  }

  /** 워커에 새 그림을 부탁한다 (계절이 움직였으면 다시 칠한 것으로). */
  async refresh(repaint = false) {
    if (repaint || this.paintWeights === null) {
      this.paintWeights = this.season.weights();
      this.paintedYear = this.season.year;
    }
    const f = await this.client.request(this.paintWeights, this.wavesOn ? this.waveT : null);
    this.renderer.setBase(f.rgba);
    this.ice = f.ice;
    this.mat = f.mat;
    this.dirty = true;
  }

  /** 지금 시각으로 빛을 입히고, 새와 물고기를 얹어 화면에 그린다.
   *  빛 단계는 그림이나 시각이 바뀌었을 때, 또는 생물이 있을 때(매 프레임 지우고 다시 얹어야 해서)만 다시 한다. */
  draw(canvasW: number, canvasH: number, camX: number, camY: number, zoom: number, life: Life | null = null) {
    if (life || this.dirty || this.cycle.hour !== this.lastHour) {
      this.renderer.light(this.cycle);
      this.dirty = false;
      this.lastHour = this.cycle.hour;
      if (life) this.lifeDrawer.draw(this.renderer.litFB, this.W, this.H, life.ops(this.cycle));
    }
    this.renderer.present(canvasW, canvasH, camX, camY, zoom);
  }

  /** 밤의 횃불 (지도 칸 [x, y, 세기]...). 바뀌면 빛을 다시 입힌다. */
  setTorches(pts: Float32Array) {
    if (pts.length === 0 && this.torchCount === 0) return;
    this.renderer.setTorches(pts);
    this.torchCount = pts.length;
    this.dirty = true;
  }
  private torchCount = 0;

  /** 정해진 순간 하나를 그려 지도 해상도 RGBA로 돌려준다 (기준 그림 비교용). season: null이면 계절 효과 없이. */
  async renderAt(season: number[] | null, waveT: number | null, hour: number): Promise<Uint8Array> {
    const f = await this.client.request(season, waveT);
    this.renderer.setBase(f.rgba);
    this.cycle.hour = ((hour % 24) + 24) % 24;
    this.renderer.light(this.cycle);
    this.dirty = true;
    return this.renderer.readLit();
  }

  dispose() { this.client.dispose(); }
}

export interface SceneOptions {
  hour?: number;
  dayLength?: number;
  year?: number;
  yearLength?: number;
}
